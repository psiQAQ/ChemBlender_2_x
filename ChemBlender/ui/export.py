"""Background XYZ/extXYZ export for the active Project Browser entity."""

from dataclasses import dataclass
from pathlib import Path
from threading import Event, Thread
from uuid import UUID

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty

from ..core import FrameSet, Structure
from ..core.exporters import (
    ExportReport,
    export_extxyz,
    export_xyz,
    preview_extxyz_export,
)
from .session import get_scene_session


_FORMAT_ITEMS = (
    ("xyz", "XYZ", "Export one Structure"),
    ("extxyz", "extXYZ", "Export a Structure or trajectory with properties"),
)


@dataclass(frozen=True, slots=True)
class ExportSelection:
    structure: Structure
    frame_set: FrameSet | None
    properties: tuple


def resolve_export_selection(project, entity_id):
    if type(entity_id) is not UUID:
        raise TypeError("select a Structure or FrameSet before exporting")
    structure = project.structures.get(entity_id)
    if structure is not None:
        return ExportSelection(structure, None, ())
    frame_set = project.datasets.get(entity_id)
    if not isinstance(frame_set, FrameSet):
        raise ValueError("selected entity is not an exportable Structure or FrameSet")
    structure = project.structures.get(frame_set.structure_id)
    if structure is None:
        raise ValueError("selected FrameSet has no Structure")
    return ExportSelection(
        structure,
        frame_set,
        tuple(
            dataset
            for dataset in project.datasets.values()
            if getattr(dataset, "frame_set_id", None) == frame_set.id
        ),
    )


def preview_export_selection(
    selection,
    format_name,
    missing_value_token=None,
):
    if type(selection) is not ExportSelection:
        raise TypeError("selection must be an ExportSelection")
    if format_name == "xyz":
        if selection.frame_set is not None:
            raise ValueError("FrameSet export requires extXYZ")
        return ExportReport("xyz", False, 1, False)
    if format_name != "extxyz":
        raise ValueError("format_name must be xyz or extxyz")
    return preview_extxyz_export(
        selection.structure,
        frame_set=selection.frame_set,
        properties=selection.properties,
        missing_value_token=missing_value_token or None,
    )


class ExportJob:
    def __init__(
        self,
        destination,
        selection,
        *,
        format_name,
        confirm_loss,
        missing_value_token,
    ):
        self.destination = Path(destination)
        self.selection = selection
        self.format_name = format_name
        self.confirm_loss = confirm_loss
        self.missing_value_token = missing_value_token
        self.result = None
        self.error = None
        self._cancelled = Event()
        self._done = Event()
        self._started = False
        self._thread = Thread(target=self._run, daemon=True)

    def _run(self):
        try:
            if self.format_name == "xyz":
                self.result = export_xyz(
                    self.destination,
                    self.selection.structure,
                    is_cancelled=self._cancelled.is_set,
                )
            else:
                self.result = export_extxyz(
                    self.destination,
                    self.selection.structure,
                    frame_set=self.selection.frame_set,
                    properties=self.selection.properties,
                    confirm_loss=self.confirm_loss,
                    missing_value_token=self.missing_value_token or None,
                    is_cancelled=self._cancelled.is_set,
                )
        except BaseException as error:
            self.error = error
        finally:
            self._done.set()

    def start(self):
        self._thread.start()
        self._started = True

    def cancel(self):
        self._cancelled.set()

    def join(self, timeout):
        if not self._started:
            return True
        self._thread.join(timeout)
        return not self._thread.is_alive()

    @property
    def done(self):
        return self._done.is_set()


def _report_text(report):
    return "; ".join(entry.message for entry in report.entries) or "No data loss"


class CHEMBLENDER_OT_export_project_entity(bpy.types.Operator):
    bl_idname = "chemblender.export_project_entity"
    bl_label = "Export Selected Data"
    bl_description = "Export the selected Structure or FrameSet"

    filepath: StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(
        default="*.xyz;*.extxyz",
        options={"HIDDEN"},
    )
    format_name: EnumProperty(items=_FORMAT_ITEMS, default="extxyz")
    confirm_loss: BoolProperty(
        name="Confirm Partial/Ambiguous Export",
        default=False,
    )
    missing_value_token: StringProperty(name="Missing Value Token")
    loss_preview: StringProperty(name="Loss Preview")

    def _selection_and_preview(self, context):
        session = get_scene_session(context.scene)
        selection = resolve_export_selection(
            session.project,
            session.active_entity_id,
        )
        if selection.frame_set is not None:
            self.format_name = "extxyz"
        report = preview_export_selection(
            selection,
            self.format_name,
            self.missing_value_token,
        )
        self.loss_preview = _report_text(report)
        return selection, report

    def invoke(self, context, _event):
        try:
            self._selection_and_preview(context)
        except (TypeError, ValueError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def draw(self, _context):
        layout = self.layout
        layout.prop(self, "format_name")
        layout.label(text=self.loss_preview or "No data loss")
        layout.prop(self, "confirm_loss")
        layout.prop(self, "missing_value_token")

    def execute(self, context):
        try:
            selection, preview = self._selection_and_preview(context)
            if preview.requires_confirmation and not self.confirm_loss:
                raise ValueError(
                    "Partial/Ambiguous export requires explicit confirmation"
                )
            destination = Path(self.filepath)
            if not destination.name:
                raise ValueError("choose an export destination")
            job = ExportJob(
                destination,
                selection,
                format_name=self.format_name,
                confirm_loss=self.confirm_loss,
                missing_value_token=self.missing_value_token or None,
            )
            if getattr(bpy.app, "background", False):
                job.start()
                job.join(None)
                return self._finish_job(job)
            manager = context.window_manager
            timer = manager.event_timer_add(0.1, window=context.window)
            manager.progress_begin(0, 100)
            manager.progress_update(10)
            manager.modal_handler_add(self)
            self._job = job
            self._timer = timer
            job.start()
            return {"RUNNING_MODAL"}
        except (OSError, TypeError, ValueError) as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}

    def _finish_job(self, job):
        if job.error is not None:
            if isinstance(job.error, (KeyboardInterrupt, SystemExit, MemoryError)):
                raise job.error
            self.report({"ERROR"}, str(job.error))
            return {"CANCELLED"}
        if not job.result.written:
            self.report({"ERROR"}, _report_text(job.result))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Exported {job.result.frame_count} frame(s)")
        return {"FINISHED"}

    def modal(self, context, event):
        job = getattr(self, "_job", None)
        if job is None:
            return {"CANCELLED"}
        if event.type == "ESC":
            job.cancel()
        if event.type != "TIMER" or not job.done:
            return {"RUNNING_MODAL"}
        job.join(0)
        manager = context.window_manager
        manager.progress_update(100)
        manager.progress_end()
        manager.event_timer_remove(self._timer)
        self._job = None
        self._timer = None
        return self._finish_job(job)

    def cancel(self, _context):
        job = getattr(self, "_job", None)
        if job is not None:
            job.cancel()


__all__ = ("CHEMBLENDER_OT_export_project_entity",)
