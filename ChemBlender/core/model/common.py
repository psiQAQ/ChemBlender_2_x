import re
from enum import Enum
from uuid import UUID


_UNIT_PATTERN = re.compile(r"[a-z][a-z0-9_]*")
_ID_PATTERN = re.compile(r"[a-z][a-z0-9_.-]*")


def _require_uuid(value, name):
    if not isinstance(value, UUID):
        raise TypeError(f"{name} must be a UUID")


def _require_uuid_tuple(values, name):
    values = tuple(values)
    for value in values:
        _require_uuid(value, name)
    return values


def _require_token(value, name, pattern=_UNIT_PATTERN):
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(f"{name} must be a lower_snake_case token")


def _require_text(value, name):
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")


class CalculationStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    INCOMPLETE = "incomplete"


class DatasetStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    AMBIGUOUS = "ambiguous"


class IssueKind(str, Enum):
    MISSING = "missing"
    UNSUPPORTED = "unsupported"
    AMBIGUOUS = "ambiguous"
    INVALID = "invalid"
    WARNING = "warning"


class BasisFunctionKind(str, Enum):
    CARTESIAN = "cartesian"
    PURE = "pure"


class OrbitalKind(str, Enum):
    RESTRICTED = "restricted"
    UNRESTRICTED = "unrestricted"
    GENERALIZED = "generalized"


class DensityMatrixLevel(str, Enum):
    SCF = "scf"
    POST_SCF = "post_scf"


class DensityMatrixSpin(str, Enum):
    TOTAL = "total"
    SPIN = "spin"


class SpectrumKind(str, Enum):
    IR = "ir"
    RAMAN = "raman"
    UV_VIS = "uv_vis"
    ECD = "ecd"


class SpectrumProfile(str, Enum):
    STICK = "stick"
    GAUSSIAN = "gaussian"
    LORENTZIAN = "lorentzian"


class SpinChannel(str, Enum):
    ALPHA = "alpha"
    BETA = "beta"


class EnergyReference(str, Enum):
    ABSOLUTE = "absolute"
    FERMI_SHIFTED = "fermi_shifted"


class CriticalPointKind(str, Enum):
    NUCLEAR = "nuclear"
    ATTRACTOR = "attractor"
    BOND = "bond"
    RING = "ring"
    CAGE = "cage"
