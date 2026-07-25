"""Blender Import Preview projection and transaction confirmation."""

import shutil
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Event, Thread
from uuid import UUID, uuid4

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, StringProperty

from ..core import (
    DiagnosticSeverity,
    QualityStatus,
    builtin_scene_presets,
    plan_scene_preset,
)
from ..core.import_pipeline.conflicts import (
    ConflictDecision,
    DuplicateAction,
    detect_import_conflicts,
)
from ..core.import_pipeline.grouping import suggest_source_groups
from ..core.import_pipeline.transaction import (
    ImportCommitDecisions,
    commit_import_preview,
)
from ..scene_preset_view import apply_scene_preset
from ..runtime.reader_api_bridge import get_reader_plugin_registry
from .properties import (
    discard_quick_import_preview,
    finish_quick_import_job,
    get_quick_import_state,
    store_quick_import_job,
)
from .session import get_scene_session


_ACTION_ITEMS = tuple(
    (action.value, action.value.replace("_", " ").title(), "")
    for action in DuplicateAction
)
_TARGET_ACTIONS = frozenset(
    {
        DuplicateAction.REUSE_EXISTING,
        DuplicateAction.LOCATE_EXISTING,
        DuplicateAction.LINK_EXISTING,
    }
)
_SKIP_ACTIONS = frozenset(
    {
        DuplicateAction.REUSE_EXISTING,
        DuplicateAction.LOCATE_EXISTING,
        DuplicateAction.LINK_EXISTING,
        DuplicateAction.IGNORE,
    }
)


class CHEMBLENDER_PG_import_preview_row(bpy.types.PropertyGroup):
    source_id: StringProperty()
    source_name: StringProperty()
    reader_id: StringProperty()
    reader_availability: StringProperty()
    capability_summary: StringProperty()
    quality: StringProperty()
    conflict_id: StringProperty()
    conflict_action: EnumProperty(items=_ACTION_ITEMS)
    conflict_target_revision_id: StringProperty()
    allowed_actions: StringProperty()
    default_view: BoolProperty(default=True)
    blocking: BoolProperty(default=False)
    blocking_reason: StringProperty()


@dataclass(slots=True)
class PreviewProjection:
    source_id: str
    source_name: str
    reader_id: str
    reader_availability: str
    capability_summary: str
    quality: str
    conflict_id: str = ""
    conflict_action: str = DuplicateAction.INDEPENDENT_COPY.value
    conflict_target_revision_id: str = ""
    allowed_actions: str = ""
    default_view: bool = True
    blocking: bool = False
    blocking_reason: str = ""


@dataclass(frozen=True, slots=True)
class ImportUICommitResult:
    status: str
    commit_result: object
    created_view_count: int


class ImportCommitCancelled(RuntimeError):
    pass


def _owned_temporary_generation(project_session, path):
    if path is None:
        return False
    candidate = Path(path)
    try:
        root = Path(project_session.temporary_root).resolve(strict=True)
        resolved = candidate.resolve(strict=False)
    except OSError:
        return False
    is_link_like = candidate.is_symlink() or (
        hasattr(candidate, "is_junction") and candidate.is_junction()
    )
    return (
        not is_link_like
        and resolved.parent == root
        and resolved.suffix.lower() == ".cbq"
    )


def _remove_owned_temporary_generation(project_session, path):
    if not _owned_temporary_generation(project_session, path):
        return
    candidate = Path(path)
    if candidate.exists():
        shutil.rmtree(candidate)


def _restore_dirty_reasons(project_session, dirty_reasons):
    current = project_session.dirty_reasons
    for reason in current - dirty_reasons:
        project_session.clear_dirty(reason)
    for reason in dirty_reasons - current:
        project_session.mark_dirty(reason)


def _new_temporary_generation(project_session):
    root = Path(project_session.temporary_root)
    while True:
        candidate = root / f"g{uuid4().hex[:8]}.cbq"
        if not candidate.exists():
            return candidate


def _commit_to_fresh_generation(
    project_session,
    staged_session,
    preview,
    decisions,
):
    previous_path = project_session.sidecar_path
    previous_project = project_session.project
    previous_dirty = project_session.dirty_reasons
    generation = _new_temporary_generation(project_session)
    project_session.sidecar_path = generation
    try:
        result = commit_import_preview(
            project_session,
            staged_session,
            preview,
            decisions,
        )
    except BaseException as error:
        project_session.sidecar_path = previous_path
        _restore_dirty_reasons(project_session, previous_dirty)
        if project_session.project is not previous_project:
            error.add_note(
                "project changed during a failed import publication"
            )
        try:
            _remove_owned_temporary_generation(project_session, generation)
        except OSError as cleanup_error:
            error.add_note(
                f"failed import generation cleanup failed: {cleanup_error}"
            )
        raise

    if previous_path is not None and previous_path != result.sidecar_path:
        try:
            _remove_owned_temporary_generation(
                project_session,
                previous_path,
            )
        except OSError as error:
            result = replace(
                result,
                cleanup_warnings=(
                    *result.cleanup_warnings,
                    f"previous import generation cleanup failed: {error}",
                ),
            )
    return result


def _diagnostics(staging, source_preview):
    values = {}
    for batch_id in source_preview.staged_batch_ids:
        batch = staging.result(batch_id)
        values.update((value.id, value) for value in batch.diagnostics)
    return tuple(
        values[diagnostic_id]
        for diagnostic_id in source_preview.diagnostic_ids
        if diagnostic_id in values
    )


def _quality_and_blocking(staging, source_preview):
    if len(source_preview.staged_batch_ids) != 1:
        return (
            QualityStatus.INCOMPLETE.value,
            "source has no single staged batch",
        )
    diagnostics = _diagnostics(staging, source_preview)
    quality = max(
        (item.quality_status for item in diagnostics),
        key=lambda item: item.summary_order,
        default=QualityStatus.COMPLETE,
    )
    blocking = next(
        (
            item
            for item in diagnostics
            if item.severity is DiagnosticSeverity.ERROR
            or item.quality_status is QualityStatus.INVALID
        ),
        None,
    )
    return (
        quality.value,
        (
            f"{blocking.code}: {blocking.message}"
            if blocking is not None
            else ""
        ),
    )


def project_import_preview(project_session, state, registry):
    """Refresh live conflicts and return a small RNA-safe row projection."""
    preview = state.preview
    staging = state.staging_session
    if preview is None or staging is None:
        raise RuntimeError("no staged Import Preview")
    ready = all(
        len(source.staged_batch_ids) == 1
        for source in preview.source_previews
    )
    conflicts = (
        detect_import_conflicts(project_session.project, preview, staging)
        if ready
        else ()
    )
    grouping_suggestions = (
        suggest_source_groups(preview, staging) if ready else ()
    )
    preview = replace(
        preview,
        conflict_ids=tuple(conflict.id for conflict in conflicts),
        grouping_suggestion_ids=tuple(
            suggestion.id for suggestion in grouping_suggestions
        ),
    )
    state.preview = preview
    state.conflicts = conflicts
    conflicts_by_source = {
        conflict.staged_source_id: conflict for conflict in conflicts
    }
    descriptors = {
        descriptor.reader_id: descriptor
        for descriptor in registry.descriptors
    }
    rows = []
    for source in preview.source_previews:
        descriptor = descriptors.get(source.selected_reader_id)
        availability = (
            descriptor.availability.reason_code
            if descriptor is not None
            else "reader unavailable"
        )
        quality, blocking_reason = _quality_and_blocking(staging, source)
        conflict = conflicts_by_source.get(source.source_id)
        rows.append(
            PreviewProjection(
                source_id=str(source.source_id),
                source_name=source.source_path.name,
                reader_id=source.selected_reader_id or "unresolved",
                reader_availability=availability,
                capability_summary=", ".join(source.capabilities) or "none",
                quality=quality,
                conflict_id=str(conflict.id) if conflict else "",
                conflict_action=(
                    conflict.default_action.value
                    if conflict
                    else DuplicateAction.INDEPENDENT_COPY.value
                ),
                conflict_target_revision_id=(
                    str(conflict.candidates[0].revision_id)
                    if conflict
                    and conflict.default_action in _TARGET_ACTIONS
                    else ""
                ),
                allowed_actions=(
                    ",".join(action.value for action in conflict.allowed_actions)
                    if conflict
                    else ""
                ),
                default_view=True,
                blocking=bool(blocking_reason),
                blocking_reason=blocking_reason,
            )
        )
    return tuple(rows)


def _source_rows(preview, rows):
    rows = tuple(rows)
    by_source = {}
    for row in rows:
        source_id = UUID(row.source_id)
        if source_id in by_source:
            raise ValueError("preview rows must have unique source IDs")
        by_source[source_id] = row
    expected = {source.source_id for source in preview.source_previews}
    if set(by_source) != expected:
        raise ValueError("preview rows do not match staged sources")
    return by_source


def import_commit_decisions(state, rows, *, project_session=None):
    preview = state.preview
    staging = state.staging_session
    if preview is None or staging is None:
        raise RuntimeError("no staged Import Preview")
    by_source = _source_rows(preview, rows)
    for source in preview.source_previews:
        _quality, blocking_reason = _quality_and_blocking(staging, source)
        if blocking_reason:
            raise ValueError(blocking_reason)
    conflicts = state.conflicts
    if project_session is not None:
        live = detect_import_conflicts(
            project_session.project,
            preview,
            staging,
        )
        if live != conflicts:
            raise ValueError("conflicts changed; refresh Import Preview")
    decisions = {}
    conflicts_by_source = {
        conflict.staged_source_id: conflict for conflict in conflicts
    }
    for source_id, row in by_source.items():
        conflict = conflicts_by_source.get(source_id)
        if conflict is None:
            if row.conflict_id:
                raise ValueError("unexpected conflict ID")
            continue
        if row.conflict_id != str(conflict.id):
            raise ValueError("conflict ID does not match the live conflict")
        action = DuplicateAction(row.conflict_action)
        if action not in conflict.allowed_actions:
            raise ValueError("conflict action is not allowed")
        if action in _TARGET_ACTIONS:
            target_id = UUID(row.conflict_target_revision_id)
            if target_id not in conflict.existing_revision_ids:
                raise ValueError("conflict target is not allowed")
            decisions[conflict.id] = ConflictDecision(action, target_id)
        else:
            decisions[conflict.id] = action
    return ImportCommitDecisions(
        conflicts=conflicts,
        conflict_decisions=decisions,
    )


def _committed_structure_ids(commit_result, rows):
    committing_rows = tuple(
        row
        for row in rows
        if not row.conflict_id
        or DuplicateAction(row.conflict_action) not in _SKIP_ACTIONS
    )
    if len(committing_rows) != len(
        commit_result.committed_source_revision_ids
    ):
        raise RuntimeError("committed source revisions do not match preview")
    selected = []
    project = commit_result.project
    for row, revision_id in zip(
        committing_rows,
        commit_result.committed_source_revision_ids,
        strict=True,
    ):
        if not row.default_view:
            continue
        revision = project.source_revisions[revision_id]
        selected.extend(
            entity_id
            for entity_id in revision.created_entity_ids
            if entity_id in project.structures
        )
    return tuple(selected)


def _remove_objects(objects):
    data_blocks = []
    for obj in reversed(objects):
        data = getattr(obj, "data", None)
        bpy.data.objects.remove(obj, do_unlink=True)
        if data is not None:
            data_blocks.append(data)
    for data in data_blocks:
        if data.users == 0:
            bpy.data.batch_remove(ids=(data,))


def _finish_committed_import(
    project_session,
    state,
    rows,
    commit_result,
    *,
    collection,
    apply_view,
    discard_staging=True,
):
    state.browser_revision += 1
    created = []
    cleanup_pending = bool(commit_result.cleanup_warnings)
    view_failed = False
    try:
        preset = builtin_scene_presets()["structure_publication"]
        for structure_id in _committed_structure_ids(commit_result, rows):
            plan = plan_scene_preset(
                preset,
                commit_result.project,
                {"structure": structure_id},
                {},
            )
            created.extend(
                apply_view(
                    plan,
                    commit_result.project,
                    collection=collection,
                )
            )
    except Exception:
        _remove_objects(created)
        created.clear()
        view_failed = True
    if discard_staging:
        try:
            discard_quick_import_preview(project_session)
        except Exception:
            cleanup_pending = True
    else:
        state.preview = None
        state.conflicts = ()
    status_parts = []
    if view_failed:
        status_parts.append("view failed")
    if cleanup_pending:
        status_parts.append("cleanup pending")
    status = (
        f"data committed; {'; '.join(status_parts)}"
        if status_parts
        else "committed"
    )
    return ImportUICommitResult(status, commit_result, len(created))


def commit_project_import(
    project_session,
    state,
    rows,
    *,
    collection,
    apply_view=None,
):
    """Synchronous background/smoke boundary; Blender views stay on caller."""
    if apply_view is None:
        apply_view = apply_scene_preset
    rows = tuple(rows)
    decisions = import_commit_decisions(
        state,
        rows,
        project_session=project_session,
    )
    result = _commit_to_fresh_generation(
        project_session,
        state.staging_session,
        state.preview,
        decisions,
    )
    return _finish_committed_import(
        project_session,
        state,
        rows,
        result,
        collection=collection,
        apply_view=apply_view,
    )


def cancel_project_import(project_session):
    discard_quick_import_preview(project_session)


def _commit_report_level(status):
    return {"WARNING"} if status.startswith("data committed;") else {"INFO"}


def _with_cleanup_pending(result):
    if "cleanup pending" in result.status:
        return result
    status = (
        "data committed; cleanup pending"
        if result.status == "committed"
        else f"{result.status}; cleanup pending"
    )
    return replace(result, status=status)


def _add_cleanup_note(error, label, cleanup_error):
    error.add_note(f"{label}: {cleanup_error}")
    for note in getattr(cleanup_error, "__notes__", ()):
        error.add_note(f"{label}: {note}")


def _error_report(error):
    return "\n".join((str(error), *getattr(error, "__notes__", ())))


class _CommitJob:
    """Own a pure commit until completion so session teardown cannot race it."""

    def __init__(self, project_session, staging, preview, decisions):
        self.project_session = project_session
        self.staging = staging
        self.preview = preview
        self.decisions = decisions
        self.result = None
        self.error = None
        self._cancelled = Event()
        self._commit_started = Event()
        self._done = Event()
        self._started = False
        self._thread = Thread(target=self._run, daemon=True)
        self._window_manager = None
        self._timer = None
        self._progress_started = False

    @property
    def done(self):
        return self._done.is_set()

    @property
    def commit_started(self):
        return self._commit_started.is_set()

    @property
    def timer_pending(self):
        return self._timer is not None

    def _run(self):
        try:
            if self._cancelled.is_set():
                raise ImportCommitCancelled("import commit cancelled")
            self._commit_started.set()
            if self._cancelled.is_set():
                raise ImportCommitCancelled("import commit cancelled")
            self.result = _commit_to_fresh_generation(
                self.project_session,
                self.staging,
                self.preview,
                self.decisions,
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
        if self._thread.is_alive() and self._commit_started.is_set():
            self._thread.join()
        return not self._thread.is_alive()

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
                if failure is None:
                    failure = error
                else:
                    failure.add_note(f"timer cleanup failed: {error}")
            else:
                self._timer = None
        if self._timer is None and not self._progress_started:
            self._window_manager = None
        if failure is not None:
            raise failure

    def abandon_ui(self):
        self._timer = None
        self._progress_started = False
        self._window_manager = None


def _copy_rows(collection, projected):
    collection.clear()
    for projection in projected:
        row = collection.add()
        for name in projection.__dataclass_fields__:
            setattr(row, name, getattr(projection, name))


def _row_values(rows):
    return tuple(
        PreviewProjection(
            **{
                name: getattr(row, name)
                for name in PreviewProjection.__dataclass_fields__
            }
        )
        for row in rows
    )


class CHEMBLENDER_OT_confirm_import(bpy.types.Operator):
    bl_idname = "chemblender.confirm_import"
    bl_label = "Import Preview"
    bl_description = "Review and commit staged scientific files"

    rows: CollectionProperty(type=CHEMBLENDER_PG_import_preview_row)
    blocking_reason: StringProperty()

    def _project(self, context):
        session = get_scene_session(context.scene)
        state = get_quick_import_state(session)
        projected = project_import_preview(
            session,
            state,
            get_reader_plugin_registry(),
        )
        _copy_rows(self.rows, projected)
        self.blocking_reason = next(
            (row.blocking_reason for row in projected if row.blocking),
            "",
        )
        self._project_session = session
        return session, state

    def invoke(self, context, _event):
        try:
            self._project(context)
        except BaseException as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return context.window_manager.invoke_props_dialog(self, width=720)

    def draw(self, _context):
        layout = self.layout
        if self.blocking_reason:
            layout.label(text=self.blocking_reason, icon="ERROR")
        for row in self.rows:
            box = layout.box()
            box.label(text=row.source_name)
            box.label(
                text=f"{row.reader_id}: {row.reader_availability}"
            )
            box.label(text=f"Capabilities: {row.capability_summary}")
            box.label(text=f"Quality: {row.quality}")
            if row.conflict_id:
                box.prop(row, "conflict_action")
            box.prop(row, "default_view")

    def _abort_setup(self, session, job, error):
        for label, cleanup in (
            ("job cancellation failed", job.cancel),
            ("job join failed", lambda: job.join(0)),
        ):
            try:
                cleanup()
            except BaseException as cleanup_error:
                _add_cleanup_note(error, label, cleanup_error)
        try:
            job.release_ui()
        except BaseException as cleanup_error:
            _add_cleanup_note(
                error,
                "job UI cleanup failed",
                cleanup_error,
            )
        else:
            for label, cleanup in (
                (
                    "job ownership cleanup failed",
                    lambda: finish_quick_import_job(session, job),
                ),
                (
                    "staging cleanup failed",
                    lambda: discard_quick_import_preview(session),
                ),
            ):
                try:
                    cleanup()
                except BaseException as cleanup_error:
                    _add_cleanup_note(error, label, cleanup_error)
        self._job = None
        self._rows = None

    def _finalize_committed_job(self, context, job, state):
        result = getattr(self, "_completion_result", None)
        if result is not None:
            return result
        progress_failed = False
        try:
            context.window_manager.progress_update(80)
        except BaseException:
            progress_failed = True
        result = _finish_committed_import(
            job.project_session,
            state,
            self._rows,
            job.result,
            collection=context.scene.collection,
            apply_view=apply_scene_preset,
            discard_staging=False,
        )
        try:
            context.window_manager.progress_update(100)
        except BaseException:
            progress_failed = True
        if progress_failed:
            result = _with_cleanup_pending(result)
        self._completion_result = result
        return result

    def _finish_modal_ownership(self, job, result, cleanup_error=None):
        state = get_quick_import_state(job.project_session)
        try:
            finish_quick_import_job(job.project_session, job)
        except BaseException as error:
            cleanup_error = cleanup_error or error
        try:
            discard_quick_import_preview(job.project_session)
        except BaseException as error:
            cleanup_error = cleanup_error or error
        if cleanup_error is not None and result is not None:
            result = _with_cleanup_pending(result)
        return state, result

    def execute(self, context):
        try:
            session = getattr(self, "_project_session", None)
            if session is None:
                session, state = self._project(context)
            else:
                state = get_quick_import_state(session)
            rows = _row_values(self.rows)
            decisions = import_commit_decisions(
                state,
                rows,
                project_session=session,
            )
        except BaseException as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        if getattr(bpy.app, "background", False):
            try:
                result = commit_project_import(
                    session,
                    state,
                    rows,
                    collection=context.scene.collection,
                )
            except BaseException as error:
                self.report({"ERROR"}, str(error))
                return {"CANCELLED"}
            self.report(
                _commit_report_level(result.status),
                result.status,
            )
            context.scene.chemblender_quick_import.recent_summary = (
                result.status
            )
            return {"FINISHED"}
        job = _CommitJob(
            session,
            state.staging_session,
            state.preview,
            decisions,
        )
        try:
            store_quick_import_job(
                session,
                state.staging_session,
                job,
            )
            manager = context.window_manager
            timer = manager.event_timer_add(0.1, window=context.window)
            job.attach_ui(manager, timer)
            manager.progress_begin(0, 100)
            job.mark_progress_started()
            manager.progress_update(10)
            manager.modal_handler_add(self)
            self._job = job
            self._rows = rows
            job.start()
        except BaseException as error:
            self._abort_setup(session, job, error)
            self.report({"ERROR"}, _error_report(error))
            return {"CANCELLED"}
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        job = getattr(self, "_job", None)
        if job is None:
            return {"CANCELLED"}
        if event.type == "ESC":
            job.cancel()
            if job.commit_started:
                self.report(
                    {"WARNING"},
                    "commit already started; cancellation cannot undo data",
                )
        if event.type != "TIMER" or not job.done:
            return {"RUNNING_MODAL"}
        job.join(0)
        state = get_quick_import_state(job.project_session)
        result = (
            self._finalize_committed_job(context, job, state)
            if job.error is None
            else None
        )
        release_error = None
        try:
            job.release_ui()
        except BaseException as error:
            release_error = error
            if job.timer_pending:
                self.report(
                    {"WARNING"},
                    f"Import Preview cleanup retry pending: {error}",
                )
                return {"RUNNING_MODAL"}
            job.abandon_ui()
        state, result = self._finish_modal_ownership(
            job,
            result,
            release_error,
        )
        if job.error is not None:
            if release_error is not None:
                _add_cleanup_note(
                    job.error,
                    "Import Preview UI cleanup failed",
                    release_error,
                )
            if isinstance(job.error, ImportCommitCancelled):
                self.report({"INFO"}, str(job.error))
            else:
                self.report({"ERROR"}, str(job.error))
            return {"CANCELLED"}
        self.report(
            _commit_report_level(result.status),
            result.status,
        )
        context.scene.chemblender_quick_import.recent_summary = result.status
        return {"FINISHED"}

    def cancel(self, context):
        job = getattr(self, "_job", None)
        if job is not None:
            job.cancel()
            return
        session = getattr(self, "_project_session", None)
        if session is None:
            session = get_scene_session(context.scene)
        cancel_project_import(session)


class CHEMBLENDER_OT_cancel_import(bpy.types.Operator):
    bl_idname = "chemblender.cancel_import"
    bl_label = "Cancel Import"

    def execute(self, context):
        session = get_scene_session(context.scene)
        state = get_quick_import_state(session)
        if state.active_job is not None:
            state.active_job.cancel()
            self.report(
                {"WARNING"},
                "cancellation requested; published data cannot be undone",
            )
        else:
            cancel_project_import(session)
        return {"FINISHED"}


__all__ = (
    "CHEMBLENDER_OT_cancel_import",
    "CHEMBLENDER_OT_confirm_import",
    "CHEMBLENDER_PG_import_preview_row",
)
