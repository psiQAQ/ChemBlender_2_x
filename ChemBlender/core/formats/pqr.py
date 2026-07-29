"""Dependency-free validated whitespace PQR reader."""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from uuid import NAMESPACE_URL, uuid5

from ..model import (
    AtomicIdentityData,
    DiagnosticSeverity,
    ImportBatch,
    ImportDiagnostic,
    IssueKind,
    ParserIssue,
    ParserReport,
    ProvenanceRecord,
    QualityStatus,
    SourceRecord,
    SourceRevision,
    Structure,
    source_parse_identity,
)
from ..readers import (
    READER_API_VERSION,
    CapabilitySupport,
    ReaderDescriptor,
    SniffMatch,
    SniffResult,
)
from .pdb import (
    _ELEMENT_NUMBERS,
    _array,
    _categorical,
    _hierarchy,
    _infer_element,
    _property,
    parse_pdb_records,
)


_READER_ID = "pqr"
_READER_VERSION = "1"
_PLUGIN_ID = "chemblender.builtin"
_PARSED_CAPABILITIES = (
    "atomic_identity",
    "atomic_property",
    "hierarchy",
    "structure",
)
_RESIDUE_IDENTIFIER = re.compile(r"([+-]?\d+)([A-Za-z]?)\Z", re.ASCII)
_MAX_LINE_BYTES = 4096


class PQRSyntaxError(ValueError):
    """Stable syntax failure for a PQR document."""


class _FieldError(ValueError):
    def __init__(self, field, message):
        self.field = field
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class PQRAtomRecord:
    raw_line: bytes
    line_number: int
    dialect: str
    record_kind: str
    serial: int
    atom_name: str
    residue_name: str
    chain_id: str
    residue_number: int
    insertion_code: str
    coordinates: tuple[float, float, float]
    charge: float
    radius: float
    element: str
    element_inferred: bool = True
    alternate_location: str = ""
    segment_index: int = 0


@dataclass(frozen=True, slots=True)
class PQRRecordSet:
    raw_source: bytes
    atoms: tuple[PQRAtomRecord, ...]
    issues: tuple[ParserIssue, ...]


def _issue(kind, record_index, field, message):
    return ParserIssue(kind, f"record[{record_index}].{field}", message)


def _positive_integer(token, field):
    try:
        value = int(token)
    except ValueError as error:
        raise _FieldError(field, f"{field} must be an integer") from error
    if value <= 0:
        raise _FieldError(field, f"{field} must be positive")
    return value


def _finite_float(token, field):
    try:
        value = float(token)
    except ValueError as error:
        raise _FieldError(field, f"{field} must be numeric") from error
    if not math.isfinite(value):
        raise _FieldError(field, f"{field} must be finite")
    return value


def _label(token, field, maximum):
    if not token.isascii() or not 1 <= len(token) <= maximum:
        raise _FieldError(
            field,
            f"{field} must be a non-empty ASCII token of at most {maximum} characters",
        )
    return token


def _residue_identifier(token):
    match = _RESIDUE_IDENTIFIER.fullmatch(token)
    if match is None:
        raise _FieldError(
            "residue_number",
            "residue number must be an integer with at most one appended insertion code",
        )
    return int(match.group(1)), match.group(2)


def _atom_name_field(atom_name):
    if atom_name[0].isdigit() or len(atom_name) > 1:
        return atom_name.ljust(4)
    return f" {atom_name:<3}"


def _parse_fields(fields, dialect, raw_line, record_index):
    with_chain = dialect == "with_chain"
    serial = _positive_integer(fields[1], "serial")
    atom_name = _label(fields[2], "atom_name", 4)
    residue_name = _label(fields[3], "residue_name", 4)
    if with_chain:
        chain_id = _label(fields[4], "chain_id", 1)
        residue_index = 5
    else:
        chain_id = ""
        residue_index = 4
    residue_number, insertion_code = _residue_identifier(
        fields[residue_index]
    )
    coordinate_index = residue_index + 1
    coordinates = tuple(
        _finite_float(fields[coordinate_index + offset], field)
        for offset, field in enumerate(("x", "y", "z"))
    )
    charge = _finite_float(fields[coordinate_index + 3], "charge")
    radius = _finite_float(fields[coordinate_index + 4], "radius")
    if radius <= 0:
        raise _FieldError("radius", "radius must be positive")
    record_name = fields[0]
    element = _infer_element(
        _atom_name_field(atom_name),
        "ATOM  " if record_name == "ATOM" else "HETATM",
        residue_name.upper(),
    )
    if element is None:
        raise _FieldError(
            "element",
            "PQR atom name does not identify a recognized element",
        )
    return PQRAtomRecord(
        raw_line=raw_line,
        line_number=record_index + 1,
        dialect=dialect,
        record_kind="atom" if record_name == "ATOM" else "hetatm",
        serial=serial,
        atom_name=atom_name,
        residue_name=residue_name,
        chain_id=chain_id,
        residue_number=residue_number,
        insertion_code=insertion_code,
        coordinates=coordinates,
        charge=charge,
        radius=radius,
        element=element,
    )


def _looks_like_fixed_pdb(raw_line):
    return bool(parse_pdb_records(raw_line).atoms)


def parse_pqr_records(raw_source, *, validation_mode="balanced"):
    if not isinstance(raw_source, bytes):
        raise TypeError("raw_source must be bytes")
    mode = getattr(validation_mode, "value", validation_mode)
    if mode not in {"strict", "balanced", "maximum"}:
        raise ValueError("validation_mode must be strict, balanced or maximum")

    atoms = []
    issues = []
    for record_index, raw_line in enumerate(raw_source.splitlines(keepends=True)):
        line_bytes = raw_line.rstrip(b"\r\n")
        if len(line_bytes) > _MAX_LINE_BYTES:
            issues.append(
                _issue(
                    IssueKind.INVALID,
                    record_index,
                    "length",
                    f"PQR record exceeds {_MAX_LINE_BYTES} bytes",
                )
            )
            continue
        try:
            line = line_bytes.decode("ascii")
        except UnicodeDecodeError:
            issues.append(
                _issue(
                    IssueKind.INVALID,
                    record_index,
                    "encoding",
                    "PQR records must be ASCII",
                )
            )
            continue
        fields = line.split()
        if not fields or fields[0] not in {"ATOM", "HETATM"}:
            continue
        if _looks_like_fixed_pdb(raw_line):
            issues.append(
                _issue(
                    IssueKind.INVALID,
                    record_index,
                    "dialect",
                    "fixed-column PDB atom record is not whitespace PQR",
                )
            )
            continue

        candidates = []
        for dialect, field_count in (("no_chain", 10), ("with_chain", 11)):
            if len(fields) != field_count:
                continue
            try:
                candidates.append(
                    _parse_fields(fields, dialect, raw_line, record_index)
                )
            except _FieldError as error:
                issues.append(
                    _issue(
                        IssueKind.INVALID,
                        record_index,
                        error.field,
                        str(error),
                    )
                )
        if len(candidates) == 1:
            atom = candidates[0]
            atoms.append(atom)
            issues.append(
                _issue(
                    IssueKind.WARNING,
                    record_index,
                    "element",
                    (
                        f"inferred {atom.element} from PQR atom name "
                        "using PDB naming rules"
                    ),
                )
            )
        elif len(candidates) > 1:
            issues.append(
                _issue(
                    IssueKind.INVALID,
                    record_index,
                    "dialect",
                    "PQR atom record is ambiguous between allowed dialects",
                )
            )
        elif len(fields) not in {10, 11}:
            issues.append(
                _issue(
                    IssueKind.INVALID,
                    record_index,
                    "field_count",
                    "PQR atom record must contain exactly 10 or 11 fields",
                )
            )

    result = PQRRecordSet(raw_source, tuple(atoms), tuple(issues))
    if mode == "strict" and any(
        issue.kind is IssueKind.INVALID for issue in issues
    ):
        raise PQRSyntaxError("PQR source contains invalid records")
    return result


def sniff_pqr(source: Path, prefix: bytes) -> SniffResult:
    try:
        parsed = parse_pqr_records(prefix)
    except (PQRSyntaxError, TypeError, ValueError):
        return SniffResult(SniffMatch.NONE, "content is not validated PQR")
    if not parsed.atoms:
        return SniffResult(
            SniffMatch.NONE,
            "missing valid PQR atom with charge and radius",
        )
    try:
        truncated = Path(source).stat().st_size > len(prefix)
    except OSError:
        truncated = True
    if truncated or any(
        issue.kind is IssueKind.INVALID for issue in parsed.issues
    ):
        return SniffResult(
            SniffMatch.PROBABLE,
            "validated PQR atoms have truncated or recoverably invalid content",
        )
    return SniffResult(
        SniffMatch.EXACT,
        "complete validated PQR charge/radius content",
    )


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
                code=f"pqr.{issue.kind.value}",
                message=issue.message,
                original_value=None,
                normalized_value=None,
                recovery_action=(
                    "inferred element from PQR atom name"
                    if issue.kind is IssueKind.WARNING
                    and issue.path.endswith(".element")
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
    validation_mode = getattr(validation_mode, "value", validation_mode)
    parsed = parse_pqr_records(
        raw_source,
        validation_mode=validation_mode,
    )
    if not parsed.atoms:
        raise ValueError("PQR source contains no valid atoms")

    provenance_id = uuid5(source_revision_id, "pqr:provenance")
    provenance = ProvenanceRecord(
        id=provenance_id,
        revision=source_hash,
        producer="ChemBlender PQR reader",
        producer_version=_READER_VERSION,
        source=str(source),
        source_hash=source_hash,
        parent_ids=(),
        operation="parse",
        parameters=(("format", "pqr"),),
    )
    structure_id = uuid5(source_revision_id, "pqr:structure")
    atoms = parsed.atoms
    structure = Structure(
        id=structure_id,
        revision=source_hash,
        atomic_numbers=tuple(_ELEMENT_NUMBERS[atom.element] for atom in atoms),
        coordinates=_array(
            tuple(atom.coordinates for atom in atoms),
            ("atom", "xyz"),
            "angstrom",
            dtype="float64",
        ),
        topology_ids=(),
        atomic_identity=AtomicIdentityData(
            isotopes=_array((0,) * len(atoms), ("atom",), dtype="int64"),
            formal_charges=_array(
                (0,) * len(atoms),
                ("atom",),
                dtype="int64",
            ),
            atom_map_numbers=_array(
                (0,) * len(atoms),
                ("atom",),
                dtype="int64",
            ),
            atom_names=_categorical(tuple(atom.atom_name for atom in atoms)),
            stereo_labels=_categorical((None,) * len(atoms)),
        ),
    )
    hierarchy = _hierarchy(
        structure_id,
        source_hash,
        provenance_id,
        0,
        atoms,
    )
    datasets = (
        _property(
            structure_id,
            source_hash,
            provenance_id,
            "partial_charge",
            "elementary_charge",
            tuple(atom.charge for atom in atoms),
        ),
        _property(
            structure_id,
            source_hash,
            provenance_id,
            "radius",
            "angstrom",
            tuple(atom.radius for atom in atoms),
        ),
    )
    diagnostics = _diagnostics(source_revision_id, parsed.issues)
    created_ids = (
        structure.id,
        hierarchy.id,
        *(dataset.id for dataset in datasets),
        provenance.id,
    )
    report = ParserReport(
        reader_id=_READER_ID,
        reader_version=_READER_VERSION,
        created_entity_ids=created_ids,
        parsed_capabilities=_PARSED_CAPABILITIES,
        issues=parsed.issues,
    )
    source_id = uuid5(source_revision_id, "pqr:source")
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
        structures=(structure,),
        biological_hierarchies=(hierarchy,),
        datasets=datasets,
        provenance=(provenance,),
        report=report,
        diagnostics=diagnostics,
    )


def parse_pqr(source):
    source = Path(source)
    raw_source = source.read_bytes()
    source_hash = hashlib.sha256(raw_source).hexdigest()
    return _parse_bytes(
        raw_source,
        source,
        source_revision_id=uuid5(
            NAMESPACE_URL,
            f"chemblender:pqr:{source_hash}",
        ),
        source_hash=source_hash,
        validation_mode="balanced",
    )


def parse_pqr_request(request):
    parameters = tuple(sorted(request.canonical_parameters.items()))
    if parameters:
        raise ValueError("unsupported PQR parse parameter")
    cancelled = request.is_cancelled()
    if type(cancelled) is not bool:
        raise TypeError("is_cancelled must return bool")
    if cancelled:
        raise RuntimeError("PQR parse was cancelled")
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


PQR_READER = ReaderDescriptor(
    reader_id=_READER_ID,
    reader_version=_READER_VERSION,
    extensions=(".pqr",),
    capabilities={
        capability: CapabilitySupport.SUPPORTED
        for capability in _PARSED_CAPABILITIES
    },
    priority=125,
    sniff=sniff_pqr,
    parse=parse_pqr,
    parse_request=parse_pqr_request,
)


__all__ = (
    "PQR_READER",
    "PQRAtomRecord",
    "PQRRecordSet",
    "PQRSyntaxError",
    "parse_pqr",
    "parse_pqr_records",
    "parse_pqr_request",
    "sniff_pqr",
)
