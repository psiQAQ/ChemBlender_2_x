"""Dependency-free Tripos MOL2 syntax parser."""

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from ...Chem_data import ELEMENTS_DEFAULT
from ..model import (
    ArrayData,
    AtomicIdentityData,
    AtomicProperty,
    CategoricalData,
    ChemicalAnnotation,
    DatasetStatus,
    DiagnosticSeverity,
    ImportBatch,
    ImportDiagnostic,
    IssueKind,
    MolecularRecord,
    ParserIssue,
    ParserReport,
    ProvenanceRecord,
    QualityStatus,
    SourceRecord,
    SourceRevision,
    Structure,
    TopologyRecord,
    TopologySource,
    source_parse_identity,
)
from ..readers import (
    READER_API_VERSION,
    CapabilitySupport,
    ReaderDescriptor,
    SniffMatch,
    SniffResult,
)


_SECTION_HEADER = re.compile(r"@<TRIPOS>([A-Z0-9_]+)", re.ASCII | re.IGNORECASE)
_ELEMENT_SYMBOLS = frozenset(
    symbol for symbol, data in ELEMENTS_DEFAULT.items() if data[0] > 0
)
_ELEMENT_NUMBERS = {
    symbol: data[0] for symbol, data in ELEMENTS_DEFAULT.items() if data[0] > 0
}
_READER_ID = "mol2"
_READER_VERSION = "1"
_PLUGIN_ID = "chemblender.builtin"
_PARSED_CAPABILITIES = (
    "structure",
    "topology",
    "atomic_property",
    "substructure",
    "multi_record",
)


@dataclass(frozen=True, slots=True)
class Mol2Section:
    name: str
    raw_lines: tuple[bytes, ...]


@dataclass(frozen=True, slots=True)
class Mol2SyntaxRecord:
    raw_block: bytes
    sections: tuple[Mol2Section, ...]


@dataclass(frozen=True, slots=True)
class Mol2Counts:
    atom_count: int
    bond_count: int
    substructure_count: int
    feature_count: int
    set_count: int


@dataclass(frozen=True, slots=True)
class Mol2Atom:
    atom_id: int
    name: str
    coordinates: tuple[float, float, float]
    atom_type: str
    element: str | None
    substructure_id: int | None
    substructure_name: str | None
    charge: float | None
    status_bits: str | None


@dataclass(frozen=True, slots=True)
class Mol2Bond:
    bond_id: int
    atom_ids: tuple[int, int]
    atom_indices: tuple[int, int] | None
    bond_type: str
    order: float | None
    aromatic: bool
    amide: bool
    unknown: bool


@dataclass(frozen=True, slots=True)
class Mol2Substructure:
    substructure_id: int
    name: str
    root_atom_id: int
    root_atom_index: int | None
    substructure_type: str | None
    raw_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Mol2ParsedRecord:
    raw_block: bytes
    sections: tuple[Mol2Section, ...]
    name: str
    counts: Mol2Counts
    molecule_type: str
    charge_type: str
    status_bits: str | None
    comment_lines: tuple[str, ...]
    atoms: tuple[Mol2Atom, ...]
    bonds: tuple[Mol2Bond, ...]
    substructures: tuple[Mol2Substructure, ...]
    unknown_sections: tuple[Mol2Section, ...]
    topology_valid: bool
    issues: tuple[ParserIssue, ...]


def _header_name(line):
    match = _SECTION_HEADER.fullmatch(line.strip())
    return None if match is None else match.group(1)


def _raw_header_name(line, *, allow_bom=False):
    try:
        return _header_name(line.decode("utf-8-sig" if allow_bom else "ascii"))
    except UnicodeDecodeError:
        return None


def _syntax_record(lines, *, allow_initial_bom=False):
    sections = []
    for index, line in enumerate(lines):
        name = _raw_header_name(
            line,
            allow_bom=allow_initial_bom and index == 0,
        )
        if name is None:
            sections[-1][1].append(line)
        else:
            sections.append((name, []))
    return Mol2SyntaxRecord(
        raw_block=b"".join(lines),
        sections=tuple(
            Mol2Section(name, tuple(raw_lines)) for name, raw_lines in sections
        ),
    )


def iter_mol2_records(raw_source: bytes):
    lines = raw_source.splitlines(keepends=True)
    starts = [
        index
        for index, line in enumerate(lines)
        if (
            _raw_header_name(line, allow_bom=index == 0) or ""
        ).upper() == "MOLECULE"
    ]
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        yield _syntax_record(lines[start:end], allow_initial_bom=start == 0)


def _section_lines(section):
    try:
        return b"".join(section.raw_lines).decode("utf-8-sig").splitlines()
    except UnicodeDecodeError as error:
        raise ValueError(f"MOL2 {section.name} section is not UTF-8 text") from error


def _required_section(record, name):
    sections = tuple(
        section for section in record.sections if section.name.upper() == name
    )
    if len(sections) != 1:
        raise ValueError(f"MOL2 record must contain one {name} section")
    return sections[0]


def _optional_section(record, name):
    sections = tuple(
        section for section in record.sections if section.name.upper() == name
    )
    if len(sections) > 1:
        raise ValueError(f"MOL2 record contains more than one {name} section")
    return None if not sections else sections[0]


def _parse_counts(line):
    try:
        values = tuple(int(value) for value in line.split())
    except ValueError as error:
        raise ValueError("MOL2 counts must be integers") from error
    if (
        len(values) != 5
        or values[0] <= 0
        or any(value < 0 for value in values[1:])
    ):
        raise ValueError("MOL2 counts are not plausible")
    return Mol2Counts(*values)


def _element_from_type(atom_type):
    prefix = atom_type.split(".", 1)[0]
    symbol = prefix[:1].upper() + prefix[1:].lower()
    return symbol if symbol in _ELEMENT_SYMBOLS else None


def _parse_atom(line, index, issues):
    fields = line.split()
    if len(fields) < 6:
        raise ValueError(f"MOL2 atom {index} has fewer than six fields")
    try:
        atom_id = int(fields[0])
        coordinates = tuple(float(value) for value in fields[2:5])
        substructure_id = (
            None
            if len(fields) < 7 or fields[6] == "****"
            else int(fields[6])
        )
        charge = None if len(fields) < 9 else float(fields[8])
    except ValueError as error:
        raise ValueError(f"MOL2 atom {index} has invalid numeric fields") from error
    if not all(math.isfinite(value) for value in coordinates) or (
        charge is not None and not math.isfinite(charge)
    ):
        raise ValueError(f"MOL2 atom {index} has non-finite numeric fields")
    atom_type = fields[5]
    element = _element_from_type(atom_type)
    if element is None:
        issues.append(
            ParserIssue(
                IssueKind.AMBIGUOUS,
                f"atom[{index}].element",
                f"cannot derive an element from Tripos atom type {atom_type!r}",
            )
        )
    return Mol2Atom(
        atom_id=atom_id,
        name=fields[1],
        coordinates=coordinates,
        atom_type=atom_type,
        element=element,
        substructure_id=substructure_id,
        substructure_name=(
            None if len(fields) < 8 or fields[7] == "****" else fields[7]
        ),
        charge=charge,
        status_bits=" ".join(fields[9:]) or None,
    )


def _parse_bond(line, index, atom_indices, issues):
    fields = line.split()
    if len(fields) < 4:
        raise ValueError(f"MOL2 bond {index} has fewer than four fields")
    try:
        bond_id, first, second = (int(value) for value in fields[:3])
    except ValueError as error:
        raise ValueError(f"MOL2 bond {index} has invalid IDs") from error
    atom_pair = (
        (atom_indices[first], atom_indices[second])
        if first in atom_indices and second in atom_indices
        else None
    )
    if atom_pair is None:
        issues.append(
            ParserIssue(
                IssueKind.INVALID,
                f"bond[{index}].atom_references",
                f"bond references unknown atom IDs {first} and/or {second}",
            )
        )
    bond_type = fields[3]
    normalized_type = bond_type.lower()
    if normalized_type in {"1", "2", "3", "4"}:
        order = float(normalized_type)
        aromatic = amide = unknown = False
    elif normalized_type == "ar":
        order, aromatic, amide, unknown = 1.5, True, False, False
    elif normalized_type == "am":
        order, aromatic, amide, unknown = 1.0, False, True, False
    else:
        order, aromatic, amide, unknown = None, False, False, True
        issues.append(
            ParserIssue(
                IssueKind.UNSUPPORTED,
                f"bond[{index}].type",
                f"unsupported MOL2 bond type {bond_type!r}",
            )
        )
    return Mol2Bond(
        bond_id,
        (first, second),
        atom_pair,
        bond_type,
        order,
        aromatic,
        amide,
        unknown,
    )


def _parse_substructure(line, index, atom_indices, issues):
    fields = line.split()
    if len(fields) < 3:
        raise ValueError(f"MOL2 substructure {index} has fewer than three fields")
    try:
        substructure_id = int(fields[0])
        root_atom_id = int(fields[2])
    except ValueError as error:
        raise ValueError(f"MOL2 substructure {index} has invalid IDs") from error
    root_atom_index = atom_indices.get(root_atom_id)
    if root_atom_index is None:
        issues.append(
            ParserIssue(
                IssueKind.INVALID,
                f"substructure[{index}].root_atom_reference",
                f"substructure references unknown root atom ID {root_atom_id}",
            )
        )
    return Mol2Substructure(
        substructure_id,
        fields[1],
        root_atom_id,
        root_atom_index,
        fields[3] if len(fields) > 3 else None,
        tuple(fields),
    )


def parse_mol2_record(record: Mol2SyntaxRecord) -> Mol2ParsedRecord:
    molecule_lines = _section_lines(_required_section(record, "MOLECULE"))
    if len(molecule_lines) < 4:
        raise ValueError("MOL2 MOLECULE section is incomplete")
    molecule_type = molecule_lines[2]
    charge_type = molecule_lines[3]
    if not molecule_type.strip():
        raise ValueError("MOL2 molecule type must be non-empty")
    if not charge_type.strip():
        raise ValueError("MOL2 charge type must be non-empty")
    counts = _parse_counts(molecule_lines[1])
    issues = []
    atom_lines = [
        line
        for line in _section_lines(_required_section(record, "ATOM"))
        if line.strip()
    ]
    atoms = tuple(
        _parse_atom(line, index, issues) for index, line in enumerate(atom_lines)
    )
    if len(atoms) != counts.atom_count:
        raise ValueError("MOL2 ATOM section does not match the declared count")
    if len({atom.atom_id for atom in atoms}) != len(atoms):
        raise ValueError("MOL2 atom IDs must be unique")
    atom_indices = {atom.atom_id: index for index, atom in enumerate(atoms)}

    bond_section = _optional_section(record, "BOND")
    bond_lines = (
        []
        if bond_section is None
        else [line for line in _section_lines(bond_section) if line.strip()]
    )
    invalid_bond_data = False
    bonds = []
    for index, line in enumerate(bond_lines):
        try:
            bonds.append(_parse_bond(line, index, atom_indices, issues))
        except ValueError as error:
            invalid_bond_data = True
            issues.append(
                ParserIssue(
                    IssueKind.INVALID,
                    f"bond[{index}].syntax",
                    str(error),
                )
            )
    bonds = tuple(bonds)
    if len(bond_lines) != counts.bond_count:
        invalid_bond_data = True
        issues.append(
            ParserIssue(
                IssueKind.INVALID,
                "bond.count",
                "MOL2 BOND section does not match the declared count",
            )
        )
    if len({bond.bond_id for bond in bonds}) != len(bonds):
        invalid_bond_data = True
        issues.append(
            ParserIssue(
                IssueKind.INVALID,
                "bond.ids",
                "MOL2 bond IDs must be unique",
            )
        )

    substructure_section = _optional_section(record, "SUBSTRUCTURE")
    substructure_lines = (
        []
        if substructure_section is None
        else [
            line
            for line in _section_lines(substructure_section)
            if line.strip()
        ]
    )
    substructures = tuple(
        _parse_substructure(line, index, atom_indices, issues)
        for index, line in enumerate(substructure_lines)
    )
    if len(substructures) != counts.substructure_count:
        raise ValueError(
            "MOL2 SUBSTRUCTURE section does not match the declared count"
        )
    if len({value.substructure_id for value in substructures}) != len(
        substructures
    ):
        raise ValueError("MOL2 substructure IDs must be unique")
    substructure_ids = {value.substructure_id for value in substructures}
    dangling_substructures = tuple(
        (index, atom.substructure_id)
        for index, atom in enumerate(atoms)
        if atom.substructure_id is not None
        and atom.substructure_id not in substructure_ids
    )
    issues.extend(
        ParserIssue(
            IssueKind.INVALID,
            f"atom[{index}].substructure_reference",
            f"atom references unknown substructure ID {substructure_id}",
        )
        for index, substructure_id in dangling_substructures
    )

    known_sections = {"MOLECULE", "ATOM", "BOND", "SUBSTRUCTURE"}
    unknown_sections = tuple(
        section
        for section in record.sections
        if section.name.upper() not in known_sections
    )
    issues.extend(
        ParserIssue(
            IssueKind.UNSUPPORTED,
            f"section.{section.name.lower()}",
            f"MOL2 {section.name} section is preserved but not interpreted",
        )
        for section in unknown_sections
    )
    topology_valid = (
        not invalid_bond_data
        and not any(bond.atom_indices is None or bond.unknown for bond in bonds)
        and all(value.root_atom_index is not None for value in substructures)
        and not dangling_substructures
    )
    return Mol2ParsedRecord(
        raw_block=record.raw_block,
        sections=record.sections,
        name=molecule_lines[0],
        counts=counts,
        molecule_type=molecule_type,
        charge_type=charge_type,
        status_bits=(
            molecule_lines[4] if len(molecule_lines) > 4 and molecule_lines[4] else None
        ),
        comment_lines=tuple(molecule_lines[5:]),
        atoms=atoms,
        bonds=bonds,
        substructures=substructures,
        unknown_sections=unknown_sections,
        topology_valid=topology_valid,
        issues=tuple(issues),
    )


def sniff_mol2(source: Path, prefix: bytes) -> SniffResult:
    try:
        lines = prefix.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError:
        return SniffResult(SniffMatch.NONE, "content is not UTF-8 MOL2 text")

    try:
        molecule = next(
            index
            for index, line in enumerate(lines)
            if (_header_name(line) or "").upper() == "MOLECULE"
        )
        atom = next(
            index
            for index, line in enumerate(lines[molecule + 1 :], molecule + 1)
            if (_header_name(line) or "").upper() == "ATOM"
        )
        counts = tuple(int(value) for value in lines[molecule + 2].split())
    except (IndexError, StopIteration, ValueError):
        return SniffResult(
            SniffMatch.NONE,
            "missing MOL2 molecule, counts or atom marker",
        )
    if (
        len(counts) != 5
        or counts[0] <= 0
        or any(value < 0 for value in counts[1:])
        or atom <= molecule + 2
    ):
        return SniffResult(SniffMatch.NONE, "MOL2 counts are not plausible")

    try:
        truncated = Path(source).stat().st_size > len(prefix)
    except OSError:
        truncated = True
    return SniffResult(
        SniffMatch.PROBABLE if truncated else SniffMatch.EXACT,
        "valid MOL2 prefix" if truncated else "complete MOL2 source",
    )


def _identity(source_revision_id, source_hash, record_index, raw_block, role):
    raw_hash = hashlib.sha256(raw_block).hexdigest()
    return uuid5(
        source_revision_id,
        f"mol2:{source_hash}:{record_index}:{raw_hash}:{role}",
    )


def _record_key(source_revision_id, source_hash, record_index, raw_block):
    return (
        f"record-{record_index:06d}-"
        f"{_identity(source_revision_id, source_hash, record_index, raw_block, 'key')}"
    )


def _array(values, dims, unit="dimensionless", *, dtype=None):
    import numpy

    return ArrayData(numpy.asarray(values, dtype=dtype), dims, unit)


def _categorical(values):
    categories = tuple(dict.fromkeys(value for value in values if value is not None))
    indices = {value: index for index, value in enumerate(categories)}
    return CategoricalData(
        _array(
            tuple(indices.get(value, -1) for value in values),
            ("atom",),
            dtype="int64",
        ),
        categories,
        -1,
    )


def _property(
    source_revision_id,
    source_hash,
    parsed,
    record_index,
    structure_id,
    provenance_id,
    semantic_role,
    data,
    status,
):
    return AtomicProperty(
        id=_identity(
            source_revision_id,
            source_hash,
            record_index,
            parsed.raw_block,
            f"property:{semantic_role}",
        ),
        revision=source_hash,
        semantic_role=semantic_role,
        domain="atom",
        data=data,
        status=status,
        source_calculation=None,
        provenance_ids=(provenance_id,),
        structure_id=structure_id,
    )


def _diagnostic(
    source_revision_id,
    source_hash,
    record_index,
    raw_block,
    record_key,
    issue,
    occurrence,
    *,
    entity_id=None,
):
    occurrence_suffix = "" if occurrence == 0 else f":{occurrence}"
    severity, quality_status, consequence = {
        IssueKind.MISSING: (
            DiagnosticSeverity.WARNING,
            QualityStatus.INCOMPLETE,
            "Required or optional MOL2 data is missing.",
        ),
        IssueKind.UNSUPPORTED: (
            DiagnosticSeverity.WARNING,
            QualityStatus.INCOMPLETE,
            "The source field remains only in the raw MOL2 record.",
        ),
        IssueKind.AMBIGUOUS: (
            DiagnosticSeverity.WARNING,
            QualityStatus.AMBIGUOUS,
            "The scientific meaning requires review.",
        ),
        IssueKind.INVALID: (
            DiagnosticSeverity.ERROR,
            QualityStatus.INVALID,
            "The invalid source field was not mapped to a scientific entity.",
        ),
        IssueKind.WARNING: (
            DiagnosticSeverity.WARNING,
            QualityStatus.PARTIAL,
            "The imported MOL2 record has a reader warning.",
        ),
    }[issue.kind]
    return ImportDiagnostic(
        id=_identity(
            source_revision_id,
            source_hash,
            record_index,
            raw_block,
            f"diagnostic:{issue.kind.value}:{issue.path}{occurrence_suffix}",
        ),
        severity=severity,
        quality_status=quality_status,
        source_revision_id=source_revision_id,
        record_key=record_key,
        entity_id=entity_id,
        field_path=issue.path,
        code=f"mol2.{issue.kind.value}",
        message=issue.message,
        original_value=None,
        normalized_value=None,
        recovery_action=(
            "the Structure was retained without an explicit topology"
            if issue.kind is IssueKind.INVALID and issue.path.startswith("bond")
            else None
        ),
        scientific_consequence=consequence,
        suggested_action=None,
    )


def _map_record(parsed, record_index, source_revision_id, source_hash, source):
    import numpy

    provenance_id = _identity(
        source_revision_id,
        source_hash,
        record_index,
        parsed.raw_block,
        "provenance",
    )
    structure_id = _identity(
        source_revision_id,
        source_hash,
        record_index,
        parsed.raw_block,
        "structure",
    )
    provenance = ProvenanceRecord(
        id=provenance_id,
        revision=source_hash,
        producer="ChemBlender MOL2 reader",
        producer_version=_READER_VERSION,
        source=str(source),
        source_hash=source_hash,
        parent_ids=(),
        operation="parse",
        parameters=(("format", "mol2"),),
    )
    record_key = _record_key(
        source_revision_id,
        source_hash,
        record_index,
        parsed.raw_block,
    )

    issues = list(parsed.issues)
    topology = None
    if parsed.topology_valid:
        bonds = sorted(
            (
                min(bond.atom_indices),
                max(bond.atom_indices),
                bond.order,
                bond.aromatic,
                "amide" if bond.amide else "",
            )
            for bond in parsed.bonds
        )
        try:
            topology = TopologyRecord(
                id=_identity(
                    source_revision_id,
                    source_hash,
                    record_index,
                    parsed.raw_block,
                    "topology",
                ),
                revision=source_hash,
                structure_id=structure_id,
                bond_indices=ArrayData(
                    numpy.asarray(
                        tuple(item[:2] for item in bonds),
                        dtype=numpy.int64,
                    ).reshape((-1, 2)),
                    ("bond", "endpoint"),
                    "dimensionless",
                ),
                bond_orders=_array(
                    tuple(item[2] for item in bonds),
                    ("bond",),
                    dtype="float64",
                ),
                aromatic_flags=_array(
                    tuple(item[3] for item in bonds),
                    ("bond",),
                    dtype="bool",
                ),
                stereo_labels=tuple(item[4] for item in bonds),
                source_kind=TopologySource.EXPLICIT_FILE,
                quality_status=QualityStatus.COMPLETE,
                inference_parameters=(),
                provenance_ids=(provenance_id,),
            )
        except ValueError as error:
            issues.append(
                ParserIssue(
                    IssueKind.INVALID,
                    "topology.bonds",
                    f"invalid MOL2 bond topology: {error}",
                )
            )
    missing_categories = tuple(
        index
        for index, atom in enumerate(parsed.atoms)
        if atom.name == "*" or atom.atom_type == "*"
    )
    issues.extend(
        ParserIssue(
            IssueKind.MISSING,
            f"atom[{index}].name_and_type",
            "MOL2 * recovery sentinel maps to categorical missing codes",
        )
        for index in missing_categories
    )
    atom_names = tuple(
        None if atom.name == "*" else atom.name for atom in parsed.atoms
    )
    structure = Structure(
        id=structure_id,
        revision=source_hash,
        atomic_numbers=tuple(
            0 if atom.element is None else _ELEMENT_NUMBERS[atom.element]
            for atom in parsed.atoms
        ),
        coordinates=_array(
            tuple(atom.coordinates for atom in parsed.atoms),
            ("atom", "xyz"),
            "angstrom",
            dtype="float64",
        ),
        topology_ids=(() if topology is None else (topology.id,)),
        atomic_identity=AtomicIdentityData(
            isotopes=_array((0,) * len(parsed.atoms), ("atom",), dtype="int64"),
            formal_charges=_array(
                (0,) * len(parsed.atoms), ("atom",), dtype="int64"
            ),
            atom_map_numbers=_array(
                (0,) * len(parsed.atoms), ("atom",), dtype="int64"
            ),
            atom_names=_categorical(atom_names),
            stereo_labels=_categorical((None,) * len(parsed.atoms)),
        ),
    )

    datasets = [
        _property(
            source_revision_id,
            source_hash,
            parsed,
            record_index,
            structure.id,
            provenance_id,
            "atom_type",
            _categorical(
                tuple(
                    None if atom.atom_type == "*" else atom.atom_type
                    for atom in parsed.atoms
                )
            ),
            (
                DatasetStatus.PARTIAL
                if missing_categories
                else DatasetStatus.COMPLETE
            ),
        )
    ]
    substructure_ids = tuple(atom.substructure_id for atom in parsed.atoms)
    if any(value is not None for value in substructure_ids):
        datasets.append(
            _property(
                source_revision_id,
                source_hash,
                parsed,
                record_index,
                structure.id,
                provenance_id,
                "substructure_id",
                _array(
                    tuple(0 if value is None else value for value in substructure_ids),
                    ("atom",),
                    dtype="int64",
                ),
                (
                    DatasetStatus.COMPLETE
                    if all(value is not None for value in substructure_ids)
                    else DatasetStatus.PARTIAL
                ),
            )
        )
    substructure_names = tuple(atom.substructure_name for atom in parsed.atoms)
    if any(value is not None for value in substructure_names):
        datasets.append(
            _property(
                source_revision_id,
                source_hash,
                parsed,
                record_index,
                structure.id,
                provenance_id,
                "substructure_name",
                _categorical(substructure_names),
                (
                    DatasetStatus.COMPLETE
                    if all(value is not None for value in substructure_names)
                    else DatasetStatus.PARTIAL
                ),
            )
        )
    charges = tuple(atom.charge for atom in parsed.atoms)
    if any(value is not None for value in charges):
        datasets.append(
            _property(
                source_revision_id,
                source_hash,
                parsed,
                record_index,
                structure.id,
                provenance_id,
                "partial_charge",
                _array(
                    tuple(0.0 if value is None else value for value in charges),
                    ("atom",),
                    dtype="float64",
                ),
                (
                    DatasetStatus.COMPLETE
                    if all(value is not None for value in charges)
                    else DatasetStatus.PARTIAL
                ),
            )
        )

    annotations = tuple(
        ChemicalAnnotation(
            id=_identity(
                source_revision_id,
                source_hash,
                record_index,
                parsed.raw_block,
                f"annotation:{key}",
            ),
            revision=source_hash,
            target_entity_id=structure.id,
            namespace="tripos",
            key=key,
            value=value,
            source="mol2",
            confidence=None,
            provenance_ids=(provenance_id,),
        )
        for key, value in (
            ("molecule_type", parsed.molecule_type),
            ("charge_type", parsed.charge_type),
            ("status_bits", parsed.status_bits),
        )
        if value is not None
    )
    record = MolecularRecord(
        id=_identity(
            source_revision_id,
            source_hash,
            record_index,
            parsed.raw_block,
            "record",
        ),
        revision=source_hash,
        source_revision_id=source_revision_id,
        record_key=record_key,
        structure_id=structure.id,
        topology_id=None if topology is None else topology.id,
        raw_block=parsed.raw_block,
        title=parsed.name,
        source_record_index=record_index,
        block_version=None,
        writer_name=None,
        writer_version=None,
        ordered_raw_properties=(),
        provenance_ids=(provenance_id,),
    )
    occurrences = {}
    diagnostics = []
    for issue in issues:
        key = (issue.kind, issue.path)
        occurrence = occurrences.get(key, 0)
        occurrences[key] = occurrence + 1
        diagnostics.append(
            _diagnostic(
                source_revision_id,
                source_hash,
                record_index,
                parsed.raw_block,
                record_key,
                issue,
                occurrence,
                entity_id=structure.id,
            )
        )
    diagnostics = tuple(diagnostics)
    return (
        structure,
        topology,
        record,
        annotations,
        tuple(datasets),
        provenance,
        diagnostics,
        tuple(issues),
    )


def _record_failure_diagnostic(
    source_revision_id,
    source_hash,
    record_index,
    raw_block,
    message,
):
    return ImportDiagnostic(
        id=_identity(
            source_revision_id,
            source_hash,
            record_index,
            raw_block,
            "diagnostic:record_parse_failed",
        ),
        severity=DiagnosticSeverity.ERROR,
        quality_status=QualityStatus.INVALID,
        source_revision_id=source_revision_id,
        record_key=_record_key(
            source_revision_id,
            source_hash,
            record_index,
            raw_block,
        ),
        entity_id=None,
        field_path=f"record.{record_index}",
        code="mol2.record_parse_failed",
        message=message,
        original_value=None,
        normalized_value=None,
        recovery_action="other MOL2 records were retained",
        scientific_consequence="This record has no imported molecular structure.",
        suggested_action="Correct the malformed MOL2 record and import again.",
    )


def _parameters(validation_mode, canonical_parameters):
    return tuple(
        sorted(
            (
                ("source_content_state", "verified"),
                ("validation_mode", validation_mode),
                *canonical_parameters,
            )
        )
    )


def _parse_bytes(
    raw_source,
    source,
    *,
    source_revision_id,
    source_hash,
    validation_mode,
    canonical_parameters=(),
):
    mapped = []
    failure_diagnostics = []
    for index, syntax in enumerate(iter_mol2_records(raw_source)):
        try:
            parsed = parse_mol2_record(syntax)
        except ValueError as error:
            if validation_mode == "strict":
                raise ValueError(f"MOL2 record {index} failed") from error
            failure_diagnostics.append(
                _record_failure_diagnostic(
                    source_revision_id,
                    source_hash,
                    index,
                    syntax.raw_block,
                    str(error),
                )
            )
            continue
        mapped_record = _map_record(
            parsed,
            index,
            source_revision_id,
            source_hash,
            source,
        )
        if validation_mode == "strict" and any(
            issue.kind is IssueKind.INVALID for issue in mapped_record[7]
        ):
            raise ValueError(f"MOL2 record {index} failed")
        mapped.append(mapped_record)
    mapped = tuple(mapped)
    structures = tuple(item[0] for item in mapped)
    topologies = tuple(item[1] for item in mapped if item[1] is not None)
    records = tuple(item[2] for item in mapped)
    annotations = tuple(value for item in mapped for value in item[3])
    datasets = tuple(value for item in mapped for value in item[4])
    provenance = tuple(item[5] for item in mapped)
    diagnostics = (
        tuple(value for item in mapped for value in item[6])
        + tuple(failure_diagnostics)
    )
    issues = tuple(issue for item in mapped for issue in item[7])
    created_ids = tuple(
        value.id
        for group in (
            structures,
            topologies,
            records,
            annotations,
            datasets,
            provenance,
        )
        for value in group
    )
    report = ParserReport(
        reader_id=_READER_ID,
        reader_version=_READER_VERSION,
        created_entity_ids=created_ids,
        parsed_capabilities=_PARSED_CAPABILITIES,
        issues=issues,
    )
    source_id = uuid5(source_revision_id, "mol2:source")
    parameters = _parameters(validation_mode, canonical_parameters)
    parameters_hash = hashlib.sha256(
        json.dumps(
            parameters,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    source_record = SourceRecord(
        id=source_id,
        display_name=Path(source).name,
        source_kind="local_file",
        created_at_utc=datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
    )
    revision = SourceRevision(
        id=source_revision_id,
        source_id=source_id,
        content_hash=source_hash,
        byte_size=len(raw_source),
        locator=str(Path(source).resolve()),
        locator_kind="absolute_path",
        original_filename=Path(source).name,
        reader_plugin_id=_PLUGIN_ID,
        reader_id=_READER_ID,
        reader_version=_READER_VERSION,
        reader_api_version=READER_API_VERSION,
        import_parameters_hash=parameters_hash,
        parse_identity=source_parse_identity(
            source_hash,
            _PLUGIN_ID,
            _READER_ID,
            _READER_VERSION,
            parameters,
        ),
        created_entity_ids=created_ids,
        diagnostic_ids=tuple(item.id for item in diagnostics),
    )
    return ImportBatch(
        sources=(source_record,),
        source_revisions=(revision,),
        structures=structures,
        topologies=topologies,
        molecular_records=records,
        annotations=annotations,
        datasets=datasets,
        provenance=provenance,
        report=report,
        diagnostics=diagnostics,
    )


def parse_mol2(source):
    source = Path(source)
    raw_source = source.read_bytes()
    source_hash = hashlib.sha256(raw_source).hexdigest()
    return _parse_bytes(
        raw_source,
        source,
        source_revision_id=uuid5(
            NAMESPACE_URL,
            f"chemblender:mol2:{source_hash}",
        ),
        source_hash=source_hash,
        validation_mode="balanced",
    )


def parse_mol2_request(request):
    parameters = tuple(sorted(request.canonical_parameters.items()))
    if parameters:
        raise ValueError("unsupported MOL2 parse parameter")
    cancelled = request.is_cancelled()
    if type(cancelled) is not bool:
        raise TypeError("is_cancelled must return bool")
    if cancelled:
        raise RuntimeError("MOL2 parse was cancelled")
    source = Path(request.source_path)
    raw_source = source.read_bytes()
    source_hash = hashlib.sha256(raw_source).hexdigest()
    if source_hash != request.source_content_hash:
        raise ValueError("source content hash mismatch")
    return _parse_bytes(
        raw_source,
        source,
        source_revision_id=request.source_revision_id,
        source_hash=source_hash,
        validation_mode=request.validation_mode,
        canonical_parameters=parameters,
    )


MOL2_READER = ReaderDescriptor(
    reader_id=_READER_ID,
    reader_version=_READER_VERSION,
    extensions=(".mol2",),
    capabilities={
        capability: CapabilitySupport.SUPPORTED
        for capability in _PARSED_CAPABILITIES
    },
    priority=120,
    sniff=sniff_mol2,
    parse=parse_mol2,
    parse_request=parse_mol2_request,
)
