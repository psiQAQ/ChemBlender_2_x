"""Dependency-free fixed-column PDB syntax parsing."""

from collections import Counter, defaultdict
from dataclasses import dataclass
import math
from pathlib import Path
import re

from ...Chem_data import ELEMENTS_DEFAULT
from ..model import IssueKind, ParserIssue
from ..readers import SniffMatch, SniffResult


_ELEMENT_SYMBOLS = frozenset(
    symbol for symbol, data in ELEMENTS_DEFAULT.items() if data[0] > 0
)
_SPACE_GROUP_PATTERN = re.compile(
    r"[PABCIFRH][ 0-9+\-/.ABCDMNabcdmn]*\Z",
    re.ASCII,
)
_STANDARD_POLYMER_RESIDUES = frozenset(
    {
        "ALA",
        "ARG",
        "ASN",
        "ASP",
        "ASX",
        "CYS",
        "GLN",
        "GLU",
        "GLX",
        "GLY",
        "HIS",
        "ILE",
        "LEU",
        "LYS",
        "MET",
        "PHE",
        "PRO",
        "PYL",
        "SEC",
        "SER",
        "THR",
        "TRP",
        "TYR",
        "VAL",
        "A",
        "C",
        "G",
        "I",
        "U",
        "DA",
        "DC",
        "DG",
        "DI",
        "DT",
    }
)


class PDBSyntaxError(ValueError):
    """Stable syntax failure for a PDB document."""


@dataclass(frozen=True, slots=True)
class PDBAtomRecord:
    raw_line: bytes
    line_number: int
    record_kind: str
    serial: int
    atom_name_field: str
    atom_name: str
    alternate_location: str
    residue_name: str
    chain_id: str
    residue_number: int
    insertion_code: str
    coordinates: tuple[float, float, float]
    occupancy: float | None
    b_factor: float | None
    element: str | None
    formal_charge: int | None
    element_inferred: bool
    model_number: int
    segment_index: int


@dataclass(frozen=True, slots=True)
class PDBTerRecord:
    raw_line: bytes
    line_number: int
    serial: int | None
    residue_name: str
    chain_id: str
    residue_number: int | None
    insertion_code: str
    model_number: int
    segment_index: int


@dataclass(frozen=True, slots=True)
class PDBConectRecord:
    raw_line: bytes
    line_number: int
    source_serial: int
    target_serials: tuple[int, ...]
    model_number: int | None


@dataclass(frozen=True, slots=True)
class PDBBond:
    model_number: int
    atom_serials: tuple[int, int]
    atom_indices: tuple[int, int] | None
    order: int | None


@dataclass(frozen=True, slots=True)
class PDBCryst1Record:
    raw_line: bytes
    line_number: int
    a: float
    b: float
    c: float
    alpha: float
    beta: float
    gamma: float
    space_group_field: str
    declared_space_group: str
    z_value: int | None
    source_record: str = "CRYST1"

    @property
    def cell_parameters(self):
        return (self.a, self.b, self.c, self.alpha, self.beta, self.gamma)


@dataclass(frozen=True, slots=True)
class PDBRecordSet:
    raw_source: bytes
    atoms: tuple[PDBAtomRecord, ...]
    ters: tuple[PDBTerRecord, ...]
    conect_records: tuple[PDBConectRecord, ...]
    bonds: tuple[PDBBond, ...]
    cryst1: PDBCryst1Record | None
    issues: tuple[ParserIssue, ...]


def _issue(kind, record_index, field, message):
    return ParserIssue(kind, f"record[{record_index}].{field}", message)


def _integer(field, name):
    try:
        value = int(field)
    except ValueError as error:
        raise PDBSyntaxError(f"{name} must be an integer") from error
    return value


def _float(field, name, *, optional=False):
    if optional and not field.strip():
        return None
    try:
        value = float(field)
    except ValueError as error:
        raise PDBSyntaxError(f"{name} must be numeric") from error
    if not math.isfinite(value):
        raise PDBSyntaxError(f"{name} must be finite")
    return value


def _element_symbol(field):
    if not field.strip():
        return None
    if len(field) != 2:
        return None
    if field[0] == " " and field[1].isalpha():
        symbol = field[1].upper()
    elif field[0].isalpha() and field[1].isalpha():
        symbol = field[0].upper() + field[1].lower()
    else:
        return None
    return symbol if symbol in _ELEMENT_SYMBOLS else None


def _infer_element(atom_name_field, record_name, residue_name):
    if len(atom_name_field) != 4:
        return None
    if atom_name_field[0] == " " and atom_name_field[1].isalpha():
        candidate = atom_name_field[1].upper()
    elif atom_name_field[0].isdigit() and atom_name_field[1].isalpha():
        candidate = atom_name_field[1].upper()
    elif not (
        atom_name_field[0].isalpha() and atom_name_field[1].isalpha()
    ):
        return None
    elif (
        record_name == "ATOM  "
        and residue_name == "SEC"
        and atom_name_field[:2].upper() == "SE"
    ):
        candidate = "Se"
    elif (
        record_name == "ATOM  "
        and residue_name in _STANDARD_POLYMER_RESIDUES
    ):
        candidate = atom_name_field[0].upper()
    else:
        candidate = atom_name_field[0].upper() + atom_name_field[1].lower()
    return candidate if candidate in _ELEMENT_SYMBOLS else None


def _formal_charge(field):
    text = field.strip()
    if not text:
        return None
    if len(text) != 2 or text[0] not in "123456789" or text[1] not in "+-":
        raise PDBSyntaxError("PDB charge must use magnitude followed by sign")
    magnitude = int(text[0])
    return magnitude if text[1] == "+" else -magnitude


def _parse_atom(line, raw_line, record_index, model_number, segment_index, issues):
    if len(line) < 54:
        issues.append(
            _issue(
                IssueKind.INVALID,
                record_index,
                "length",
                "ATOM/HETATM record is shorter than coordinate column 54",
            )
        )
        return None
    try:
        serial = _integer(line[6:11], "atom serial")
        residue_number = _integer(line[22:26], "residue number")
        coordinates = tuple(
            _float(line[start:end], name)
            for start, end, name in (
                (30, 38, "x coordinate"),
                (38, 46, "y coordinate"),
                (46, 54, "z coordinate"),
            )
        )
        occupancy = _float(line[54:60], "occupancy", optional=True)
        b_factor = _float(line[60:66], "B-factor", optional=True)
    except PDBSyntaxError as error:
        issues.append(_issue(IssueKind.INVALID, record_index, "syntax", str(error)))
        return None

    atom_name_field = line[12:16]
    residue_name = line[17:20].strip()
    element_field = line[76:78] if len(line) >= 78 else ""
    element = _element_symbol(element_field)
    inferred = False
    if element is None:
        field_kind = IssueKind.MISSING if not element_field.strip() else IssueKind.INVALID
        field_name = "element" if field_kind is IssueKind.MISSING else "element_column"
        inferred_element = _infer_element(atom_name_field, line[:6], residue_name)
        message = (
            "PDB element column is blank"
            if field_kind is IssueKind.MISSING
            else f"invalid PDB element column {element_field!r}"
        )
        if inferred_element is not None:
            message += f"; inferred {inferred_element} from atom-name alignment"
        issues.append(_issue(field_kind, record_index, field_name, message))
        element = inferred_element
        inferred = element is not None
        if field_kind is IssueKind.INVALID and inferred:
            issues.append(
                _issue(
                    IssueKind.WARNING,
                    record_index,
                    "element",
                    f"using inferred element {element} instead of invalid column",
                )
            )
        elif element is None:
            issues.append(
                _issue(
                    IssueKind.INVALID,
                    record_index,
                    "element",
                    "atom-name alignment does not identify a recognized element",
                )
            )

    try:
        formal_charge = _formal_charge(line[78:80] if len(line) >= 80 else "")
    except PDBSyntaxError as error:
        issues.append(_issue(IssueKind.INVALID, record_index, "charge", str(error)))
        formal_charge = None

    return PDBAtomRecord(
        raw_line=raw_line,
        line_number=record_index + 1,
        record_kind="atom" if line[:6] == "ATOM  " else "hetatm",
        serial=serial,
        atom_name_field=atom_name_field,
        atom_name=atom_name_field.strip(),
        alternate_location=line[16:17].strip(),
        residue_name=residue_name,
        chain_id=line[21:22].strip(),
        residue_number=residue_number,
        insertion_code=line[26:27].strip(),
        coordinates=coordinates,
        occupancy=occupancy,
        b_factor=b_factor,
        element=element,
        formal_charge=formal_charge,
        element_inferred=inferred,
        model_number=model_number,
        segment_index=segment_index,
    )


def _parse_ter(line, raw_line, record_index, model_number, segment_index, issues):
    if len(line) < 26:
        issues.append(
            _issue(
                IssueKind.INVALID,
                record_index,
                "length",
                "TER record is shorter than residue-number column 26",
            )
        )
        return None
    try:
        serial = None if not line[6:11].strip() else _integer(line[6:11], "TER serial")
        residue_number = (
            None
            if not line[22:26].strip()
            else _integer(line[22:26], "TER residue number")
        )
    except PDBSyntaxError as error:
        issues.append(_issue(IssueKind.INVALID, record_index, "syntax", str(error)))
        return None
    return PDBTerRecord(
        raw_line,
        record_index + 1,
        serial,
        line[17:20].strip(),
        line[21:22].strip(),
        residue_number,
        line[26:27].strip(),
        model_number,
        segment_index,
    )


def _parse_conect(line, raw_line, record_index, model_number, issues):
    if len(line) < 11:
        issues.append(
            _issue(
                IssueKind.INVALID,
                record_index,
                "length",
                "CONECT record is shorter than source serial column 11",
            )
        )
        return None
    fields = tuple(line[start : start + 5] for start in range(6, len(line), 5))
    try:
        serials = tuple(_integer(field, "CONECT serial") for field in fields if field.strip())
    except PDBSyntaxError as error:
        issues.append(_issue(IssueKind.INVALID, record_index, "syntax", str(error)))
        return None
    if len(serials) < 2:
        issues.append(
            _issue(
                IssueKind.INVALID,
                record_index,
                "targets",
                "CONECT record must contain at least one target serial",
            )
        )
        return None
    return PDBConectRecord(
        raw_line,
        record_index + 1,
        serials[0],
        serials[1:],
        model_number,
    )


def _parse_cryst1(line, raw_line, record_index, issues):
    if len(line) < 66:
        issues.append(
            _issue(
                IssueKind.INVALID,
                record_index,
                "length",
                "CRYST1 record is shorter than space-group column 66",
            )
        )
        return None
    try:
        values = tuple(
            _float(line[start:end], name)
            for start, end, name in (
                (6, 15, "cell length a"),
                (15, 24, "cell length b"),
                (24, 33, "cell length c"),
                (33, 40, "cell angle alpha"),
                (40, 47, "cell angle beta"),
                (47, 54, "cell angle gamma"),
            )
        )
        z_value = (
            None if not line[66:70].strip() else _integer(line[66:70], "CRYST1 Z")
        )
    except PDBSyntaxError as error:
        issues.append(_issue(IssueKind.INVALID, record_index, "syntax", str(error)))
        return None
    if any(value <= 0 for value in values[:3]) or any(
        not 0 < value < 180 for value in values[3:]
    ):
        issues.append(
            _issue(
                IssueKind.INVALID,
                record_index,
                "cell",
                "CRYST1 lengths must be positive and angles must be between 0 and 180",
            )
        )
        return None
    alpha, beta, gamma = (math.radians(value) for value in values[3:])
    volume_factor = (
        1
        - math.cos(alpha) ** 2
        - math.cos(beta) ** 2
        - math.cos(gamma) ** 2
        + 2 * math.cos(alpha) * math.cos(beta) * math.cos(gamma)
    )
    if volume_factor <= 1e-12:
        issues.append(
            _issue(
                IssueKind.INVALID,
                record_index,
                "cell",
                "CRYST1 angles do not define a positive-volume triclinic cell",
            )
        )
        return None
    space_group_field = line[55:66]
    space_group = space_group_field.strip()
    if not space_group:
        issues.append(
            _issue(
                IssueKind.MISSING,
                record_index,
                "space_group",
                "CRYST1 declared space group is blank",
            )
        )
    elif _SPACE_GROUP_PATTERN.fullmatch(space_group) is None:
        issues.append(
            _issue(
                IssueKind.INVALID,
                record_index,
                "space_group",
                "CRYST1 space group is outside the Hermann-Mauguin lexical envelope",
            )
        )
    if z_value is None:
        issues.append(
            _issue(
                IssueKind.MISSING,
                record_index,
                "z_value",
                "CRYST1 Z value is blank",
            )
        )
    elif z_value <= 0:
        issues.append(
            _issue(
                IssueKind.INVALID,
                record_index,
                "z_value",
                "CRYST1 Z value must be positive",
            )
        )
    return PDBCryst1Record(
        raw_line=raw_line,
        line_number=record_index + 1,
        a=values[0],
        b=values[1],
        c=values[2],
        alpha=values[3],
        beta=values[4],
        gamma=values[5],
        space_group_field=space_group_field,
        declared_space_group=space_group,
        z_value=z_value,
    )


def _resolve_bonds(atoms, records, issues):
    indices_by_key = defaultdict(list)
    for index, atom in enumerate(atoms):
        indices_by_key[atom.model_number, atom.serial].append(index)
    model_numbers = tuple(sorted({atom.model_number for atom in atoms})) or (1,)
    unique_records = tuple(
        {
            (record.model_number, record.source_serial, record.target_serials): record
            for record in records
        }.values()
    )
    directional = defaultdict(set)
    pair_models = defaultdict(set)
    for record in unique_records:
        target_counts = Counter(record.target_serials)
        scopes = (
            model_numbers
            if record.model_number is None
            else (record.model_number,)
        )
        for target, count in target_counts.items():
            if target == record.source_serial:
                for model_number in scopes:
                    issues.append(
                        ParserIssue(
                            IssueKind.INVALID,
                            (
                                f"bond[model={model_number},"
                                f"{record.source_serial},{target}].self_reference"
                            ),
                            "CONECT self-reference is invalid",
                        )
                    )
                continue
            directional[
                record.model_number,
                record.source_serial,
                target,
            ].add(count)
            pair = tuple(sorted((record.source_serial, target)))
            pair_models[pair].update(scopes)

    bonds = []
    for (first, second), scopes in sorted(pair_models.items()):
        for model_number in sorted(scopes):
            first_indices = indices_by_key[model_number, first]
            second_indices = indices_by_key[model_number, second]
            if len(first_indices) != 1 or len(second_indices) != 1:
                issues.append(
                    ParserIssue(
                        IssueKind.INVALID,
                        (
                            f"bond[model={model_number},"
                            f"{first},{second}].atom_references"
                        ),
                        (
                            "CONECT serials must each resolve to exactly one "
                            "atom in the same model"
                        ),
                    )
                )
                continue
            forward = (
                directional[None, first, second]
                | directional[model_number, first, second]
            )
            reverse = (
                directional[None, second, first]
                | directional[model_number, second, first]
            )
            order = (
                next(iter(forward))
                if len(forward) == len(reverse) == 1
                and forward == reverse
                and next(iter(forward)) > 1
                else None
            )
            if order is None:
                issues.append(
                    ParserIssue(
                        IssueKind.AMBIGUOUS,
                        f"bond[model={model_number},{first},{second}].order",
                        (
                            "CONECT establishes connectivity but not "
                            "unambiguous bond order"
                        ),
                    )
                )
            bonds.append(
                PDBBond(
                    model_number,
                    (first, second),
                    (first_indices[0], second_indices[0]),
                    order,
                )
            )
    return tuple(bonds)


def parse_pdb_records(raw_source, *, validation_mode="balanced"):
    if not isinstance(raw_source, bytes):
        raise TypeError("raw_source must be bytes")
    mode = getattr(validation_mode, "value", validation_mode)
    if mode not in {"strict", "balanced", "maximum"}:
        raise ValueError("validation_mode must be strict, balanced or maximum")

    atoms = []
    ters = []
    conect_records = []
    issues = []
    cryst1 = None
    active_model = None
    segment_indices = defaultdict(int)
    raw_lines = raw_source.splitlines(keepends=True)

    for record_index, raw_line in enumerate(raw_lines):
        try:
            line = raw_line.rstrip(b"\r\n").decode("ascii")
        except UnicodeDecodeError:
            issues.append(
                _issue(
                    IssueKind.INVALID,
                    record_index,
                    "encoding",
                    "PDB fixed-column records must be ASCII",
                )
            )
            continue
        record_name = line[:6]
        model_number = 1 if active_model is None else active_model
        if record_name in {"ATOM  ", "HETATM"}:
            atom = _parse_atom(
                line,
                raw_line,
                record_index,
                model_number,
                segment_indices[model_number],
                issues,
            )
            if atom is not None:
                atoms.append(atom)
        elif record_name == "MODEL ":
            try:
                new_model = _integer(line[10:14], "MODEL serial")
            except PDBSyntaxError as error:
                issues.append(_issue(IssueKind.INVALID, record_index, "model", str(error)))
                continue
            if active_model is not None:
                issues.append(
                    _issue(
                        IssueKind.INVALID,
                        record_index,
                        "model",
                        f"nested MODEL replaced unclosed model {active_model}",
                    )
                )
            active_model = new_model
            segment_indices[new_model] = 0
        elif record_name == "ENDMDL":
            if active_model is None:
                issues.append(
                    _issue(
                        IssueKind.INVALID,
                        record_index,
                        "model",
                        "ENDMDL has no matching MODEL",
                    )
                )
            else:
                active_model = None
        elif record_name == "TER   ":
            current_segment = segment_indices[model_number]
            ter = _parse_ter(
                line,
                raw_line,
                record_index,
                model_number,
                current_segment,
                issues,
            )
            if ter is not None:
                ters.append(ter)
            segment_indices[model_number] = current_segment + 1
        elif record_name == "CONECT":
            conect = _parse_conect(
                line,
                raw_line,
                record_index,
                active_model,
                issues,
            )
            if conect is not None:
                conect_records.append(conect)
        elif record_name == "CRYST1":
            parsed_cryst1 = _parse_cryst1(line, raw_line, record_index, issues)
            if parsed_cryst1 is not None:
                if cryst1 is None:
                    cryst1 = parsed_cryst1
                else:
                    issues.append(
                        _issue(
                            IssueKind.AMBIGUOUS,
                            record_index,
                            "cryst1",
                            "additional CRYST1 record was preserved only as source bytes",
                        )
                    )

    if active_model is not None:
        issues.append(
            ParserIssue(
                IssueKind.INVALID,
                "document.model",
                f"MODEL {active_model} has no matching ENDMDL",
            )
        )
    bonds = _resolve_bonds(tuple(atoms), tuple(conect_records), issues)
    result = PDBRecordSet(
        raw_source,
        tuple(atoms),
        tuple(ters),
        tuple(conect_records),
        bonds,
        cryst1,
        tuple(issues),
    )
    if mode == "strict" and any(issue.kind is IssueKind.INVALID for issue in issues):
        raise PDBSyntaxError("PDB source contains invalid records")
    return result


def sniff_pdb(source: Path, prefix: bytes) -> SniffResult:
    try:
        parsed = parse_pdb_records(prefix)
    except (PDBSyntaxError, TypeError, ValueError):
        return SniffResult(SniffMatch.NONE, "content is not fixed-column PDB")
    if not parsed.atoms and parsed.cryst1 is None:
        return SniffResult(
            SniffMatch.NONE,
            "missing valid PDB coordinate or CRYST1 record",
        )
    try:
        truncated = Path(source).stat().st_size > len(prefix)
    except OSError:
        truncated = True
    if truncated:
        return SniffResult(
            SniffMatch.PROBABLE,
            "valid fixed-column PDB prefix is truncated",
        )
    if parsed.issues:
        return SniffResult(
            SniffMatch.PROBABLE,
            "fixed-column PDB content has recoverable syntax issues",
        )
    return SniffResult(SniffMatch.EXACT, "complete fixed-column PDB content")


__all__ = (
    "PDBAtomRecord",
    "PDBBond",
    "PDBConectRecord",
    "PDBCryst1Record",
    "PDBRecordSet",
    "PDBSyntaxError",
    "PDBTerRecord",
    "parse_pdb_records",
    "sniff_pdb",
)
