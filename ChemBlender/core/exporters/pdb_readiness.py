"""PDB/PQR P1 representability checks; this module does not write files."""

from dataclasses import dataclass
from enum import Enum

import numpy

from ..model import ArrayData, AtomicProperty, DatasetStatus, FrameSet


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


def _categorical_values(data):
    return tuple(
        None if int(code) == data.missing_code else data.categories[int(code)]
        for code in numpy.asarray(data.codes.values)
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
        or value.data.shape != (len(structure.atomic_numbers),)
    ):
        issues.add(f"{token}.shape")
        return
    if value.data.unit != unit:
        issues.add(f"{token}.unit")
    values = numpy.asarray(value.data.values)
    if numpy.dtype(value.data.dtype).kind not in "iuf":
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
        atom_names = _categorical_values(identity.atom_names)
        if any(value is None or not value for value in atom_names):
            issues.add("identity.atom_name.missing")
        if any(value is not None and len(value) > 4 for value in atom_names):
            issues.add("identity.atom_name.overflow")

    if hierarchy is not None:
        if hierarchy.atom_count != len(structure.atomic_numbers):
            issues.add("hierarchy.shape")
        else:
            chains = hierarchy.chains
            residues = hierarchy.residues
            if any(len(chain.chain_id) > 1 for chain in chains):
                issues.add("identity.chain_id.overflow")
            if any(len(residue.residue_name) > 3 for residue in residues):
                issues.add("identity.residue_name.overflow")
            if any(len(residue.insertion_code) > 1 for residue in residues):
                issues.add("identity.insertion_code.overflow")
            if any(len(str(residue.sequence_number)) > 4 for residue in residues):
                issues.add("identity.residue_number.overflow")
            altlocs = _categorical_values(
                hierarchy.atom_sites.alternate_locations
            )
            if any(value is not None and len(value) > 1 for value in altlocs):
                issues.add("identity.altloc.overflow")
            if pqr and any(value not in (None, "") for value in altlocs):
                issues.add("identity.altloc.unsupported")
            if any(
                value not in {"atom", "hetatm"}
                for value in _categorical_values(
                    hierarchy.atom_sites.record_kinds
                )
            ):
                issues.add("identity.record_kind")

            serials = tuple(
                int(value)
                for value in hierarchy.atom_sites.serial_numbers.values
            )
            if len(serials) > 99999:
                issues.add("serial.overflow")
            elif (
                len(serials) != len(set(serials))
                or any(value <= 0 or value > 99999 for value in serials)
            ):
                issues.add("serial.renumber")

            model_number = hierarchy.model.number
            if model_number is not None and len(str(model_number)) > 4:
                issues.add("model.overflow")

    coordinates = numpy.asarray(structure.coordinates.values)
    if structure.coordinates.unit != "angstrom":
        issues.add("coordinates.unit")
    if numpy.dtype(structure.coordinates.dtype).kind not in "iuf" or not numpy.all(
        numpy.isfinite(coordinates)
    ):
        issues.add("coordinates.values")
    elif not _fits(coordinates.flat, 8, 3):
        issues.add("coordinates.overflow")

    frames = _one(
        (
            candidate
            for candidate in datasets
            if isinstance(candidate, FrameSet)
            and candidate.structure_id == structure.id
        ),
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
            or frames.data.shape[1:] != (len(structure.atomic_numbers), 3)
            or numpy.dtype(frames.data.dtype).kind not in "iuf"
            or not numpy.all(numpy.isfinite(values))
        ):
            issues.add("dataset.coordinates.invalid")
        elif not _fits(values.flat, 8, 3):
            issues.add("coordinates.overflow")
        if frames.data.shape[0] > 9999:
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
    if len({value.id for value in structures}) != len(structures):
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
