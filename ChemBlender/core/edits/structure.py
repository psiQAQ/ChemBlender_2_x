"""Scientific Structure edit preview and derivation."""

from dataclasses import dataclass, replace
import hashlib
import json
from uuid import NAMESPACE_URL, UUID, uuid5

from ..model import (
    ArrayData,
    ImportBatch,
    IssueKind,
    ParserIssue,
    ParserReport,
    ProvenanceRecord,
    QCProject,
    QualityStatus,
    Structure,
    TopologyRecord,
    TopologySource,
)
from ..model.molecular_topology import canonical_topology_edge


EDIT_VERSION = "1"
_ANGSTROM_SCALE = {"angstrom": 1.0, "bohr": 0.529177210903}
_TOLERANCE_ANGSTROM = 1.0e-6


@dataclass(frozen=True, slots=True)
class StructureEditPreview:
    atom_count_before: int
    atom_count_after: int
    coordinate_change_count: int
    element_change_count: int
    bond_added_count: int
    bond_removed_count: int
    bond_order_change_count: int
    cell_changed: bool
    max_displacement_angstrom: float
    affected_result_ids: tuple[UUID, ...]

    @property
    def affected_dataset_ids(self):
        """Compatibility name for early Wave 1 callers."""
        return self.affected_result_ids

    @property
    def has_changes(self):
        return any(
            (
                self.atom_count_before != self.atom_count_after,
                self.coordinate_change_count,
                self.element_change_count,
                self.bond_added_count,
                self.bond_removed_count,
                self.bond_order_change_count,
                self.cell_changed,
            )
        )


def _length_values(value, dims, shape, name):
    import numpy

    if not isinstance(value, ArrayData):
        raise TypeError(f"{name} must be ArrayData")
    if value.dims != dims or value.shape != shape:
        raise ValueError(f"{name} must have dims {dims} and shape {shape}")
    try:
        scale = _ANGSTROM_SCALE[value.unit]
    except KeyError as error:
        raise ValueError(f"{name} must use angstrom or bohr") from error
    values = numpy.asarray(value.values, dtype=float)
    if numpy.iscomplexobj(values) or not numpy.all(numpy.isfinite(values)):
        raise ValueError(f"{name} must contain finite real values")
    return values * scale


def _atomic_numbers(values):
    values = tuple(values)
    if any(
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= 118
        for value in values
    ):
        raise ValueError("atomic_numbers must contain integers from 0 to 118")
    return values


def _source_atom_indices(values, source_count, edited_count):
    if values is None:
        return tuple(
            index if index < source_count else None
            for index in range(edited_count)
        )
    values = tuple(values)
    if len(values) != edited_count:
        raise ValueError(
            "source_atom_indices must contain one value per edited atom"
        )
    if any(
        value is not None
        and (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 0 <= value < source_count
        )
        for value in values
    ):
        raise ValueError(
            "source_atom_indices must contain source indices or None"
        )
    retained = tuple(value for value in values if value is not None)
    if len(retained) != len(set(retained)):
        raise ValueError("source_atom_indices must not repeat source atoms")
    return values


def _bond_map(indices, orders, shifts, atom_count, name):
    import numpy

    if indices is None or orders is None:
        if indices is not None or orders is not None or shifts is not None:
            raise ValueError(
                f"{name} bond_indices and bond_orders must both be provided"
            )
        return None
    if not isinstance(indices, ArrayData) or not isinstance(orders, ArrayData):
        raise TypeError(f"{name} bonds must be ArrayData")
    raw_indices = numpy.asarray(indices.values)
    raw_orders = numpy.asarray(orders.values)
    if (
        indices.dims != ("bond", "endpoint")
        or len(indices.shape) != 2
        or indices.shape[1] != 2
        or indices.unit != "dimensionless"
        or raw_indices.dtype.kind not in "iu"
    ):
        raise ValueError(f"{name} bond_indices must contain integer pairs")
    if (
        orders.dims != ("bond",)
        or orders.shape != (indices.shape[0],)
        or orders.unit != "dimensionless"
        or raw_orders.dtype.kind not in "iuf"
        or not numpy.all(numpy.isfinite(raw_orders))
        or numpy.any(raw_orders < 0.0)
    ):
        raise ValueError(f"{name} bond_orders must contain non-negative values")
    if raw_indices.size and (
        numpy.any(raw_indices < 0) or int(raw_indices.max()) >= atom_count
    ):
        raise ValueError(f"{name} bond index is outside the edited structure")
    if shifts is None:
        raw_shifts = numpy.zeros((len(raw_indices), 3), dtype=int)
    else:
        if not isinstance(shifts, ArrayData):
            raise TypeError(f"{name} bond_lattice_shifts must be ArrayData")
        raw_shifts = numpy.asarray(shifts.values)
        if (
            shifts.dims != ("bond", "xyz")
            or shifts.shape != (indices.shape[0], 3)
            or shifts.unit != "dimensionless"
            or raw_shifts.dtype.kind not in "iu"
        ):
            raise ValueError(
                f"{name} bond_lattice_shifts must contain integer xyz values"
            )
    result = {}
    for endpoints, order, shift in zip(
        raw_indices.tolist(),
        raw_orders.tolist(),
        raw_shifts.tolist(),
    ):
        left, right = map(int, endpoints)
        shift = tuple(map(int, shift))
        try:
            key = canonical_topology_edge(left, right, shift)
        except ValueError as error:
            raise ValueError(f"{name} {error}") from error
        if key in result:
            raise ValueError(f"{name} bonds must not repeat")
        result[key] = float(order)
    return result


def _source_bonds(topology, atom_count):
    if topology is None:
        return None
    return _bond_map(
        topology.bond_indices,
        topology.bond_orders,
        topology.bond_lattice_shifts,
        atom_count,
        "source",
    )


def _edit_values(
    source,
    source_topology,
    *,
    atomic_numbers,
    coordinates,
    bond_indices,
    bond_orders,
    cell,
    bond_lattice_shifts,
    source_atom_indices,
):
    import numpy

    numbers = _atomic_numbers(atomic_numbers)
    atom_indices = _source_atom_indices(
        source_atom_indices,
        len(source.atomic_numbers),
        len(numbers),
    )
    edited_coordinates = _length_values(
        coordinates,
        ("atom", "xyz"),
        (len(numbers), 3),
        "coordinates",
    )
    edited_cell = (
        None
        if cell is None
        else _length_values(
            cell,
            ("cell_vector", "xyz"),
            (3, 3),
            "cell",
        )
    )
    if edited_cell is not None and abs(float(numpy.linalg.det(edited_cell))) < 1e-12:
        raise ValueError("cell must be non-singular")
    edited_bonds = _bond_map(
        bond_indices,
        bond_orders,
        bond_lattice_shifts,
        len(numbers),
        "edited",
    )
    source_coordinates = _length_values(
        source.coordinates,
        ("atom", "xyz"),
        (len(source.atomic_numbers), 3),
        "source coordinates",
    )
    source_cell = (
        None
        if source.cell is None
        else _length_values(
            source.cell,
            ("cell_vector", "xyz"),
            (3, 3),
            "source cell",
        )
    )
    return (
        numbers,
        edited_coordinates,
        edited_cell,
        edited_bonds,
        source_coordinates,
        source_cell,
        _source_bonds(source_topology, len(source.atomic_numbers)),
        atom_indices,
    )


def _affected_result_ids(project, structure_id):
    linked = {
        entity.id
        for registry in (
            project.datasets,
            project.basis_sets,
            project.orbital_sets,
            project.density_matrices,
        )
        for entity in registry.values()
        if getattr(entity, "structure_id", None) == structure_id
    }
    linked.update(
        result.id
        for result in project.symmetry_results.values()
        if structure_id
        in (result.structure_id, result.standardized_structure_id)
    )
    linked.update(
        calculation.id
        for calculation in project.calculations.values()
        if structure_id
        in (
            *calculation.input_structure_ids,
            *calculation.result_structure_ids,
        )
    )
    return tuple(sorted(linked, key=str))


def preview_structure_edits(
    project,
    source,
    source_topology=None,
    *,
    atomic_numbers,
    coordinates,
    bond_indices=None,
    bond_orders=None,
    cell=None,
    bond_lattice_shifts=None,
    source_atom_indices=None,
):
    import numpy

    if not isinstance(project, QCProject):
        raise TypeError("project must be a QCProject")
    if not isinstance(source, Structure):
        raise TypeError("source must be a Structure")
    if project.structures.get(source.id) is not source:
        raise ValueError("source must be the current project Structure")
    if source_topology is not None:
        if not isinstance(source_topology, TopologyRecord):
            raise TypeError("source_topology must be a TopologyRecord or None")
        if (
            project.topologies.get(source_topology.id) is not source_topology
            or source_topology.structure_id != source.id
        ):
            raise ValueError(
                "source_topology must belong to the current project Structure"
            )
    (
        numbers,
        edited_coordinates,
        edited_cell,
        edited_bonds,
        source_coordinates,
        source_cell,
        source_bonds,
        atom_indices,
    ) = _edit_values(
        source,
        source_topology,
        atomic_numbers=atomic_numbers,
        coordinates=coordinates,
        bond_indices=bond_indices,
        bond_orders=bond_orders,
        cell=cell,
        bond_lattice_shifts=bond_lattice_shifts,
        source_atom_indices=source_atom_indices,
    )
    displacements = numpy.asarray(
        [
            numpy.linalg.norm(
                edited_coordinates[index] - source_coordinates[source_index]
            )
            for index, source_index in enumerate(atom_indices)
            if source_index is not None
        ],
        dtype=float,
    )
    coordinate_changes = int(
        numpy.count_nonzero(displacements > _TOLERANCE_ANGSTROM)
    )
    source_bonds = {} if source_bonds is None else source_bonds
    edited_bonds = {} if edited_bonds is None else edited_bonds
    common_bonds = set(source_bonds).intersection(edited_bonds)
    order_changes = sum(
        abs(source_bonds[key] - edited_bonds[key]) > 1.0e-12
        for key in common_bonds
    )
    return StructureEditPreview(
        atom_count_before=len(source.atomic_numbers),
        atom_count_after=len(numbers),
        coordinate_change_count=coordinate_changes,
        element_change_count=sum(
            source.atomic_numbers[source_index] != numbers[index]
            for index, source_index in enumerate(atom_indices)
            if source_index is not None
        ),
        bond_added_count=len(set(edited_bonds) - set(source_bonds)),
        bond_removed_count=len(set(source_bonds) - set(edited_bonds)),
        bond_order_change_count=order_changes,
        cell_changed=(
            source_cell is None
            and edited_cell is not None
            or source_cell is not None
            and edited_cell is None
            or source_cell is not None
            and edited_cell is not None
            and not numpy.allclose(
                source_cell,
                edited_cell,
                rtol=0.0,
                atol=_TOLERANCE_ANGSTROM,
            )
        ),
        max_displacement_angstrom=(
            0.0 if not len(displacements) else float(displacements.max())
        ),
        affected_result_ids=_affected_result_ids(project, source.id),
    )


def _canonical_identity(source, source_topology, values):
    numbers, coordinates, cell, bonds, *_unused, atom_indices = values
    document = {
        "atomic_numbers": numbers,
        "bonds": (
            None
            if bonds is None
            else [
                [left, right, list(shift), order]
                for (left, right, shift), order in sorted(bonds.items())
            ]
        ),
        "cell_angstrom": None if cell is None else cell.tolist(),
        "coordinates_angstrom": coordinates.tolist(),
        "source_revision": source.revision,
        "source_atom_indices": atom_indices,
        "source_structure_id": str(source.id),
        "source_topology": (
            None
            if source_topology is None
            else [str(source_topology.id), source_topology.revision]
        ),
        "version": EDIT_VERSION,
    }
    encoded = json.dumps(
        document,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _derived_periodic(source, coordinates, cell):
    import numpy

    if source.periodic is None:
        return None
    if len(coordinates) != len(source.atomic_numbers):
        raise ValueError(
            "periodic atom-count edits require explicit periodic site metadata"
        )
    if cell is None:
        raise ValueError("periodic Structure edits require a cell")
    fractional = coordinates @ numpy.linalg.inv(cell)
    return replace(
        source.periodic,
        fractional_coordinates=ArrayData(
            fractional,
            ("atom", "xyz"),
            "dimensionless",
        ),
    )


def _derived_topology(
    topology_id,
    revision,
    structure_id,
    bonds,
    source_topology,
    provenance_id,
    source_atom_indices,
):
    import numpy

    if bonds is None:
        return None
    items = sorted(bonds.items())
    if source_topology is None:
        source_map = {}
    else:
        source_indices = numpy.asarray(source_topology.bond_indices.values)
        source_atom_count = (
            0 if not source_indices.size else int(source_indices.max()) + 1
        )
        source_map = _source_bonds(source_topology, source_atom_count)
    source_keys = tuple(source_map)
    aromatic_source = (
        ()
        if source_topology is None or source_topology.aromatic_flags is None
        else tuple(bool(value) for value in source_topology.aromatic_flags.values)
    )
    label_source = (
        () if source_topology is None else source_topology.stereo_labels
    )
    aromatic_by_key = {
        key: aromatic_source[index]
        for index, key in enumerate(source_keys)
        if index < len(aromatic_source)
    }
    label_by_key = {
        key: label_source[index]
        for index, key in enumerate(source_keys)
        if index < len(label_source)
    }
    def source_key(key):
        left = source_atom_indices[key[0]]
        right = source_atom_indices[key[1]]
        if left is None or right is None:
            return None
        shift = key[2]
        return canonical_topology_edge(left, right, shift)

    return TopologyRecord(
        id=topology_id,
        revision=revision,
        structure_id=structure_id,
        bond_indices=ArrayData(
            numpy.asarray(
                [(key[0], key[1]) for key, _order in items],
                dtype=numpy.int64,
            ).reshape((-1, 2)),
            ("bond", "endpoint"),
            "dimensionless",
        ),
        bond_orders=ArrayData(
            numpy.asarray([order for _key, order in items], dtype=float),
            ("bond",),
            "dimensionless",
        ),
        aromatic_flags=ArrayData(
            numpy.asarray(
                [
                    aromatic_by_key.get(source_key(key), False)
                    for key, _order in items
                ],
                dtype=bool,
            ),
            ("bond",),
            "dimensionless",
        ),
        stereo_labels=tuple(
            label_by_key.get(source_key(key), "") for key, _order in items
        ),
        source_kind=TopologySource.USER_EDITED,
        quality_status=(
            QualityStatus.COMPLETE
            if all(order > 0.0 for _key, order in items)
            else QualityStatus.PARTIAL
        ),
        inference_parameters=(),
        provenance_ids=(provenance_id,),
        bond_lattice_shifts=ArrayData(
            numpy.asarray(
                [key[2] for key, _order in items],
                dtype=numpy.int64,
            ).reshape((-1, 3)),
            ("bond", "xyz"),
            "dimensionless",
        ),
    )


def commit_structure_edits(
    project,
    source,
    source_topology=None,
    *,
    atomic_numbers,
    coordinates,
    bond_indices=None,
    bond_orders=None,
    cell=None,
    bond_lattice_shifts=None,
    source_atom_indices=None,
):
    import numpy

    arguments = {
        "atomic_numbers": atomic_numbers,
        "coordinates": coordinates,
        "bond_indices": bond_indices,
        "bond_orders": bond_orders,
        "cell": cell,
        "bond_lattice_shifts": bond_lattice_shifts,
        "source_atom_indices": source_atom_indices,
    }
    preview = preview_structure_edits(
        project,
        source,
        source_topology,
        **arguments,
    )
    if not preview.has_changes:
        raise ValueError("no scientific edits were detected")
    values = _edit_values(
        source,
        source_topology,
        **arguments,
    )
    numbers, edited_coordinates, edited_cell, edited_bonds, *_unused = values
    revision = _canonical_identity(source, source_topology, values)
    structure_id = uuid5(
        NAMESPACE_URL,
        f"chemblender:scientific-edit:{EDIT_VERSION}:{revision}:structure",
    )
    topology_id = uuid5(
        NAMESPACE_URL,
        f"chemblender:scientific-edit:{EDIT_VERSION}:{revision}:topology",
    )
    provenance_id = uuid5(
        NAMESPACE_URL,
        f"chemblender:scientific-edit:{EDIT_VERSION}:{revision}:provenance",
    )
    topology = _derived_topology(
        topology_id,
        revision,
        structure_id,
        edited_bonds,
        source_topology,
        provenance_id,
        values[-1],
    )
    derived = Structure(
        id=structure_id,
        revision=revision,
        atomic_numbers=numbers,
        coordinates=ArrayData(
            numpy.asarray(edited_coordinates, dtype=float),
            ("atom", "xyz"),
            "angstrom",
        ),
        cell=(
            None
            if edited_cell is None
            else ArrayData(
                numpy.asarray(edited_cell, dtype=float),
                ("cell_vector", "xyz"),
                "angstrom",
            )
        ),
        periodic=_derived_periodic(
            source,
            edited_coordinates,
            edited_cell,
        ),
        molecular_charge=(
            source.molecular_charge
            if numbers == source.atomic_numbers
            else None
        ),
        molecular_multiplicity=(
            source.molecular_multiplicity
            if numbers == source.atomic_numbers
            else None
        ),
        topology_ids=(() if topology is None else (topology.id,)),
    )
    parameters = (
        ("affected_result_count", len(preview.affected_result_ids)),
        ("atom_count_after", preview.atom_count_after),
        ("atom_count_before", preview.atom_count_before),
        ("cell_changed", preview.cell_changed),
        ("coordinate_change_count", preview.coordinate_change_count),
        ("element_change_count", preview.element_change_count),
        (
            "source_atom_indices",
            tuple(-1 if value is None else value for value in values[-1]),
        ),
    )
    provenance = ProvenanceRecord(
        id=provenance_id,
        revision=revision,
        producer="ChemBlender scientific edit",
        producer_version=EDIT_VERSION,
        source="",
        source_hash=revision,
        parent_ids=(
            source.id,
            *((source_topology.id,) if source_topology is not None else ()),
        ),
        operation="scientific_edit",
        parameters=parameters,
    )
    issues = (
        (
            ParserIssue(
                kind=IssueKind.WARNING,
                path="structure.linked_results",
                message=(
                    f"{len(preview.affected_result_ids)} source-linked result "
                    "record(s) were not inherited by the derived Structure"
                ),
            ),
        )
        if preview.affected_result_ids
        else ()
    )
    created_ids = (
        derived.id,
        *((topology.id,) if topology is not None else ()),
        provenance.id,
    )
    return ImportBatch(
        structures=(derived,),
        topologies=(() if topology is None else (topology,)),
        provenance=(provenance,),
        report=ParserReport(
            reader_id="scientific-edit",
            reader_version=EDIT_VERSION,
            created_entity_ids=created_ids,
            parsed_capabilities=(
                "structure",
                *(("topology",) if topology is not None else ()),
            ),
            issues=issues,
        ),
    )


__all__ = (
    "StructureEditPreview",
    "commit_structure_edits",
    "preview_structure_edits",
)
