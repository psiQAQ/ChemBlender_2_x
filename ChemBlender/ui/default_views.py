"""Pure format-aware planning for default import views."""

from dataclasses import dataclass
from uuid import UUID

from cbq_core.grid_semantics import builtin_grid_semantic_presets
from cbq_core.model import DatasetStatus
from cbq_core.model import Grid3D
from cbq_core.model import SourceRevision


_SIGNED_SCALAR_ROLES = frozenset(
    value.semantic_role for value in builtin_grid_semantic_presets().values() if value.default_surface_mode == "signed_isosurface"
)
_SUPPORTED_GRID_COORDINATE_UNITS = frozenset({"angstrom", "bohr"})


@dataclass(frozen=True, slots=True)
class DefaultViewPlan:
    source_revision_id: UUID
    preset_id: str
    bindings: tuple[tuple[str, UUID], ...]
    settings: tuple[tuple[str, object], ...]
    display_label: str


def _signed_scalar(role):
    return role in _SIGNED_SCALAR_ROLES or role.endswith("_spin_density")


def default_grid_preset(grid):
    """Choose from authoritative role/status metadata, without reading values."""
    signed = grid.status is DatasetStatus.COMPLETE and _signed_scalar(grid.semantic_role)
    return "signed_isosurface" if signed else "grid_volume"


def plan_default_view(source_revision, structures, datasets):
    if not isinstance(source_revision, SourceRevision):
        raise TypeError("source_revision must be a SourceRevision")
    entity_ids = source_revision.created_entity_ids
    grids = tuple(
        datasets[entity_id]
        for entity_id in entity_ids
        if (
            isinstance(datasets.get(entity_id), Grid3D)
            and datasets[entity_id].coordinate_unit
            in _SUPPORTED_GRID_COORDINATE_UNITS
        )
    )
    complete = tuple(
        grid for grid in grids if grid.status is DatasetStatus.COMPLETE
    )
    grid = next(
        (value for value in complete if _signed_scalar(value.semantic_role)),
        complete[0] if complete else (grids[0] if grids else None),
    )
    if grid is not None:
        preset_id = default_grid_preset(grid)
        return DefaultViewPlan(
            source_revision.id,
            preset_id,
            (("grid", grid.id),),
            (("dataset_index", 0),),
            "Signed Isosurface" if preset_id == "signed_isosurface" else "Grid Volume",
        )
    structure = next(
        (
            structures[entity_id]
            for entity_id in entity_ids
            if entity_id in structures
        ),
        None,
    )
    if structure is None:
        return None
    return DefaultViewPlan(
        source_revision.id,
        "structure_publication",
        (("structure", structure.id),),
        (),
        "Structure",
    )


def describe_default_view(plan):
    label = (
        plan.display_label
        if isinstance(plan, DefaultViewPlan)
        else "No supported visual data"
    )
    return f"Default view: {label}"


__all__ = (
    "DefaultViewPlan",
    "default_grid_preset",
    "describe_default_view",
    "plan_default_view",
)
