from enum import Enum


class QualityStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    AMBIGUOUS = "ambiguous"
    INCOMPLETE = "incomplete"
    INVALID = "invalid"

    @property
    def summary_order(self):
        return _QUALITY_SUMMARY_ORDER[self]


class DiagnosticSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

    @property
    def summary_order(self):
        return _SEVERITY_SUMMARY_ORDER[self]


_QUALITY_SUMMARY_ORDER = {
    QualityStatus.COMPLETE: 0,
    QualityStatus.PARTIAL: 1,
    QualityStatus.AMBIGUOUS: 2,
    QualityStatus.INCOMPLETE: 3,
    QualityStatus.INVALID: 4,
}

_SEVERITY_SUMMARY_ORDER = {
    DiagnosticSeverity.ERROR: 0,
    DiagnosticSeverity.WARNING: 1,
    DiagnosticSeverity.INFO: 2,
}
