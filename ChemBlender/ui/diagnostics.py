import json
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
        "open_read_only",
        "detach",
    ),
    ProjectLinkStatus.MISMATCH: (
        "relink",
        "verify",
        "open_read_only",
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
    entity_id_map: tuple[tuple[UUID, UUID], ...] = ()
    selected_view_names: tuple[str, ...] = ()
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
        if type(self.entity_id_map) is not tuple or any(
            type(pair) is not tuple
            or len(pair) != 2
            or any(type(identifier) is not UUID for identifier in pair)
            for pair in self.entity_id_map
        ):
            raise TypeError("entity_id_map must contain UUID pairs")
        if (
            type(self.selected_view_names) is not tuple
            or any(
                type(name) is not str or not name
                for name in self.selected_view_names
            )
            or len(self.selected_view_names)
            != len(set(self.selected_view_names))
        ):
            raise ValueError(
                "selected_view_names must contain unique non-empty names"
            )


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
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    return str(value)


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
            except BaseException:
                restored = False
            if not restored:
                residual.append(scene_index)
        if rollback_errors or residual:
            raise ProjectLinkDetachRecoveryError(
                detach_error,
                rollback_errors,
                residual,
            ) from detach_error
        raise
    return detached
