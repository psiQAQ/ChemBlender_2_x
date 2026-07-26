import json
import ntpath
from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import Enum
from uuid import NAMESPACE_URL, UUID, uuid5

from ..model import ImportBatch, QCProject, SourceRecord, SourceRevision
from .preview import ImportPreview
from .staging import StagedImportSession


class DuplicateAction(str, Enum):
    REUSE_EXISTING = "reuse_existing"
    INDEPENDENT_COPY = "independent_copy"
    LOCATE_EXISTING = "locate_existing"
    NEW_REVISION = "new_revision"
    INDEPENDENT_SOURCE = "independent_source"
    IGNORE = "ignore"
    LINK_EXISTING = "link_existing"


class ImportConflictCategory(str, Enum):
    SAME_PARSE_IDENTITY = "same_parse_identity"
    SAME_LOCATOR_CHANGED_CONTENT = "same_locator_changed_content"
    SAME_CONTENT_RELOCATED = "same_content_relocated"


_CATEGORY_ACTIONS = {
    ImportConflictCategory.SAME_PARSE_IDENTITY: (
        DuplicateAction.REUSE_EXISTING,
        DuplicateAction.INDEPENDENT_COPY,
        DuplicateAction.LOCATE_EXISTING,
    ),
    ImportConflictCategory.SAME_LOCATOR_CHANGED_CONTENT: (
        DuplicateAction.NEW_REVISION,
        DuplicateAction.INDEPENDENT_SOURCE,
        DuplicateAction.IGNORE,
    ),
    ImportConflictCategory.SAME_CONTENT_RELOCATED: (
        DuplicateAction.LINK_EXISTING,
        DuplicateAction.INDEPENDENT_COPY,
    ),
}
_TARGET_ACTIONS = {
    DuplicateAction.REUSE_EXISTING,
    DuplicateAction.LOCATE_EXISTING,
    DuplicateAction.LINK_EXISTING,
}


def _require_uuid(value, name):
    if type(value) is not UUID:
        raise TypeError(f"{name} must be a UUID")


def _require_uuid_tuple(values, name, *, nonempty=False):
    if type(values) is not tuple:
        raise TypeError(f"{name} must be a tuple")
    if any(type(value) is not UUID for value in values):
        raise TypeError(f"{name} must contain UUID values")
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must contain unique UUID values")
    if nonempty and not values:
        raise ValueError(f"{name} must not be empty")


@dataclass(frozen=True, slots=True)
class ImportConflictCandidate:
    source_id: UUID
    revision_id: UUID
    created_entity_ids: tuple[UUID, ...]

    def __post_init__(self):
        _require_uuid(self.source_id, "source_id")
        _require_uuid(self.revision_id, "revision_id")
        _require_uuid_tuple(self.created_entity_ids, "created_entity_ids")


@dataclass(frozen=True, slots=True)
class ConflictDecision:
    action: DuplicateAction
    existing_revision_id: UUID | None = None

    def __post_init__(self):
        if type(self.action) is not DuplicateAction:
            raise TypeError("action must be a DuplicateAction")
        if self.action in _TARGET_ACTIONS:
            if self.existing_revision_id is None:
                raise ValueError(
                    "target action requires an existing revision id"
                )
            if type(self.existing_revision_id) is not UUID:
                raise TypeError("existing_revision_id must be a UUID")
        elif self.existing_revision_id is not None:
            raise ValueError(
                "non-target action must not select an existing revision"
            )


@dataclass(frozen=True, slots=True)
class ImportConflict:
    id: UUID
    staged_source_id: UUID
    staged_revision_id: UUID
    category: ImportConflictCategory
    default_action: DuplicateAction
    allowed_actions: tuple[DuplicateAction, ...]
    candidates: tuple[ImportConflictCandidate, ...]

    def __post_init__(self):
        for name in ("id", "staged_source_id", "staged_revision_id"):
            _require_uuid(getattr(self, name), name)
        if type(self.category) is not ImportConflictCategory:
            raise TypeError("category must be an ImportConflictCategory")
        if type(self.default_action) is not DuplicateAction:
            raise TypeError("default_action must be a DuplicateAction")
        if type(self.allowed_actions) is not tuple or any(
            type(action) is not DuplicateAction
            for action in self.allowed_actions
        ):
            raise TypeError("allowed_actions must contain DuplicateAction values")
        expected = _CATEGORY_ACTIONS[self.category]
        if self.allowed_actions != expected or self.default_action is not expected[0]:
            raise ValueError("actions do not match conflict category")
        if type(self.candidates) is not tuple or any(
            type(candidate) is not ImportConflictCandidate
            for candidate in self.candidates
        ):
            raise TypeError(
                "candidates must contain ImportConflictCandidate values"
            )
        if not self.candidates:
            raise ValueError("candidates must not be empty")
        if self.candidates != tuple(
            sorted(self.candidates, key=lambda item: str(item.revision_id))
        ):
            raise ValueError("candidates must be sorted by revision id")
        revision_ids = tuple(
            candidate.revision_id for candidate in self.candidates
        )
        if len(revision_ids) != len(set(revision_ids)):
            raise ValueError("candidate revision ids must be unique")

    @property
    def existing_source_ids(self):
        return _sorted_unique(
            candidate.source_id for candidate in self.candidates
        )

    @property
    def existing_revision_ids(self):
        return tuple(
            candidate.revision_id for candidate in self.candidates
        )

    @property
    def existing_created_entity_ids(self):
        return _sorted_unique(
            entity_id
            for candidate in self.candidates
            for entity_id in candidate.created_entity_ids
        )


def _locator_key(revision):
    locator = revision.locator
    if revision.locator_kind in {
        "path",
        "relative_path",
        "absolute_path",
    }:
        locator = ntpath.normcase(ntpath.normpath(locator.replace("/", "\\")))
    return revision.locator_kind, locator


def _staged_revisions(preview, session):
    if preview.session_id != session.id:
        raise ValueError("preview session does not match staged session")
    used_batch_ids = []
    diagnostic_ids = []
    entries = []
    for source_preview in preview.source_previews:
        if len(source_preview.staged_batch_ids) != 1:
            raise ValueError("each source preview must have exactly one staged batch")
        batch_id = source_preview.staged_batch_ids[0]
        used_batch_ids.append(batch_id)
        try:
            batch = session.result(batch_id)
        except KeyError as error:
            raise ValueError("preview references an unknown staged batch") from error
        if (
            type(batch) is not ImportBatch
            or len(batch.sources) != 1
            or len(batch.source_revisions) != 1
            or type(batch.sources[0]) is not SourceRecord
            or type(batch.source_revisions[0]) is not SourceRevision
        ):
            raise ValueError(
                "staged batch must contain exactly one source and revision"
            )
        source = batch.sources[0]
        revision = batch.source_revisions[0]
        if (
            source.id != source_preview.source_id
            or revision.source_id != source.id
            or source_preview.content_hash != revision.content_hash
        ):
            raise ValueError("staged source and revision do not match source preview")
        if source_preview.selected_reader_id != revision.reader_id:
            raise ValueError("staged reader does not match source preview")
        if source_preview.byte_size != revision.byte_size:
            raise ValueError("staged byte size does not match source preview")
        if revision.locator_kind != "absolute_path":
            raise ValueError(
                "staged revision locator_kind must be absolute_path"
            )
        if ntpath.normcase(
            ntpath.normpath(str(source_preview.source_path))
        ) != ntpath.normcase(
            ntpath.normpath(revision.locator.replace("/", "\\"))
        ):
            raise ValueError("staged locator does not match source preview")
        batch_diagnostic_ids = tuple(item.id for item in batch.diagnostics)
        if batch_diagnostic_ids != source_preview.diagnostic_ids:
            raise ValueError("staged diagnostics do not match source preview")
        diagnostic_ids.extend(batch_diagnostic_ids)
        entries.append((source_preview, revision))
    if (
        len(used_batch_ids) != len(set(used_batch_ids))
        or tuple(used_batch_ids) != preview.staged_batch_ids
    ):
        raise ValueError("preview staged batch ids are duplicated or inconsistent")
    if tuple(diagnostic_ids) != preview.diagnostic_ids:
        raise ValueError("preview diagnostic ids are inconsistent")
    return tuple(entries)


def _conflict_id(
    session_id,
    staged_source_id,
    staged_revision_id,
    category,
    candidates,
):
    snapshot = json.dumps(
        {
            "candidates": [
                {
                    "created_entity_ids": [
                        str(entity_id)
                        for entity_id in candidate.created_entity_ids
                    ],
                    "revision_id": str(candidate.revision_id),
                    "source_id": str(candidate.source_id),
                }
                for candidate in candidates
            ],
            "category": category.value,
            "session_id": str(session_id),
            "staged_revision_id": str(staged_revision_id),
            "staged_source_id": str(staged_source_id),
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return uuid5(
        NAMESPACE_URL,
        f"chemblender:import-conflict:v2:{snapshot}",
    )


def _sorted_unique(values):
    return tuple(sorted(set(values), key=str))


def detect_import_conflicts(project, preview, session):
    if type(project) is not QCProject:
        raise TypeError("project must be a QCProject")
    if type(preview) is not ImportPreview:
        raise TypeError("preview must be an ImportPreview")
    if type(session) is not StagedImportSession:
        raise TypeError("session must be a StagedImportSession")

    # ponytail: linear scan is simplest; index if import scale makes this hot.
    existing = tuple(project.source_revisions.values())
    conflicts = []
    for _, staged in _staged_revisions(preview, session):
        candidates = tuple(
            revision
            for revision in existing
            if revision.parse_identity == staged.parse_identity
        )
        if candidates:
            category = ImportConflictCategory.SAME_PARSE_IDENTITY
        else:
            candidates = tuple(
                revision
                for revision in existing
                if _locator_key(revision) == _locator_key(staged)
                and revision.content_hash != staged.content_hash
            )
            if candidates:
                category = ImportConflictCategory.SAME_LOCATOR_CHANGED_CONTENT
            else:
                candidates = tuple(
                    revision
                    for revision in existing
                    if revision.content_hash == staged.content_hash
                    and _locator_key(revision) != _locator_key(staged)
                )
                if not candidates:
                    continue
                category = ImportConflictCategory.SAME_CONTENT_RELOCATED

        candidates = tuple(sorted(candidates, key=lambda item: str(item.id)))
        candidate_snapshot = tuple(
            ImportConflictCandidate(
                source_id=item.source_id,
                revision_id=item.id,
                created_entity_ids=item.created_entity_ids,
            )
            for item in candidates
        )
        allowed = _CATEGORY_ACTIONS[category]
        conflicts.append(
            ImportConflict(
                id=_conflict_id(
                    session.id,
                    staged.source_id,
                    staged.id,
                    category,
                    candidate_snapshot,
                ),
                staged_source_id=staged.source_id,
                staged_revision_id=staged.id,
                category=category,
                default_action=allowed[0],
                allowed_actions=allowed,
                candidates=candidate_snapshot,
            )
        )
    if len({conflict.id for conflict in conflicts}) != len(conflicts):
        raise ValueError("detected conflict ids must be unique")
    return tuple(conflicts)


def apply_conflict_decisions(
    preview,
    conflicts,
    decisions,
    *,
    project,
    session,
):
    """Apply decisions after revalidating preview conflicts against session."""
    if type(preview) is not ImportPreview:
        raise TypeError("preview must be an ImportPreview")
    if type(conflicts) is not tuple or any(
        type(conflict) is not ImportConflict for conflict in conflicts
    ):
        raise TypeError("conflicts must contain ImportConflict values")
    if type(project) is not QCProject:
        raise TypeError("project must be a QCProject")
    if type(session) is not StagedImportSession:
        raise TypeError("session must be a StagedImportSession")
    if not isinstance(decisions, Mapping):
        raise TypeError("decisions must be a Mapping")
    decision_map = dict(decisions)
    if any(type(key) is not UUID for key in decision_map):
        raise TypeError("decision keys must be UUID values")
    if any(
        type(decision) not in (DuplicateAction, ConflictDecision)
        for decision in decision_map.values()
    ):
        raise TypeError(
            "decisions must contain DuplicateAction or ConflictDecision values"
        )

    live_conflicts = detect_import_conflicts(project, preview, session)
    if live_conflicts != conflicts:
        raise ValueError("conflicts do not match the live project")
    staged_by_source = {
        source_preview.source_id: revision
        for source_preview, revision in _staged_revisions(preview, session)
    }
    conflict_ids = tuple(conflict.id for conflict in conflicts)
    if len(conflict_ids) != len(set(conflict_ids)):
        raise ValueError("conflict ids must be unique")
    if preview.conflict_ids != conflict_ids:
        raise ValueError("conflicts do not match preview")
    if set(decision_map) != set(conflict_ids):
        raise ValueError("each conflict requires exactly one decision")

    source_conflicts = {}
    for conflict in conflicts:
        if conflict.staged_source_id in source_conflicts:
            raise ValueError("each staged source may have only one conflict")
        staged = staged_by_source.get(conflict.staged_source_id)
        if (
            staged is None
            or staged.id != conflict.staged_revision_id
        ):
            raise ValueError("conflict staged revision does not match preview")
        expected_id = _conflict_id(
            preview.session_id,
            conflict.staged_source_id,
            conflict.staged_revision_id,
            conflict.category,
            conflict.candidates,
        )
        if conflict.id != expected_id:
            raise ValueError("conflict id does not match its snapshot")
        decision = decision_map[conflict.id]
        if type(decision) is DuplicateAction:
            if decision in _TARGET_ACTIONS:
                raise ValueError(
                    "target action requires an explicit ConflictDecision"
                )
            decision = ConflictDecision(decision)
        action = decision.action
        if action not in conflict.allowed_actions:
            raise ValueError("decision is not allowed for conflict")
        candidate_revision_ids = {
            candidate.revision_id for candidate in conflict.candidates
        }
        if (
            action in _TARGET_ACTIONS
            and decision.existing_revision_id
            not in candidate_revision_ids
        ):
            raise ValueError("decision target is not a conflict candidate")
        source_conflicts[conflict.staged_source_id] = action

    source_ids = {item.source_id for item in preview.source_previews}
    if not set(source_conflicts).issubset(source_ids):
        raise ValueError("conflict source does not exist in preview")

    source_previews = []
    removed_batch_ids = set()
    removed_diagnostic_ids = set()
    for source_preview in preview.source_previews:
        action = source_conflicts.get(source_preview.source_id)
        if action is DuplicateAction.IGNORE:
            removed_batch_ids.update(source_preview.staged_batch_ids)
            removed_diagnostic_ids.update(source_preview.diagnostic_ids)
            continue
        if action in (
            DuplicateAction.REUSE_EXISTING,
            DuplicateAction.LOCATE_EXISTING,
        ):
            removed_batch_ids.update(source_preview.staged_batch_ids)
            removed_diagnostic_ids.update(source_preview.diagnostic_ids)
            source_preview = replace(
                source_preview,
                staged_batch_ids=(),
                diagnostic_ids=(),
            )
        source_previews.append(source_preview)

    return replace(
        preview,
        source_previews=tuple(source_previews),
        staged_batch_ids=tuple(
            batch_id
            for batch_id in preview.staged_batch_ids
            if batch_id not in removed_batch_ids
        ),
        conflict_ids=(),
        diagnostic_ids=tuple(
            diagnostic_id
            for diagnostic_id in preview.diagnostic_ids
            if diagnostic_id not in removed_diagnostic_ids
        ),
    )
