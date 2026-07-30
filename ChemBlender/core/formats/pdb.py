"""Dependency-free fixed-column PDB reader and syntax parsing."""

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from uuid import NAMESPACE_URL, uuid5

from ...Chem_data import ELEMENTS_DEFAULT
from ..model import (
    ArrayData,
    AtomicIdentityData,
    AtomicProperty,
    BiologicalAtomSiteData,
    BiologicalChain,
    BiologicalHierarchy,
    BiologicalModel,
    BiologicalResidue,
    CategoricalData,
    DatasetStatus,
    DiagnosticSeverity,
    FrameSet,
    ImportBatch,
    ImportDiagnostic,
    IssueKind,
    ParserIssue,
    ParserReport,
    PeriodicSiteData,
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


_ELEMENT_SYMBOLS = frozenset(
    symbol for symbol, data in ELEMENTS_DEFAULT.items() if data[0] > 0
)
_ELEMENT_NUMBERS = {
    symbol: data[0] for symbol, data in ELEMENTS_DEFAULT.items() if data[0] > 0
}
_READER_ID = "pdb"
_READER_VERSION = "1"
_PLUGIN_ID = "chemblender.builtin"
_PARSED_CAPABILITIES = (
    "atomic_identity",
    "atomic_property",
    "crystal",
    "hierarchy",
    "multi_model",
    "structure",
    "topology",
    "trajectory",
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
    model_occurrence: int
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
    model_occurrence: int
    segment_index: int


@dataclass(frozen=True, slots=True)
class PDBConectRecord:
    raw_line: bytes
    line_number: int
    source_serial: int
    target_serials: tuple[int, ...]
    model_number: int | None
    model_occurrence: int | None


@dataclass(frozen=True, slots=True)
class PDBBond:
    model_number: int
    model_occurrence: int
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
        if candidate not in "CHNOPS":
            return None
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


def _parse_atom(
    line,
    raw_line,
    record_index,
    model_number,
    model_occurrence,
    segment_index,
    issues,
):
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
    if serial <= 0:
        issues.append(
            _issue(
                IssueKind.INVALID,
                record_index,
                "serial",
                "atom serial must be positive",
            )
        )
        return None
    if occupancy is not None and not 0.0 <= occupancy <= 1.0:
        issues.append(
            _issue(
                IssueKind.INVALID,
                record_index,
                "occupancy",
                "occupancy must be between 0 and 1 or blank",
            )
        )
        occupancy = None

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
        model_occurrence=model_occurrence,
        segment_index=segment_index,
    )


def _parse_ter(
    line,
    raw_line,
    record_index,
    model_number,
    model_occurrence,
    segment_index,
    issues,
):
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
        model_occurrence,
        segment_index,
    )


def _parse_conect(
    line,
    raw_line,
    record_index,
    model_number,
    model_occurrence,
    issues,
):
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
        model_occurrence,
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
        indices_by_key[atom.model_occurrence, atom.serial].append(index)
    occurrence_numbers = {
        atom.model_occurrence: atom.model_number for atom in atoms
    }
    for record in records:
        if (
            record.model_occurrence is not None
            and record.model_number is not None
        ):
            occurrence_numbers.setdefault(
                record.model_occurrence,
                record.model_number,
            )
    if not occurrence_numbers:
        occurrence_numbers[0] = 1
    unique_records = tuple(
        {
            (
                record.model_occurrence,
                record.source_serial,
                record.target_serials,
            ): record
            for record in records
        }.values()
    )
    directional = defaultdict(set)
    pair_occurrences = defaultdict(set)
    for record in unique_records:
        target_counts = Counter(record.target_serials)
        scopes = (
            tuple(sorted(occurrence_numbers))
            if record.model_occurrence is None
            else (record.model_occurrence,)
        )
        for target, count in target_counts.items():
            if target == record.source_serial:
                for model_occurrence in scopes:
                    model_number = occurrence_numbers.get(
                        model_occurrence,
                        record.model_number,
                    )
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
                record.model_occurrence,
                record.source_serial,
                target,
            ].add(count)
            pair = tuple(sorted((record.source_serial, target)))
            pair_occurrences[pair].update(scopes)

    bonds = []
    for (first, second), scopes in sorted(pair_occurrences.items()):
        for model_occurrence in sorted(scopes):
            model_number = occurrence_numbers.get(model_occurrence, 1)
            first_indices = indices_by_key[model_occurrence, first]
            second_indices = indices_by_key[model_occurrence, second]
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
                | directional[model_occurrence, first, second]
            )
            reverse = (
                directional[None, second, first]
                | directional[model_occurrence, second, first]
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
                    model_occurrence,
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
    active_occurrence = None
    next_occurrence = 0
    seen_model_numbers = set()
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
        model_occurrence = 0 if active_occurrence is None else active_occurrence
        if record_name in {"ATOM  ", "HETATM"}:
            atom = _parse_atom(
                line,
                raw_line,
                record_index,
                model_number,
                model_occurrence,
                segment_indices[model_occurrence],
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
            next_occurrence += 1
            if new_model in seen_model_numbers:
                issues.append(
                    _issue(
                        IssueKind.AMBIGUOUS,
                        record_index,
                        "model",
                        (
                            f"MODEL serial {new_model} is repeated in "
                            f"occurrence {next_occurrence}; source blocks "
                            "remain distinct"
                        ),
                    )
                )
            seen_model_numbers.add(new_model)
            active_model = new_model
            active_occurrence = next_occurrence
            segment_indices[active_occurrence] = 0
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
                active_occurrence = None
        elif record_name == "TER   ":
            current_segment = segment_indices[model_occurrence]
            ter = _parse_ter(
                line,
                raw_line,
                record_index,
                model_number,
                model_occurrence,
                current_segment,
                issues,
            )
            if ter is not None:
                ters.append(ter)
            segment_indices[model_occurrence] = current_segment + 1
        elif record_name == "CONECT":
            conect = _parse_conect(
                line,
                raw_line,
                record_index,
                active_model,
                active_occurrence,
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


def _atom_identity(atom):
    return (
        atom.record_kind,
        atom.chain_id,
        atom.residue_number,
        atom.insertion_code,
        atom.residue_name,
        atom.atom_name,
        atom.alternate_location,
    )


def _cell(cryst1):
    import numpy

    alpha, beta, gamma = map(
        math.radians,
        (cryst1.alpha, cryst1.beta, cryst1.gamma),
    )
    sin_gamma = math.sin(gamma)
    c_x = cryst1.c * math.cos(beta)
    c_y = cryst1.c * (
        math.cos(alpha) - math.cos(beta) * math.cos(gamma)
    ) / sin_gamma
    c_z = math.sqrt(max(0.0, cryst1.c**2 - c_x**2 - c_y**2))
    return _array(
        numpy.asarray(
            (
                (cryst1.a, 0.0, 0.0),
                (
                    cryst1.b * math.cos(gamma),
                    cryst1.b * sin_gamma,
                    0.0,
                ),
                (c_x, c_y, c_z),
            ),
            dtype=numpy.float64,
        ),
        ("cell_vector", "xyz"),
        "angstrom",
    )


def _periodic(atoms, coordinates, cell, cryst1):
    import numpy

    fractional = numpy.asarray(coordinates.values) @ numpy.linalg.inv(
        numpy.asarray(cell.values)
    )
    return PeriodicSiteData(
        fractional_coordinates=_array(
            fractional,
            ("atom", "xyz"),
            dtype="float64",
        ),
        site_labels=tuple(
            atom.atom_name or f"atom-{atom.serial}" for atom in atoms
        ),
        occupancies=_array(
            tuple(
                math.nan if atom.occupancy is None else atom.occupancy
                for atom in atoms
            ),
            ("atom",),
            dtype="float64",
        ),
        isotropic_displacements=None,
        anisotropic_displacements=None,
        adp_types=("none",) * len(atoms),
        disorder_groups=(0,) * len(atoms),
        declared_space_group_name=(
            cryst1.declared_space_group
            if _SPACE_GROUP_PATTERN.fullmatch(cryst1.declared_space_group)
            else None
        ),
        declared_space_group_number=None,
        symmetry_operations=(),
        cif_envelope_id=None,
    )


def _topologies(
    structure_id,
    source_hash,
    provenance_id,
    group,
    bonds_by_occurrence,
):
    import numpy

    reference = group[0]
    reference_indices_by_global = {
        global_index: index
        for index, (global_index, _atom) in enumerate(reference["atoms"])
    }
    reference_indices_by_identity = {
        _atom_identity(atom): index
        for index, (_global_index, atom) in enumerate(reference["atoms"])
    }
    result = []
    for model in group:
        model_number = model["number"]
        model_occurrence = model["occurrence"]
        edges = {}
        atoms_by_global = dict(model["atoms"])
        for bond in bonds_by_occurrence[model_occurrence]:
            if bond.atom_indices is None:
                continue
            try:
                if model_occurrence == reference["occurrence"]:
                    endpoints = tuple(
                        reference_indices_by_global[index]
                        for index in bond.atom_indices
                    )
                else:
                    endpoints = tuple(
                        reference_indices_by_identity[
                            _atom_identity(atoms_by_global[index])
                        ]
                        for index in bond.atom_indices
                    )
            except KeyError:
                continue
            edge = tuple(sorted(endpoints))
            order = 0.0 if bond.order is None else float(bond.order)
            previous = edges.get(edge)
            edges[edge] = order if previous in (None, order) else 0.0
        if not edges:
            continue
        ordered = tuple(sorted(edges.items()))
        topology = TopologyRecord(
            id=uuid5(
                structure_id,
                (
                    f"topology:model:{model_number}:"
                    f"occurrence:{model_occurrence}"
                ),
            ),
            revision=source_hash,
            structure_id=structure_id,
            bond_indices=ArrayData(
                numpy.asarray(
                    tuple(edge for edge, _order in ordered),
                    dtype=numpy.int64,
                ).reshape((-1, 2)),
                ("bond", "endpoint"),
                "dimensionless",
            ),
            bond_orders=_array(
                tuple(order for _edge, order in ordered),
                ("bond",),
                dtype="float64",
            ),
            aromatic_flags=None,
            stereo_labels=("",) * len(ordered),
            source_kind=TopologySource.EXPLICIT_FILE,
            quality_status=(
                QualityStatus.AMBIGUOUS
                if any(order == 0.0 for _edge, order in ordered)
                else QualityStatus.COMPLETE
            ),
            inference_parameters=(
                ("model_number", model_number),
                ("model_occurrence", model_occurrence),
            ),
            provenance_ids=(provenance_id,),
        )
        result.append(topology)
    return tuple(result)


def _hierarchy(
    structure_id,
    source_hash,
    provenance_id,
    model_number,
    atoms,
):
    chain_indices = {}
    chains = []
    residue_indices = {}
    residues = []
    atom_residue_indices = []
    for atom in atoms:
        chain_key = (atom.chain_id, atom.segment_index)
        chain_index = chain_indices.get(chain_key)
        if chain_index is None:
            chain_index = len(chains)
            chain_indices[chain_key] = chain_index
            chains.append(BiologicalChain(*chain_key))
        residue_key = (
            chain_index,
            atom.residue_number,
            atom.insertion_code,
            atom.record_kind == "hetatm",
        )
        residue_index = residue_indices.get(residue_key)
        if residue_index is None:
            residue_index = len(residues)
            residue_indices[residue_key] = residue_index
            residues.append(
                BiologicalResidue(
                    chain_index,
                    atom.residue_name,
                    atom.residue_number,
                    atom.insertion_code,
                    atom.record_kind == "hetatm",
                )
            )
        elif residues[residue_index].residue_name != atom.residue_name:
            raise ValueError(
                "PDB residue identity conflicts within one chain segment"
            )
        atom_residue_indices.append(residue_index)
    return BiologicalHierarchy(
        id=uuid5(structure_id, "hierarchy"),
        revision=source_hash,
        structure_id=structure_id,
        model=BiologicalModel(model_number if model_number > 0 else None),
        chains=tuple(chains),
        residues=tuple(residues),
        atom_sites=BiologicalAtomSiteData(
            serial_numbers=_array(
                tuple(atom.serial for atom in atoms),
                ("atom",),
                dtype="int64",
            ),
            residue_indices=_array(
                atom_residue_indices,
                ("atom",),
                dtype="int64",
            ),
            alternate_locations=_categorical(
                tuple(
                    atom.alternate_location or None
                    for atom in atoms
                )
            ),
            record_kinds=_categorical(
                tuple(atom.record_kind for atom in atoms)
            ),
        ),
        provenance_ids=(provenance_id,),
    )


def _property(
    structure_id,
    source_hash,
    provenance_id,
    role,
    unit,
    values,
):
    complete = all(value is not None for value in values)
    return AtomicProperty(
        id=uuid5(structure_id, f"property:{role}"),
        revision=source_hash,
        semantic_role=role,
        domain="atom",
        data=_array(
            tuple(math.nan if value is None else value for value in values),
            ("atom",),
            unit,
            dtype="float64",
        ),
        status=DatasetStatus.COMPLETE if complete else DatasetStatus.PARTIAL,
        source_calculation=None,
        provenance_ids=(provenance_id,),
        structure_id=structure_id,
    )


def _groups(atoms, issues):
    models = {}
    for global_index, atom in enumerate(atoms):
        models.setdefault(atom.model_occurrence, []).append((global_index, atom))
    groups = []
    compatible = {}
    baseline_identities = None
    for model_occurrence, model_atoms in models.items():
        model_number = model_atoms[0][1].model_number
        if model_number <= 0:
            issues.append(
                ParserIssue(
                    IssueKind.INVALID,
                    f"model[{model_number}].number",
                    "PDB MODEL number must be positive",
                )
            )
        identities = tuple(_atom_identity(atom) for _index, atom in model_atoms)
        duplicates = tuple(sorted(
            (identity, count)
            for identity, count in Counter(identities).items()
            if count > 1
        ))
        if duplicates:
            issues.append(
                ParserIssue(
                    IssueKind.INVALID,
                    f"model[{model_number}].identity",
                    (
                        "duplicate seven-field atom identity prevents MODEL "
                        f"alignment: duplicates={duplicates!r}"
                    ),
                )
            )
            key = ("duplicate", model_occurrence)
        else:
            key = frozenset(identities)
        identity_set = frozenset(identities)
        if baseline_identities is None:
            baseline_identities = identity_set
        group_index = compatible.get(key)
        if group_index is None:
            if groups and not duplicates:
                missing = tuple(sorted(baseline_identities - identity_set))
                additional = tuple(sorted(identity_set - baseline_identities))
                issues.append(
                    ParserIssue(
                        IssueKind.WARNING,
                        f"model[{model_number}].identity",
                        (
                            "MODEL identity set differs from the reference "
                            f"model: missing={missing!r}; "
                            f"additional={additional!r}; created an "
                            "independent Structure"
                        ),
                    )
                )
            group_index = len(groups)
            compatible[key] = group_index
            groups.append([])
        groups[group_index].append(
            {
                "number": model_number,
                "occurrence": model_occurrence,
                "atoms": tuple(model_atoms),
            }
        )
    return tuple(tuple(group) for group in groups)


def _isolate_residue_conflicts(atoms, issues):
    residue_names = {}
    retained = []
    for atom in atoms:
        key = (
            atom.model_occurrence,
            atom.chain_id,
            atom.segment_index,
            atom.residue_number,
            atom.insertion_code,
            atom.record_kind == "hetatm",
        )
        previous = residue_names.get(key)
        if previous is not None and previous != atom.residue_name:
            issues.append(
                _issue(
                    IssueKind.INVALID,
                    atom.line_number - 1,
                    "residue_name",
                    (
                        f"residue key was first labeled {previous!r} and "
                        f"conflicts with {atom.residue_name!r}; isolated "
                        "the conflicting atom record"
                    ),
                )
            )
            continue
        residue_names[key] = atom.residue_name
        retained.append(atom)
    return tuple(retained)


def _diagnostics(source_revision_id, issues):
    outcomes = {
        IssueKind.MISSING: (
            DiagnosticSeverity.WARNING,
            QualityStatus.INCOMPLETE,
            "source data is missing",
        ),
        IssueKind.UNSUPPORTED: (
            DiagnosticSeverity.WARNING,
            QualityStatus.INCOMPLETE,
            "source data is preserved but not represented as a typed entity",
        ),
        IssueKind.AMBIGUOUS: (
            DiagnosticSeverity.WARNING,
            QualityStatus.AMBIGUOUS,
            "scientific meaning requires review",
        ),
        IssueKind.INVALID: (
            DiagnosticSeverity.ERROR,
            QualityStatus.INVALID,
            "invalid source data was not mapped as valid scientific data",
        ),
        IssueKind.WARNING: (
            DiagnosticSeverity.WARNING,
            QualityStatus.PARTIAL,
            "the source was recovered with a reader warning",
        ),
    }
    occurrences = Counter()
    diagnostics = []
    for issue in issues:
        occurrence_key = (issue.kind.value, issue.path)
        occurrence = occurrences[occurrence_key]
        occurrences[occurrence_key] += 1
        severity, quality, consequence = outcomes[issue.kind]
        diagnostics.append(
            ImportDiagnostic(
                id=uuid5(
                    source_revision_id,
                    (
                        f"diagnostic:{issue.kind.value}:{issue.path}:"
                        f"{occurrence}"
                    ),
                ),
                severity=severity,
                quality_status=quality,
                source_revision_id=source_revision_id,
                record_key=None,
                entity_id=None,
                field_path=issue.path,
                code=f"pdb.{issue.kind.value}",
                message=issue.message,
                original_value=None,
                normalized_value=None,
                recovery_action=(
                    "retained valid PDB models as independent Structures"
                    if issue.path.endswith(".identity")
                    else None
                ),
                scientific_consequence=consequence,
                suggested_action=None,
            )
        )
    return tuple(diagnostics)


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
    parsed = parse_pdb_records(raw_source, validation_mode=validation_mode)
    if not parsed.atoms:
        raise ValueError("PDB source contains no valid atoms")
    issues = list(parsed.issues)
    atoms = _isolate_residue_conflicts(parsed.atoms, issues)
    groups = _groups(atoms, issues)
    if validation_mode == "strict" and any(
        issue.kind is IssueKind.INVALID for issue in issues
    ):
        raise PDBSyntaxError("PDB source contains invalid model mapping")

    provenance_id = uuid5(source_revision_id, "pdb:provenance")
    provenance_parameters = [("format", "pdb")]
    if parsed.cryst1 is not None:
        provenance_parameters.extend(
            (
                ("cryst1_source_record", parsed.cryst1.source_record),
                ("cryst1_space_group_field", parsed.cryst1.space_group_field),
                ("cryst1_z", parsed.cryst1.z_value),
            )
        )
    provenance = ProvenanceRecord(
        id=provenance_id,
        revision=source_hash,
        producer="ChemBlender PDB reader",
        producer_version=_READER_VERSION,
        source=str(source),
        source_hash=source_hash,
        parent_ids=(),
        operation="parse",
        parameters=tuple(provenance_parameters),
    )

    structures = []
    topologies = []
    hierarchies = []
    datasets = []
    bonds_by_occurrence = defaultdict(list)
    for bond in parsed.bonds:
        bonds_by_occurrence[bond.model_occurrence].append(bond)
    for group_index, group in enumerate(groups):
        model_occurrences = ",".join(
            f"{model['occurrence']}:{model['number']}" for model in group
        )
        structure_id = uuid5(
            source_revision_id,
            f"pdb:structure:{group_index}:models:{model_occurrences}",
        )
        reference = group[0]
        reference_atoms = tuple(atom for _index, atom in reference["atoms"])
        group_topologies = _topologies(
            structure_id,
            source_hash,
            provenance_id,
            group,
            bonds_by_occurrence,
        )
        coordinates = _array(
            tuple(atom.coordinates for atom in reference_atoms),
            ("atom", "xyz"),
            "angstrom",
            dtype="float64",
        )
        cell = None if parsed.cryst1 is None else _cell(parsed.cryst1)
        structure = Structure(
            id=structure_id,
            revision=source_hash,
            atomic_numbers=tuple(
                0 if atom.element is None else _ELEMENT_NUMBERS[atom.element]
                for atom in reference_atoms
            ),
            coordinates=coordinates,
            cell=cell,
            periodic=(
                None
                if parsed.cryst1 is None
                else _periodic(
                    reference_atoms,
                    coordinates,
                    cell,
                    parsed.cryst1,
                )
            ),
            topology_ids=tuple(value.id for value in group_topologies),
            atomic_identity=AtomicIdentityData(
                isotopes=_array(
                    (0,) * len(reference_atoms),
                    ("atom",),
                    dtype="int64",
                ),
                formal_charges=_array(
                    tuple(atom.formal_charge or 0 for atom in reference_atoms),
                    ("atom",),
                    dtype="int64",
                ),
                atom_map_numbers=_array(
                    (0,) * len(reference_atoms),
                    ("atom",),
                    dtype="int64",
                ),
                atom_names=_categorical(
                    tuple(atom.atom_name or None for atom in reference_atoms)
                ),
                stereo_labels=_categorical((None,) * len(reference_atoms)),
            ),
        )
        hierarchy = _hierarchy(
            structure_id,
            source_hash,
            provenance_id,
            reference["number"],
            reference_atoms,
        )
        group_datasets = [
            _property(
                structure_id,
                source_hash,
                provenance_id,
                "occupancy",
                "dimensionless",
                tuple(atom.occupancy for atom in reference_atoms),
            ),
            _property(
                structure_id,
                source_hash,
                provenance_id,
                "b_factor",
                "angstrom_squared",
                tuple(atom.b_factor for atom in reference_atoms),
            ),
        ]
        if len(group) > 1:
            reference_order = {
                _atom_identity(atom): index
                for index, atom in enumerate(reference_atoms)
            }
            frame_values = []
            for model in group:
                ordered = [None] * len(reference_atoms)
                for _global_index, atom in model["atoms"]:
                    ordered[reference_order[_atom_identity(atom)]] = atom.coordinates
                frame_values.append(tuple(ordered))
            group_datasets.append(
                FrameSet(
                    id=uuid5(structure_id, "frames"),
                    revision=source_hash,
                    semantic_role="coordinates",
                    domain="frame",
                    data=_array(
                        frame_values,
                        ("frame", "atom", "xyz"),
                        "angstrom",
                        dtype="float64",
                    ),
                    status=DatasetStatus.COMPLETE,
                    source_calculation=None,
                    provenance_ids=(provenance_id,),
                    structure_id=structure_id,
                    comments=tuple(
                        f"MODEL {model['number']}" for model in group
                    ),
                )
            )
        structures.append(structure)
        topologies.extend(group_topologies)
        hierarchies.append(hierarchy)
        datasets.extend(group_datasets)

    structures = tuple(structures)
    topologies = tuple(topologies)
    hierarchies = tuple(hierarchies)
    datasets = tuple(datasets)
    diagnostics = _diagnostics(source_revision_id, tuple(issues))
    created_ids = tuple(
        value.id
        for values in (
            structures,
            topologies,
            hierarchies,
            datasets,
            (provenance,),
        )
        for value in values
    )
    report = ParserReport(
        reader_id=_READER_ID,
        reader_version=_READER_VERSION,
        created_entity_ids=created_ids,
        parsed_capabilities=_PARSED_CAPABILITIES,
        issues=tuple(issues),
    )
    source_id = uuid5(source_revision_id, "pdb:source")
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
        diagnostic_ids=tuple(value.id for value in diagnostics),
    )
    return ImportBatch(
        sources=(source_record,),
        source_revisions=(revision,),
        structures=structures,
        topologies=topologies,
        biological_hierarchies=hierarchies,
        datasets=datasets,
        provenance=(provenance,),
        report=report,
        diagnostics=diagnostics,
    )


def parse_pdb(source):
    source = Path(source)
    raw_source = source.read_bytes()
    source_hash = hashlib.sha256(raw_source).hexdigest()
    return _parse_bytes(
        raw_source,
        source,
        source_revision_id=uuid5(
            NAMESPACE_URL,
            f"chemblender:pdb:{source_hash}",
        ),
        source_hash=source_hash,
        validation_mode="balanced",
    )


def parse_pdb_request(request):
    parameters = tuple(sorted(request.canonical_parameters.items()))
    if parameters:
        raise ValueError("unsupported PDB parse parameter")
    cancelled = request.is_cancelled()
    if type(cancelled) is not bool:
        raise TypeError("is_cancelled must return bool")
    if cancelled:
        raise RuntimeError("PDB parse was cancelled")
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


PDB_READER = ReaderDescriptor(
    reader_id=_READER_ID,
    reader_version=_READER_VERSION,
    extensions=(".pdb",),
    capabilities={
        "atomic_identity": CapabilitySupport.SUPPORTED,
        "atomic_property": CapabilitySupport.SUPPORTED,
        "crystal": CapabilitySupport.PARTIAL,
        "hierarchy": CapabilitySupport.SUPPORTED,
        "multi_model": CapabilitySupport.SUPPORTED,
        "structure": CapabilitySupport.SUPPORTED,
        "topology": CapabilitySupport.PARTIAL,
        "trajectory": CapabilitySupport.SUPPORTED,
    },
    priority=120,
    sniff=sniff_pdb,
    parse=parse_pdb,
    parse_request=parse_pdb_request,
)


__all__ = (
    "PDB_READER",
    "PDBAtomRecord",
    "PDBBond",
    "PDBConectRecord",
    "PDBCryst1Record",
    "PDBRecordSet",
    "PDBSyntaxError",
    "PDBTerRecord",
    "parse_pdb",
    "parse_pdb_request",
    "parse_pdb_records",
    "sniff_pdb",
)
