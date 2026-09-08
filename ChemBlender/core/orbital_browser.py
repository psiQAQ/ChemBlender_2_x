"""Orbital display metadata and computation estimates without Blender or GBasis."""

from dataclasses import dataclass
from math import isfinite
from uuid import UUID

from .model import DatasetStatus, Grid3D, OrbitalKind
from .wavefunction_grid import (
    DEFAULT_CHUNK_SIZE, _channel, _derivation_identity, grid_evaluation_memory,
)


@dataclass(frozen=True, slots=True)
class OrbitalRow:
    index: int
    energy: float | None
    occupation: float | None
    spin: str
    source: str
    labels: tuple[str, ...]
    cached_dataset_ids: tuple[UUID, ...]
    evaluation_error: str


def _numbers(array, count):
    import numpy

    if array is None:
        return (None,) * count
    if numpy.dtype(array.dtype).kind == "c":
        return (None,) * count
    return tuple(float(value) if isfinite(value) else None for value in array.values)


def orbital_rows(project, orbital_set, channel, *, grid_parameters=None):
    """Return zero-based rows; cache means current scientific Grid3D, not VDB."""
    import numpy

    selected = _channel(orbital_set, channel)
    count = selected.coefficients.shape[0]
    energies = _numbers(selected.energies, count)
    occupations = _numbers(selected.occupations, count)
    labels = [[] for _ in range(count)]
    error = ""
    if orbital_set.kind is OrbitalKind.GENERALIZED:
        error = "Generalized spinors are not supported"
    elif numpy.dtype(selected.coefficients.dtype).kind == "c":
        error = "Complex orbitals are not supported"
    maximum = 2 if channel == "restricted" else 1
    # Labels require actual occupations and energies; ordering is not evidence.
    integral = all(value is not None and value in range(maximum + 1)
                   for value in occupations)
    if not error and integral and all(value is not None for value in energies):
        occupied = [i for i, value in enumerate(occupations) if value > 0]
        virtual = [i for i, value in enumerate(occupations) if value == 0]
        for name, indices, choose in (("HOMO", occupied, max), ("LUMO", virtual, min)):
            if indices:
                frontier = choose(energies[i] for i in indices)
                for i in indices:
                    if energies[i] == frontier:
                        labels[i].append(name)
        if channel == "restricted":
            for i, value in enumerate(occupations):
                if value == 1:
                    labels[i].append("SOMO")
    sources = tuple(dict.fromkeys(
        record.source for item in orbital_set.provenance_ids
        if (record := project.provenance.get(item)) is not None and record.source
    ))
    source = "; ".join(sources) or "Source not recorded"
    structure = project.structures[orbital_set.structure_id]
    basis = project.basis_sets[orbital_set.basis_set_id]
    cached = [[] for _ in range(count)]
    for grid in project.datasets.values():
        if (not isinstance(grid, Grid3D) or grid.semantic_role != "molecular_orbital"
                or grid.status is not DatasetStatus.COMPLETE
                or grid.structure_id != structure.id):
            continue
        for provenance_id in grid.provenance_ids:
            record = project.provenance.get(provenance_id)
            if record is None or record.parent_ids != (structure.id, basis.id, orbital_set.id):
                continue
            params = dict(record.parameters)
            orbital_index = params.get("orbital_index")
            if (params.get("channel") != channel or type(orbital_index) is not int
                    or not 0 <= orbital_index < count):
                continue
            geometry = {"origin": grid.origin, "step_vectors": grid.step_vectors,
                        "shape": grid.grid_shape}
            if grid_parameters is not None and any(
                not numpy.array_equal(geometry[key], grid_parameters[key]) for key in geometry
            ):
                continue
            expected = _derivation_identity(structure, basis, orbital_set,
                "evaluate_molecular_orbital_grid",
                {**geometry, "channel": channel, "orbital_index": orbital_index})
            if grid.revision == expected:
                cached[orbital_index].append(grid.id)
                break
    return tuple(OrbitalRow(i, energies[i], occupations[i], channel, source,
                           tuple(labels[i]), tuple(cached[i]), error) for i in range(count))


def suggest_grid(structure, *, spacing=0.25, padding=6.0):
    """Suggest an axis-aligned Bohr grid enclosing the molecule and padding."""
    import numpy

    if structure.coordinates.unit != "bohr":
        raise ValueError("wavefunction grid coordinates must use bohr")
    if (isinstance(spacing, bool) or not isfinite(spacing) or spacing <= 0
            or isinstance(padding, bool) or not isfinite(padding) or padding < 0):
        raise ValueError("spacing must be positive and padding non-negative finite numbers")
    coordinates = numpy.asarray(structure.coordinates.values)
    if not coordinates.size or not numpy.isfinite(coordinates).all():
        raise ValueError("structure must have finite atomic coordinates")
    lower = numpy.floor((coordinates.min(axis=0) - padding) / spacing) * spacing
    upper = numpy.ceil((coordinates.max(axis=0) + padding) / spacing) * spacing
    shape = tuple(int(round((high - low) / spacing)) + 1 for low, high in zip(lower, upper))
    return {"origin": tuple(float(value) for value in lower),
            "step_vectors": ((spacing, 0., 0.), (0., spacing, 0.), (0., 0., spacing)),
            "shape": shape}


def estimate_grid_memory(shape, basis_count, *, block_size=DEFAULT_CHUNK_SIZE,
                         operation="mo", orbital_count=None):
    """Use the evaluator's actual block limit and common-array memory estimate."""
    return grid_evaluation_memory(shape, basis_count, chunk_size=block_size,
                                  operation=operation, orbital_count=orbital_count)
