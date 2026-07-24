import math
from dataclasses import dataclass
from uuid import UUID, uuid4

from .common import (
    _ID_PATTERN,
    IssueKind,
    _require_text,
    _require_token,
    _require_uuid,
    _require_uuid_tuple,
)
from .quality import DiagnosticSeverity, QualityStatus


def _canonical_diagnostic_value(value):
    if value is None:
        return ("none",)
    if type(value) is bool:
        return ("bool", value)
    if type(value) is int:
        return ("int", value)
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("diagnostic floats must be finite")
        return ("float", value)
    if type(value) is str:
        return ("str", value)
    if type(value) in (list, tuple):
        return (
            "sequence",
            tuple(_canonical_diagnostic_value(item) for item in value),
        )
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise TypeError("diagnostic mapping keys must be strings")
        return (
            "mapping",
            tuple(
                (("str", key), _canonical_diagnostic_value(value[key]))
                for key in sorted(value)
            ),
        )
    raise TypeError("diagnostic values must be canonical JSON-safe data")


def _validate_canonical_diagnostic_value(value):
    if type(value) is not tuple or not value or type(value[0]) is not str:
        raise TypeError("invalid canonical diagnostic value")
    tag = value[0]
    if tag == "none":
        valid = len(value) == 1
    elif tag == "bool":
        valid = len(value) == 2 and type(value[1]) is bool
    elif tag == "int":
        valid = len(value) == 2 and type(value[1]) is int
    elif tag == "float":
        valid = (
            len(value) == 2
            and type(value[1]) is float
            and math.isfinite(value[1])
        )
    elif tag == "str":
        valid = len(value) == 2 and type(value[1]) is str
    elif tag == "sequence":
        valid = len(value) == 2 and type(value[1]) is tuple
        if valid:
            for item in value[1]:
                _validate_canonical_diagnostic_value(item)
    elif tag == "mapping":
        valid = len(value) == 2 and type(value[1]) is tuple
        keys = []
        if valid:
            for item in value[1]:
                if (
                    type(item) is not tuple
                    or len(item) != 2
                    or type(item[0]) is not tuple
                    or item[0][:1] != ("str",)
                    or len(item[0]) != 2
                    or type(item[0][1]) is not str
                ):
                    raise TypeError("invalid canonical diagnostic mapping")
                keys.append(item[0][1])
                _validate_canonical_diagnostic_value(item[1])
            valid = keys == sorted(keys) and len(keys) == len(set(keys))
    else:
        valid = False
    if not valid:
        raise TypeError("invalid canonical diagnostic value")
    return value


def _require_optional_text(value, name):
    if value is not None:
        _require_text(value, name)


@dataclass(frozen=True, slots=True)
class DiagnosticValue:
    value: object

    def __post_init__(self):
        object.__setattr__(
            self,
            "value",
            _canonical_diagnostic_value(self.value),
        )

    @classmethod
    def _from_canonical(cls, value):
        instance = object.__new__(cls)
        object.__setattr__(
            instance,
            "value",
            _validate_canonical_diagnostic_value(value),
        )
        return instance


@dataclass(frozen=True, slots=True)
class ImportDiagnostic:
    id: UUID
    severity: DiagnosticSeverity
    quality_status: QualityStatus
    source_revision_id: UUID
    record_key: str | None
    entity_id: UUID | None
    field_path: str
    code: str
    message: str
    original_value: DiagnosticValue | None
    normalized_value: DiagnosticValue | None
    recovery_action: str | None
    scientific_consequence: str
    suggested_action: str | None

    def __post_init__(self):
        _require_uuid(self.id, "id")
        if not isinstance(self.severity, DiagnosticSeverity):
            raise TypeError("severity must be a DiagnosticSeverity")
        if not isinstance(self.quality_status, QualityStatus):
            raise TypeError("quality_status must be a QualityStatus")
        _require_uuid(self.source_revision_id, "source_revision_id")
        _require_optional_text(self.record_key, "record_key")
        if self.entity_id is not None:
            _require_uuid(self.entity_id, "entity_id")
        _require_text(self.field_path, "field_path")
        _require_token(self.code, "code", _ID_PATTERN)
        _require_text(self.message, "message")
        for value, name in (
            (self.original_value, "original_value"),
            (self.normalized_value, "normalized_value"),
        ):
            if value is not None and not isinstance(value, DiagnosticValue):
                raise TypeError(f"{name} must be a DiagnosticValue or None")
        _require_optional_text(self.recovery_action, "recovery_action")
        _require_text(self.scientific_consequence, "scientific_consequence")
        _require_optional_text(self.suggested_action, "suggested_action")


_LEGACY_ISSUE_OUTCOMES = {
    IssueKind.MISSING: (
        DiagnosticSeverity.WARNING,
        QualityStatus.INCOMPLETE,
        "required or optional source data is missing",
    ),
    IssueKind.UNSUPPORTED: (
        DiagnosticSeverity.WARNING,
        QualityStatus.INCOMPLETE,
        "the reader cannot represent this source field",
    ),
    IssueKind.AMBIGUOUS: (
        DiagnosticSeverity.WARNING,
        QualityStatus.AMBIGUOUS,
        "the scientific meaning requires review",
    ),
    IssueKind.INVALID: (
        DiagnosticSeverity.ERROR,
        QualityStatus.INVALID,
        "the source value is invalid",
    ),
    IssueKind.WARNING: (
        DiagnosticSeverity.WARNING,
        QualityStatus.PARTIAL,
        "the imported result has a reader warning",
    ),
}


def diagnostic_from_parser_issue(
    issue,
    source_revision_id,
    *,
    reader_id,
    record_key=None,
    entity_id=None,
):
    if not isinstance(issue, ParserIssue):
        raise TypeError("issue must be a ParserIssue")
    _require_uuid(source_revision_id, "source_revision_id")
    _require_token(reader_id, "reader_id", _ID_PATTERN)
    severity, quality_status, consequence = _LEGACY_ISSUE_OUTCOMES[issue.kind]
    return ImportDiagnostic(
        id=uuid4(),
        severity=severity,
        quality_status=quality_status,
        source_revision_id=source_revision_id,
        record_key=record_key,
        entity_id=entity_id,
        field_path=issue.path,
        code=f"{reader_id}.{issue.kind.value}",
        message=issue.message,
        original_value=None,
        normalized_value=None,
        recovery_action=None,
        scientific_consequence=consequence,
        suggested_action=None,
    )


@dataclass(frozen=True, slots=True)
class ParserIssue:
    kind: IssueKind
    path: str
    message: str

    def __post_init__(self):
        if not isinstance(self.kind, IssueKind):
            raise TypeError("kind must be an IssueKind")
        _require_text(self.path, "path")
        _require_text(self.message, "message")


@dataclass(frozen=True, slots=True)
class ParserReport:
    reader_id: str
    reader_version: str
    created_entity_ids: tuple[UUID, ...]
    parsed_capabilities: tuple[str, ...]
    issues: tuple[ParserIssue, ...]

    def __post_init__(self):
        _require_token(self.reader_id, "reader_id", _ID_PATTERN)
        _require_text(self.reader_version, "reader_version")
        object.__setattr__(
            self,
            "created_entity_ids",
            _require_uuid_tuple(self.created_entity_ids, "created_entity_ids"),
        )
        capabilities = tuple(self.parsed_capabilities)
        for capability in capabilities:
            _require_token(capability, "parsed_capability")
        issues = tuple(self.issues)
        if any(not isinstance(issue, ParserIssue) for issue in issues):
            raise TypeError("issues must contain ParserIssue values")
        object.__setattr__(self, "parsed_capabilities", capabilities)
        object.__setattr__(self, "issues", issues)
