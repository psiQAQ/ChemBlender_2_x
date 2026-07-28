"""Background XYZ/extXYZ export for the active Project Browser entity."""

from dataclasses import dataclass
from pathlib import Path
from threading import Event, Thread
from uuid import UUID

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty

from ..core import (
    ConformerSet,
    FrameSet,
    MolecularRecord,
    Structure,
    TopologyRecord,
)
from ..core.exporters import (
    ExportReport,
    ExportReportEntry,
    export_extxyz,
    export_xyz,
    export_mol,
    export_sdf,
    export_smiles,
    preview_extxyz_export,
    preview_molecular_export,
    sdf_entries_from_conformer_set,
)
from .session import get_scene_session


_FORMAT_ITEMS = (
    ("xyz", "XYZ", "Export one Structure"),
    ("extxyz", "extXYZ", "Export a Structure or trajectory with properties"),
    ("mol", "MOL", "Export a molecular Structure"),
    ("sdf", "SDF", "Export molecular records or conformers"),
    ("smiles", "SMILES", "Export a molecular Structure"),
)
_FATAL_EXCEPTIONS = (
    KeyboardInterrupt,
    SystemExit,
    GeneratorExit,
    MemoryError,
)


def _merge_cleanup_failure(failure, error, label):
    if failure is None:
        return error
    if isinstance(error, _FATAL_EXCEPTIONS) and not isinstance(
        failure,
        _FATAL_EXCEPTIONS,
    ):
        error.add_note(f"earlier cleanup failed: {failure}")
        return error
    failure.add_note(f"{label}: {error}")
    return failure


@dataclass(frozen=True, slots=True)
class ExportSelection:
    structure: Structure
    frame_set: FrameSet | None
    properties: tuple
    topology: TopologyRecord | None = None
    record: MolecularRecord | None = None
    conformer_set: ConformerSet | None = None
    records_by_id: dict | None = None


def _molecular_selection(
    project,
    structure,
    *,
    record=None,
    conformer_set=None,
):
    explicit_record = record is not None
    topologies = tuple(
        project.topologies[topology_id]
        for topology_id in structure.topology_ids
        if topology_id in project.topologies
        and project.topologies[topology_id].quality_status.value == "complete"
    )
    if not topologies:
        if explicit_record:
            raise ValueError(
                "selected MolecularRecord has no matching complete topology"
            )
        raise ValueError("selected Structure has no complete molecular topology")
    if record is None:
        record = next(
            (
                item
                for item in project.molecular_records.values()
                if item.structure_id == structure.id
            ),
            None,
        )
    required_topology_id = (
        conformer_set.reference_topology_id
        if conformer_set is not None
        else record.topology_id if explicit_record else None
    )
    topology = next(
        (
            item
            for item in topologies
            if item.id == required_topology_id
        ),
        topologies[0] if required_topology_id is None else None,
    )
    if topology is None:
        if conformer_set is not None:
            raise ValueError(
                "selected ConformerSet has no matching complete topology"
            )
        raise ValueError(
            "selected MolecularRecord has no matching complete topology"
        )
    if conformer_set is not None:
        record = None
    elif record is not None and record.topology_id not in {None, topology.id}:
        record = None
    return ExportSelection(
        structure, None, (), topology, record, conformer_set,
        {item.id: item for item in project.molecular_records.values()},
    )


def resolve_export_selection(project, entity_id):
    if type(entity_id) is not UUID:
        raise TypeError("select a Structure or FrameSet before exporting")
    structure = project.structures.get(entity_id)
    if structure is not None:
        try:
            return _molecular_selection(project, structure)
        except ValueError:
            return ExportSelection(structure, None, ())
    record = project.molecular_records.get(entity_id)
    if record is not None:
        structure = project.structures.get(record.structure_id)
        if structure is None:
            raise ValueError("selected MolecularRecord has no Structure")
        return _molecular_selection(project, structure, record=record)
    frame_set = project.datasets.get(entity_id)
    if isinstance(frame_set, ConformerSet):
        structure = project.structures.get(frame_set.reference_structure_id)
        if structure is None:
            raise ValueError("selected ConformerSet has no Structure")
        return _molecular_selection(project, structure, conformer_set=frame_set)
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
    if format_name in {"mol", "sdf", "smiles"}:
        if selection.topology is None:
            raise ValueError("molecular export requires a complete topology")
        if selection.conformer_set is not None and format_name != "sdf":
            raise ValueError("ConformerSet export requires SDF")
        frame_count = (
            len(selection.conformer_set.record_ids)
            if selection.conformer_set is not None
            else 1
        )
        extra_entries = ()
        if selection.conformer_set is not None:
            records = selection.records_by_id or {}
            missing_count = sum(
                record_id not in records
                for record_id in selection.conformer_set.record_ids
            )
            if missing_count:
                extra_entries = (
                    ExportReportEntry(
                        "conformer_properties_omitted",
                        (
                            f"{missing_count} conformer(s) have no matching "
                            "source record for properties"
                        ),
                    ),
                )
        return preview_molecular_export(
            selection.structure,
            selection.topology,
            record=(
                None
                if selection.conformer_set is not None
                else selection.record
            ),
            format_name=format_name,
            frame_count=frame_count,
            extra_loss_entries=extra_entries,
        )
    if format_name != "extxyz":
        raise ValueError("format_name must be xyz, extxyz, mol, sdf or smiles")
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
        self._window_manager = None
        self._timer = None
        self._progress_started = False

    def _run(self):
        try:
            if self.format_name == "xyz":
                self.result = export_xyz(
                    self.destination,
                    self.selection.structure,
                    is_cancelled=self._cancelled.is_set,
                )
            elif self.format_name == "extxyz":
                self.result = export_extxyz(
                    self.destination,
                    self.selection.structure,
                    frame_set=self.selection.frame_set,
                    properties=self.selection.properties,
                    confirm_loss=self.confirm_loss,
                    missing_value_token=self.missing_value_token or None,
                    is_cancelled=self._cancelled.is_set,
                )
            elif self.format_name == "mol":
                self.result = export_mol(
                    self.selection.structure,
                    self.selection.topology,
                    record=self.selection.record,
                    confirm_loss=self.confirm_loss,
                    destination=self.destination,
                    is_cancelled=self._cancelled.is_set,
                ).report
            elif self.format_name == "sdf":
                if self.selection.conformer_set is not None:
                    entries = sdf_entries_from_conformer_set(
                        self.selection.conformer_set,
                        self.selection.structure,
                        self.selection.topology,
                        self.selection.records_by_id or {},
                    )
                    self.result = export_sdf(
                        entries=entries,
                        confirm_loss=self.confirm_loss,
                        destination=self.destination,
                        is_cancelled=self._cancelled.is_set,
                    ).report
                else:
                    self.result = export_sdf(
                        self.selection.structure,
                        self.selection.topology,
                        record=self.selection.record,
                        confirm_loss=self.confirm_loss,
                        destination=self.destination,
                        is_cancelled=self._cancelled.is_set,
                    ).report
            elif self.format_name == "smiles":
                self.result = export_smiles(
                    self.selection.structure,
                    self.selection.topology,
                    record=self.selection.record,
                    confirm_loss=self.confirm_loss,
                    destination=self.destination,
                    is_cancelled=self._cancelled.is_set,
                ).report
            else:
                raise ValueError("format_name must be xyz, extxyz, mol, sdf or smiles")
        except BaseException as error:
            self.error = error
        finally:
            self._done.set()

    def start(self):
        try:
            self._thread.start()
        except BaseException:
            self._started = self._thread.is_alive()
            raise
        else:
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

    @property
    def timer_pending(self):
        return self._timer is not None

    def attach_ui(self, manager, timer):
        self._window_manager = manager
        self._timer = timer

    def mark_progress_started(self):
        self._progress_started = True

    def release_ui(self):
        manager = self._window_manager
        if manager is None:
            return
        failure = None
        if self._progress_started:
            try:
                manager.progress_end()
            except BaseException as error:
                failure = error
            else:
                self._progress_started = False
        if self._timer is not None:
            try:
                manager.event_timer_remove(self._timer)
            except BaseException as error:
                failure = _merge_cleanup_failure(
                    failure,
                    error,
                    "timer cleanup failed",
                )
            else:
                self._timer = None
        if self._timer is None and not self._progress_started:
            self._window_manager = None
        if failure is not None:
            raise failure

    def abandon_ui(self):
        self._window_manager = None
        self._timer = None
        self._progress_started = False


def _report_text(report):
    return "; ".join(entry.message for entry in report.entries) or "No data loss"


def _export_preview_changed(self, context):
    self.confirm_loss = False
    preview = getattr(self, "_selection_and_preview", None)
    if preview is None:
        return
    try:
        preview(context)
    except (TypeError, ValueError) as error:
        self.loss_preview = str(error)


class CHEMBLENDER_OT_export_project_entity(bpy.types.Operator):
    bl_idname = "chemblender.export_project_entity"
    bl_label = "Export Selected Data"
    bl_description = "Export the selected Structure or FrameSet"

    filepath: StringProperty(subtype="FILE_PATH")
    filter_glob: StringProperty(
        default="*.xyz;*.extxyz;*.mol;*.sdf;*.smi;*.smiles",
        options={"HIDDEN"},
    )
    format_name: EnumProperty(
        items=_FORMAT_ITEMS,
        default="extxyz",
        update=_export_preview_changed,
    )
    confirm_loss: BoolProperty(
        name="Confirm Partial/Ambiguous Export",
        default=False,
    )
    missing_value_token: StringProperty(
        name="Missing Value Token",
        update=_export_preview_changed,
    )
    loss_preview: StringProperty(name="Loss Preview")

    def _selection_and_preview(self, context, *, default_format=False):
        session = get_scene_session(context.scene)
        selection = resolve_export_selection(
            session.project,
            session.active_entity_id,
        )
        if default_format:
            if selection.conformer_set is not None or selection.record is not None:
                self.format_name = "sdf"
            elif selection.frame_set is not None:
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
            self._selection_and_preview(context, default_format=True)
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

    def _clear_job_ownership(self, job):
        if getattr(self, "_job", None) is job:
            self._job = None
            self._timer = None

    def _cancel_and_release_job(self, job):
        failure = None
        job.cancel()
        try:
            if not job.join(None):
                raise RuntimeError("export worker did not stop")
        except BaseException as error:
            failure = error
        try:
            job.release_ui()
        except BaseException as error:
            failure = _merge_cleanup_failure(
                failure,
                error,
                "export UI cleanup failed",
            )
        self._clear_job_ownership(job)
        if failure is not None:
            job.abandon_ui()
            raise failure

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
            self._job = job
            self._timer = None
            timer = manager.event_timer_add(0.1, window=context.window)
            self._timer = timer
            job.attach_ui(manager, timer)
            manager.progress_begin(0, 100)
            job.mark_progress_started()
            manager.progress_update(10)
            manager.modal_handler_add(self)
            job.start()
            return {"RUNNING_MODAL"}
        except BaseException as error:
            if "job" in locals() and getattr(self, "_job", None) is job:
                try:
                    self._cancel_and_release_job(job)
                except BaseException as cleanup_error:
                    if isinstance(cleanup_error, _FATAL_EXCEPTIONS):
                        raise
                    error.add_note(
                        f"export setup cleanup failed: {cleanup_error}"
                    )
            if isinstance(error, _FATAL_EXCEPTIONS):
                raise
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}

    def _finish_job(self, job):
        if job.error is not None:
            if isinstance(job.error, _FATAL_EXCEPTIONS):
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
        if not getattr(job, "_completion_checked", False):
            failure = None
            try:
                job.join(0)
            except BaseException as error:
                failure = error
            if failure is None:
                try:
                    context.window_manager.progress_update(100)
                except BaseException as error:
                    failure = error
            job._completion_error = failure
            job._completion_checked = True
        failure = job._completion_error
        try:
            job.release_ui()
        except BaseException as error:
            if (
                not isinstance(error, _FATAL_EXCEPTIONS)
                and job.timer_pending
            ):
                self.report(
                    {"WARNING"},
                    f"Export cleanup retry pending: {error}",
                )
                return {"RUNNING_MODAL"}
            job.abandon_ui()
            failure = _merge_cleanup_failure(
                failure,
                error,
                "export UI cleanup failed",
            )
        self._clear_job_ownership(job)
        if failure is not None:
            if isinstance(failure, _FATAL_EXCEPTIONS):
                raise failure
            self.report({"ERROR"}, str(failure))
            return {"CANCELLED"}
        return self._finish_job(job)

    def cancel(self, _context):
        job = getattr(self, "_job", None)
        if job is not None:
            try:
                self._cancel_and_release_job(job)
            except BaseException as error:
                if isinstance(error, _FATAL_EXCEPTIONS):
                    raise
                self.report({"ERROR"}, f"Export cleanup failed: {error}")


__all__ = ("CHEMBLENDER_OT_export_project_entity",)
