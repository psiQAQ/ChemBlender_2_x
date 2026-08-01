"""Deterministic normalized PDB export from authoritative core entities."""

import math

import numpy

from ..formats.pdb import _ELEMENT_NUMBERS
from ..model import AtomicProperty, DatasetStatus, FrameSet
from .pdb_readiness import (
    PDBPQRExportStatus,
    _categorical_values,
    _entities,
    pdb_export_readiness,
)
from .rdkit_molecular import MolecularExport, _values
from .xyz import (
    ExportCancelled,
    ExportReport,
    ExportReportEntry,
    _cancelled,
    atomic_write_chunks,
)


_ELEMENTS_BY_NUMBER = {
    number: symbol for symbol, number in _ELEMENT_NUMBERS.items()
}
_LOSS_MESSAGES = {
    "atom_serials_renumbered": "source atom serials are normalized to 1..N",
    "cell_omitted": "PDB CRYST1/unit-cell data is omitted",
    "formal_charge_omitted": "PDB formal charges are omitted",
    "source_records_omitted": "PDB source-only records are omitted",
    "topology_omitted": "PDB CONECT/topology data is omitted",
}


def _one(values):
    values = tuple(values)
    return values[0] if len(values) == 1 else None


def _structure_order(project_entities, structure):
    sources = {
        value.id: value for value in _entities(project_entities, "sources")
    }
    candidates = []
    for revision in _entities(project_entities, "source_revisions"):
        if structure.id not in revision.created_entity_ids:
            continue
        source = sources.get(revision.source_id)
        candidates.append(
            (
                "" if source is None else source.created_at_utc,
                revision.content_hash,
                revision.created_entity_ids.index(structure.id),
                str(revision.id),
            )
        )
    return (
        (0, *min(candidates), structure.revision, str(structure.id))
        if candidates
        else (1, "", "", 0, "", structure.revision, str(structure.id))
    )


def _ordered_entries(project_entities):
    structures = tuple(
        sorted(
            _entities(project_entities, "structures"),
            key=lambda value: _structure_order(project_entities, value),
        )
    )
    hierarchies = _entities(project_entities, "biological_hierarchies")
    datasets = _entities(project_entities, "datasets")
    entries = []
    for structure in structures:
        hierarchy = _one(
            value
            for value in hierarchies
            if value.structure_id == structure.id
        )
        frames = _one(
            value
            for value in datasets
            if isinstance(value, FrameSet)
            and value.structure_id == structure.id
        )

        def property_value(role):
            return _one(
                value
                for value in datasets
                if isinstance(value, AtomicProperty)
                and value.structure_id == structure.id
                and value.semantic_role == role
            )

        entries.append(
            (
                structure,
                hierarchy,
                frames,
                property_value("occupancy"),
                property_value("b_factor"),
            )
        )
    return tuple(entries)


def _loss_entries(project_entities, readiness, entries):
    codes = set()
    structure_ids = {entry[0].id for entry in entries}
    if readiness.status is PDBPQRExportStatus.READY_WITH_RENUMBERING:
        codes.add("atom_serials_renumbered")
    if any(
        topology.structure_id in structure_ids
        for topology in _entities(project_entities, "topologies")
    ):
        codes.add("topology_omitted")
    if any(
        structure.cell is not None or structure.periodic is not None
        for structure, *_rest in entries
    ):
        codes.add("cell_omitted")
    if any(
        numpy.any(_values(structure.atomic_identity.formal_charges) != 0)
        for structure, *_rest in entries
    ):
        codes.add("formal_charge_omitted")
    if any(
        revision.reader_id == "pdb"
        and structure_ids.intersection(revision.created_entity_ids)
        for revision in _entities(project_entities, "source_revisions")
    ):
        codes.add("source_records_omitted")
    return tuple(
        ExportReportEntry(code, _LOSS_MESSAGES[code]) for code in sorted(codes)
    )


def preview_pdb_export(project_entities):
    readiness = pdb_export_readiness(project_entities)
    if readiness.status not in {
        PDBPQRExportStatus.READY,
        PDBPQRExportStatus.READY_WITH_RENUMBERING,
    }:
        raise ValueError(
            f"PDB export is {readiness.status.value}: "
            + ", ".join(readiness.tokens)
        )
    entries = _ordered_entries(project_entities)
    losses = _loss_entries(project_entities, readiness, entries)
    frame_count = sum(
        1 if frames is None else frames.data.shape[0]
        for _structure, _hierarchy, frames, _occupancy, _b_factor in entries
    )
    return ExportReport("pdb", False, frame_count, bool(losses), losses)


def _optional_property(value, atom_count, role, unit):
    if value is None:
        return (None,) * atom_count
    if (
        not isinstance(value, AtomicProperty)
        or value.semantic_role != role
        or value.data.dims != ("atom",)
        or value.data.shape != (atom_count,)
        or value.data.unit != unit
        or value.status not in {DatasetStatus.COMPLETE, DatasetStatus.PARTIAL}
    ):
        raise ValueError(f"PDB {role} property is invalid")
    values = _values(value.data)
    if values.dtype.kind not in "iuf" or numpy.iscomplexobj(values):
        raise ValueError(f"PDB {role} values are invalid")
    if numpy.any(~numpy.isfinite(values) & ~numpy.isnan(values)):
        raise ValueError(f"PDB {role} values are invalid")
    if value.status is DatasetStatus.COMPLETE and numpy.any(~numpy.isfinite(values)):
        raise ValueError(f"PDB {role} values are invalid")
    return tuple(None if numpy.isnan(item) else float(item) for item in values)


def _field(value, width, precision, name):
    if value is None:
        return " " * width
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"PDB {name} must be finite")
    text = f"{0.0 if number == 0.0 else number:{width}.{precision}f}"
    if len(text) != width:
        raise ValueError(f"PDB {name} overflows width {width}")
    return text


def _atom_name(value, element):
    if not isinstance(value, str) or not value or len(value) > 4:
        raise ValueError("PDB atom name is invalid")
    if any(ord(character) < 33 or ord(character) > 126 for character in value):
        raise ValueError("PDB atom name contains whitespace or control characters")
    if len(value) == 4 or value[0].isdigit() or len(element) == 2:
        return value.ljust(4)
    return (" " + value).ljust(4)


def _character(value, name):
    if value is None:
        return ""
    if not isinstance(value, str) or len(value) > 1 or any(
        ord(character) < 33 or ord(character) > 126 for character in value
    ):
        raise ValueError(f"PDB {name} is invalid")
    return value


def _atom_line(
    *,
    kind,
    serial,
    atom_name,
    altloc,
    residue_name,
    chain_id,
    residue_number,
    insertion_code,
    coordinates,
    occupancy,
    b_factor,
    atomic_number,
):
    if kind not in {"atom", "hetatm"}:
        raise ValueError("PDB record kind is invalid")
    if type(serial) is not int or not 1 <= serial <= 99999:
        raise ValueError("PDB atom serial is invalid")
    element = _ELEMENTS_BY_NUMBER.get(int(atomic_number))
    if element is None or len(element) > 2:
        raise ValueError("PDB atomic number is not representable")
    if (
        not isinstance(residue_name, str)
        or not residue_name
        or len(residue_name) > 3
        or any(ord(character) < 33 or ord(character) > 126 for character in residue_name)
    ):
        raise ValueError("PDB residue name is invalid")
    if type(residue_number) is not int or len(f"{residue_number:d}") > 4:
        raise ValueError("PDB residue number is invalid")
    altloc = _character(altloc, "alternate location")
    chain_id = _character(chain_id, "chain ID")
    insertion_code = _character(insertion_code, "insertion code")
    x, y, z = tuple(coordinates)
    line = (
        f"{kind.upper():<6}{serial:5d} "
        f"{_atom_name(atom_name, element)}{altloc or ' '}{residue_name:>3} "
        f"{chain_id or ' '}{residue_number:4d}{insertion_code or ' '}   "
        f"{_field(x, 8, 3, 'x coordinate')}"
        f"{_field(y, 8, 3, 'y coordinate')}"
        f"{_field(z, 8, 3, 'z coordinate')}"
        f"{_field(occupancy, 6, 2, 'occupancy')}"
        f"{_field(b_factor, 6, 2, 'B-factor')}"
        f"{'':10}{element:>2}{'':2}"
    )
    if len(line) != 80 or not line.isascii():
        raise ValueError("PDB atom record must be exactly 80 ASCII columns")
    return line + "\n"


def _entry_models(entry, preserve_serials):
    structure, hierarchy, frames, occupancy_property, b_factor_property = entry
    atom_count = len(structure.atomic_numbers)
    if hierarchy is None or hierarchy.atom_count != atom_count:
        raise ValueError("PDB hierarchy does not match the Structure")
    coordinates = (
        (_values(structure.coordinates),)
        if frames is None
        else tuple(_values(frames.data))
    )
    serials = tuple(
        int(value) for value in _values(hierarchy.atom_sites.serial_numbers)
    )
    if not preserve_serials:
        serials = tuple(range(1, atom_count + 1))
    atom_names = _categorical_values(
        structure.atomic_identity.atom_names,
        atom_count,
        allow_missing=False,
    )
    altlocs = _categorical_values(
        hierarchy.atom_sites.alternate_locations,
        atom_count,
        allow_missing=True,
    )
    record_kinds = _categorical_values(
        hierarchy.atom_sites.record_kinds,
        atom_count,
        allow_missing=False,
    )
    residue_indices = tuple(
        int(value) for value in _values(hierarchy.atom_sites.residue_indices)
    )
    occupancy = _optional_property(
        occupancy_property,
        atom_count,
        "occupancy",
        "dimensionless",
    )
    b_factors = _optional_property(
        b_factor_property,
        atom_count,
        "b_factor",
        "angstrom_squared",
    )
    rows = []
    for frame in coordinates:
        if numpy.asarray(frame).shape != (atom_count, 3):
            raise ValueError("PDB coordinates must have (atom, xyz) shape")
        model_rows = []
        for index in range(atom_count):
            residue = hierarchy.residues[residue_indices[index]]
            chain = hierarchy.chains[residue.chain_index]
            model_rows.append(
                _atom_line(
                    kind=record_kinds[index],
                    serial=serials[index],
                    atom_name=atom_names[index],
                    altloc=altlocs[index],
                    residue_name=residue.residue_name,
                    chain_id=chain.chain_id,
                    residue_number=residue.sequence_number,
                    insertion_code=residue.insertion_code,
                    coordinates=frame[index],
                    occupancy=occupancy[index],
                    b_factor=b_factors[index],
                    atomic_number=structure.atomic_numbers[index],
                )
            )
        rows.append(tuple(model_rows))
    return tuple(rows)


def _chunks(project_entities, is_cancelled):
    readiness = pdb_export_readiness(project_entities)
    if readiness.status not in {
        PDBPQRExportStatus.READY,
        PDBPQRExportStatus.READY_WITH_RENUMBERING,
    }:
        raise ValueError(
            f"PDB export is {readiness.status.value}: "
            + ", ".join(readiness.tokens)
        )
    preserve_serials = readiness.status is PDBPQRExportStatus.READY
    models = []
    for entry in _ordered_entries(project_entities):
        if _cancelled(is_cancelled):
            raise ExportCancelled("export cancelled")
        models.extend(_entry_models(entry, preserve_serials))
    chunks = []
    multiple = len(models) > 1
    for model_number, rows in enumerate(models, start=1):
        if _cancelled(is_cancelled):
            raise ExportCancelled("export cancelled")
        if multiple:
            chunks.append(f"MODEL     {model_number:4d}\n")
        chunks.extend(rows)
        if multiple:
            chunks.append("ENDMDL\n")
    chunks.append("END\n")
    return tuple(chunks)


def export_pdb(
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
    preview = preview_pdb_export(project_entities)
    if preview.requires_confirmation and not confirm_loss:
        return MolecularExport("", preview)
    chunks = _chunks(project_entities, is_cancelled)
    text = "".join(chunks)
    if destination is not None:
        atomic_write_chunks(destination, chunks, is_cancelled=is_cancelled)
    return MolecularExport(
        text,
        ExportReport(
            "pdb",
            destination is not None,
            preview.frame_count,
            preview.requires_confirmation,
            preview.entries,
        ),
    )


__all__ = ("export_pdb", "preview_pdb_export")
