"""Deterministic normalized MOL2 export from authoritative core entities."""

from dataclasses import dataclass
import math

import numpy

from ..formats.mol2 import (
    _ELEMENT_NUMBERS,
    _element_from_type,
    iter_mol2_records,
    parse_mol2_record,
)
from ..model import (
    AtomicProperty,
    CategoricalData,
    DatasetStatus,
    MolecularRecord,
    QualityStatus,
)
from .mol2_readiness import (
    Mol2ExportStatus,
    _entities,
    mol2_export_readiness,
)
from .rdkit_molecular import MolecularExport, _categories, _values
from .xyz import (
    ExportCancelled,
    ExportReport,
    ExportReportEntry,
    _cancelled,
    atomic_write_chunks,
)


_RAW_LOSS_MESSAGES = {
    "source_atom_ids_renumbered": "source atom IDs are normalized to 1..N",
    "source_bond_ids_renumbered": "source bond IDs are normalized to 1..N",
    "molecule_status_bits_omitted": "molecule status bits are omitted",
    "molecule_comments_omitted": "molecule comments are omitted",
    "atom_status_bits_omitted": "atom status bits are omitted",
    "substructure_fields_omitted": "non-canonical substructure fields are omitted",
    "unknown_sections_omitted": "unknown MOL2 sections are omitted",
}


@dataclass(frozen=True, slots=True)
class _Mol2Entry:
    structure: object
    topology: object
    record: MolecularRecord | None
    molecule_type: object | None
    charge_type: object | None
    atom_type: AtomicProperty
    substructure_id: AtomicProperty | None
    substructure_name: AtomicProperty | None
    partial_charge: AtomicProperty | None


def _one(values):
    values = tuple(values)
    return values[0] if len(values) == 1 else None


def _ordered_entries(project_entities):
    structures = _entities(project_entities, "structures")
    topologies = _entities(project_entities, "topologies")
    records = _entities(project_entities, "molecular_records")
    annotations = _entities(project_entities, "annotations")
    datasets = _entities(project_entities, "datasets")
    entries = []
    for structure in structures:
        topology = _one(
            value
            for value in topologies
            if value.id in structure.topology_ids
            and value.structure_id == structure.id
            and value.quality_status is QualityStatus.COMPLETE
        )
        if topology is None:
            raise ValueError("MOL2 export requires one selected complete topology")
        record = _one(
            value
            for value in records
            if value.structure_id == structure.id
            and value.topology_id == topology.id
        )
        annotation = lambda key: _one(
            value
            for value in annotations
            if value.target_entity_id == structure.id
            and value.namespace == "tripos"
            and value.key == key
        )
        property_value = lambda role: _one(
            value
            for value in datasets
            if isinstance(value, AtomicProperty)
            and value.structure_id == structure.id
            and value.semantic_role == role
        )
        atom_type = property_value("atom_type")
        if atom_type is None:
            raise ValueError("MOL2 export requires one atom_type property")
        charge_type = annotation("charge_type")
        entries.append(
            _Mol2Entry(
                structure,
                topology,
                record,
                annotation("molecule_type"),
                charge_type,
                atom_type,
                property_value("substructure_id"),
                property_value("substructure_name"),
                (
                    None
                    if charge_type is not None
                    and charge_type.value == "NO_CHARGES"
                    else property_value("partial_charge")
                ),
            )
        )
    return tuple(
        sorted(
            entries,
            key=lambda entry: (
                0 if entry.record is None else entry.record.source_record_index,
                "" if entry.record is None else entry.record.record_key,
                str(entry.structure.id),
            ),
        )
    )


def _parsed_raw(record):
    if record is None:
        return None
    records = tuple(iter_mol2_records(record.raw_block))
    if len(records) != 1:
        raise ValueError("bound MolecularRecord must contain exactly one MOL2 record")
    return parse_mol2_record(records[0])


def _raw_loss_entries(entries):
    codes = set()
    for entry in entries:
        parsed = _parsed_raw(entry.record)
        if parsed is None:
            continue
        if tuple(atom.atom_id for atom in parsed.atoms) != tuple(
            range(1, len(parsed.atoms) + 1)
        ):
            codes.add("source_atom_ids_renumbered")
        if tuple(bond.bond_id for bond in parsed.bonds) != tuple(
            range(1, len(parsed.bonds) + 1)
        ):
            codes.add("source_bond_ids_renumbered")
        if parsed.status_bits is not None:
            codes.add("molecule_status_bits_omitted")
        if parsed.comment_lines:
            codes.add("molecule_comments_omitted")
        if any(atom.status_bits is not None for atom in parsed.atoms):
            codes.add("atom_status_bits_omitted")
        if any(
            len(value.raw_fields) != 4
            or (value.substructure_type or "").upper() != "GROUP"
            for value in parsed.substructures
        ):
            codes.add("substructure_fields_omitted")
        if parsed.unknown_sections:
            codes.add("unknown_sections_omitted")
    return tuple(
        ExportReportEntry(code, _RAW_LOSS_MESSAGES[code]) for code in sorted(codes)
    )


def preview_mol2_export(project_entities):
    readiness = mol2_export_readiness(project_entities)
    if readiness.status is Mol2ExportStatus.UNSUPPORTED:
        raise ValueError(
            "MOL2 export is unsupported: " + ", ".join(readiness.missing_fields)
        )
    entries = _ordered_entries(project_entities)
    report_entries = tuple(
        ExportReportEntry(
            f"missing:{token}",
            f"MOL2 field is missing: {token}",
        )
        for token in readiness.missing_fields
    ) + _raw_loss_entries(entries)
    report_entries = tuple(
        sorted(
            set(report_entries),
            key=lambda entry: (entry.code, entry.message),
        )
    )
    return ExportReport(
        "mol2",
        False,
        len(entries),
        bool(report_entries),
        report_entries,
    )


def _token(value, name):
    if not isinstance(value, str) or not value or any(
        character.isspace() for character in value
    ):
        raise ValueError(f"MOL2 {name} must be one non-empty token")
    return value


def _title(value):
    if not isinstance(value, str) or not value or "\n" in value or "\r" in value:
        raise ValueError("MOL2 title must be one non-empty line")
    return value


def _number(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("MOL2 numeric values must be finite")
    return format(0.0 if value == 0.0 else value, ".17g")


def _categorical(property_value, count, role):
    if (
        not isinstance(property_value, AtomicProperty)
        or property_value.status is not DatasetStatus.COMPLETE
        or not isinstance(property_value.data, CategoricalData)
        or property_value.data.dims != ("atom",)
        or property_value.data.shape != (count,)
        or property_value.data.unit != "dimensionless"
    ):
        raise ValueError(f"MOL2 {role} must be one complete atom categorical property")
    values = _categories(property_value.data)
    if any(value is None for value in values):
        raise ValueError(f"MOL2 {role} contains missing values")
    return tuple(_token(value, role) for value in values)


def _numeric(property_value, count, role, kinds):
    if (
        not isinstance(property_value, AtomicProperty)
        or property_value.status is not DatasetStatus.COMPLETE
        or isinstance(property_value.data, CategoricalData)
        or property_value.data.dims != ("atom",)
        or property_value.data.shape != (count,)
        or property_value.data.unit != "dimensionless"
    ):
        raise ValueError(f"MOL2 {role} must be one complete atom numeric property")
    values = numpy.asarray(_values(property_value.data))
    if values.dtype.kind not in kinds or not numpy.all(numpy.isfinite(values)):
        raise ValueError(f"MOL2 {role} values are invalid")
    return values


def _normalized_record(entry):
    structure = entry.structure
    topology = entry.topology
    count = len(structure.atomic_numbers)
    if structure.coordinates.unit != "angstrom":
        raise ValueError("MOL2 export requires angstrom coordinates")
    coordinates = numpy.asarray(_values(structure.coordinates))
    if (
        coordinates.shape != (count, 3)
        or numpy.iscomplexobj(coordinates)
        or not numpy.all(numpy.isfinite(coordinates))
    ):
        raise ValueError("MOL2 export requires finite (atom, xyz) coordinates")
    shifts = topology.bond_lattice_shifts
    if shifts is not None and numpy.any(_values(shifts)):
        raise ValueError("periodic bond lattice shifts are not representable")
    indices = numpy.asarray(_values(topology.bond_indices))
    orders = numpy.asarray(_values(topology.bond_orders))
    if indices.shape != (len(orders), 2) or len(orders) != len(topology.stereo_labels):
        raise ValueError("MOL2 topology dimensions are inconsistent")
    if indices.size and (
        numpy.any(indices < 0) or numpy.any(indices >= count)
    ):
        raise ValueError("MOL2 bond endpoint is out of range")
    aromatic = (
        (False,) * len(orders)
        if topology.aromatic_flags is None
        else tuple(bool(value) for value in _values(topology.aromatic_flags))
    )
    if len(aromatic) != len(orders):
        raise ValueError("MOL2 aromatic flags do not match bonds")

    identity = structure.atomic_identity
    if identity is None or identity.atom_count != count:
        raise ValueError("MOL2 export requires matching atomic identity")
    atom_names = tuple(
        _token(value, "atom name") for value in _categories(identity.atom_names)
    )
    atom_types = _categorical(entry.atom_type, count, "atom_type")
    for number, atom_type in zip(structure.atomic_numbers, atom_types, strict=True):
        symbol = _element_from_type(atom_type)
        if symbol is None or _ELEMENT_NUMBERS[symbol] != number:
            raise ValueError("MOL2 atom_type does not match atomic number")

    molecule_type = _token(
        "SMALL" if entry.molecule_type is None else entry.molecule_type.value,
        "molecule type",
    )
    charge_type = _token(
        "NO_CHARGES" if entry.charge_type is None else entry.charge_type.value,
        "charge type",
    )
    substructure_ids = substructure_names = None
    if entry.substructure_id is not None and entry.substructure_name is not None:
        substructure_ids = _numeric(
            entry.substructure_id, count, "substructure_id", "iu"
        )
        if numpy.any(substructure_ids <= 0):
            raise ValueError("MOL2 substructure IDs must be positive")
        substructure_names = _categorical(
            entry.substructure_name, count, "substructure_name"
        )
    charges = (
        None
        if entry.partial_charge is None
        else _numeric(entry.partial_charge, count, "partial_charge", "iuf")
    )
    groups = {}
    if substructure_ids is not None:
        for atom_index, (identifier, name) in enumerate(
            zip(substructure_ids, substructure_names, strict=True)
        ):
            identifier = int(identifier)
            previous = groups.setdefault(identifier, (name, atom_index + 1))
            if previous[0] != name:
                raise ValueError("one MOL2 substructure ID maps to multiple names")

    title = _title(
        str(structure.id)
        if entry.record is None or entry.record.title is None
        else entry.record.title
    )
    lines = [
        "@<TRIPOS>MOLECULE",
        title,
        f"{count} {len(orders)} {len(groups)} 0 0",
        molecule_type,
        charge_type,
        "@<TRIPOS>ATOM",
    ]
    for index, (name, row, atom_type) in enumerate(
        zip(atom_names, coordinates, atom_types, strict=True), start=1
    ):
        fields = [
            str(index),
            name,
            *(_number(value) for value in row),
            atom_type,
        ]
        if substructure_ids is not None:
            fields.extend(
                (str(int(substructure_ids[index - 1])), substructure_names[index - 1])
            )
        elif charges is not None:
            fields.extend(("****", "****"))
        if charges is not None:
            fields.append(_number(charges[index - 1]))
        lines.append(" ".join(fields))
    lines.append("@<TRIPOS>BOND")
    for index, (endpoints, order, is_aromatic, label) in enumerate(
        zip(indices, orders, aromatic, topology.stereo_labels, strict=True), start=1
    ):
        if is_aromatic:
            bond_type = "ar"
        elif label == "amide":
            bond_type = "am"
        elif label == "" and float(order) in (1.0, 2.0, 3.0):
            bond_type = str(int(order))
        else:
            raise ValueError("unsupported MOL2 bond mapping")
        lines.append(
            f"{index} {int(endpoints[0]) + 1} {int(endpoints[1]) + 1} {bond_type}"
        )
    if groups:
        lines.append("@<TRIPOS>SUBSTRUCTURE")
        lines.extend(
            f"{identifier} {name} {root} GROUP"
            for identifier, (name, root) in sorted(groups.items())
        )
    return "\n".join(lines) + "\n"


def export_mol2(
    project_entities,
    *,
    confirm_loss=False,
    destination=None,
    is_cancelled=None,
):
    if type(confirm_loss) is not bool:
        raise TypeError("confirm_loss must be bool")
    if _cancelled(is_cancelled):
        raise ExportCancelled("export cancelled")
    preview = preview_mol2_export(project_entities)
    if preview.requires_confirmation and not confirm_loss:
        return MolecularExport("", preview)
    text = "".join(_normalized_record(entry) for entry in _ordered_entries(project_entities))
    if destination is not None:
        atomic_write_chunks(destination, (text,), is_cancelled=is_cancelled)
    return MolecularExport(
        text,
        ExportReport(
            "mol2",
            destination is not None,
            preview.frame_count,
            preview.requires_confirmation,
            preview.entries,
        ),
    )


__all__ = ("export_mol2", "preview_mol2_export")
