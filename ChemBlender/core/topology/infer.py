from dataclasses import dataclass
import hashlib
from itertools import product
import json
from math import isfinite
from uuid import NAMESPACE_URL, uuid5

from ..model import (
    ArrayData,
    ImportBatch,
    IssueKind,
    ParserIssue,
    ParserReport,
    ProvenanceRecord,
    QualityStatus,
    Structure,
    TopologyRecord,
    TopologySource,
)
from ..model.molecular_topology import canonical_topology_edge
from .radii import covalent_radius_angstrom, is_metal


INFERENCE_VERSION = "1"
_ANGSTROM_SCALE = {"angstrom": 1.0, "bohr": 0.529177210903}
_NEIGHBOR_OFFSETS = tuple(product((-1, 0, 1), repeat=3))


@dataclass(frozen=True, slots=True)
class TopologyInferenceSettings:
    covalent_scale: float = 1.15
    tolerance_angstrom: float = 0.20
    minimum_distance_angstrom: float = 0.25
    max_coordination_default: int = 8
    metal_mode: str = "coordination"
    periodic: bool = False

    def __post_init__(self):
        for name in (
            "covalent_scale",
            "tolerance_angstrom",
            "minimum_distance_angstrom",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or value <= 0.0
            ):
                raise ValueError(f"{name} must be a finite positive number")
        if (
            isinstance(self.max_coordination_default, bool)
            or not isinstance(self.max_coordination_default, int)
            or self.max_coordination_default <= 0
        ):
            raise ValueError("max_coordination_default must be a positive integer")
        if self.metal_mode not in {"coordination", "covalent"}:
            raise ValueError("metal_mode must be coordination or covalent")
        if type(self.periodic) is not bool:
            raise TypeError("periodic must be a bool")


def _settings_parameters(settings, structure):
    return (
        ("covalent_scale", float(settings.covalent_scale)),
        ("max_coordination_default", settings.max_coordination_default),
        ("metal_mode", settings.metal_mode),
        ("minimum_distance_angstrom", float(settings.minimum_distance_angstrom)),
        ("periodic", settings.periodic),
        ("radii_source", "ChemBlender.Chem_data.ELEMENTS_DEFAULT"),
        ("structure_revision", structure.revision),
        ("tolerance_angstrom", float(settings.tolerance_angstrom)),
    )


def _invalid_duplicate_batch(structure, settings, left, right, distance):
    issue = ParserIssue(
        kind=IssueKind.INVALID,
        path="structure.coordinates",
        message=(
            f"atoms {left} and {right} are {distance:.12g} angstrom apart, "
            "below minimum_distance_angstrom="
            f"{settings.minimum_distance_angstrom:.12g}"
        ),
    )
    return ImportBatch(
        report=ParserReport(
            reader_id="topology-distance",
            reader_version=INFERENCE_VERSION,
            created_entity_ids=(),
            parsed_capabilities=("topology",),
            issues=(issue,),
        )
    )


def _inference_batch(
    structure,
    *,
    parameters,
    edges,
    orders,
    quality_status,
    operation,
    bond_lattice_shifts=None,
):
    import numpy

    edges = tuple(edges)
    orders = tuple(orders)
    shifts = (
        ((0, 0, 0),) * len(edges)
        if bond_lattice_shifts is None
        else tuple(bond_lattice_shifts)
    )
    if len(orders) != len(edges) or len(shifts) != len(edges):
        raise ValueError("inferred topology bond arrays must have matching lengths")
    canonical = sorted(
        (
            canonical_topology_edge(left, right, shift),
            float(order),
        )
        for (left, right), shift, order in zip(edges, shifts, orders)
    )
    keys = tuple(key for key, _order in canonical)
    if len(set(keys)) != len(keys):
        raise ValueError("inferred topology edges must not repeat")
    edges = tuple(key[:2] for key in keys)
    orders = tuple(order for _key, order in canonical)
    if bond_lattice_shifts is not None:
        bond_lattice_shifts = tuple(key[2] for key in keys)
    identity = json.dumps(
        {
            "bond_lattice_shifts": bond_lattice_shifts,
            "edges": edges,
            "operation": operation,
            "orders": orders,
            "parameters": parameters,
            "structure_id": str(structure.id),
        },
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    revision = hashlib.sha256(identity).hexdigest()
    topology_id = uuid5(
        NAMESPACE_URL,
        f"chemblender:topology-distance:{INFERENCE_VERSION}:{revision}:topology",
    )
    provenance_id = uuid5(
        NAMESPACE_URL,
        f"chemblender:topology-distance:{INFERENCE_VERSION}:{revision}:provenance",
    )
    topology = TopologyRecord(
        id=topology_id,
        revision=revision,
        structure_id=structure.id,
        bond_indices=ArrayData(
            numpy.asarray(edges, dtype=numpy.int64).reshape((-1, 2)),
            ("bond", "endpoint"),
            "dimensionless",
        ),
        bond_orders=ArrayData(
            numpy.asarray(orders, dtype=float),
            ("bond",),
            "dimensionless",
        ),
        aromatic_flags=None,
        stereo_labels=("",) * len(edges),
        source_kind=TopologySource.DISTANCE_INFERRED,
        quality_status=quality_status,
        inference_parameters=parameters,
        provenance_ids=(provenance_id,),
        bond_lattice_shifts=(
            None
            if bond_lattice_shifts is None
            else ArrayData(
                numpy.asarray(bond_lattice_shifts, dtype=numpy.int64).reshape(
                    (-1, 3)
                ),
                ("bond", "xyz"),
                "dimensionless",
            )
        ),
    )
    provenance = ProvenanceRecord(
        id=provenance_id,
        revision=revision,
        producer="ChemBlender topology inference",
        producer_version=INFERENCE_VERSION,
        source="",
        source_hash=revision,
        parent_ids=(structure.id,),
        operation=operation,
        parameters=parameters,
    )
    return ImportBatch(
        topologies=(topology,),
        provenance=(provenance,),
        report=ParserReport(
            reader_id="topology-distance",
            reader_version=INFERENCE_VERSION,
            created_entity_ids=(topology.id, provenance.id),
            parsed_capabilities=("topology",),
            issues=(),
        ),
    )


def infer_distance_topology(structure, settings=None):
    import numpy

    if not isinstance(structure, Structure):
        raise TypeError("structure must be a Structure")
    if settings is None:
        settings = TopologyInferenceSettings()
    if not isinstance(settings, TopologyInferenceSettings):
        raise TypeError("settings must be TopologyInferenceSettings")
    if settings.periodic:
        raise ValueError("infer_distance_topology supports nonperiodic inference")
    try:
        scale = _ANGSTROM_SCALE[structure.coordinates.unit]
    except KeyError as error:
        raise ValueError("coordinates must use angstrom or bohr") from error

    coordinates = numpy.asarray(structure.coordinates.values, dtype=float) * scale
    if not numpy.all(numpy.isfinite(coordinates)):
        raise ValueError("structure coordinates must be finite")
    radii = numpy.fromiter(
        (covalent_radius_angstrom(number) for number in structure.atomic_numbers),
        dtype=float,
        count=len(structure.atomic_numbers),
    )
    largest_radius = float(radii.max(initial=0.0))
    cell_width = max(
        2.0 * largest_radius * settings.covalent_scale
        + settings.tolerance_angstrom,
        settings.minimum_distance_angstrom,
    )
    cells = {}
    atom_cells = numpy.floor(coordinates / cell_width).astype(numpy.int64)
    for index, cell in enumerate(atom_cells):
        cells.setdefault(tuple(map(int, cell)), []).append(index)

    candidates = []
    for left, cell in enumerate(atom_cells):
        cell_key = tuple(map(int, cell))
        for offset in _NEIGHBOR_OFFSETS:
            neighbor_key = tuple(
                cell_key[axis] + offset[axis] for axis in range(3)
            )
            for right in cells.get(neighbor_key, ()):
                if right <= left:
                    continue
                distance = float(
                    numpy.linalg.norm(coordinates[right] - coordinates[left])
                )
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
                    candidates.append((distance, left, right))

    coordination = [0] * len(structure.atomic_numbers)
    selected = []
    for distance, left, right in sorted(candidates):
        if (
            coordination[left] >= settings.max_coordination_default
            or coordination[right] >= settings.max_coordination_default
        ):
            continue
        coordination[left] += 1
        coordination[right] += 1
        selected.append((left, right, distance))
    selected.sort(key=lambda item: (item[0], item[1]))

    edges = tuple((left, right) for left, right, _distance in selected)
    metal_connections = tuple(
        is_metal(structure.atomic_numbers[left])
        or is_metal(structure.atomic_numbers[right])
        for left, right in edges
    )
    coordination_mode = settings.metal_mode == "coordination"
    orders = tuple(
        0.0 if coordination_mode and metal else 1.0
        for metal in metal_connections
    )
    parameters = _settings_parameters(settings, structure)
    return _inference_batch(
        structure,
        parameters=parameters,
        edges=edges,
        orders=orders,
        quality_status=(
            QualityStatus.AMBIGUOUS
            if coordination_mode and any(metal_connections)
            else QualityStatus.COMPLETE
        ),
        operation="infer_distance_topology",
    )
