from itertools import product
from math import ceil

from ..model import QualityStatus, Structure
from ..model.molecular_topology import canonical_topology_edge
from .infer import (
    _ANGSTROM_SCALE,
    _NEIGHBOR_OFFSETS,
    _inference_batch,
    _invalid_duplicate_batch,
    _settings_parameters,
    TopologyInferenceSettings,
)
from .radii import covalent_radius_angstrom

def infer_periodic_topology(structure, settings=None):
    import numpy

    if not isinstance(structure, Structure) or structure.periodic is None:
        raise TypeError("structure must be a periodic Structure")
    if settings is None:
        settings = TopologyInferenceSettings(periodic=True)
    if not isinstance(settings, TopologyInferenceSettings):
        raise TypeError("settings must be TopologyInferenceSettings")
    if not settings.periodic:
        raise ValueError("periodic topology inference requires periodic=True")

    scale = _ANGSTROM_SCALE[structure.coordinates.unit]
    coordinates = numpy.asarray(structure.coordinates.values, dtype=float) * scale
    cell = numpy.asarray(structure.cell.values, dtype=float) * scale
    if not numpy.all(numpy.isfinite(coordinates)):
        raise ValueError("structure coordinates must be finite")
    inverse_cell = numpy.linalg.inv(cell)
    fractional = coordinates @ inverse_cell
    condition = float(
        numpy.linalg.norm(cell, ord=numpy.inf)
        * numpy.linalg.norm(inverse_cell, ord=numpy.inf)
    )
    # Three-term dot products plus a 3x3 inverse stay within this
    # condition-scaled floating-point uncertainty.
    roundoff_factor = (
        8.0 * numpy.finfo(fractional.dtype).eps * max(1.0, condition)
    )
    for axis, periodic in enumerate(structure.periodic.pbc):
        if periodic:
            column = fractional[:, axis]
            nearest = numpy.rint(column)
            roundoff = roundoff_factor * numpy.maximum(1.0, numpy.abs(column))
            column[:] = numpy.where(
                numpy.abs(column - nearest) <= roundoff,
                nearest,
                column,
            )
            column -= numpy.floor(column)
    coordinates = fractional @ cell
    radii = numpy.fromiter(
        (covalent_radius_angstrom(number) for number in structure.atomic_numbers),
        dtype=float,
        count=len(structure.atomic_numbers),
    )
    largest_radius = float(radii.max(initial=0.0))
    maximum_cutoff = (
        2.0 * largest_radius * settings.covalent_scale
        + settings.tolerance_angstrom
    )
    cell_width = max(maximum_cutoff, settings.minimum_distance_angstrom)
    image_limits = tuple(
        (
            max(
                1,
                ceil(
                    maximum_cutoff
                    * float(numpy.linalg.norm(inverse_cell[:, axis]))
                ),
            )
            if periodic
            else 0
        )
        for axis, periodic in enumerate(structure.periodic.pbc)
    )
    shift_ranges = tuple(
        range(-limit, limit + 1) if periodic else (0,)
        for limit, periodic in zip(image_limits, structure.periodic.pbc)
    )

    image_cells = {}
    for shift in product(*shift_ranges):
        translation = numpy.asarray(shift, dtype=float) @ cell
        for right, coordinate in enumerate(coordinates):
            image_coordinate = coordinate + translation
            key = tuple(
                map(int, numpy.floor(image_coordinate / cell_width))
            )
            image_cells.setdefault(key, []).append((right, shift))

    candidates = {}
    for left, coordinate in enumerate(coordinates):
        cell_key = tuple(map(int, numpy.floor(coordinate / cell_width)))
        for offset in _NEIGHBOR_OFFSETS:
            neighbor_key = tuple(
                cell_key[axis] + offset[axis] for axis in range(3)
            )
            for right, shift in image_cells.get(neighbor_key, ()):
                if left == right and shift == (0, 0, 0):
                    continue
                displacement = (
                    coordinates[right]
                    + numpy.asarray(shift, dtype=float) @ cell
                    - coordinate
                )
                distance = float(numpy.linalg.norm(displacement))
                if distance < settings.minimum_distance_angstrom:
                    return _invalid_duplicate_batch(
                        structure,
                        settings,
                        left,
                        right,
                        distance,
                    )
                if radii[left] <= 0.0 or radii[right] <= 0.0:
                    continue
                cutoff = (
                    (radii[left] + radii[right]) * settings.covalent_scale
                    + settings.tolerance_angstrom
                )
                if distance <= cutoff:
                    edge = canonical_topology_edge(left, right, shift)
                    candidates[edge] = min(distance, candidates.get(edge, distance))

    coordination = [0] * len(structure.atomic_numbers)
    selected = []
    ordered = sorted(
        (
            (distance, left, right, shift)
            for (left, right, shift), distance in candidates.items()
        ),
        key=lambda item: (item[0], item[1], item[2], item[3]),
    )
    for _distance, left, right, shift in ordered:
        left_increment = 2 if left == right else 1
        if (
            coordination[left] + left_increment
            > settings.max_coordination_default
            or (
                left != right
                and coordination[right] + 1
                > settings.max_coordination_default
            )
        ):
            continue
        coordination[left] += left_increment
        if left != right:
            coordination[right] += 1
        selected.append((left, right, shift))
    selected.sort(key=lambda item: (item[0], item[1], item[2]))

    edges = tuple((left, right) for left, right, _shift in selected)
    shifts = tuple(shift for _left, _right, shift in selected)
    parameters = tuple(
        sorted(
            _settings_parameters(settings, structure)
            + (
                (
                    "fractional_normalization",
                    "cartesian_pbc_modulo_one",
                ),
                ("pbc", structure.periodic.pbc),
            )
        )
    )
    return _inference_batch(
        structure,
        parameters=parameters,
        edges=edges,
        orders=(0.0,) * len(edges),
        quality_status=QualityStatus.AMBIGUOUS,
        operation="infer_periodic_topology",
        bond_lattice_shifts=shifts,
    )
