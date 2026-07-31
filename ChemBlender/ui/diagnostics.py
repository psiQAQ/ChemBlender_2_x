import json
import reprlib
from dataclasses import dataclass
from uuid import UUID

from ..core import QualityStatus
from ..core.import_pipeline.report import render_diagnostics_markdown
from ..project_link import (
    MANIFEST_HASH_KEY,
    PROJECT_ID_KEY,
    PROJECT_SCHEMA_KEY,
    SIDECAR_LOCATOR_KEY,
    ProjectLinkStatus,
)


@dataclass(frozen=True, slots=True)
class QualityPresentation:
    label: str
    icon: str
    alert: bool = False


_QUALITY_PRESENTATIONS = {
    QualityStatus.COMPLETE: QualityPresentation("Complete", "CHECKMARK"),
    QualityStatus.PARTIAL: QualityPresentation("Partial", "INFO"),
    QualityStatus.AMBIGUOUS: QualityPresentation("Ambiguous", "QUESTION"),
    QualityStatus.INCOMPLETE: QualityPresentation(
        "Incomplete",
        "ERROR",
        alert=True,
    ),
    QualityStatus.INVALID: QualityPresentation(
        "Invalid",
        "CANCEL",
        alert=True,
    ),
}
_PROJECT_LINK_KEYS = (
    PROJECT_ID_KEY,
    PROJECT_SCHEMA_KEY,
    SIDECAR_LOCATOR_KEY,
    MANIFEST_HASH_KEY,
)
DIAGNOSTIC_PREVIEW_CHAR_LIMIT = 256
_TRUNCATION_SUFFIX = " [truncated]"
_PREVIEW_REPR = reprlib.Repr()
_PREVIEW_REPR.maxlevel = 3
_PREVIEW_REPR.maxdict = 8
_PREVIEW_REPR.maxlist = 8
_PREVIEW_REPR.maxtuple = 8
_PREVIEW_REPR.maxstring = 96
_PREVIEW_REPR.maxother = 96
_FATAL_EXCEPTIONS = (
    KeyboardInterrupt,
    SystemExit,
    GeneratorExit,
    MemoryError,
)
_REVISION_ACTION_ITEMS = (
    (
        "update_selected_views",
        "Update Selected Views",
        "Create replacement views for the selected current views",
    ),
    (
        "comparison_view",
        "Comparison View",
        "Create a new-revision view beside the current view",
    ),
    (
        "keep_current",
        "Keep Current",
        "Keep every current view unchanged",
    ),
)
_REVISION_ACTIONS = frozenset(item[0] for item in _REVISION_ACTION_ITEMS)
_RECOVERY_ACTIONS = {
    ProjectLinkStatus.MISSING: (
        "relink",
        "verify",
        "inspect_existing",
        "detach",
    ),
    ProjectLinkStatus.MISMATCH: (
        "relink",
        "verify",
        "inspect_existing",
        "detach",
    ),
    ProjectLinkStatus.INCOMPATIBLE: (
        "relink",
        "verify",
        "open_diagnostics",
        "detach",
    ),
    ProjectLinkStatus.INVALID: (
        "relink",
        "verify",
        "open_diagnostics",
        "detach",
    ),
    ProjectLinkStatus.CONNECTED: (),
}


@dataclass(frozen=True, slots=True)
class RevisionViewPrompt:
    current_revision_id: UUID
    new_revision_id: UUID
    action: str = "keep_current"

    def __post_init__(self):
        if (
            type(self.current_revision_id) is not UUID
            or type(self.new_revision_id) is not UUID
        ):
            raise TypeError("revision IDs must be UUIDs")
        if self.current_revision_id == self.new_revision_id:
            raise ValueError("current and new revision IDs must differ")
        if self.action not in _REVISION_ACTIONS:
            raise ValueError("unknown revision view action")


class ProjectLinkDetachRecoveryError(RuntimeError):
    def __init__(self, detach_error, rollback_errors, residual_scene_indices):
        super().__init__(
            "project link detach failed and rollback was incomplete"
        )
        self.detach_error = detach_error
        self.rollback_errors = tuple(rollback_errors)
        self.residual_scene_indices = tuple(residual_scene_indices)


def quality_presentation(status):
    if not isinstance(status, QualityStatus):
        status = QualityStatus(status)
    return _QUALITY_PRESENTATIONS[status]


def draw_quality_badge(layout, status, *, prefix="Quality"):
    presentation = quality_presentation(status)
    row = layout.row(align=True)
    row.alert = presentation.alert
    row.label(
        text=(
            f"{prefix}: {presentation.label}"
            if prefix
            else presentation.label
        ),
        icon=presentation.icon,
    )
    return row


def _display_value(value):
    if value is None:
        return "—"
    if type(value) in (dict, list):
        text = _PREVIEW_REPR.repr(value)
        truncated = (
            "..." in text
            or len(text) > DIAGNOSTIC_PREVIEW_CHAR_LIMIT
        )
    else:
        text = str(value)
        truncated = len(text) > DIAGNOSTIC_PREVIEW_CHAR_LIMIT
    if truncated:
        text = (
            text[
                : DIAGNOSTIC_PREVIEW_CHAR_LIMIT
                - len(_TRUNCATION_SUFFIX)
            ]
            + _TRUNCATION_SUFFIX
        )
    return text


def diagnostic_detail_rows(item):
    return tuple(
        (label, _display_value(item[field]))
        for label, field in (
            ("Severity", "severity"),
            ("Source", "source_id"),
            ("Source revision", "source_revision_id"),
            ("Record", "record_key"),
            ("Entity", "entity_id"),
            ("Field", "field_path"),
            ("Code", "code"),
            ("Message", "message"),
            ("Original", "original_value"),
            ("Normalized", "normalized_value"),
            ("Recovery", "recovery_action"),
            ("Scientific consequence", "scientific_consequence"),
            ("Suggested action", "suggested_action"),
        )
    )


def canonical_report_text(document, format_name):
    markdown = render_diagnostics_markdown(document)
    if format_name == "markdown":
        return markdown
    if format_name == "json":
        return (
            json.dumps(
                document,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
    raise ValueError("format_name must be 'markdown' or 'json'")


def revision_action_items():
    return _REVISION_ACTION_ITEMS


def project_recovery_actions(status):
    if not isinstance(status, ProjectLinkStatus):
        status = ProjectLinkStatus(status)
    return _RECOVERY_ACTIONS[status]


def detach_project_links_for_scenes(scenes):
    scenes = tuple(scenes)
    missing = object()
    snapshots = tuple(
        {
            key: scene[key] if key in scene else missing
            for key in _PROJECT_LINK_KEYS
        }
        for scene in scenes
    )
    detached = 0
    try:
        for scene, snapshot in zip(scenes, snapshots, strict=True):
            changed = False
            for key in _PROJECT_LINK_KEYS:
                if snapshot[key] is not missing:
                    del scene[key]
                    changed = True
            detached += int(changed)
    except BaseException as detach_error:
        rollback_errors = []
        for scene_index in range(len(scenes) - 1, -1, -1):
            scene = scenes[scene_index]
            snapshot = snapshots[scene_index]
            for key in reversed(_PROJECT_LINK_KEYS):
                try:
                    if snapshot[key] is missing:
                        if key in scene:
                            del scene[key]
                    else:
                        scene[key] = snapshot[key]
                except BaseException as rollback_error:
                    rollback_errors.append(
                        (scene_index, key, rollback_error)
                    )
        residual = []
        for scene_index, (scene, snapshot) in enumerate(
            zip(scenes, snapshots, strict=True)
        ):
            try:
                restored = all(
                    (
                        key not in scene
                        if snapshot[key] is missing
                        else key in scene and scene[key] == snapshot[key]
                    )
                    for key in _PROJECT_LINK_KEYS
                )
            except BaseException as rollback_error:
                rollback_errors.append(
                    (scene_index, "<verification>", rollback_error)
                )
                restored = False
            if not restored:
                residual.append(scene_index)
        fatal_rollback = next(
            (
                rollback_error
                for _scene_index, _key, rollback_error in rollback_errors
                if isinstance(rollback_error, _FATAL_EXCEPTIONS)
            ),
            None,
        )
        if isinstance(detach_error, _FATAL_EXCEPTIONS):
            if rollback_errors:
                detach_error.add_note(
                    "project link rollback failures: "
                    + "; ".join(
                        f"scene {scene_index} {key}: {error}"
                        for scene_index, key, error in rollback_errors
                    )
                )
            if residual:
                detach_error.add_note(
                    "project link rollback residual scenes: "
                    + ", ".join(str(value) for value in residual)
                )
            raise
        if fatal_rollback is not None:
            fatal_rollback.add_note(
                f"project link detach failed first: {detach_error}"
            )
            if residual:
                fatal_rollback.add_note(
                    "project link rollback residual scenes: "
                    + ", ".join(str(value) for value in residual)
                )
            raise fatal_rollback from detach_error
        if rollback_errors or residual:
            raise ProjectLinkDetachRecoveryError(
                detach_error,
                rollback_errors,
                residual,
            ) from detach_error
        raise
    return detached
