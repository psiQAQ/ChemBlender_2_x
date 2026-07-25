"""Blender Import Preview projection and transaction confirmation."""

import shutil
from dataclasses import dataclass, fields, is_dataclass, replace
from pathlib import Path
from threading import Event, Thread
from uuid import UUID, uuid4

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    IntProperty,
    StringProperty,
)

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
    GroupingDecision,
    ImportCommitDecisions,
    commit_import_preview,
)
from ..scene_preset_view import (
    _remove_objects as _remove_scene_preset_objects,
    apply_scene_preset,
)
from ..runtime.reader_api_bridge import get_reader_plugin_registry
from .default_views import describe_default_view, plan_default_view
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
_ACTION_ITEMS_BY_VALUE = {
    identifier: (identifier, label, description)
    for identifier, label, description in _ACTION_ITEMS
}
_GROUPING_ACTION_ITEMS = (
    (
        "keep_independent",
        "Keep Independent",
        "Do not create a Calculation Group",
    ),
    (
        "accept_group",
        "Accept Group",
        "Create the suggested Calculation Group",
    ),
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


def _conflict_action_items(row, _context):
    values = tuple(
        value
        for value in getattr(row, "allowed_actions", "").split(",")
        if value in _ACTION_ITEMS_BY_VALUE
    )
    if not values:
        values = (DuplicateAction.INDEPENDENT_COPY.value,)
    return tuple(_ACTION_ITEMS_BY_VALUE[value] for value in values)


class CHEMBLENDER_PG_import_conflict_candidate(bpy.types.PropertyGroup):
    revision_id: StringProperty()
    source_id: StringProperty()
    display_label: StringProperty()
    created_entity_count: IntProperty()
    selected: BoolProperty(default=False)


class CHEMBLENDER_PG_import_grouping_evidence(bpy.types.PropertyGroup):
    evidence_id: StringProperty()
    source_revision_ids: StringProperty()
    kind: StringProperty()
    summary: StringProperty()
    metric: StringProperty()
    metric_unit: StringProperty()
    selected: BoolProperty(default=True)


class CHEMBLENDER_PG_import_grouping_suggestion(bpy.types.PropertyGroup):
    suggestion_id: StringProperty()
    source_count: IntProperty()
    confidence: StringProperty()
    requires_review: BoolProperty()
    grouping_action: EnumProperty(items=_GROUPING_ACTION_ITEMS)
    review_confirmed: BoolProperty(default=False)
    evidence: CollectionProperty(
        type=CHEMBLENDER_PG_import_grouping_evidence
    )


class CHEMBLENDER_PG_import_preview_row(bpy.types.PropertyGroup):
    source_id: StringProperty()
    source_name: StringProperty()
    reader_id: StringProperty()
    reader_availability: StringProperty()
    capability_summary: StringProperty()
    quality: StringProperty()
    conflict_id: StringProperty()
    conflict_action: EnumProperty(items=_conflict_action_items)
    conflict_candidates: CollectionProperty(
        type=CHEMBLENDER_PG_import_conflict_candidate
    )
    allowed_actions: StringProperty()
    default_view: BoolProperty(default=True)
    default_view_label: StringProperty()
    blocking: BoolProperty(default=False)
    blocking_reason: StringProperty()


@dataclass(slots=True)
class ConflictCandidateProjection:
    revision_id: str
    source_id: str
    display_label: str
    created_entity_count: int
    selected: bool = False


@dataclass(slots=True)
class PreviewProjection:
    source_id: str
    source_name: str
    reader_id: str
    reader_availability: str
    capability_summary: str
    quality: str
    conflict_id: str = ""
    allowed_actions: str = ""
    conflict_action: str = DuplicateAction.INDEPENDENT_COPY.value
    conflict_candidates: tuple[ConflictCandidateProjection, ...] = ()
    default_view: bool = True
    default_view_label: str = ""
    blocking: bool = False
    blocking_reason: str = ""


@dataclass(slots=True)
class GroupingEvidenceProjection:
    evidence_id: str
    source_revision_ids: str
    kind: str
    summary: str
    metric: str
    metric_unit: str
    selected: bool = True


@dataclass(slots=True)
class GroupingSuggestionProjection:
    suggestion_id: str
    source_count: int
    confidence: str
    requires_review: bool
    grouping_action: str = "keep_independent"
    review_confirmed: bool = False
    evidence: tuple[GroupingEvidenceProjection, ...] = ()


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


def _candidate_projection(project, candidate, *, selected):
    source = project.sources[candidate.source_id]
    revision = project.source_revisions[candidate.revision_id]
    return ConflictCandidateProjection(
        revision_id=str(candidate.revision_id),
        source_id=str(candidate.source_id),
        display_label=(
            f"{source.display_name} · {revision.original_filename} · "
            f"{str(candidate.revision_id)[:8]}"
        ),
        created_entity_count=len(candidate.created_entity_ids),
        selected=selected,
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
    state.grouping_suggestions = grouping_suggestions
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
        default_view_plan = None
        if len(source.staged_batch_ids) == 1:
            batch = staging.result(source.staged_batch_ids[0])
            revision = next(
                (
                    value
                    for value in batch.source_revisions
                    if value.source_id == source.source_id
                ),
                None,
            )
            if revision is not None:
                default_view_plan = plan_default_view(
                    revision,
                    {value.id: value for value in batch.structures},
                    {value.id: value for value in batch.datasets},
                )
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
                conflict_candidates=(
                    tuple(
                        _candidate_projection(
                            project_session.project,
                            candidate,
                            selected=(
                                len(conflict.candidates) == 1
                                and conflict.default_action in _TARGET_ACTIONS
                            ),
                        )
                        for candidate in conflict.candidates
                    )
                    if conflict
                    else ()
                ),
                allowed_actions=(
                    ",".join(action.value for action in conflict.allowed_actions)
                    if conflict
                    else ""
                ),
                default_view=True,
                default_view_label=describe_default_view(
                    default_view_plan
                ),
                blocking=bool(blocking_reason),
                blocking_reason=blocking_reason,
            )
        )
    return tuple(rows)


def project_grouping_suggestions(state):
    return tuple(
        GroupingSuggestionProjection(
            suggestion_id=str(suggestion.id),
            source_count=len(suggestion.source_revision_ids),
            confidence=suggestion.confidence,
            requires_review=suggestion.requires_review,
            evidence=tuple(
                GroupingEvidenceProjection(
                    evidence_id=str(item.id),
                    source_revision_ids=",".join(
                        map(str, item.source_revision_ids)
                    ),
                    kind=item.kind,
                    summary=item.summary,
                    metric=(
                        ""
                        if item.metric is None
                        else format(item.metric, ".12g")
                    ),
                    metric_unit=item.metric_unit or "",
                )
                for item in suggestion.evidence
            ),
        )
        for suggestion in state.grouping_suggestions
    )


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


def _grouping_decisions(
    state,
    grouping_rows,
    *,
    project_session,
):
    preview = state.preview
    staging = state.staging_session
    suggestions = state.grouping_suggestions
    if preview.grouping_suggestion_ids != tuple(
        suggestion.id for suggestion in suggestions
    ):
        raise ValueError("grouping suggestions do not match Import Preview")
    if project_session is not None:
        live = suggest_source_groups(preview, staging)
        if live != suggestions:
            raise ValueError(
                "grouping suggestions changed; refresh Import Preview"
            )
    if grouping_rows is None:
        grouping_rows = project_grouping_suggestions(state)
    grouping_rows = tuple(grouping_rows)
    by_id = {}
    for row in grouping_rows:
        suggestion_id = UUID(row.suggestion_id)
        if suggestion_id in by_id:
            raise ValueError("grouping suggestion rows must be unique")
        by_id[suggestion_id] = row
    live_by_id = {
        suggestion.id: suggestion for suggestion in suggestions
    }
    if set(by_id) != set(live_by_id):
        raise ValueError(
            "grouping suggestion rows do not match Import Preview"
        )
    decisions = []
    for suggestion_id, row in by_id.items():
        suggestion = live_by_id[suggestion_id]
        if row.grouping_action == "keep_independent":
            continue
        if row.grouping_action != "accept_group":
            raise ValueError("Split/Edit grouping is unavailable in alpha.1")
        if suggestion.requires_review and not row.review_confirmed:
            raise ValueError("grouping review requires explicit confirmation")
        evidence_rows = tuple(row.evidence)
        evidence_ids = tuple(UUID(item.evidence_id) for item in evidence_rows)
        if len(evidence_ids) != len(set(evidence_ids)) or set(
            evidence_ids
        ) != set(suggestion.evidence_ids):
            raise ValueError(
                "grouping evidence does not match Import Preview"
            )
        selected_ids = tuple(
            UUID(item.evidence_id)
            for item in evidence_rows
            if item.selected
        )
        suggestion.confirm(selected_ids)
        decisions.append(
            GroupingDecision(
                suggestion=suggestion,
                evidence_ids=selected_ids,
            )
        )
    return tuple(decisions)


def import_commit_decisions(
    state,
    rows,
    *,
    grouping_rows=None,
    project_session=None,
):
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
            selected = tuple(
                candidate
                for candidate in row.conflict_candidates
                if candidate.selected
            )
            if len(selected) != 1:
                raise ValueError("select exactly one conflict target")
            try:
                target_id = UUID(selected[0].revision_id)
            except (AttributeError, TypeError, ValueError) as error:
                raise ValueError(
                    "conflict target is not allowed"
                ) from error
            if target_id not in conflict.existing_revision_ids:
                raise ValueError("conflict target is not allowed")
            decisions[conflict.id] = ConflictDecision(action, target_id)
        else:
            decisions[conflict.id] = action
    return ImportCommitDecisions(
        conflicts=conflicts,
        conflict_decisions=decisions,
        grouping_decisions=_grouping_decisions(
            state,
            grouping_rows,
            project_session=project_session,
        ),
    )


def _committed_default_view_plans(commit_result, rows):
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
        plan = plan_default_view(
            revision,
            project.structures,
            project.datasets,
        )
        if plan is not None:
            selected.append(plan)
    return tuple(selected)


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
        presets = builtin_scene_presets()
        for default_view in _committed_default_view_plans(
            commit_result,
            rows,
        ):
            preset = presets[default_view.preset_id]
            plan = plan_scene_preset(
                preset,
                commit_result.project,
                dict(default_view.bindings),
                dict(default_view.settings),
            )
            apply_keywords = {"collection": collection}
            if default_view.preset_id != "structure_publication":
                cache_root = (
                    Path(project_session.temporary_root) / "view-cache"
                )
                cache_root.mkdir(exist_ok=True)
                apply_keywords["cache_root"] = cache_root
            created.extend(
                apply_view(
                    plan,
                    commit_result.project,
                    **apply_keywords,
                )
            )
    except Exception:
        _remove_scene_preset_objects(created)
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
        state.grouping_suggestions = ()
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
    grouping_rows=None,
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
        grouping_rows=grouping_rows,
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


def _copy_projections(collection, projected):
    if collection is None:
        return projected
    collection.clear()
    for projection in projected:
        item = collection.add()
        for field in fields(projection):
            value = getattr(projection, field.name)
            if type(value) is tuple and (
                not value or all(is_dataclass(member) for member in value)
            ):
                nested = getattr(item, field.name, None)
                copied = _copy_projections(nested, value)
                if nested is None:
                    setattr(item, field.name, copied)
            else:
                setattr(item, field.name, value)
    return collection


def _projection_value(cls, value, nested=()):
    nested = dict(nested)
    return cls(
        **{
            field.name: (
                tuple(
                    _projection_value(nested[field.name], member)
                    for member in getattr(value, field.name)
                )
                if field.name in nested
                else getattr(value, field.name)
            )
            for field in fields(cls)
        }
    )


def _row_values(rows):
    return tuple(
        _projection_value(
            PreviewProjection,
            row,
            (("conflict_candidates", ConflictCandidateProjection),),
        )
        for row in rows
    )


def _grouping_values(rows):
    return tuple(
        _projection_value(
            GroupingSuggestionProjection,
            row,
            (("evidence", GroupingEvidenceProjection),),
        )
        for row in rows
    )


class CHEMBLENDER_OT_confirm_import(bpy.types.Operator):
    bl_idname = "chemblender.confirm_import"
    bl_label = "Import Preview"
    bl_description = "Review and commit staged scientific files"

    rows: CollectionProperty(type=CHEMBLENDER_PG_import_preview_row)
    grouping_suggestions: CollectionProperty(
        type=CHEMBLENDER_PG_import_grouping_suggestion
    )
    blocking_reason: StringProperty()

    def _project(self, context):
        session = get_scene_session(context.scene)
        state = get_quick_import_state(session)
        projected = project_import_preview(
            session,
            state,
            get_reader_plugin_registry(),
        )
        _copy_projections(self.rows, projected)
        grouping_suggestions = project_grouping_suggestions(state)
        collection = getattr(self, "grouping_suggestions", None)
        copied = _copy_projections(collection, grouping_suggestions)
        if collection is None:
            self.grouping_suggestions = copied
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
                if DuplicateAction(row.conflict_action) in _TARGET_ACTIONS:
                    box.label(text="Select exactly one target:")
                    for candidate in row.conflict_candidates:
                        candidate_row = box.row(align=True)
                        candidate_row.prop(
                            candidate,
                            "selected",
                            text=candidate.display_label,
                        )
                        candidate_row.label(
                            text=(
                                f"{candidate.created_entity_count} "
                                "created entities"
                            )
                        )
            box.prop(row, "default_view")
            box.label(text=row.default_view_label)
        for suggestion in self.grouping_suggestions:
            box = layout.box()
            box.label(
                text=(
                    f"Suggested source group: {suggestion.source_count} "
                    f"sources · {suggestion.confidence} confidence"
                )
            )
            box.prop(suggestion, "grouping_action", expand=True)
            if suggestion.grouping_action == "accept_group":
                for evidence in suggestion.evidence:
                    evidence_row = box.row(align=True)
                    evidence_row.prop(
                        evidence,
                        "selected",
                        text=evidence.summary,
                    )
                    detail = evidence.kind
                    if evidence.metric:
                        detail += (
                            f": {evidence.metric} {evidence.metric_unit}"
                        )
                    evidence_row.label(text=detail)
                if suggestion.requires_review:
                    box.prop(
                        suggestion,
                        "review_confirmed",
                        text="I reviewed this grouping conflict",
                    )
            unavailable = box.row()
            unavailable.enabled = False
            unavailable.label(text="Split / Edit unavailable in alpha.1")

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
            grouping_rows = _grouping_values(
                self.grouping_suggestions
            )
            decisions = import_commit_decisions(
                state,
                rows,
                grouping_rows=grouping_rows,
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
                    grouping_rows=grouping_rows,
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
    "CHEMBLENDER_PG_import_conflict_candidate",
    "CHEMBLENDER_PG_import_grouping_evidence",
    "CHEMBLENDER_PG_import_grouping_suggestion",
    "CHEMBLENDER_PG_import_preview_row",
)
