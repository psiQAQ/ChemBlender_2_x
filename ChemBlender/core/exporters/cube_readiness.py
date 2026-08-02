"""Pure representability checks for deterministic native Cube export."""

from dataclasses import dataclass
from enum import Enum

import numpy

from ..model import ArrayData, AtomicProperty, DatasetStatus, Grid3D


_LENGTH_UNITS = frozenset(("angstrom", "bohr"))
_REAL_KINDS = frozenset("iuf")


class CubeExportStatus(str, Enum):
    READY = "Ready"
    MISSING_ENTITY = "MissingEntity"
    MISSING_SELECTION = "MissingSelection"
    AMBIGUOUS = "Ambiguous"
    INVALID = "Invalid"
    UNSUPPORTED_UNIT = "UnsupportedUnit"


@dataclass(frozen=True, slots=True)
class CubeExportReadiness:
    status: CubeExportStatus
    tokens: tuple[str, ...]


def _entities(project_entities, name):
    values = getattr(project_entities, name)
    return tuple(values.values() if isinstance(values, dict) else values)


def _real_finite(data, expected_shape, *, dataset_index=None):
    if not isinstance(data, ArrayData) or data.shape != expected_shape:
        return False
    live = data.values
    was_unloaded = getattr(live, "loaded", None) is False
    primary = None
    try:
        try:
            values = numpy.asarray(live)
            if (
                values.shape != expected_shape
                or numpy.dtype(data.dtype).kind not in _REAL_KINDS
                or values.dtype.kind not in _REAL_KINDS
                or numpy.dtype(data.dtype) != values.dtype
            ):
                return False
            selected = values if dataset_index is None else values[dataset_index]
            return bool(numpy.all(numpy.isfinite(selected)))
        except BaseException as error:
            primary = error
            raise
    finally:
        if was_unloaded:
            try:
                live.close()
            except BaseException as close_error:
                if primary is None:
                    raise
                primary.add_note(f"lazy Cube readiness array close failed: {close_error}")


def cube_export_readiness(project_entities, *, dataset_index=None):
    """Return deterministic Cube export readiness without serializing."""
    structures = _entities(project_entities, "structures")
    datasets = _entities(project_entities, "datasets")
    grids = tuple(value for value in datasets if isinstance(value, Grid3D))
    issues = set()

    ids = tuple(value.id for value in (*structures, *datasets))
    if len(ids) != len(set(ids)):
        issues.add("entity.uuid.duplicate")

    grid = None
    if not grids:
        issues.add("grid.missing")
    elif len(grids) > 1:
        issues.add("grid.ambiguous")
    else:
        grid = grids[0]

    structure = None
    if grid is not None:
        linked = tuple(
            value for value in structures if value.id == grid.structure_id
        )
        if not linked:
            issues.add("structure.missing")
        elif len(linked) > 1:
            issues.add("structure.ambiguous")
        else:
            structure = linked[0]

    if structure is not None:
        atom_count = len(structure.atomic_numbers)
        if atom_count == 0:
            issues.add("structure.atom_count")
        if structure.coordinates.unit not in _LENGTH_UNITS:
            issues.add("structure.coordinates.unit")
        if (
            structure.coordinates.dims != ("atom", "xyz")
            or not _real_finite(
                structure.coordinates,
                (atom_count, 3),
            )
        ):
            issues.add("structure.coordinates")

        charges = tuple(
            value
            for value in datasets
            if isinstance(value, AtomicProperty)
            and value.structure_id == structure.id
            and value.semantic_role == "nuclear_charge"
        )
        if not charges:
            issues.add("dataset.nuclear_charge.missing")
        elif len(charges) > 1:
            issues.add("dataset.nuclear_charge.ambiguous")
        else:
            charge = charges[0]
            if (
                charge.status is not DatasetStatus.COMPLETE
                or charge.domain != "atom"
                or charge.data.dims != ("atom",)
                or charge.data.unit != "elementary_charge"
                or not _real_finite(charge.data, (atom_count,))
            ):
                issues.add("dataset.nuclear_charge")

    if grid is not None:
        if grid.coordinate_unit not in _LENGTH_UNITS:
            issues.add("grid.coordinate_unit")
        if grid.data.dims == ("x", "y", "z"):
            selected_index = None
            if dataset_index is not None:
                issues.add("dataset_index.invalid")
        elif grid.data.dims == ("dataset", "x", "y", "z"):
            selected_index = dataset_index
            if dataset_index is None:
                issues.add("dataset_index.missing")
            elif (
                type(dataset_index) is not int
                or not 0 <= dataset_index < grid.data.shape[0]
            ):
                issues.add("dataset_index.invalid")
                selected_index = None
        else:
            issues.add("grid.leading_dims")
            selected_index = None

        if not {
            "dataset_index.invalid",
            "dataset_index.missing",
            "grid.leading_dims",
        }.intersection(issues) and not _real_finite(
            grid.data,
            grid.data.shape,
            dataset_index=selected_index,
        ):
            issues.add("grid.data")

    tokens = tuple(sorted(issues))
    status = (
        CubeExportStatus.AMBIGUOUS
        if any(
            token.endswith(".ambiguous") or token == "entity.uuid.duplicate"
            for token in tokens
        )
        else CubeExportStatus.MISSING_ENTITY
        if any(
            token.endswith(".missing") and token != "dataset_index.missing"
            for token in tokens
        )
        else CubeExportStatus.MISSING_SELECTION
        if "dataset_index.missing" in tokens
        else CubeExportStatus.UNSUPPORTED_UNIT
        if any(
            token in {"grid.coordinate_unit", "structure.coordinates.unit"}
            for token in tokens
        )
        else CubeExportStatus.INVALID
        if tokens
        else CubeExportStatus.READY
    )
    return CubeExportReadiness(status, tokens)


__all__ = (
    "CubeExportReadiness",
    "CubeExportStatus",
    "cube_export_readiness",
)
