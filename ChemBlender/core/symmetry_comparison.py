from dataclasses import dataclass

from .model import ArrayData, DeclaredSymmetry, SymmetryResult


_STATUSES = {
    "match",
    "equivalent_after_setting",
    "different",
    "insufficient_data",
}


@dataclass(frozen=True, slots=True)
class SymmetryComparison:
    status: str
    details: tuple[str, ...]

    def __post_init__(self):
        if self.status not in _STATUSES:
            raise ValueError("unsupported symmetry comparison status")
        details = tuple(self.details)
        if any(not isinstance(value, str) or not value for value in details):
            raise ValueError("details must contain non-empty strings")
        object.__setattr__(self, "details", details)


def _symbol(value):
    return "".join(value.split()).casefold() if value is not None else None


def _explicit_transformation(value):
    import numpy

    if not isinstance(value, ArrayData):
        raise TypeError("setting_transformation must be ArrayData or None")
    if value.shape != (3, 3) or value.unit != "dimensionless":
        raise ValueError(
            "setting_transformation must be a dimensionless 3 by 3 matrix"
        )
    matrix = numpy.asarray(value.values)
    if matrix.dtype.kind not in "iuf" or not numpy.all(numpy.isfinite(matrix)):
        raise ValueError("setting_transformation must be finite and real")


def compare_symmetry(
    declared,
    derived,
    *,
    setting_transformation=None,
):
    if not isinstance(declared, DeclaredSymmetry):
        raise TypeError("declared must be DeclaredSymmetry")
    if not isinstance(derived, SymmetryResult):
        raise TypeError("derived must be SymmetryResult")
    if setting_transformation is not None:
        _explicit_transformation(setting_transformation)

    comparable = False
    differences = []
    if declared.international_number is not None:
        comparable = True
        if declared.international_number != derived.international_number:
            differences.append(
                "declared and derived international numbers differ"
            )
    if declared.name is not None:
        comparable = True
        if _symbol(declared.name) != _symbol(derived.international_symbol):
            differences.append(
                "declared and derived international symbols differ"
            )
    if declared.hall_symbol is not None:
        comparable = True
        if _symbol(declared.hall_symbol) != _symbol(derived.hall_symbol):
            differences.append("declared and derived Hall symbols differ")
    if not comparable:
        return SymmetryComparison(
            "insufficient_data",
            ("declared symmetry has no comparable group identity",),
        )
    if not differences:
        return SymmetryComparison(
            "match",
            ("declared and derived group identity match",),
        )
    if (
        setting_transformation is not None
        and declared.international_number == derived.international_number
    ):
        return SymmetryComparison(
            "equivalent_after_setting",
            tuple(differences)
            + ("an explicit setting transformation was supplied",),
        )
    return SymmetryComparison("different", tuple(differences))


__all__ = (
    "SymmetryComparison",
    "compare_symmetry",
)
