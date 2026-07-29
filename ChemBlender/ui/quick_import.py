"""Blender file chooser that stages the shared import pipeline."""

from pathlib import Path
from queue import Empty, SimpleQueue
from threading import Event, Thread

import bpy
from bpy.props import CollectionProperty, EnumProperty, StringProperty

from ..core.import_pipeline.request import (
    ImportRequest,
    ImportSource,
    ValidationMode,
)
from ..core.import_pipeline.conformer_grouping import (
    suggest_staged_conformer_groups as prepare_conformer_suggestions,
)
from ..reader_api.import_pipeline_bridge import preflight_reader_plugins
from ..runtime.reader_api_bridge import get_reader_plugin_registry
from .properties import (
    VALIDATION_MODE_ITEMS,
    clear_quick_import_state,
    create_quick_import_staging,
    finish_quick_import_job,
    get_quick_import_state,
    store_quick_import_job,
    store_quick_import_preview,
)
from .session import get_scene_session


_FATAL_EXCEPTIONS = (
    KeyboardInterrupt,
    SystemExit,
    GeneratorExit,
    MemoryError,
)


def _merge_cleanup_failure(failure, error, label):
    if isinstance(error, _FATAL_EXCEPTIONS) and not isinstance(
        failure,
        _FATAL_EXCEPTIONS,
    ):
        error.add_note(f"earlier failure: {failure}")
        return error
    failure.add_note(f"{label}: {error}")
    return failure


def _selected_paths(directory, files):
    root = Path(directory).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("directory must be a directory")
    paths = []
    for item in files:
        name = getattr(item, "name", None)
        if type(name) is not str or not name or Path(name).name != name:
            raise ValueError("selected file names must be plain file names")
        path = (root / name).resolve(strict=True)
        if path.parent != root or not path.is_file():
            raise ValueError("selected path must be a file in directory")
        paths.append(path)
    paths = tuple(sorted(set(paths), key=lambda path: path.name))
    if not paths:
        raise ValueError("select at least one file")
    return paths


def _preview_summary(preview):
    readers = sorted(
        {
            row.selected_reader_id
            for row in preview.source_previews
            if row.selected_reader_id is not None
        }
    )
    suffix = f" via {', '.join(readers)}" if readers else ""
    return f"{len(preview.source_previews)} source(s) staged{suffix}"


class _PreflightJob:
    def __init__(
        self,
        request,
        registry,
        staging,
        *,
        canonical_parameters_by_source=None,
        prepare_conformers=True,
    ):
        self.request = request
        self.registry = registry
        self.staging = staging
        self.canonical_parameters_by_source = canonical_parameters_by_source
        self.prepare_conformers = prepare_conformers
        self.preview = None
        self.conformer_suggestions = None
        self.error = None
        self.progress_events = SimpleQueue()
        self._cancelled = Event()
        self._done = Event()
        self._started = False
        self._thread = Thread(target=self._run, daemon=True)
        self._window_manager = None
        self._timer = None
        self._progress_started = False

    def _run(self):
        try:
            self.preview = preflight_reader_plugins(
                self.request,
                self.registry,
                self.staging,
                canonical_parameters_by_source=(
                    self.canonical_parameters_by_source
                ),
                progress=self._progress,
                is_cancelled=self._cancelled.is_set,
            )
            if self.prepare_conformers:
                self._progress("conformer_grouping", 0, 1)
                self.conformer_suggestions = prepare_conformer_suggestions(
                    self.preview,
                    self.staging,
                    is_cancelled=self._cancelled.is_set,
                )
                self._progress("conformer_grouping", 1, 1)
        except BaseException as error:
            self.error = error
        finally:
            self._done.set()

    def _progress(self, stage, completed, total):
        self.progress_events.put((stage, completed, total))

    def attach_ui(self, window_manager, timer):
        self._window_manager = window_manager
        self._timer = timer

    def mark_progress_started(self):
        self._progress_started = True

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

    @property
    def timer_pending(self):
        return self._timer is not None

    def drain_progress(self):
        latest = None
        while True:
            try:
                latest = self.progress_events.get_nowait()
            except Empty:
                return latest

    def release_ui(self):
        manager = self._window_manager
        if manager is None:
            return
        failure = None
        if self._timer is not None:
            try:
                manager.event_timer_remove(self._timer)
            except BaseException as error:
                failure = error
            else:
                self._timer = None
        if self._progress_started:
            try:
                manager.progress_end()
            except BaseException as error:
                failure = (
                    error
                    if failure is None
                    else _merge_cleanup_failure(
                        failure,
                        error,
                        "progress cleanup failed",
                    )
                )
            else:
                self._progress_started = False
        if self._timer is None and not self._progress_started:
            self._window_manager = None
        if failure is not None:
            raise failure

    def abandon_ui(self):
        self._window_manager = None
        self._timer = None
        self._progress_started = False


class CHEMBLENDER_OT_quick_import(bpy.types.Operator):
    bl_idname = "chemblender.quick_import"
    bl_label = "Select Files"
    bl_description = "Stage scientific files for import preview"

    files: CollectionProperty(
        type=bpy.types.OperatorFileListElement,
        options={"SKIP_SAVE", "HIDDEN"},
    )
    directory: StringProperty(
        subtype="DIR_PATH",
        options={"SKIP_SAVE", "HIDDEN"},
    )
    validation_mode: EnumProperty(
        name="Validation",
        items=VALIDATION_MODE_ITEMS,
        default=ValidationMode.BALANCED.value,
    )

    def invoke(self, context, _event):
        self.validation_mode = (
            context.scene.chemblender_quick_import.validation_mode
        )
        if getattr(self, "files", ()):
            try:
                return self.execute(context)
            finally:
                self.files.clear()
                self.directory = ""
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        try:
            paths = _selected_paths(self.directory, self.files)
            request = ImportRequest(
                sources=tuple(ImportSource(path) for path in paths),
                validation_mode=ValidationMode(self.validation_mode),
            )
            project_session = get_scene_session(context.scene)
            staging = create_quick_import_staging(project_session)
            registry = get_reader_plugin_registry()
        except BaseException as error:
            return self._handle_error(locals().get("project_session"), error)
        if not getattr(bpy.app, "background", False):
            return self._start_modal(
                context,
                project_session,
                staging,
                request,
                registry,
            )
        try:
            preview = preflight_reader_plugins(
                request,
                registry,
                staging,
                progress=lambda _stage, _completed, _total: None,
                is_cancelled=lambda: False,
            )
            conformer_suggestions = prepare_conformer_suggestions(
                preview,
                staging,
                is_cancelled=lambda: False,
            )
            store_quick_import_preview(
                project_session,
                staging,
                preview,
                conformer_grouping_suggestions=conformer_suggestions,
            )
        except BaseException as error:
            return self._handle_error(project_session, error)
        return self._finish_preview(context, preview)

    def _start_modal(
        self,
        context,
        project_session,
        staging,
        request,
        registry,
    ):
        job = _PreflightJob(request, registry, staging)
        try:
            store_quick_import_job(project_session, staging, job)
            manager = context.window_manager
            timer = manager.event_timer_add(0.1, window=context.window)
            job.attach_ui(manager, timer)
            manager.progress_begin(0, 100)
            job.mark_progress_started()
            manager.modal_handler_add(self)
            self._project_session = project_session
            self._job = job
            job.start()
        except BaseException as error:
            return self._handle_error(project_session, error)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        job = getattr(self, "_job", None)
        if job is None:
            return {"CANCELLED"}
        if event.type == "ESC":
            job.cancel()
        if event.type != "TIMER":
            return {"RUNNING_MODAL"}
        if not getattr(job, "_completion_checked", False):
            completion_error = None
            try:
                progress = job.drain_progress()
                if progress is not None:
                    _stage, completed, total = progress
                    context.window_manager.progress_update(
                        100 * completed / total if total else 0
                    )
                if not job.done:
                    return {"RUNNING_MODAL"}
                job.join(0)
            except BaseException as error:
                completion_error = error
                job.cancel()
                try:
                    job.join(None)
                except BaseException as cleanup_error:
                    completion_error = _merge_cleanup_failure(
                        completion_error,
                        cleanup_error,
                        "Quick Import job cleanup failed",
                    )
            job._completion_error = completion_error
            job._completion_checked = True
        project_session = self._project_session
        failure = job._completion_error
        if failure is None:
            failure = job.error
        try:
            job.release_ui()
        except BaseException as error:
            if (
                not isinstance(error, _FATAL_EXCEPTIONS)
                and job.timer_pending
            ):
                self.report(
                    {"WARNING"},
                    f"Quick Import cleanup retry pending: {error}",
                )
                return {"RUNNING_MODAL"}
            job.abandon_ui()
            failure = (
                error
                if failure is None
                else _merge_cleanup_failure(
                    failure,
                    error,
                    "Quick Import UI cleanup failed",
                )
            )
        try:
            finish_quick_import_job(project_session, job)
        except BaseException as error:
            failure = (
                error
                if failure is None
                else _merge_cleanup_failure(
                    failure,
                    error,
                    "Quick Import ownership cleanup failed",
                )
            )
        self._job = None
        if failure is not None:
            return self._handle_error(project_session, failure)
        try:
            store_quick_import_preview(
                project_session,
                job.staging,
                job.preview,
                conformer_grouping_suggestions=job.conformer_suggestions,
            )
        except BaseException as error:
            return self._handle_error(project_session, error)
        return self._finish_preview(context, job.preview)

    def cancel(self, _context):
        job = getattr(self, "_job", None)
        if job is not None:
            job.cancel()

    def _handle_error(self, project_session, error):
        if project_session is not None:
            try:
                clear_quick_import_state(project_session)
            except BaseException as cleanup_error:
                error = _merge_cleanup_failure(
                    error,
                    cleanup_error,
                    "Quick Import cleanup failed",
                )
        if isinstance(error, _FATAL_EXCEPTIONS):
            raise error
        self.report({"ERROR"}, str(error))
        return {"CANCELLED"}

    def _finish_preview(self, context, preview):
        settings = context.scene.chemblender_quick_import
        settings.validation_mode = self.validation_mode
        settings.recent_summary = _preview_summary(preview)
        if not getattr(bpy.app, "background", False):
            bpy.ops.chemblender.confirm_import("INVOKE_DEFAULT")
        return {"FINISHED"}


class CHEMBLENDER_OT_import_smiles_text(CHEMBLENDER_OT_quick_import):
    bl_idname = "chemblender.import_smiles_text"
    bl_label = "Import SMILES"
    bl_description = "Stage SMILES text for import preview"

    smiles_text: StringProperty(name="SMILES")

    def invoke(self, context, _event):
        self.validation_mode = context.scene.chemblender_quick_import.validation_mode
        if not getattr(bpy.app, "background", False):
            return context.window_manager.invoke_props_dialog(self)
        return self.execute(context)

    def draw(self, _context):
        self.layout.prop(self, "smiles_text")
        self.layout.prop(self, "validation_mode")

    def execute(self, context):
        try:
            request = ImportRequest(
                sources=(ImportSource.smiles_text(self.smiles_text),),
                validation_mode=ValidationMode(self.validation_mode),
            )
            project_session = get_scene_session(context.scene)
            staging = create_quick_import_staging(project_session)
            registry = get_reader_plugin_registry()
        except BaseException as error:
            return self._handle_error(locals().get("project_session"), error)
        if not getattr(bpy.app, "background", False):
            return self._start_modal(context, project_session, staging, request, registry)
        try:
            preview = preflight_reader_plugins(
                request, registry, staging,
                progress=lambda _stage, _completed, _total: None,
                is_cancelled=lambda: False,
            )
            conformer_suggestions = prepare_conformer_suggestions(
                preview,
                staging,
                is_cancelled=lambda: False,
            )
            store_quick_import_preview(
                project_session,
                staging,
                preview,
                conformer_grouping_suggestions=conformer_suggestions,
            )
        except BaseException as error:
            return self._handle_error(project_session, error)
        return self._finish_preview(context, preview)


class CHEMBLENDER_PT_quick_import(bpy.types.Panel):
    bl_label = "Quick Import"
    bl_idname = "CHEMBLENDER_PT_QUICK_IMPORT"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "ChemBlender"

    def draw(self, context):
        from .session import get_scene_session_status

        layout = self.layout
        session = get_scene_session(context.scene)
        status, message = get_scene_session_status(context.scene)
        settings = context.scene.chemblender_quick_import

        layout.label(text=f"Project: {status.title()}")
        layout.label(
            text="Unsaved changes" if session.dirty else "Project is clean",
            icon="ERROR" if session.dirty else "CHECKMARK",
        )
        if message:
            layout.label(text=message, icon="INFO")
        layout.prop(settings, "validation_mode")
        operator = layout.operator(
            "chemblender.quick_import",
            text="Select Files",
            icon="FILE_FOLDER",
        )
        operator.validation_mode = settings.validation_mode
        smiles = layout.operator(
            "chemblender.import_smiles_text",
            text="Import SMILES",
            icon="TEXT",
        )
        smiles.validation_mode = settings.validation_mode
        if settings.recent_summary:
            layout.label(text=settings.recent_summary)
        if get_quick_import_state(session).preview is not None:
            row = layout.row(align=True)
            row.operator(
                "chemblender.confirm_import",
                text="Review",
                icon="PRESET",
            )
            row.operator(
                "chemblender.cancel_import",
                text="Cancel",
                icon="X",
            )

        save_operator = (
            "wm.save_mainfile"
            if bpy.data.filepath
            else "wm.save_as_mainfile"
        )
        layout.operator(save_operator, text="Save Project", icon="FILE_TICK")

        if hasattr(bpy.types, "CHEMBLENDER_OT_open_workspace"):
            layout.operator(
                "chemblender.open_workspace",
                text="Open Workspace",
            )
        else:
            row = layout.row()
            row.enabled = False
            row.label(text="Open Workspace")


__all__ = (
    "CHEMBLENDER_OT_quick_import",
    "CHEMBLENDER_OT_import_smiles_text",
    "CHEMBLENDER_PT_quick_import",
    "clear_quick_import_state",
    "get_quick_import_state",
)
