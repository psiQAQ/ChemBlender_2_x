"""PDB/PQR P1 representability checks; this module does not write files."""

from dataclasses import dataclass
from enum import Enum

import numpy

from ..model import (
    ArrayData,
    AtomicProperty,
    CategoricalData,
    DatasetStatus,
    FrameSet,
)
from ..formats.pdb import _ELEMENT_NUMBERS
from ..formats.pqr import _infer_pqr_element


class PDBPQRExportStatus(str, Enum):
    READY = "Ready"
    READY_WITH_RENUMBERING = "ReadyWithRenumbering"
    MISSING_HIERARCHY = "MissingHierarchy"
    MISSING_PROPERTY = "MissingProperty"
    INVALID = "Invalid"
    FIELD_OVERFLOW = "FieldOverflow"
    AMBIGUOUS = "Ambiguous"


@dataclass(frozen=True, slots=True)
class PDBPQRExportReadiness:
    status: PDBPQRExportStatus
    tokens: tuple[str, ...]


def _entities(project_entities, name):
    values = getattr(project_entities, name)
    return tuple(values.values() if isinstance(values, dict) else values)


def _integer_atom_values(data, atom_count):
    if (
        not isinstance(data, ArrayData)
        or data.dims != ("atom",)
        or data.unit != "dimensionless"
    ):
        return None
    values = numpy.asarray(data.values)
    if values.shape != (atom_count,) or values.dtype.kind not in "iu":
        return None
    return values


def _categorical_values(data, atom_count, *, allow_missing):
    if not isinstance(data, CategoricalData):
        return None
    codes = _integer_atom_values(data.codes, atom_count)
    categories = tuple(data.categories)
    if (
        codes is None
        or any(type(value) is not str for value in categories)
        or len(categories) != len(set(categories))
        or type(data.missing_code) is not int
        or 0 <= data.missing_code < len(categories)
    ):
        return None
    missing = codes == data.missing_code
    if numpy.any((~missing) & ((codes < 0) | (codes >= len(categories)))):
        return None
    if not allow_missing and numpy.any(missing):
        return None
    return tuple(
        None if is_missing else categories[int(code)]
        for code, is_missing in zip(codes, missing)
    )


def _one(values, missing_token, ambiguous_token, issues, *, required):
    values = tuple(values)
    if len(values) == 1:
        return values[0]
    if len(values) > 1:
        issues.add(ambiguous_token)
    elif required:
        issues.add(missing_token)
    return None


def _fits(values, width, precision):
    return all(len(f"{float(value):{width}.{precision}f}") <= width for value in values)


def _property(
    structure,
    datasets,
    role,
    unit,
    issues,
    *,
    required,
    width,
    precision,
    positive=False,
    occupancy=False,
):
    token = f"dataset.{role}"
    value = _one(
        (
            candidate
            for candidate in datasets
            if isinstance(candidate, AtomicProperty)
            and candidate.structure_id == structure.id
            and candidate.semantic_role == role
        ),
        f"{token}.missing",
        f"{token}.ambiguous",
        issues,
        required=required,
    )
    if value is None:
        return
    if (
        not isinstance(value.data, ArrayData)
        or value.data.dims != ("atom",)
    ):
        issues.add(f"{token}.shape")
        return
    if value.data.unit != unit:
        issues.add(f"{token}.unit")
    values = numpy.asarray(value.data.values)
    if values.shape != (len(structure.atomic_numbers),):
        issues.add(f"{token}.shape")
        return
    if (
        numpy.dtype(value.data.dtype).kind not in "iuf"
        or values.dtype.kind not in "iuf"
    ):
        issues.add(f"{token}.values")
        return
    finite = numpy.isfinite(values)
    if required:
        if value.status is not DatasetStatus.COMPLETE:
            issues.add(f"{token}.status")
        if not numpy.all(finite):
            issues.add(f"{token}.values")
    elif value.status not in {DatasetStatus.COMPLETE, DatasetStatus.PARTIAL}:
        issues.add(f"{token}.status")
    elif value.status is DatasetStatus.COMPLETE and not numpy.all(finite):
        issues.add(f"{token}.values")
    elif numpy.any(~finite & ~numpy.isnan(values)):
        issues.add(f"{token}.values")
    valid = values[finite]
    if positive and numpy.any(valid <= 0.0):
        issues.add(f"{token}.values")
    if occupancy and numpy.any((valid < 0.0) | (valid > 1.0)):
        issues.add(f"{token}.values")
    if not _fits(valid, width, precision):
        issues.add(f"{token}.overflow")


def _structure_readiness(structure, hierarchies, datasets, issues, *, pqr):
    atom_count = len(structure.atomic_numbers)
    atom_names = None
    record_kinds = None
    residue_indices = None
    hierarchy = _one(
        (
            candidate
            for candidate in hierarchies
            if candidate.structure_id == structure.id
        ),
        "hierarchy.missing",
        "hierarchy.ambiguous",
        issues,
        required=True,
    )
    identity = structure.atomic_identity
    if identity is None:
        issues.add("identity.atom_name.missing")
    else:
        atom_names = _categorical_values(
            identity.atom_names,
            atom_count,
            allow_missing=True,
        )
        if atom_names is None:
            issues.add("identity.atom_name.invalid")
        elif any(value is None or not value.strip() for value in atom_names):
            issues.add("identity.atom_name.missing")
        if atom_names is not None and any(
            value is not None and len(value) > 4 for value in atom_names
        ):
            issues.add("identity.atom_name.overflow")

    if hierarchy is not None:
        serials = _integer_atom_values(
            hierarchy.atom_sites.serial_numbers,
            atom_count,
        )
        residue_indices = _integer_atom_values(
            hierarchy.atom_sites.residue_indices,
            atom_count,
        )
        chains = hierarchy.chains
        residues = hierarchy.residues
        if (
            serials is None
            or residue_indices is None
            or numpy.any(residue_indices < 0)
            or numpy.any(residue_indices >= len(residues))
            or any(
                type(residue.chain_index) is not int
                or residue.chain_index < 0
                or residue.chain_index >= len(chains)
                for residue in residues
            )
        ):
            issues.add("hierarchy.shape")
        if any(len(chain.chain_id) > 1 for chain in chains):
            issues.add("identity.chain_id.overflow")
        if any(len(residue.residue_name) > 3 for residue in residues):
            issues.add("identity.residue_name.overflow")
        if any(len(residue.insertion_code) > 1 for residue in residues):
            issues.add("identity.insertion_code.overflow")
        if any(len(str(residue.sequence_number)) > 4 for residue in residues):
            issues.add("identity.residue_number.overflow")

        altlocs = _categorical_values(
            hierarchy.atom_sites.alternate_locations,
            atom_count,
            allow_missing=True,
        )
        if altlocs is None:
            issues.add("identity.altloc.invalid")
        else:
            if any(value is not None and len(value) > 1 for value in altlocs):
                issues.add("identity.altloc.overflow")
            if pqr and any(value not in (None, "") for value in altlocs):
                issues.add("identity.altloc.unsupported")
        record_kinds = _categorical_values(
            hierarchy.atom_sites.record_kinds,
            atom_count,
            allow_missing=False,
        )
        if record_kinds is None or any(
            value not in {"atom", "hetatm"} for value in record_kinds
        ):
            issues.add("identity.record_kind")

        if serials is not None:
            serial_values = tuple(int(value) for value in serials)
            if len(serial_values) > 99999:
                issues.add("serial.overflow")
            elif (
                len(serial_values) != len(set(serial_values))
                or any(
                    value <= 0 or value > 99999
                    for value in serial_values
                )
            ):
                issues.add("serial.renumber")

        model_number = hierarchy.model.number
        if model_number is not None and len(str(model_number)) > 4:
            issues.add("model.overflow")

    if (
        pqr
        and hierarchy is not None
        and atom_names is not None
        and record_kinds is not None
        and residue_indices is not None
        and all(value is not None for value in atom_names)
        and all(value in {"atom", "hetatm"} for value in record_kinds)
    ):
        for atomic_number, atom_name, record_kind, residue_index in zip(
            structure.atomic_numbers,
            atom_names,
            record_kinds,
            residue_indices,
            strict=True,
        ):
            if not 0 <= int(residue_index) < len(hierarchy.residues):
                continue
            residue = hierarchy.residues[int(residue_index)]
            element = _infer_pqr_element(
                atom_name,
                record_kind.upper(),
                residue.residue_name,
            )
            if _ELEMENT_NUMBERS.get(element) != atomic_number:
                issues.add("identity.element.mismatch")
                break

    coordinates = numpy.asarray(structure.coordinates.values)
    if structure.coordinates.unit != "angstrom":
        issues.add("coordinates.unit")
    if coordinates.shape != (atom_count, 3):
        issues.add("coordinates.shape")
    elif (
        numpy.dtype(structure.coordinates.dtype).kind not in "iuf"
        or coordinates.dtype.kind not in "iuf"
    ):
        issues.add("coordinates.values")
    elif not numpy.all(numpy.isfinite(coordinates)):
        issues.add("coordinates.values")
    elif not _fits(coordinates.flat, 8, 3):
        issues.add("coordinates.overflow")

    frame_candidates = tuple(
        candidate
        for candidate in datasets
        if isinstance(candidate, FrameSet)
        and candidate.structure_id == structure.id
    )
    frames = None
    if pqr:
        if frame_candidates:
            issues.add("dataset.coordinates.unsupported")
    else:
        frames = _one(
            frame_candidates,
            "dataset.coordinates.missing",
            "dataset.coordinates.ambiguous",
            issues,
            required=False,
        )
    if frames is not None:
        values = numpy.asarray(frames.data.values)
        if (
            frames.status is not DatasetStatus.COMPLETE
            or frames.data.unit != "angstrom"
            or frames.data.dims != ("frame", "atom", "xyz")
            or values.ndim != 3
            or values.shape[0] == 0
            or values.shape[1:] != (atom_count, 3)
            or numpy.dtype(frames.data.dtype).kind not in "iuf"
            or values.dtype.kind not in "iuf"
            or not numpy.all(numpy.isfinite(values))
        ):
            issues.add("dataset.coordinates.invalid")
        elif not _fits(values.flat, 8, 3):
            issues.add("coordinates.overflow")
        if values.ndim == 3 and values.shape[0] > 9999:
            issues.add("model.overflow")

    if pqr:
        _property(
            structure,
            datasets,
            "partial_charge",
            "elementary_charge",
            issues,
            required=True,
            width=8,
            precision=4,
        )
        _property(
            structure,
            datasets,
            "radius",
            "angstrom",
            issues,
            required=True,
            width=7,
            precision=4,
            positive=True,
        )
    else:
        _property(
            structure,
            datasets,
            "occupancy",
            "dimensionless",
            issues,
            required=False,
            width=6,
            precision=2,
            occupancy=True,
        )
        _property(
            structure,
            datasets,
            "b_factor",
            "angstrom_squared",
            issues,
            required=False,
            width=6,
            precision=2,
        )


def _readiness(project_entities, *, pqr):
    structures = _entities(project_entities, "structures")
    hierarchies = _entities(project_entities, "biological_hierarchies")
    datasets = _entities(project_entities, "datasets")
    issues = set()
    if not structures:
        issues.add("structure.missing")
    if (pqr and len(structures) > 1) or (
        len({value.id for value in structures}) != len(structures)
    ):
        issues.add("structure.ambiguous")
    for structure in structures:
        _structure_readiness(structure, hierarchies, datasets, issues, pqr=pqr)

    tokens = tuple(sorted(issues))
    status = (
        PDBPQRExportStatus.AMBIGUOUS
        if any(token.endswith(".ambiguous") for token in tokens)
        else PDBPQRExportStatus.MISSING_HIERARCHY
        if "hierarchy.missing" in tokens
        else PDBPQRExportStatus.MISSING_PROPERTY
        if any(token.endswith(".missing") for token in tokens)
        else PDBPQRExportStatus.FIELD_OVERFLOW
        if any(token.endswith(".overflow") for token in tokens)
        else PDBPQRExportStatus.READY_WITH_RENUMBERING
        if tokens == ("serial.renumber",)
        else PDBPQRExportStatus.INVALID
        if tokens
        else PDBPQRExportStatus.READY
    )
    return PDBPQRExportReadiness(status, tokens)


def pdb_export_readiness(project_entities):
    """Return PDB P1 readiness without serializing."""
    return _readiness(project_entities, pqr=False)


def pqr_export_readiness(project_entities):
    """Return PQR P1 readiness without serializing."""
    return _readiness(project_entities, pqr=True)
