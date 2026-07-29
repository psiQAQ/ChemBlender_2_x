"""Dependency-free Tripos MOL2 syntax parser."""

import math
import re
from dataclasses import dataclass
from pathlib import Path

from ...Chem_data import ELEMENTS_DEFAULT
from ..model import IssueKind, ParserIssue
from ..readers import SniffMatch, SniffResult


_SECTION_HEADER = re.compile(r"@<TRIPOS>([A-Z0-9_]+)", re.ASCII | re.IGNORECASE)
_ELEMENT_SYMBOLS = frozenset(
    symbol for symbol, data in ELEMENTS_DEFAULT.items() if data[0] > 0
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
    bonds = tuple(
        _parse_bond(line, index, atom_indices, issues)
        for index, line in enumerate(bond_lines)
    )
    if len(bonds) != counts.bond_count:
        raise ValueError("MOL2 BOND section does not match the declared count")
    if len({bond.bond_id for bond in bonds}) != len(bonds):
        raise ValueError("MOL2 bond IDs must be unique")

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
        not any(bond.atom_indices is None or bond.unknown for bond in bonds)
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
