"""Deterministic normalized PQR export from authoritative core entities."""

import math

import numpy

from ..formats.pdb import _ELEMENT_NUMBERS
from ..formats.pqr import _infer_pqr_element
from ..model import AtomicProperty
from .pdb_readiness import (
    PDBPQRExportStatus,
    _categorical_values,
    _entities,
    pqr_export_readiness,
)
from .rdkit_molecular import MolecularExport, _values
from .xyz import (
    ExportCancelled,
    ExportReport,
    ExportReportEntry,
    _cancelled,
    atomic_write_chunks,
)


_LOSS_MESSAGES = {
    "atom_map_numbers_omitted": "atom-map numbers are omitted",
    "atom_serials_renumbered": "source atom serials are normalized to 1..N",
    "atom_stereo_omitted": "atom stereo labels are omitted",
    "cell_omitted": "PQR periodic-cell data is omitted",
    "formal_charge_omitted": "PQR formal charges are omitted",
    "isotopes_omitted": "isotope labels are omitted",
    "molecular_charge_omitted": "molecular total charge is omitted",
    "molecular_multiplicity_omitted": "molecular spin multiplicity is omitted",
    "topology_omitted": "PQR topology data is omitted",
}


def _one(values):
    values = tuple(values)
    return values[0] if len(values) == 1 else None


def _ready(project_entities):
    readiness = pqr_export_readiness(project_entities)
    if readiness.status not in {
        PDBPQRExportStatus.READY,
        PDBPQRExportStatus.READY_WITH_RENUMBERING,
    }:
        raise ValueError(
            f"PQR export is {readiness.status.value}: "
            + ", ".join(readiness.tokens)
        )
    return readiness


def _label(value, name, maximum, *, required=True):
    if value in (None, "") and not required:
        return ""
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum
        or not value.isascii()
        or any(ord(character) < 33 for character in value)
    ):
        raise ValueError(f"PQR {name} is invalid")
    return value


def _number(value, width, precision, name, *, positive=False):
    number = float(value)
    if not math.isfinite(number) or positive and number <= 0.0:
        raise ValueError(f"PQR {name} is invalid")
    if len(f"{number:{width}.{precision}f}") > width:
        raise ValueError(f"PQR {name} overflows")
    return f"{0.0 if number == 0.0 else number:.{precision}f}"


def _projection(project_entities):
    readiness = _ready(project_entities)
    structure = _one(_entities(project_entities, "structures"))
    hierarchy = _one(
        value
        for value in _entities(project_entities, "biological_hierarchies")
        if value.structure_id == structure.id
    )

    def property_value(role):
        return _one(
            value
            for value in _entities(project_entities, "datasets")
            if isinstance(value, AtomicProperty)
            and value.structure_id == structure.id
            and value.semantic_role == role
        )

    charge = property_value("partial_charge")
    radius = property_value("radius")
    atom_count = len(structure.atomic_numbers)
    coordinates = _values(structure.coordinates)
    charges = _values(charge.data)
    radii = _values(radius.data)
    serials = _values(hierarchy.atom_sites.serial_numbers)
    residue_indices = _values(hierarchy.atom_sites.residue_indices)
    atom_names = _categorical_values(
        structure.atomic_identity.atom_names,
        atom_count,
        allow_missing=False,
    )
    record_kinds = _categorical_values(
        hierarchy.atom_sites.record_kinds,
        atom_count,
        allow_missing=False,
    )
    if (
        hierarchy.atom_count != atom_count
        or coordinates.shape != (atom_count, 3)
        or charges.shape != (atom_count,)
        or radii.shape != (atom_count,)
        or serials.shape != (atom_count,)
        or residue_indices.shape != (atom_count,)
        or atom_names is None
        or record_kinds is None
    ):
        raise ValueError("PQR export inputs changed after readiness validation")
    if any(array.dtype.kind not in "iuf" for array in (coordinates, charges, radii)):
        raise ValueError("PQR numeric values are invalid")
    if not (
        numpy.all(numpy.isfinite(coordinates))
        and numpy.all(numpy.isfinite(charges))
        and numpy.all(numpy.isfinite(radii))
        and numpy.all(radii > 0.0)
    ):
        raise ValueError("PQR numeric values are invalid")
    preserve_serials = readiness.status is PDBPQRExportStatus.READY
    rows = []
    for index in range(atom_count):
        residue_index = int(residue_indices[index])
        if not 0 <= residue_index < len(hierarchy.residues):
            raise ValueError("PQR residue index is invalid")
        residue = hierarchy.residues[residue_index]
        chain = hierarchy.chains[residue.chain_index]
        kind = record_kinds[index]
        if kind not in {"atom", "hetatm"}:
            raise ValueError("PQR record kind is invalid")
        atom_name = _label(atom_names[index], "atom name", 4)
        residue_name = _label(residue.residue_name, "residue name", 3)
        chain_id = _label(chain.chain_id, "chain ID", 1, required=False)
        insertion_code = _label(
            residue.insertion_code,
            "insertion code",
            1,
            required=False,
        )
        residue_id = f"{residue.sequence_number}{insertion_code}"
        _label(residue_id, "residue number", 5)
        element = _infer_pqr_element(atom_name, kind.upper(), residue_name)
        if _ELEMENT_NUMBERS.get(element) != structure.atomic_numbers[index]:
            raise ValueError("PQR identity.element.mismatch")
        serial = int(serials[index]) if preserve_serials else index + 1
        if not 1 <= serial <= 99999:
            raise ValueError("PQR atom serial is invalid")
        x, y, z = coordinates[index]
        fields = [
            kind.upper(),
            str(serial),
            atom_name,
            residue_name,
        ]
        if chain_id:
            fields.append(chain_id)
        fields.extend(
            (
                residue_id,
                _number(x, 8, 3, "x coordinate"),
                _number(y, 8, 3, "y coordinate"),
                _number(z, 8, 3, "z coordinate"),
                _number(charges[index], 8, 4, "charge"),
                _number(radii[index], 7, 4, "radius", positive=True),
            )
        )
        line = " ".join(fields) + "\n"
        if not line.isascii():
            raise ValueError("PQR output must be ASCII")
        rows.append(line)
    return readiness, structure, tuple(rows)


def _loss_entries(project_entities, readiness, structure):
    codes = set()
    identity = structure.atomic_identity
    if readiness.status is PDBPQRExportStatus.READY_WITH_RENUMBERING:
        codes.add("atom_serials_renumbered")
    if structure.topology is not None or any(
        value.structure_id == structure.id
        for value in _entities(project_entities, "topologies")
    ):
        codes.add("topology_omitted")
    if structure.cell is not None or structure.periodic is not None:
        codes.add("cell_omitted")
    if structure.molecular_charge is not None:
        codes.add("molecular_charge_omitted")
    if structure.molecular_multiplicity is not None:
        codes.add("molecular_multiplicity_omitted")
    if numpy.any(_values(identity.isotopes) != 0):
        codes.add("isotopes_omitted")
    if numpy.any(_values(identity.formal_charges) != 0):
        codes.add("formal_charge_omitted")
    if numpy.any(_values(identity.atom_map_numbers) != 0):
        codes.add("atom_map_numbers_omitted")
    stereo = _categorical_values(
        identity.stereo_labels,
        len(structure.atomic_numbers),
        allow_missing=True,
    )
    if stereo is None:
        raise ValueError("PQR atom stereo labels are invalid")
    if any(value not in (None, "") for value in stereo):
        codes.add("atom_stereo_omitted")
    return tuple(
        ExportReportEntry(code, _LOSS_MESSAGES[code]) for code in sorted(codes)
    )


def preview_pqr_export(project_entities):
    readiness, structure, _rows = _projection(project_entities)
    losses = _loss_entries(project_entities, readiness, structure)
    return ExportReport("pqr", False, 1, bool(losses), losses)


def _chunks(project_entities, is_cancelled):
    _readiness, _structure, rows = _projection(project_entities)
    chunks = []
    for row in rows:
        if _cancelled(is_cancelled):
            raise ExportCancelled("export cancelled")
        chunks.append(row)
    return tuple(chunks)


def export_pqr(
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
    preview = preview_pqr_export(project_entities)
    if preview.requires_confirmation and not confirm_loss:
        return MolecularExport("", preview)
    chunks = _chunks(project_entities, is_cancelled)
    text = "".join(chunks)
    if destination is not None:
        atomic_write_chunks(destination, chunks, is_cancelled=is_cancelled)
    return MolecularExport(
        text,
        ExportReport(
            "pqr",
            destination is not None,
            preview.frame_count,
            preview.requires_confirmation,
            preview.entries,
        ),
    )


__all__ = ("export_pqr", "preview_pqr_export")
