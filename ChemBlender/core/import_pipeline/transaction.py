from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass, replace
from pathlib import Path
from types import MappingProxyType
from uuid import UUID, uuid4

from ..model import (
    ArrayData,
    DiagnosticValue,
    ImportBatch,
    QCProject,
)
from ..model_registry import MODEL_TYPES
from ..session import ProjectSession
from ..sidecar import close_project
from ..storage.publication import solidify_session
from .conflicts import (
    ConflictDecision,
    DuplicateAction,
    ImportConflict,
    apply_conflict_decisions,
    detect_import_conflicts,
)
from .grouping import (
    GroupingEvidence,
    SourceGroupSuggestion,
    suggest_source_groups,
)
from .preview import ImportPreview
from .staging import StagedImportSession


_BATCH_ENTITY_FIELDS = (
    "structures",
    "cif_envelopes",
    "qcschema_envelopes",
    "cjson_envelopes",
    "symmetry_results",
    "calculations",
    "datasets",
    "basis_sets",
    "orbital_sets",
    "density_matrices",
    "provenance",
)
_SKIP_ACTIONS = {
    DuplicateAction.REUSE_EXISTING,
    DuplicateAction.LOCATE_EXISTING,
    DuplicateAction.LINK_EXISTING,
    DuplicateAction.IGNORE,
}
_REIDENTIFY_ACTIONS = {
    DuplicateAction.INDEPENDENT_COPY,
    DuplicateAction.INDEPENDENT_SOURCE,
    DuplicateAction.NEW_REVISION,
}
_TRUSTED_MODEL_TYPES = frozenset(MODEL_TYPES.values())


def _uuid_tuple(values, name):
    if type(values) is not tuple:
        raise TypeError(f"{name} must be a tuple")
    if any(type(value) is not UUID for value in values):
        raise TypeError(f"{name} must contain UUID values")
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must contain unique UUID values")
    return values


@dataclass(frozen=True, slots=True)
class GroupingDecision:
    suggestion: SourceGroupSuggestion
    evidence_ids: tuple[UUID, ...]

    def __post_init__(self):
        if type(self.suggestion) is not SourceGroupSuggestion:
            raise TypeError("suggestion must be a SourceGroupSuggestion")
        object.__setattr__(
            self,
            "evidence_ids",
            _uuid_tuple(self.evidence_ids, "evidence_ids"),
        )
        if not self.evidence_ids:
            raise ValueError("evidence_ids must not be empty")


@dataclass(frozen=True, slots=True)
class ImportCommitDecisions:
    conflicts: tuple[ImportConflict, ...] = ()
    conflict_decisions: Mapping = field(default_factory=dict)
    grouping_decisions: tuple[GroupingDecision, ...] = ()

    def __post_init__(self):
        if type(self.conflicts) is not tuple or any(
            type(conflict) is not ImportConflict for conflict in self.conflicts
        ):
            raise TypeError("conflicts must contain ImportConflict values")
        if not isinstance(self.conflict_decisions, Mapping):
            raise TypeError("conflict_decisions must be a Mapping")
        conflict_decisions = dict(self.conflict_decisions)
        if any(type(key) is not UUID for key in conflict_decisions):
            raise TypeError("conflict decision keys must be UUID values")
        if any(
            type(value) not in (DuplicateAction, ConflictDecision)
            for value in conflict_decisions.values()
        ):
            raise TypeError("conflict decisions contain an invalid value")
        if type(self.grouping_decisions) is not tuple or any(
            type(decision) is not GroupingDecision
            for decision in self.grouping_decisions
        ):
            raise TypeError(
                "grouping_decisions must contain GroupingDecision values"
            )
        object.__setattr__(
            self,
            "conflict_decisions",
            MappingProxyType(conflict_decisions),
        )


@dataclass(frozen=True, slots=True)
class ImportCommitResult:
    project: QCProject
    sidecar_path: Path
    committed_source_ids: tuple[UUID, ...]
    committed_source_revision_ids: tuple[UUID, ...]
    committed_entity_ids: tuple[UUID, ...]
    calculation_group_ids: tuple[UUID, ...]
    default_view_plan_ids: tuple[UUID, ...]
    cleanup_warnings: tuple[str, ...] = ()

    def __post_init__(self):
        if type(self.project) is not QCProject:
            raise TypeError("project must be a QCProject")
        if not isinstance(self.sidecar_path, Path):
            raise TypeError("sidecar_path must be a Path")
        if not self.sidecar_path.is_absolute():
            raise ValueError("sidecar_path must be absolute")
        for name in (
            "committed_source_ids",
            "committed_source_revision_ids",
            "committed_entity_ids",
            "calculation_group_ids",
            "default_view_plan_ids",
        ):
            _uuid_tuple(getattr(self, name), name)
        if type(self.cleanup_warnings) is not tuple or any(
            type(warning) is not str or not warning
            for warning in self.cleanup_warnings
        ):
            raise TypeError(
                "cleanup_warnings must contain non-empty string values"
            )


def _copy_project(project):
    return QCProject(
        **{
            item.name: (
                dict(getattr(project, item.name))
                if isinstance(getattr(project, item.name), dict)
                else getattr(project, item.name)
            )
            for item in fields(QCProject)
        }
    )


def _batch_ids(batch):
    return tuple(
        entity.id
        for name in (
            "sources",
            "source_revisions",
            *_BATCH_ENTITY_FIELDS,
            "diagnostics",
        )
        for entity in getattr(batch, name)
    )


def _remap(value, replacements):
    if type(value) is UUID:
        return replacements.get(value, value)
    if type(value) in (ArrayData, DiagnosticValue):
        return value
    if type(value) is tuple:
        return tuple(_remap(item, replacements) for item in value)
    if type(value) is list:
        return [_remap(item, replacements) for item in value]
    if type(value) is dict:
        return {
            _remap(key, replacements): _remap(item, replacements)
            for key, item in value.items()
        }
    if type(value) in _TRUSTED_MODEL_TYPES and is_dataclass(value):
        return replace(
            value,
            **{
                item.name: (
                    getattr(value, item.name)
                    if item.name == "parameters"
                    else _remap(getattr(value, item.name), replacements)
                )
                for item in fields(value)
                if item.init
            },
        )
    return value


def _validate_batch_report(batch):
    if batch.report is None:
        return
    created_ids = {
        entity.id
        for name in _BATCH_ENTITY_FIELDS
        for entity in getattr(batch, name)
    }
    if set(batch.report.created_entity_ids) != created_ids:
        raise ValueError("parser report created IDs must match the import batch")


def _merge_batches(batches):
    for batch in batches:
        _validate_batch_report(batch)
    return ImportBatch(
        **{
            name: tuple(
                entity
                for batch in batches
                for entity in getattr(batch, name)
            )
            for name in (
                "sources",
                "source_revisions",
                *_BATCH_ENTITY_FIELDS,
                "diagnostics",
            )
        }
    )


def _target_candidate(conflict, decision):
    if type(decision) is ConflictDecision:
        revision_id = decision.existing_revision_id
        return next(
            candidate
            for candidate in conflict.candidates
            if candidate.revision_id == revision_id
        )
    source_ids = {candidate.source_id for candidate in conflict.candidates}
    if len(source_ids) != 1:
        raise ValueError(
            "new revision conflict requires one unambiguous existing source"
        )
    return conflict.candidates[0]


def _new_uuid(existing):
    value = uuid4()
    while value in existing:
        value = uuid4()
    existing.add(value)
    return value


def _resolved_batches(project, preview, staged_session, decisions):
    live_conflicts = detect_import_conflicts(
        project,
        preview,
        staged_session,
    )
    if live_conflicts != decisions.conflicts:
        raise ValueError("conflicts do not match the live project")
    resolved_preview = apply_conflict_decisions(
        preview,
        live_conflicts,
        decisions.conflict_decisions,
        project=project,
        session=staged_session,
    )
    conflicts_by_source = {
        conflict.staged_source_id: conflict for conflict in live_conflicts
    }
    decisions_by_source = {
        conflict.staged_source_id: decisions.conflict_decisions[conflict.id]
        for conflict in live_conflicts
    }
    batches_by_source = {
        row.source_id: staged_session.result(row.staged_batch_ids[0])
        for row in preview.source_previews
    }
    used_ids = set(project._all_entity_ids()).union(
        old_id
        for batch in batches_by_source.values()
        for old_id in _batch_ids(batch)
    )
    replacements = {}
    skipped = set()
    ignored_revision_ids = set()

    for source_id, batch in batches_by_source.items():
        raw_decision = decisions_by_source.get(source_id)
        action = (
            raw_decision.action
            if type(raw_decision) is ConflictDecision
            else raw_decision
        )
        if action in _SKIP_ACTIONS:
            skipped.add(source_id)
            if action is DuplicateAction.IGNORE:
                ignored_revision_ids.update(
                    revision.id for revision in batch.source_revisions
                )
                continue
            target = _target_candidate(
                conflicts_by_source[source_id],
                raw_decision,
            )
            revision = batch.source_revisions[0]
            replacements[batch.sources[0].id] = target.source_id
            replacements[revision.id] = target.revision_id
            if (
                action is not DuplicateAction.LINK_EXISTING
                and len(revision.created_entity_ids) == len(
                    target.created_entity_ids
                )
            ):
                replacements.update(
                    zip(
                        revision.created_entity_ids,
                        target.created_entity_ids,
                        strict=True,
                    )
                )
            continue
        if action in _REIDENTIFY_ACTIONS:
            for old_id in _batch_ids(batch):
                replacements[old_id] = _new_uuid(used_ids)
            if action is DuplicateAction.NEW_REVISION:
                target = _target_candidate(
                    conflicts_by_source[source_id],
                    raw_decision,
                )
                replacements[batch.sources[0].id] = target.source_id

    resolved = []
    for source_id, batch in batches_by_source.items():
        if source_id in skipped:
            continue
        remapped = _remap(batch, replacements)
        raw_decision = decisions_by_source.get(source_id)
        action = (
            raw_decision.action
            if type(raw_decision) is ConflictDecision
            else raw_decision
        )
        if action is DuplicateAction.NEW_REVISION:
            remapped = replace(remapped, sources=())
        resolved.append(remapped)
    return (
        resolved_preview,
        tuple(resolved),
        replacements,
        frozenset(ignored_revision_ids),
    )


def _grouping_preview(preview):
    rows = tuple(
        row for row in preview.source_previews if row.staged_batch_ids
    )
    batch_ids = tuple(
        batch_id for row in rows for batch_id in row.staged_batch_ids
    )
    diagnostic_ids = tuple(
        diagnostic_id for row in rows for diagnostic_id in row.diagnostic_ids
    )
    return replace(
        preview,
        source_previews=rows,
        staged_batch_ids=batch_ids,
        diagnostic_ids=diagnostic_ids,
    )


def _validated_grouping_decisions(preview, staged_session, decisions):
    live_suggestions = suggest_source_groups(
        _grouping_preview(preview),
        staged_session,
    )
    if preview.grouping_suggestion_ids != tuple(
        suggestion.id for suggestion in live_suggestions
    ):
        raise ValueError("grouping suggestions do not match live staging")
    live_by_id = {
        suggestion.id: suggestion for suggestion in live_suggestions
    }
    validated = []
    seen = set()
    for decision in decisions.grouping_decisions:
        suggestion = live_by_id.get(decision.suggestion.id)
        if suggestion is None or suggestion != decision.suggestion:
            raise ValueError("grouping decision does not match live staging")
        if suggestion.id in seen:
            raise ValueError("grouping suggestion was decided more than once")
        seen.add(suggestion.id)
        suggestion.confirm(decision.evidence_ids)
        validated.append((suggestion, decision.evidence_ids))
    return tuple(validated)


def _remapped_grouping_suggestion(suggestion, replacements):
    evidence_pairs = tuple(
        (
            item,
            GroupingEvidence(
                kind=item.kind,
                source_revision_ids=tuple(
                    replacements.get(revision_id, revision_id)
                    for revision_id in item.source_revision_ids
                ),
                summary=item.summary,
                entity_ids=tuple(
                    replacements.get(entity_id, entity_id)
                    for entity_id in item.entity_ids
                ),
                metric=item.metric,
                metric_unit=item.metric_unit,
            ),
        )
        for item in suggestion.evidence
    )
    return (
        SourceGroupSuggestion(
            source_revision_ids=tuple(
                replacements.get(revision_id, revision_id)
                for revision_id in suggestion.source_revision_ids
            ),
            evidence=tuple(remapped for _, remapped in evidence_pairs),
        ),
        {
            original.id: remapped.id
            for original, remapped in evidence_pairs
        },
    )


def _confirmed_groups(
    validated_decisions,
    replacements,
    ignored_revision_ids,
    available_entity_ids,
):
    groups = []
    for suggestion, evidence_ids in validated_decisions:
        if set(suggestion.source_revision_ids).intersection(
            ignored_revision_ids
        ):
            raise ValueError(
                "confirmed grouping suggestion references an ignored source"
            )
        remapped, evidence_id_map = _remapped_grouping_suggestion(
            suggestion,
            replacements,
        )
        remapped_selected_ids = tuple(
            evidence_id_map[evidence_id] for evidence_id in evidence_ids
        )
        selected_entity_ids = {
            entity_id
            for item in remapped.evidence
            if item.id in remapped_selected_ids
            for entity_id in item.entity_ids
        }
        if not selected_entity_ids.issubset(available_entity_ids):
            raise ValueError(
                "grouping evidence references an unavailable entity"
            )
        groups.append(remapped.confirm(remapped_selected_ids))
    return tuple(groups)


def commit_import_preview(
    project_session,
    staged_session,
    preview,
    decisions,
):
    if type(project_session) is not ProjectSession:
        raise TypeError("project_session must be a ProjectSession")
    if type(staged_session) is not StagedImportSession:
        raise TypeError("staged_session must be a StagedImportSession")
    if type(preview) is not ImportPreview:
        raise TypeError("preview must be an ImportPreview")
    if type(decisions) is not ImportCommitDecisions:
        raise TypeError("decisions must be ImportCommitDecisions")
    if preview.session_id != staged_session.id:
        raise ValueError("preview session does not match staged session")

    validated_grouping_decisions = _validated_grouping_decisions(
        preview,
        staged_session,
        decisions,
    )
    (
        resolved_preview,
        batches,
        replacements,
        ignored_revision_ids,
    ) = _resolved_batches(
        project_session.project,
        preview,
        staged_session,
        decisions,
    )
    candidate = _copy_project(project_session.project)
    candidate.commit(_merge_batches(batches))
    groups = _confirmed_groups(
        validated_grouping_decisions,
        replacements,
        ignored_revision_ids,
        candidate._all_entity_ids(),
    )
    candidate.commit_calculation_groups(groups)

    destination = (
        project_session.sidecar_path
        if project_session.sidecar_path is not None
        else project_session.temporary_root / "project.cbq"
    )
    candidate_session = ProjectSession(
        id=project_session.id,
        project=candidate,
        temporary_root=project_session.temporary_root,
        sidecar_path=project_session.sidecar_path,
        link_status=project_session.link_status,
    )
    published = solidify_session(
        candidate_session,
        destination,
        transfer_verified_project=True,
    )
    reopened = published.project
    if type(reopened) is not QCProject:
        raise RuntimeError("publication did not transfer its verified project")

    previous = project_session.project
    project_session.project = reopened
    project_session.sidecar_path = published.path
    project_session.mark_dirty("import")
    cleanup_warnings = []
    try:
        close_project(previous)
    except Exception as error:
        cleanup_warnings.append(
            f"previous project cleanup failed: {error}"
        )

    committed_source_ids = tuple(
        source.id for batch in batches for source in batch.sources
    )
    committed_revision_ids = tuple(
        revision.id
        for batch in batches
        for revision in batch.source_revisions
    )
    committed_entity_ids = tuple(
        entity.id
        for batch in batches
        for name in _BATCH_ENTITY_FIELDS
        for entity in getattr(batch, name)
    )
    return ImportCommitResult(
        project=reopened,
        sidecar_path=project_session.sidecar_path,
        committed_source_ids=committed_source_ids,
        committed_source_revision_ids=committed_revision_ids,
        committed_entity_ids=committed_entity_ids,
        calculation_group_ids=tuple(group.id for group in groups),
        default_view_plan_ids=resolved_preview.default_view_plan_ids,
        cleanup_warnings=tuple(cleanup_warnings),
    )
