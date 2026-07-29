"""Deterministic native POSCAR/CONTCAR export."""

from dataclasses import dataclass
import math

from ...Chem_data import ELEMENTS_DEFAULT
from ..formats.poscar import PoscarLatticeVelocityBlock
from ..model import AtomicProperty, ImportBatch, Structure
from .xyz import ExportReport, ExportReportEntry, atomic_write_chunks


_SYMBOLS = {
    data[0]: symbol
    for symbol, data in ELEMENTS_DEFAULT.items()
    if 0 < data[0] <= 118
}


def _positive(value, name):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0.0
    ):
        raise ValueError(f"{name} must be finite and positive")
    return float(value)


def _nonzero(value, name):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value == 0.0
    ):
        raise ValueError(f"{name} must be finite and non-zero")
    return float(value)


@dataclass(frozen=True, slots=True)
class PoscarExportSettings:
    comment: str = "ChemBlender"
    coordinate_mode: str = "direct"
    scale_policy: str = "unit"
    target_volume: float | None = None
    source_scale: float | None = None
    include_selective_dynamics: bool = True
    velocity_mode: str = "cartesian"

    def __post_init__(self):
        if not isinstance(self.comment, str) or "\n" in self.comment or "\r" in self.comment:
            raise ValueError("comment must be one line")
        if self.coordinate_mode not in {"direct", "cartesian"}:
            raise ValueError("coordinate_mode must be direct or cartesian")
        if self.velocity_mode not in {"direct", "cartesian"}:
            raise ValueError("velocity_mode must be direct or cartesian")
        if self.scale_policy not in {"unit", "preserve_source", "target_volume"}:
            raise ValueError(
                "scale_policy must be unit, preserve_source or target_volume"
            )
        if type(self.include_selective_dynamics) is not bool:
            raise TypeError("include_selective_dynamics must be a bool")
        if self.scale_policy == "unit":
            if self.target_volume is not None or self.source_scale is not None:
                raise ValueError("unit scale policy takes no scale value")
        elif self.scale_policy == "preserve_source":
            _nonzero(self.source_scale, "source_scale")
            if self.target_volume is not None:
                raise ValueError("preserve_source does not take target_volume")
        else:
            _positive(self.target_volume, "target_volume")
            if self.source_scale is not None:
                raise ValueError("target_volume does not take source_scale")


def _number(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("POSCAR numeric values must be finite")
    return format(0.0 if value == 0.0 else value, ".17g")


def _structure_data(structure):
    import numpy

    if not isinstance(structure, Structure) or structure.periodic is None:
        raise TypeError("POSCAR export requires a periodic Structure")
    if structure.cell is None or structure.cell.unit != "angstrom":
        raise ValueError("POSCAR export requires an angstrom cell")
    if structure.coordinates.unit != "angstrom":
        raise ValueError("POSCAR export requires angstrom coordinates")
    try:
        symbols = tuple(_SYMBOLS[value] for value in structure.atomic_numbers)
    except KeyError as error:
        raise ValueError(
            f"POSCAR export does not support atomic number {error.args[0]}"
        ) from error
    cell = numpy.asarray(structure.cell.values, dtype=float)
    cartesian = numpy.asarray(structure.coordinates.values, dtype=float)
    fractional = numpy.asarray(
        structure.periodic.fractional_coordinates.values,
        dtype=float,
    )
    if (
        not numpy.all(numpy.isfinite(cell))
        or not numpy.all(numpy.isfinite(cartesian))
        or not numpy.all(numpy.isfinite(fractional))
        or abs(float(numpy.linalg.det(cell))) < 1.0e-12
    ):
        raise ValueError("POSCAR cell and coordinates must be finite and non-singular")
    return symbols, cell, cartesian, fractional


def _grouped_indices(symbols):
    order = tuple(dict.fromkeys(symbols))
    return (
        order,
        tuple(symbols.count(symbol) for symbol in order),
        tuple(
            index
            for symbol in order
            for index, value in enumerate(symbols)
            if value == symbol
        ),
    )


def _scale(settings, cell):
    import numpy

    volume = abs(float(numpy.linalg.det(cell)))
    if settings.scale_policy == "unit":
        return 1.0, 1.0
    if settings.scale_policy == "preserve_source":
        scale = float(settings.source_scale)
        if scale > 0.0:
            return scale, scale
        if not math.isclose(-scale, volume, rel_tol=1.0e-10, abs_tol=1.0e-10):
            raise ValueError("source_scale volume does not match the scientific cell")
        return scale, 1.0
    target = float(settings.target_volume)
    if not math.isclose(target, volume, rel_tol=1.0e-10, abs_tol=1.0e-10):
        raise ValueError("target_volume does not match the scientific cell")
    return -target, 1.0


def _atomic_values(dataset, structure, role, dtype):
    import numpy

    if dataset is None:
        return None
    if (
        not isinstance(dataset, AtomicProperty)
        or dataset.structure_id != structure.id
        or dataset.semantic_role != role
        or dataset.data.dims != ("atom", "xyz")
        or dataset.data.shape != (len(structure.atomic_numbers), 3)
    ):
        raise ValueError(f"{role} must be a matching (atom, xyz) AtomicProperty")
    values = numpy.asarray(dataset.data.values, dtype=dtype)
    if dtype is not numpy.bool_ and not numpy.all(numpy.isfinite(values)):
        raise ValueError(f"{role} values must be finite")
    return values


def _rows(values):
    return tuple(" ".join(_number(value) for value in row) for row in values)


def _document(
    structure,
    settings,
    *,
    selective_dynamics,
    velocities,
    lattice_velocities,
):
    import numpy

    symbols, cell, cartesian, fractional = _structure_data(structure)
    species, counts, indices = _grouped_indices(symbols)
    scale, factor = _scale(settings, cell)
    coordinates = (
        fractional
        if settings.coordinate_mode == "direct"
        else cartesian / factor
    )
    selective = _atomic_values(
        selective_dynamics,
        structure,
        "selective_dynamics",
        numpy.bool_,
    )
    velocity_values = _atomic_values(
        velocities,
        structure,
        "atomic_velocity",
        numpy.float64,
    )
    lines = [
        settings.comment,
        _number(scale),
        *_rows(cell / factor),
        " ".join(species),
        " ".join(str(value) for value in counts),
    ]
    if selective is not None and settings.include_selective_dynamics:
        lines.append("Selective dynamics")
    lines.append("Direct" if settings.coordinate_mode == "direct" else "Cartesian")
    for index in indices:
        row = _rows((coordinates[index],))[0]
        if selective is not None and settings.include_selective_dynamics:
            row += " " + " ".join(
                "T" if value else "F" for value in selective[index]
            )
        lines.append(row)
    if lattice_velocities is not None:
        if not isinstance(lattice_velocities, PoscarLatticeVelocityBlock):
            raise TypeError(
                "lattice_velocities must be PoscarLatticeVelocityBlock or None"
            )
        lines.extend(
            (
                "Lattice velocities and vectors",
                _number(lattice_velocities.initialization_state),
                *_rows(lattice_velocities.velocities),
                *_rows(lattice_velocities.lattice_vectors),
            )
        )
    if velocity_values is not None:
        lines.append(
            "Direct" if settings.velocity_mode == "direct" else "Cartesian"
        )
        lines.extend(_rows(velocity_values[list(indices)]))
    return "\n".join(lines) + "\n"


def export_poscar(
    destination,
    structure,
    settings=None,
    *,
    selective_dynamics=None,
    velocities=None,
    lattice_velocities=None,
    is_cancelled=None,
):
    settings = PoscarExportSettings() if settings is None else settings
    if not isinstance(settings, PoscarExportSettings):
        raise TypeError("settings must be PoscarExportSettings")
    content = _document(
        structure,
        settings,
        selective_dynamics=selective_dynamics,
        velocities=velocities,
        lattice_velocities=lattice_velocities,
    )
    atomic_write_chunks(destination, (content,), is_cancelled=is_cancelled)
    return ExportReport(
        "poscar",
        True,
        1,
        False,
        (
            ExportReportEntry(
                f"scale_{settings.scale_policy}",
                f"POSCAR scale policy: {settings.scale_policy}",
            ),
        ),
    )


def _dataset(batch, role):
    return next(
        (value for value in batch.datasets if value.semantic_role == role),
        None,
    )


def _records(batch):
    import numpy

    if not isinstance(batch, ImportBatch) or len(batch.structures) != 1:
        raise TypeError("POSCAR comparison requires one-Structure ImportBatch values")
    structure = batch.structures[0]
    selective = _dataset(batch, "selective_dynamics")
    velocities = _dataset(batch, "atomic_velocity")
    flags = (
        None
        if selective is None
        else numpy.asarray(selective.data.values, dtype=numpy.bool_)
    )
    velocity_values = (
        None
        if velocities is None
        else numpy.asarray(velocities.data.values, dtype=float)
    )
    fractional = numpy.mod(
        numpy.asarray(structure.periodic.fractional_coordinates.values, dtype=float),
        1.0,
    )
    records = []
    for index, number in enumerate(structure.atomic_numbers):
        records.append(
            (
                number,
                fractional[index],
                None if flags is None else tuple(flags[index]),
                None
                if velocity_values is None
                else velocity_values[index],
            )
        )
    return structure, tuple(records)


def _same_records(left, right, tolerance):
    import numpy

    if len(left) != len(right):
        return False
    unmatched = set(range(len(right)))
    for number, fractional, flags, velocity in left:
        for index in tuple(unmatched):
            other_number, other_fractional, other_flags, other_velocity = right[index]
            delta = numpy.abs(fractional - other_fractional)
            same_fractional = numpy.all(
                numpy.minimum(delta, 1.0 - delta) <= tolerance
            )
            same_velocity = (
                velocity is other_velocity is None
                or (
                    velocity is not None
                    and other_velocity is not None
                    and numpy.allclose(
                        velocity,
                        other_velocity,
                        rtol=0.0,
                        atol=tolerance,
                    )
                )
            )
            if (
                number == other_number
                and flags == other_flags
                and same_fractional
                and same_velocity
            ):
                unmatched.remove(index)
                break
        else:
            return False
    return True


def semantic_poscar_differences(left, right, *, tolerance=1.0e-9):
    import numpy

    _positive(tolerance, "tolerance")
    left_structure, left_records = _records(left)
    right_structure, right_records = _records(right)
    differences = []
    if not numpy.allclose(
        left_structure.cell.values,
        right_structure.cell.values,
        rtol=0.0,
        atol=tolerance,
    ):
        differences.append("cell")
    if left_structure.periodic.pbc != right_structure.periodic.pbc:
        differences.append("pbc")
    if not _same_records(left_records, right_records, tolerance):
        differences.append("atoms")
    return tuple(differences)


__all__ = (
    "PoscarExportSettings",
    "export_poscar",
    "semantic_poscar_differences",
)
