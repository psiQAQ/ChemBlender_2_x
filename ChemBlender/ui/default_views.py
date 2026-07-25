"""Pure format-aware planning for default import views."""

from dataclasses import dataclass
from uuid import UUID

from ..core import DatasetStatus, Grid3D, SourceRevision


_SIGNED_SCALAR_ROLES = frozenset(
    {
        "electrostatic_potential",
        "molecular_orbital",
        "spin_density",
    }
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
        signed = (
            grid.status is DatasetStatus.COMPLETE
            and _signed_scalar(grid.semantic_role)
        )
        return DefaultViewPlan(
            source_revision.id,
            "signed_isosurface" if signed else "grid_volume",
            (("grid", grid.id),),
            (("dataset_index", 0),),
            "Signed Isosurface" if signed else "Grid Volume",
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
    "describe_default_view",
    "plan_default_view",
)
