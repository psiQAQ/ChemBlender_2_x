"""Optional symmetry capability and presentation helpers."""

from .model import Structure, SymmetryResult
from .spglib_adapter import derive_symmetry, spglib_availability
from .symmetry_comparison import compare_symmetry


def symmetry_availability():
    return spglib_availability()


def derive_structure_symmetry(
    structure,
    *,
    symprec=1.0e-5,
    angle_tolerance=-1.0,
    hall_number=0,
):
    return derive_symmetry(
        structure,
        symprec=symprec,
        angle_tolerance=angle_tolerance,
        hall_number=hall_number,
    )


def symmetry_comparison_rows(structure, derived=None):
    if not isinstance(structure, Structure) or structure.periodic is None:
        raise TypeError("structure must be a periodic Structure")
    if derived is None:
        return (
            ("Status", "Not derived"),
            ("Symprec", "Not derived"),
            ("Angle tolerance", "Not derived"),
            ("Standardized Structure", "Not derived"),
        )
    if (
        not isinstance(derived, SymmetryResult)
        or derived.structure_id != structure.id
    ):
        raise ValueError("derived symmetry must belong to structure")
    comparison = compare_symmetry(
        structure.periodic.declared_symmetry,
        derived,
        setting_transformation=derived.transformation_matrix,
    )
    angle = (
        "automatic"
        if derived.angle_tolerance == -1.0
        else f"{derived.angle_tolerance:g}°"
    )
    return (
        ("Status", comparison.status.replace("_", " ").title()),
        ("Symprec", f"{derived.symprec:g} Å"),
        ("Angle tolerance", angle),
        ("Standardized Structure", str(derived.standardized_structure_id)),
        ("Details", "; ".join(comparison.details)),
    )


__all__ = (
    "derive_structure_symmetry",
    "symmetry_availability",
    "symmetry_comparison_rows",
)
