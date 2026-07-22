import operator
import re
from math import isfinite
from dataclasses import dataclass, field
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


@dataclass(frozen=True, slots=True)
class ArrayData:
    values: object
    dims: tuple[str, ...]
    unit: str
    shape: tuple[int, ...] = field(init=False)
    dtype: str = field(init=False)

    def __post_init__(self):
        try:
            raw_shape = self.values.shape
        except AttributeError as error:
            raise TypeError("values must expose a shape") from error

        shape = []
        for dimension in raw_shape:
            if isinstance(dimension, bool):
                raise ValueError("array dimensions must be non-negative integers")
            try:
                size = operator.index(dimension)
            except TypeError as error:
                raise ValueError(
                    "array dimensions must be non-negative integers"
                ) from error
            if size < 0:
                raise ValueError("array dimensions must be non-negative integers")
            shape.append(size)

        dims = tuple(self.dims)
        if len(shape) != len(dims):
            raise ValueError("dims must match array rank")
        if len(set(dims)) != len(dims) or any(
            not isinstance(dim, str) or not dim for dim in dims
        ):
            raise ValueError("dims must be unique non-empty names")
        if not isinstance(self.unit, str) or not _UNIT_PATTERN.fullmatch(self.unit):
            raise ValueError("unit must be a lower_snake_case token")

        dtype = getattr(self.values, "dtype", getattr(self.values, "format", "unknown"))
        object.__setattr__(self, "dims", dims)
        object.__setattr__(self, "shape", tuple(shape))
        object.__setattr__(self, "dtype", str(dtype))


@dataclass(frozen=True, slots=True)
class CIFEnvelope:
    id: UUID
    revision: str
    block_name: str
    source_bytes: bytes
    tag_names: tuple[str, ...]
    provenance_ids: tuple[UUID, ...]

    def __post_init__(self):
        _require_uuid(self.id, "id")
        _require_text(self.revision, "revision")
        _require_text(self.block_name, "block_name")
        if not isinstance(self.source_bytes, bytes) or not self.source_bytes:
            raise ValueError("source_bytes must be non-empty bytes")
        tag_names = tuple(self.tag_names)
        if any(
            not isinstance(tag, str) or not tag.startswith("_")
            for tag in tag_names
        ):
            raise ValueError("tag_names must contain CIF tags")
        object.__setattr__(self, "tag_names", tag_names)
        object.__setattr__(
            self,
            "provenance_ids",
            _require_uuid_tuple(self.provenance_ids, "provenance_ids"),
        )


@dataclass(frozen=True, slots=True)
class PeriodicSiteData:
    fractional_coordinates: ArrayData
    site_labels: tuple[str, ...]
    occupancies: ArrayData
    isotropic_displacements: ArrayData | None
    anisotropic_displacements: ArrayData | None
    adp_types: tuple[str, ...]
    disorder_groups: tuple[int, ...]
    declared_space_group_name: str | None
    declared_space_group_number: int | None
    symmetry_operations: tuple[str, ...]
    cif_envelope_id: UUID | None
    pbc: tuple[bool, bool, bool] = (True, True, True)

    def __post_init__(self):
        import numpy

        fractional = numpy.asarray(self.fractional_coordinates.values)
        if (
            self.fractional_coordinates.dims != ("atom", "xyz")
            or len(self.fractional_coordinates.shape) != 2
            or self.fractional_coordinates.shape[1] != 3
            or self.fractional_coordinates.unit != "dimensionless"
            or numpy.iscomplexobj(fractional)
            or not numpy.all(numpy.isfinite(fractional))
        ):
            raise ValueError(
                "fractional_coordinates must contain finite (atom, xyz) values"
            )
        atom_count = self.fractional_coordinates.shape[0]
        occupancies = numpy.asarray(self.occupancies.values)
        if (
            self.occupancies.dims != ("atom",)
            or self.occupancies.shape != (atom_count,)
            or self.occupancies.unit != "dimensionless"
            or numpy.iscomplexobj(occupancies)
            or not numpy.all(numpy.isfinite(occupancies))
            or numpy.any(occupancies < 0.0)
            or numpy.any(occupancies > 1.0)
        ):
            raise ValueError("occupancies must contain one value from 0 to 1 per atom")
        labels = tuple(self.site_labels)
        adp_types = tuple(self.adp_types)
        disorder_groups = tuple(self.disorder_groups)
        if len(labels) != atom_count or any(
            not isinstance(value, str) or not value for value in labels
        ):
            raise ValueError("site_labels must contain one non-empty label per atom")
        if len(adp_types) != atom_count or any(
            not isinstance(value, str) or not value for value in adp_types
        ):
            raise ValueError("adp_types must contain one non-empty value per atom")
        if len(disorder_groups) != atom_count or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in disorder_groups
        ):
            raise ValueError("disorder_groups must contain non-negative integers")
        if self.isotropic_displacements is not None:
            values = numpy.asarray(self.isotropic_displacements.values)
            if (
                self.isotropic_displacements.dims != ("atom",)
                or self.isotropic_displacements.shape != (atom_count,)
                or self.isotropic_displacements.unit != "angstrom_squared"
                or numpy.iscomplexobj(values)
                or not numpy.all(numpy.isfinite(values) | numpy.isnan(values))
            ):
                raise ValueError(
                    "isotropic displacements must be finite or missing per-atom values"
                )
        if self.anisotropic_displacements is not None:
            values = numpy.asarray(self.anisotropic_displacements.values)
            if (
                self.anisotropic_displacements.dims
                != ("atom", "tensor_component")
                or self.anisotropic_displacements.shape != (atom_count, 6)
                or self.anisotropic_displacements.unit != "angstrom_squared"
                or numpy.iscomplexobj(values)
            ):
                raise ValueError(
                    "anisotropic displacements must contain finite or missing Uij rows"
                )
            complete_rows = numpy.all(numpy.isfinite(values), axis=1)
            missing_rows = numpy.all(numpy.isnan(values), axis=1)
            if not numpy.all(complete_rows | missing_rows):
                raise ValueError(
                    "anisotropic displacements must contain finite or missing Uij rows"
                )
        if self.declared_space_group_name is not None:
            _require_text(
                self.declared_space_group_name, "declared_space_group_name"
            )
        if self.declared_space_group_number is not None and (
            isinstance(self.declared_space_group_number, bool)
            or not isinstance(self.declared_space_group_number, int)
            or not 1 <= self.declared_space_group_number <= 230
        ):
            raise ValueError("declared_space_group_number must be from 1 to 230")
        symmetry_operations = tuple(self.symmetry_operations)
        if any(
            not isinstance(value, str) or not value
            for value in symmetry_operations
        ):
            raise ValueError("symmetry_operations must contain non-empty strings")
        if self.cif_envelope_id is not None:
            _require_uuid(self.cif_envelope_id, "cif_envelope_id")
        pbc = tuple(self.pbc)
        if len(pbc) != 3 or any(not isinstance(value, bool) for value in pbc):
            raise ValueError("pbc must contain three bool values")
        object.__setattr__(self, "site_labels", labels)
        object.__setattr__(self, "adp_types", adp_types)
        object.__setattr__(self, "disorder_groups", disorder_groups)
        object.__setattr__(self, "symmetry_operations", symmetry_operations)
        object.__setattr__(self, "pbc", pbc)


@dataclass(frozen=True, slots=True)
class Structure:
    id: UUID
    revision: str
    atomic_numbers: tuple[int, ...]
    coordinates: ArrayData
    cell: ArrayData | None = None
    periodic: PeriodicSiteData | None = None

    def __post_init__(self):
        _require_uuid(self.id, "id")
        _require_text(self.revision, "revision")
        atomic_numbers = tuple(self.atomic_numbers)
        if any(
            isinstance(number, bool)
            or not isinstance(number, int)
            or not 0 <= number <= 118
            for number in atomic_numbers
        ):
            raise ValueError("atomic numbers must be integers from 0 to 118")
        if self.coordinates.dims != ("atom", "xyz") or self.coordinates.shape != (
            len(atomic_numbers),
            3,
        ):
            raise ValueError("coordinates must have dims (atom, xyz) and shape (n, 3)")
        if self.coordinates.unit in {"dimensionless", "unknown"}:
            raise ValueError("coordinate unit must be known dimensional length")
        if self.cell is not None:
            if self.cell.dims != ("cell_vector", "xyz") or self.cell.shape != (3, 3):
                raise ValueError("cell must have dims (cell_vector, xyz) and shape (3, 3)")
            if self.cell.unit != self.coordinates.unit:
                raise ValueError("cell and coordinates must use the same unit")
        if self.periodic is not None:
            if not isinstance(self.periodic, PeriodicSiteData):
                raise TypeError("periodic must be PeriodicSiteData")
            if self.cell is None:
                raise ValueError("periodic structure requires a cell")
            if self.periodic.fractional_coordinates.shape[0] != len(atomic_numbers):
                raise ValueError("periodic atom dimension must match atomic numbers")
        object.__setattr__(self, "atomic_numbers", atomic_numbers)


@dataclass(frozen=True, slots=True)
class SymmetryResult:
    id: UUID
    revision: str
    structure_id: UUID
    standardized_structure_id: UUID
    hall_number: int
    international_number: int
    international_symbol: str
    hall_symbol: str
    choice: str
    pointgroup: str
    rotations: ArrayData
    translations: ArrayData
    wyckoffs: tuple[str, ...]
    site_symmetry_symbols: tuple[str, ...]
    equivalent_atoms: ArrayData
    crystallographic_orbits: ArrayData
    transformation_matrix: ArrayData
    origin_shift: ArrayData
    mapping_to_primitive: ArrayData
    std_mapping_to_primitive: ArrayData
    std_rotation_matrix: ArrayData
    symprec: float
    angle_tolerance: float
    provenance_ids: tuple[UUID, ...]

    def __post_init__(self):
        import numpy

        _require_uuid(self.id, "id")
        _require_uuid(self.structure_id, "structure_id")
        _require_uuid(self.standardized_structure_id, "standardized_structure_id")
        _require_text(self.revision, "revision")
        if (
            isinstance(self.hall_number, bool)
            or not isinstance(self.hall_number, int)
            or not 1 <= self.hall_number <= 530
        ):
            raise ValueError("hall_number must be from 1 to 530")
        if (
            isinstance(self.international_number, bool)
            or not isinstance(self.international_number, int)
            or not 1 <= self.international_number <= 230
        ):
            raise ValueError("international_number must be from 1 to 230")
        for name in ("international_symbol", "hall_symbol", "pointgroup"):
            _require_text(getattr(self, name), name)
        if not isinstance(self.choice, str):
            raise TypeError("choice must be a string")
        arrays = (
            self.rotations,
            self.translations,
            self.equivalent_atoms,
            self.crystallographic_orbits,
            self.transformation_matrix,
            self.origin_shift,
            self.mapping_to_primitive,
            self.std_mapping_to_primitive,
            self.std_rotation_matrix,
        )
        if any(not isinstance(value, ArrayData) for value in arrays):
            raise TypeError("symmetry arrays must be ArrayData")
        operation_count = self.rotations.shape[0]
        if (
            self.rotations.dims
            != ("operation", "output_axis", "input_axis")
            or self.rotations.shape[1:] != (3, 3)
            or self.translations.dims != ("operation", "axis")
            or self.translations.shape != (operation_count, 3)
        ):
            raise ValueError("rotations and translations must describe operations")
        atom_count = self.equivalent_atoms.shape[0]
        if (
            self.equivalent_atoms.dims != ("atom",)
            or self.crystallographic_orbits.dims != ("atom",)
            or self.crystallographic_orbits.shape != (atom_count,)
            or self.mapping_to_primitive.dims != ("atom",)
            or self.mapping_to_primitive.shape != (atom_count,)
        ):
            raise ValueError("input-atom symmetry mappings must have matching shape")
        if self.std_mapping_to_primitive.dims != ("standard_atom",):
            raise ValueError("standard atom mapping must use standard_atom dimension")
        matrix_shapes = (
            (
                self.transformation_matrix,
                ("standard_axis", "input_axis"),
            ),
            (
                self.std_rotation_matrix,
                ("cartesian_output_axis", "cartesian_input_axis"),
            ),
        )
        if any(
            value.dims != dims or value.shape != (3, 3)
            for value, dims in matrix_shapes
        ):
            raise ValueError("symmetry transformation matrices must be 3 by 3")
        if self.origin_shift.dims != ("axis",) or self.origin_shift.shape != (3,):
            raise ValueError("origin_shift must contain three values")
        for value in arrays:
            array = numpy.asarray(value.values)
            if (
                value.unit != "dimensionless"
                or numpy.iscomplexobj(array)
                or not numpy.all(numpy.isfinite(array))
            ):
                raise ValueError("symmetry arrays must be finite and dimensionless")
        wyckoffs = tuple(self.wyckoffs)
        site_symmetry_symbols = tuple(self.site_symmetry_symbols)
        if len(wyckoffs) != atom_count or any(
            not isinstance(value, str) or len(value) != 1 for value in wyckoffs
        ):
            raise ValueError("wyckoffs must contain one letter per input atom")
        if len(site_symmetry_symbols) != atom_count or any(
            not isinstance(value, str) or not value
            for value in site_symmetry_symbols
        ):
            raise ValueError("site symmetry symbols must match input atoms")
        for value, name, positive in (
            (self.symprec, "symprec", True),
            (self.angle_tolerance, "angle_tolerance", False),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or (positive and value <= 0.0)
            ):
                raise ValueError(f"{name} must be finite")
        object.__setattr__(self, "wyckoffs", wyckoffs)
        object.__setattr__(self, "site_symmetry_symbols", site_symmetry_symbols)
        object.__setattr__(
            self,
            "provenance_ids",
            _require_uuid_tuple(self.provenance_ids, "provenance_ids"),
        )


@dataclass(frozen=True, slots=True)
class CalculationRecord:
    id: UUID
    revision: str
    status: CalculationStatus
    input_structure_ids: tuple[UUID, ...]
    result_structure_ids: tuple[UUID, ...]
    dataset_ids: tuple[UUID, ...]
    provenance_ids: tuple[UUID, ...]

    def __post_init__(self):
        _require_uuid(self.id, "id")
        _require_text(self.revision, "revision")
        if not isinstance(self.status, CalculationStatus):
            raise TypeError("status must be a CalculationStatus")
        for name in (
            "input_structure_ids",
            "result_structure_ids",
            "dataset_ids",
            "provenance_ids",
        ):
            object.__setattr__(self, name, _require_uuid_tuple(getattr(self, name), name))


@dataclass(frozen=True, slots=True)
class PropertyDataset:
    id: UUID
    revision: str
    semantic_role: str
    domain: str
    data: ArrayData
    status: DatasetStatus
    source_calculation: UUID | None
    provenance_ids: tuple[UUID, ...]

    def __post_init__(self):
        _require_uuid(self.id, "id")
        _require_text(self.revision, "revision")
        _require_token(self.semantic_role, "semantic_role")
        _require_token(self.domain, "domain")
        if not isinstance(self.data, ArrayData):
            raise TypeError("data must be ArrayData")
        if not isinstance(self.status, DatasetStatus):
            raise TypeError("status must be a DatasetStatus")
        if self.data.unit == "unknown" and self.status is not DatasetStatus.AMBIGUOUS:
            raise ValueError("unknown unit requires ambiguous dataset status")
        if self.source_calculation is not None:
            _require_uuid(self.source_calculation, "source_calculation")
        object.__setattr__(
            self,
            "provenance_ids",
            _require_uuid_tuple(self.provenance_ids, "provenance_ids"),
        )


@dataclass(frozen=True, slots=True)
class AtomicProperty(PropertyDataset):
    structure_id: UUID

    def __post_init__(self):
        super(AtomicProperty, self).__post_init__()
        _require_uuid(self.structure_id, "structure_id")
        if self.domain != "atom" or not self.data.dims or self.data.dims[0] != "atom":
            raise ValueError(
                "AtomicProperty must use atom domain and leading atom dimension"
            )


@dataclass(frozen=True, slots=True)
class FrameSet(PropertyDataset):
    structure_id: UUID
    comments: tuple[str, ...]

    def __post_init__(self):
        super(FrameSet, self).__post_init__()
        _require_uuid(self.structure_id, "structure_id")
        if self.semantic_role != "coordinates" or self.domain != "frame":
            raise ValueError("FrameSet must describe frame coordinates")
        if self.data.dims != ("frame", "atom", "xyz") or any(
            size <= 0 for size in self.data.shape
        ):
            raise ValueError(
                "FrameSet data must have positive (frame, atom, xyz) dimensions"
            )
        if self.data.shape[2] != 3:
            raise ValueError("FrameSet xyz dimension must have length 3")
        if self.data.unit in {"dimensionless", "unknown"}:
            raise ValueError(
                "FrameSet coordinate unit must be known dimensional length"
            )
        comments = tuple(self.comments)
        if len(comments) != self.data.shape[0] or any(
            not isinstance(comment, str) for comment in comments
        ):
            raise ValueError(
                "FrameSet comments must contain one string per frame"
            )
        object.__setattr__(self, "comments", comments)


@dataclass(frozen=True, slots=True)
class VibrationalModeSet(PropertyDataset):
    structure_id: UUID
    displacements: ArrayData
    reduced_masses: ArrayData | None
    force_constants: ArrayData | None
    ir_intensities: ArrayData | None
    raman_activities: ArrayData | None
    symmetries: tuple[str, ...] | None
    displacement_convention: str

    def __post_init__(self):
        super(VibrationalModeSet, self).__post_init__()
        _require_uuid(self.structure_id, "structure_id")
        if (
            self.semantic_role != "vibrational_modes"
            or self.domain != "mode"
            or self.data.dims != ("mode",)
            or self.data.shape[0] <= 0
            or self.data.unit != "inverse_centimeter"
            or "complex" in self.data.dtype.lower()
        ):
            raise ValueError(
                "VibrationalModeSet data must contain real signed mode frequencies"
            )
        if (
            not isinstance(self.displacements, ArrayData)
            or self.displacements.dims != ("mode", "atom", "xyz")
            or len(self.displacements.shape) != 3
            or self.displacements.shape[0] != self.data.shape[0]
            or self.displacements.shape[1] <= 0
            or self.displacements.shape[2] != 3
            or self.displacements.unit != "angstrom"
            or "complex" in self.displacements.dtype.lower()
        ):
            raise ValueError(
                "vibration displacements must have (mode, atom, xyz) in angstrom"
            )
        optional_arrays = (
            (self.reduced_masses, "dalton", "reduced_masses"),
            (
                self.force_constants,
                "millidyne_per_angstrom",
                "force_constants",
            ),
            (
                self.ir_intensities,
                "kilometer_per_mole",
                "ir_intensities",
            ),
            (
                self.raman_activities,
                "angstrom_four_per_dalton",
                "raman_activities",
            ),
        )
        for values, unit, name in optional_arrays:
            if values is None:
                continue
            if (
                not isinstance(values, ArrayData)
                or values.dims != ("mode",)
                or values.shape != self.data.shape
                or values.unit != unit
                or "complex" in values.dtype.lower()
            ):
                raise ValueError(f"{name} must contain one real value per mode")
        if self.symmetries is not None:
            symmetries = tuple(self.symmetries)
            if len(symmetries) != self.data.shape[0] or any(
                not isinstance(value, str) or not value for value in symmetries
            ):
                raise ValueError("symmetries must contain one non-empty label per mode")
            object.__setattr__(self, "symmetries", symmetries)
        _require_token(self.displacement_convention, "displacement_convention")


@dataclass(frozen=True, slots=True)
class ExcitationContribution:
    occupied_orbital: int
    occupied_spin: SpinChannel
    virtual_orbital: int
    virtual_spin: SpinChannel
    coefficient: float

    def __post_init__(self):
        for value, name in (
            (self.occupied_orbital, "occupied_orbital"),
            (self.virtual_orbital, "virtual_orbital"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if not isinstance(self.occupied_spin, SpinChannel) or not isinstance(
            self.virtual_spin, SpinChannel
        ):
            raise TypeError("excitation spin values must be SpinChannel values")
        if (
            isinstance(self.coefficient, bool)
            or not isinstance(self.coefficient, (int, float))
            or not isfinite(self.coefficient)
        ):
            raise ValueError("excitation coefficient must be finite")

    @property
    def weight(self):
        return float(self.coefficient) ** 2


@dataclass(frozen=True, slots=True)
class ExcitedStateReferences:
    transition_density: UUID | None = None
    nto_hole: UUID | None = None
    nto_particle: UUID | None = None
    hole_density: UUID | None = None
    electron_density: UUID | None = None

    def __post_init__(self):
        for name in (
            "transition_density",
            "nto_hole",
            "nto_particle",
            "hole_density",
            "electron_density",
        ):
            value = getattr(self, name)
            if value is not None:
                _require_uuid(value, name)

    @property
    def referenced_ids(self):
        return tuple(
            value
            for value in (
                self.transition_density,
                self.nto_hole,
                self.nto_particle,
                self.hole_density,
                self.electron_density,
            )
            if value is not None
        )


@dataclass(frozen=True, slots=True)
class ExcitedStateSet(PropertyDataset):
    structure_id: UUID
    oscillator_strengths: ArrayData | None
    rotatory_strengths: ArrayData | None
    electric_transition_dipoles: ArrayData | None
    velocity_transition_dipoles: ArrayData | None
    magnetic_transition_dipoles: ArrayData | None
    symmetries: tuple[str, ...] | None
    multiplicities: tuple[int | None, ...]
    configurations: tuple[tuple[ExcitationContribution, ...], ...] | None
    state_references: tuple[ExcitedStateReferences, ...]

    def __post_init__(self):
        import numpy

        super(ExcitedStateSet, self).__post_init__()
        _require_uuid(self.structure_id, "structure_id")
        energies = numpy.asarray(self.data.values)
        if (
            self.semantic_role != "excited_states"
            or self.domain != "state"
            or self.data.dims != ("state",)
            or self.data.shape[0] <= 0
            or self.data.unit != "inverse_centimeter"
            or numpy.iscomplexobj(energies)
            or not numpy.all(numpy.isfinite(energies))
            or numpy.any(energies < 0.0)
        ):
            raise ValueError(
                "ExcitedStateSet data must contain finite non-negative excitation energies"
            )
        state_count = self.data.shape[0]
        if self.oscillator_strengths is not None:
            values = numpy.asarray(self.oscillator_strengths.values)
            if (
                self.oscillator_strengths.dims != ("state",)
                or self.oscillator_strengths.shape != (state_count,)
                or self.oscillator_strengths.unit != "dimensionless"
                or numpy.iscomplexobj(values)
                or not numpy.all(numpy.isfinite(values))
                or numpy.any(values < 0.0)
            ):
                raise ValueError(
                    "oscillator_strengths must contain one finite non-negative value per state"
                )
        if self.rotatory_strengths is not None:
            values = numpy.asarray(self.rotatory_strengths.values)
            if (
                self.rotatory_strengths.dims != ("state",)
                or self.rotatory_strengths.shape != (state_count,)
                or self.rotatory_strengths.unit != "unknown"
                or numpy.iscomplexobj(values)
                or not numpy.all(numpy.isfinite(values))
                or self.status is not DatasetStatus.AMBIGUOUS
            ):
                raise ValueError(
                    "rotatory_strengths require finite values and ambiguous unknown unit"
                )
        for values, name in (
            (self.electric_transition_dipoles, "electric_transition_dipoles"),
            (self.velocity_transition_dipoles, "velocity_transition_dipoles"),
            (self.magnetic_transition_dipoles, "magnetic_transition_dipoles"),
        ):
            if values is None:
                continue
            array = numpy.asarray(values.values)
            if (
                values.dims != ("state", "xyz")
                or values.shape != (state_count, 3)
                or values.unit != "elementary_charge_bohr"
                or numpy.iscomplexobj(array)
                or not numpy.all(numpy.isfinite(array))
            ):
                raise ValueError(f"{name} must contain one finite xyz vector per state")
        if self.symmetries is not None:
            symmetries = tuple(self.symmetries)
            if len(symmetries) != state_count or any(
                not isinstance(value, str) or not value for value in symmetries
            ):
                raise ValueError("symmetries must contain one non-empty label per state")
            object.__setattr__(self, "symmetries", symmetries)
        multiplicities = tuple(self.multiplicities)
        if len(multiplicities) != state_count or any(
            value is not None
            and (isinstance(value, bool) or not isinstance(value, int) or value <= 0)
            for value in multiplicities
        ):
            raise ValueError(
                "multiplicities must contain one positive integer or None per state"
            )
        object.__setattr__(self, "multiplicities", multiplicities)
        if self.configurations is not None:
            configurations = tuple(tuple(state) for state in self.configurations)
            if len(configurations) != state_count or any(
                any(not isinstance(item, ExcitationContribution) for item in state)
                for state in configurations
            ):
                raise ValueError(
                    "configurations must contain typed contributions for each state"
                )
            object.__setattr__(self, "configurations", configurations)
        references = tuple(self.state_references)
        if len(references) != state_count or any(
            not isinstance(item, ExcitedStateReferences) for item in references
        ):
            raise ValueError(
                "state_references must contain one ExcitedStateReferences per state"
            )
        object.__setattr__(self, "state_references", references)


@dataclass(frozen=True, slots=True)
class Spectrum(PropertyDataset):
    axis: ArrayData
    kind: SpectrumKind
    profile: SpectrumProfile
    source_dataset_id: UUID
    fwhm: float | None
    selection_policy: str

    def __post_init__(self):
        super(Spectrum, self).__post_init__()
        if not isinstance(self.kind, SpectrumKind):
            raise TypeError("kind must be a SpectrumKind")
        if not isinstance(self.profile, SpectrumProfile):
            raise TypeError("profile must be a SpectrumProfile")
        expected_role = f"{self.kind.value}_spectrum"
        expected_unit = {
            SpectrumKind.IR: "kilometer_per_mole",
            SpectrumKind.RAMAN: "angstrom_four_per_dalton",
            SpectrumKind.UV_VIS: "dimensionless",
            SpectrumKind.ECD: "unknown",
        }[self.kind]
        if (
            self.semantic_role != expected_role
            or self.domain != "frequency"
            or self.data.dims != ("sample",)
            or self.data.shape[0] <= 0
            or self.data.unit != expected_unit
            or "complex" in self.data.dtype.lower()
        ):
            raise ValueError("Spectrum intensity axis does not match its kind")
        if (
            not isinstance(self.axis, ArrayData)
            or self.axis.dims != ("sample",)
            or self.axis.shape != self.data.shape
            or self.axis.unit != "inverse_centimeter"
            or "complex" in self.axis.dtype.lower()
        ):
            raise ValueError("Spectrum axis must contain one frequency per sample")
        _require_uuid(self.source_dataset_id, "source_dataset_id")
        if self.profile is SpectrumProfile.STICK:
            if self.fwhm is not None:
                raise ValueError("stick Spectrum must not define fwhm")
        elif (
            isinstance(self.fwhm, bool)
            or not isinstance(self.fwhm, (int, float))
            or not isfinite(self.fwhm)
            or self.fwhm <= 0.0
        ):
            raise ValueError("broadened Spectrum requires positive finite fwhm")
        if not isinstance(self.selection_policy, str) or not self.selection_policy:
            raise ValueError("selection_policy must be a non-empty string")
        if self.kind is SpectrumKind.ECD and self.status is not DatasetStatus.AMBIGUOUS:
            raise ValueError("ECD Spectrum requires ambiguous status for unknown units")


@dataclass(frozen=True, slots=True)
class BandPathBranch:
    start_index: int
    end_index: int
    start_label: str | None
    end_label: str | None

    def __post_init__(self):
        for value, name in (
            (self.start_index, "start_index"),
            (self.end_index, "end_index"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.end_index < self.start_index:
            raise ValueError("branch end_index must not precede start_index")
        for value, name in (
            (self.start_label, "start_label"),
            (self.end_label, "end_label"),
        ):
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"{name} must be None or a non-empty string")


def _validate_spin_channels(values, spin_count):
    channels = tuple(values)
    expected = ("alpha",) if spin_count == 1 else ("alpha", "beta")
    if channels != expected:
        raise ValueError(f"spin_channels must be {expected}")
    return channels


@dataclass(frozen=True, slots=True)
class BandStructure(PropertyDataset):
    structure_id: UUID
    occupations: ArrayData | None
    kpoints: ArrayData
    reciprocal_lattice: ArrayData
    distances: ArrayData
    spin_channels: tuple[str, ...]
    labels: tuple[str | None, ...]
    branches: tuple[BandPathBranch, ...]
    projections: ArrayData | None
    orbital_labels: tuple[str, ...]
    fermi_energy: float
    energy_reference: EnergyReference

    def __post_init__(self):
        import numpy

        super(BandStructure, self).__post_init__()
        _require_uuid(self.structure_id, "structure_id")
        energies = numpy.asarray(self.data.values)
        if (
            self.semantic_role != "band_structure"
            or self.domain != "band"
            or self.data.dims != ("spin", "kpoint", "band")
            or any(size <= 0 for size in self.data.shape)
            or self.data.unit != "electron_volt"
            or numpy.iscomplexobj(energies)
            or not numpy.all(numpy.isfinite(energies))
        ):
            raise ValueError("BandStructure data must contain finite spin-kpoint-band energies")
        spin_count, kpoint_count, band_count = self.data.shape
        if self.occupations is not None:
            occupations = numpy.asarray(self.occupations.values)
            if (
                self.occupations.dims != self.data.dims
                or self.occupations.shape != self.data.shape
                or self.occupations.unit != "dimensionless"
                or numpy.iscomplexobj(occupations)
                or not numpy.all(numpy.isfinite(occupations))
                or numpy.any(occupations < 0.0)
                or numpy.any(occupations > 2.0)
            ):
                raise ValueError("occupations must match band energies and lie from 0 to 2")
        kpoints = numpy.asarray(self.kpoints.values)
        if (
            self.kpoints.dims != ("kpoint", "reciprocal_axis")
            or self.kpoints.shape != (kpoint_count, 3)
            or self.kpoints.unit != "dimensionless"
            or numpy.iscomplexobj(kpoints)
            or not numpy.all(numpy.isfinite(kpoints))
        ):
            raise ValueError("kpoints must contain finite fractional reciprocal coordinates")
        reciprocal = numpy.asarray(self.reciprocal_lattice.values)
        if (
            self.reciprocal_lattice.dims
            != ("reciprocal_vector", "cartesian_axis")
            or self.reciprocal_lattice.shape != (3, 3)
            or self.reciprocal_lattice.unit != "inverse_angstrom"
            or numpy.iscomplexobj(reciprocal)
            or not numpy.all(numpy.isfinite(reciprocal))
            or abs(float(numpy.linalg.det(reciprocal))) < 1e-12
        ):
            raise ValueError("reciprocal_lattice must be finite and non-singular")
        distances = numpy.asarray(self.distances.values)
        if (
            self.distances.dims != ("kpoint",)
            or self.distances.shape != (kpoint_count,)
            or self.distances.unit != "inverse_angstrom"
            or numpy.iscomplexobj(distances)
            or not numpy.all(numpy.isfinite(distances))
            or not numpy.isclose(distances[0], 0.0)
            or numpy.any(numpy.diff(distances) < 0.0)
        ):
            raise ValueError("distances must be finite non-decreasing and start at zero")
        channels = _validate_spin_channels(self.spin_channels, spin_count)
        labels = tuple(self.labels)
        if len(labels) != kpoint_count or any(
            value is not None and (not isinstance(value, str) or not value)
            for value in labels
        ):
            raise ValueError("labels must contain one string or None per kpoint")
        branches = tuple(self.branches)
        if any(
            not isinstance(branch, BandPathBranch)
            or branch.end_index >= kpoint_count
            or (
                branch.start_label is not None
                and labels[branch.start_index] != branch.start_label
            )
            or (
                branch.end_label is not None
                and labels[branch.end_index] != branch.end_label
            )
            for branch in branches
        ):
            raise ValueError("branches must reference matching kpoint endpoints")
        orbital_labels = tuple(self.orbital_labels)
        if self.projections is None:
            if orbital_labels:
                raise ValueError("orbital_labels require projections")
        else:
            projections = numpy.asarray(self.projections.values)
            if (
                self.projections.dims
                != ("spin", "kpoint", "band", "atom", "orbital")
                or self.projections.shape[:3]
                != (spin_count, kpoint_count, band_count)
                or self.projections.shape[3] <= 0
                or self.projections.shape[4] <= 0
                or self.projections.unit != "dimensionless"
                or numpy.iscomplexobj(projections)
                or not numpy.all(numpy.isfinite(projections))
                or numpy.any(projections < 0.0)
                or len(orbital_labels) != self.projections.shape[4]
                or any(not isinstance(label, str) or not label for label in orbital_labels)
            ):
                raise ValueError("projections must match band axes and orbital labels")
        if (
            isinstance(self.fermi_energy, bool)
            or not isinstance(self.fermi_energy, (int, float))
            or not isfinite(self.fermi_energy)
        ):
            raise ValueError("fermi_energy must be finite")
        if not isinstance(self.energy_reference, EnergyReference):
            raise TypeError("energy_reference must be an EnergyReference")
        object.__setattr__(self, "spin_channels", channels)
        object.__setattr__(self, "labels", labels)
        object.__setattr__(self, "branches", branches)
        object.__setattr__(self, "orbital_labels", orbital_labels)


@dataclass(frozen=True, slots=True)
class DensityOfStates(PropertyDataset):
    structure_id: UUID
    energies: ArrayData
    spin_channels: tuple[str, ...]
    projections: ArrayData | None
    orbital_labels: tuple[str, ...]
    fermi_energy: float
    energy_reference: EnergyReference

    def __post_init__(self):
        import numpy

        super(DensityOfStates, self).__post_init__()
        _require_uuid(self.structure_id, "structure_id")
        values = numpy.asarray(self.data.values)
        allowed_units = {
            "states_per_electron_volt",
            "states_per_electron_volt_per_cubic_angstrom",
        }
        if (
            self.semantic_role != "density_of_states"
            or self.domain != "energy"
            or self.data.dims != ("spin", "energy")
            or any(size <= 0 for size in self.data.shape)
            or self.data.unit not in allowed_units
            or numpy.iscomplexobj(values)
            or not numpy.all(numpy.isfinite(values))
            or numpy.any(values < 0.0)
        ):
            raise ValueError("DensityOfStates data must contain finite non-negative densities")
        spin_count, energy_count = self.data.shape
        energies = numpy.asarray(self.energies.values)
        if (
            self.energies.dims != ("energy",)
            or self.energies.shape != (energy_count,)
            or self.energies.unit != "electron_volt"
            or numpy.iscomplexobj(energies)
            or not numpy.all(numpy.isfinite(energies))
            or numpy.any(numpy.diff(energies) <= 0.0)
        ):
            raise ValueError("DOS energies must be finite and strictly increasing")
        channels = _validate_spin_channels(self.spin_channels, spin_count)
        orbital_labels = tuple(self.orbital_labels)
        if self.projections is None:
            if orbital_labels:
                raise ValueError("orbital_labels require projections")
        else:
            projections = numpy.asarray(self.projections.values)
            if (
                self.projections.dims
                != ("spin", "energy", "atom", "orbital")
                or self.projections.shape[:2] != (spin_count, energy_count)
                or self.projections.shape[2] <= 0
                or self.projections.shape[3] <= 0
                or self.projections.unit != self.data.unit
                or numpy.iscomplexobj(projections)
                or not numpy.all(numpy.isfinite(projections))
                or numpy.any(projections < 0.0)
                or len(orbital_labels) != self.projections.shape[3]
                or any(not isinstance(label, str) or not label for label in orbital_labels)
            ):
                raise ValueError("DOS projections must match spin-energy axes and units")
        if (
            isinstance(self.fermi_energy, bool)
            or not isinstance(self.fermi_energy, (int, float))
            or not isfinite(self.fermi_energy)
        ):
            raise ValueError("fermi_energy must be finite")
        if not isinstance(self.energy_reference, EnergyReference):
            raise TypeError("energy_reference must be an EnergyReference")
        object.__setattr__(self, "spin_channels", channels)
        object.__setattr__(self, "orbital_labels", orbital_labels)


@dataclass(frozen=True, slots=True)
class PhononModeSet(PropertyDataset):
    structure_id: UUID
    qpoints: ArrayData
    eigenvectors: ArrayData
    masses: ArrayData
    group_velocities: ArrayData | None
    weights: ArrayData | None
    eigenvector_convention: str

    def __post_init__(self):
        import numpy

        super(PhononModeSet, self).__post_init__()
        _require_uuid(self.structure_id, "structure_id")
        frequencies = numpy.asarray(self.data.values)
        if (
            self.semantic_role != "phonon_modes"
            or self.domain != "mode"
            or self.data.dims != ("qpoint", "mode")
            or any(size <= 0 for size in self.data.shape)
            or self.data.unit != "terahertz"
            or numpy.iscomplexobj(frequencies)
            or not numpy.all(numpy.isfinite(frequencies))
        ):
            raise ValueError("PhononModeSet data must contain finite qpoint-mode frequencies")
        qpoint_count, mode_count = self.data.shape
        qpoints = numpy.asarray(self.qpoints.values)
        if (
            self.qpoints.dims != ("qpoint", "reciprocal_axis")
            or self.qpoints.shape != (qpoint_count, 3)
            or self.qpoints.unit != "dimensionless"
            or numpy.iscomplexobj(qpoints)
            or not numpy.all(numpy.isfinite(qpoints))
        ):
            raise ValueError("qpoints must contain finite reciprocal fractional coordinates")
        eigenvectors = numpy.asarray(self.eigenvectors.values)
        if (
            self.eigenvectors.dims != ("qpoint", "mode", "atom", "xyz")
            or self.eigenvectors.shape[:2] != (qpoint_count, mode_count)
            or self.eigenvectors.shape[2] <= 0
            or self.eigenvectors.shape[3] != 3
            or mode_count != self.eigenvectors.shape[2] * 3
            or self.eigenvectors.unit != "dimensionless"
            or not numpy.iscomplexobj(eigenvectors)
            or not numpy.all(numpy.isfinite(eigenvectors))
        ):
            raise ValueError("eigenvectors must contain three modes per atom as finite complex values")
        atom_count = self.eigenvectors.shape[2]
        masses = numpy.asarray(self.masses.values)
        if (
            self.masses.dims != ("atom",)
            or self.masses.shape != (atom_count,)
            or self.masses.unit != "atomic_mass_unit"
            or numpy.iscomplexobj(masses)
            or not numpy.all(numpy.isfinite(masses))
            or numpy.any(masses <= 0.0)
        ):
            raise ValueError("masses must contain one positive atomic mass per atom")
        if self.group_velocities is not None:
            velocities = numpy.asarray(self.group_velocities.values)
            if (
                self.group_velocities.dims != ("qpoint", "mode", "xyz")
                or self.group_velocities.shape != (qpoint_count, mode_count, 3)
                or self.group_velocities.unit != "terahertz_angstrom"
                or numpy.iscomplexobj(velocities)
                or not numpy.all(numpy.isfinite(velocities))
            ):
                raise ValueError("group velocities must match qpoint-mode axes")
        if self.weights is not None:
            weights = numpy.asarray(self.weights.values)
            if (
                self.weights.dims != ("qpoint",)
                or self.weights.shape != (qpoint_count,)
                or self.weights.unit != "dimensionless"
                or numpy.iscomplexobj(weights)
                or not numpy.all(numpy.isfinite(weights))
                or numpy.any(weights < 0.0)
            ):
                raise ValueError("weights must contain one non-negative value per qpoint")
        if self.eigenvector_convention != "phonopy_mass_weighted_dynamical_matrix":
            raise ValueError("unsupported eigenvector_convention")


@dataclass(frozen=True, slots=True)
class SurfaceProperty:
    semantic_role: str
    domain: str
    data: ArrayData

    def __post_init__(self):
        _require_token(self.semantic_role, "semantic_role")
        if self.domain not in {"vertex", "face"}:
            raise ValueError("surface property domain must be vertex or face")
        if not isinstance(self.data, ArrayData):
            raise TypeError("surface property data must be ArrayData")
        if not self.data.dims or self.data.dims[0] != self.domain:
            raise ValueError("surface property leading dimension must match its domain")


@dataclass(frozen=True, slots=True)
class FermiSurfaceMesh(PropertyDataset):
    structure_id: UUID
    band_structure_id: UUID
    faces: ArrayData
    band_indices: ArrayData
    spin_index: int
    fermi_energy: float
    coordinate_convention: str
    properties: tuple[SurfaceProperty, ...]

    def __post_init__(self):
        import numpy

        super(FermiSurfaceMesh, self).__post_init__()
        _require_uuid(self.structure_id, "structure_id")
        _require_uuid(self.band_structure_id, "band_structure_id")
        vertices = numpy.asarray(self.data.values)
        if (
            self.semantic_role != "fermi_surface"
            or self.domain != "surface_vertex"
            or self.data.dims != ("vertex", "xyz")
            or self.data.shape[0] < 3
            or self.data.shape[1] != 3
            or self.data.unit != "inverse_angstrom"
            or numpy.iscomplexobj(vertices)
            or not numpy.all(numpy.isfinite(vertices))
        ):
            raise ValueError("FermiSurfaceMesh vertices must be finite reciprocal coordinates")
        faces = numpy.asarray(self.faces.values)
        if (
            self.faces.dims != ("face", "corner")
            or self.faces.shape[0] <= 0
            or self.faces.shape[1] != 3
            or self.faces.unit != "dimensionless"
            or not numpy.issubdtype(faces.dtype, numpy.integer)
            or numpy.any(faces < 0)
            or numpy.any(faces >= self.data.shape[0])
            or any(len(set(int(value) for value in face)) != 3 for face in faces)
        ):
            raise ValueError("face indices must contain valid non-degenerate triangles")
        band_indices = numpy.asarray(self.band_indices.values)
        if (
            self.band_indices.dims != ("face",)
            or self.band_indices.shape != (self.faces.shape[0],)
            or self.band_indices.unit != "dimensionless"
            or not numpy.issubdtype(band_indices.dtype, numpy.integer)
            or numpy.any(band_indices < 0)
        ):
            raise ValueError("band_indices must contain one non-negative index per face")
        if (
            isinstance(self.spin_index, bool)
            or not isinstance(self.spin_index, int)
            or self.spin_index < 0
        ):
            raise ValueError("spin_index must be a non-negative integer")
        if (
            isinstance(self.fermi_energy, bool)
            or not isinstance(self.fermi_energy, (int, float))
            or not isfinite(self.fermi_energy)
        ):
            raise ValueError("fermi_energy must be finite")
        if self.coordinate_convention != "cartesian_reciprocal_2pi":
            raise ValueError("unsupported coordinate_convention")
        properties = tuple(self.properties)
        if any(not isinstance(prop, SurfaceProperty) for prop in properties):
            raise TypeError("properties must contain SurfaceProperty values")
        if len({prop.semantic_role for prop in properties}) != len(properties):
            raise ValueError("surface property semantic roles must be unique")
        for prop in properties:
            expected = self.data.shape[0] if prop.domain == "vertex" else self.faces.shape[0]
            if prop.data.shape[0] != expected:
                raise ValueError("surface property domain shape does not match mesh")
        object.__setattr__(self, "properties", properties)


@dataclass(frozen=True, slots=True)
class TopologyConnection:
    id: UUID
    critical_point_id: UUID
    endpoint_id: UUID
    relationship: str
    lattice_vector: tuple[int, int, int]
    distance: float
    path_length: float
    length_unit: str

    def __post_init__(self):
        for value, name in (
            (self.id, "id"),
            (self.critical_point_id, "critical_point_id"),
            (self.endpoint_id, "endpoint_id"),
        ):
            _require_uuid(value, name)
        if self.critical_point_id == self.endpoint_id:
            raise ValueError("topology connection endpoint must differ from its origin")
        if self.relationship not in {"attractor", "repulsor"}:
            raise ValueError("unsupported topology connection relationship")
        lattice_vector = tuple(self.lattice_vector)
        if len(lattice_vector) != 3 or any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in lattice_vector
        ):
            raise ValueError("lattice_vector must contain three integers")
        for value, name in (
            (self.distance, "distance"),
            (self.path_length, "path_length"),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or value < 0.0
            ):
                raise ValueError(f"{name} must be finite and non-negative")
        _require_token(self.length_unit, "length_unit")
        object.__setattr__(self, "lattice_vector", lattice_vector)


@dataclass(frozen=True, slots=True)
class TopologyPath:
    id: UUID
    start_id: UUID
    end_id: UUID
    samples: ArrayData

    def __post_init__(self):
        import numpy

        for value, name in (
            (self.id, "id"),
            (self.start_id, "start_id"),
            (self.end_id, "end_id"),
        ):
            _require_uuid(value, name)
        if self.start_id == self.end_id:
            raise ValueError("topology path endpoints must differ")
        values = numpy.asarray(self.samples.values)
        if (
            self.samples.dims != ("sample", "xyz")
            or self.samples.shape[0] < 2
            or self.samples.shape[1] != 3
            or self.samples.unit in {"dimensionless", "unknown"}
            or numpy.iscomplexobj(values)
            or not numpy.all(numpy.isfinite(values))
        ):
            raise ValueError("topology path samples must be finite length coordinates")


@dataclass(frozen=True, slots=True)
class TopologyGraph(PropertyDataset):
    structure_id: UUID
    source_grid_id: UUID | None
    critical_point_ids: tuple[UUID, ...]
    names: tuple[str, ...]
    kinds: tuple[CriticalPointKind, ...]
    ranks: tuple[int, ...]
    signatures: tuple[int, ...]
    multiplicities: tuple[int, ...]
    field_semantic_role: str
    field_values: ArrayData
    laplacians: ArrayData
    hessian_eigenvalues: ArrayData
    connections: tuple[TopologyConnection, ...]
    paths: tuple[TopologyPath, ...]

    def __post_init__(self):
        import numpy

        super(TopologyGraph, self).__post_init__()
        _require_uuid(self.structure_id, "structure_id")
        if self.source_grid_id is not None:
            _require_uuid(self.source_grid_id, "source_grid_id")
        _require_token(self.field_semantic_role, "field_semantic_role")
        positions = numpy.asarray(self.data.values)
        if (
            self.semantic_role != "topology_graph"
            or self.domain != "topology"
            or self.data.dims != ("critical_point", "xyz")
            or self.data.shape[0] <= 0
            or self.data.shape[1] != 3
            or self.data.unit in {"dimensionless", "unknown"}
            or numpy.iscomplexobj(positions)
            or not numpy.all(numpy.isfinite(positions))
        ):
            raise ValueError("TopologyGraph positions must be finite length coordinates")
        count = self.data.shape[0]
        ids = _require_uuid_tuple(self.critical_point_ids, "critical_point_ids")
        names = tuple(self.names)
        kinds = tuple(self.kinds)
        ranks = tuple(self.ranks)
        signatures = tuple(self.signatures)
        multiplicities = tuple(self.multiplicities)
        if len(ids) != count or len(set(ids)) != count:
            raise ValueError("critical_point_ids must be unique and match positions")
        if len(names) != count or any(not isinstance(name, str) or not name for name in names):
            raise ValueError("critical point names must match positions")
        if len(kinds) != count or any(not isinstance(kind, CriticalPointKind) for kind in kinds):
            raise ValueError("critical point kinds must match positions")
        if len(ranks) != count or any(value != 3 for value in ranks):
            raise ValueError("critical point ranks must all be 3")
        if len(signatures) != count or any(value not in {-3, -1, 1, 3} for value in signatures):
            raise ValueError("critical point signatures must be -3, -1, 1 or 3")
        expected_kinds = {
            CriticalPointKind.NUCLEAR: -3,
            CriticalPointKind.ATTRACTOR: -3,
            CriticalPointKind.BOND: -1,
            CriticalPointKind.RING: 1,
            CriticalPointKind.CAGE: 3,
        }
        if any(expected_kinds[kind] != signature for kind, signature in zip(kinds, signatures)):
            raise ValueError("critical point kind and signature disagree")
        if len(multiplicities) != count or any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in multiplicities
        ):
            raise ValueError("critical point multiplicities must be positive integers")
        arrays = (
            (self.field_values, ("critical_point",), (count,), "field_values"),
            (self.laplacians, ("critical_point",), (count,), "laplacians"),
            (
                self.hessian_eigenvalues,
                ("critical_point", "eigenvalue"),
                (count, 3),
                "hessian_eigenvalues",
            ),
        )
        for array, dims, shape, name in arrays:
            values = numpy.asarray(array.values)
            if (
                not isinstance(array, ArrayData)
                or array.dims != dims
                or array.shape != shape
                or array.unit == "unknown"
                or numpy.iscomplexobj(values)
                or not numpy.all(numpy.isfinite(values))
            ):
                raise ValueError(f"{name} must contain finite critical-point values")
        connections = tuple(self.connections)
        paths = tuple(self.paths)
        id_set = set(ids)
        if any(not isinstance(value, TopologyConnection) for value in connections):
            raise TypeError("connections must contain TopologyConnection values")
        if len({value.id for value in connections}) != len(connections):
            raise ValueError("topology connection IDs must be unique")
        if any(
            value.critical_point_id not in id_set
            or value.endpoint_id not in id_set
            or value.length_unit != self.data.unit
            for value in connections
        ):
            raise ValueError("topology connection endpoint or unit is invalid")
        if any(not isinstance(value, TopologyPath) for value in paths):
            raise TypeError("paths must contain TopologyPath values")
        if len({value.id for value in paths}) != len(paths):
            raise ValueError("topology path IDs must be unique")
        if any(
            value.start_id not in id_set
            or value.end_id not in id_set
            or value.samples.unit != self.data.unit
            for value in paths
        ):
            raise ValueError("topology path endpoint or unit is invalid")
        object.__setattr__(self, "critical_point_ids", ids)
        object.__setattr__(self, "names", names)
        object.__setattr__(self, "kinds", kinds)
        object.__setattr__(self, "ranks", ranks)
        object.__setattr__(self, "signatures", signatures)
        object.__setattr__(self, "multiplicities", multiplicities)
        object.__setattr__(self, "connections", connections)
        object.__setattr__(self, "paths", paths)


def _basis_function_count(angular_momentum, kind):
    if kind is BasisFunctionKind.CARTESIAN:
        return (angular_momentum + 1) * (angular_momentum + 2) // 2
    if kind is BasisFunctionKind.PURE and angular_momentum >= 2:
        return 2 * angular_momentum + 1
    raise ValueError("pure basis functions require angular momentum >= 2")


@dataclass(frozen=True, slots=True)
class BasisShell:
    center_atom: int
    angular_momenta: tuple[int, ...]
    kinds: tuple[BasisFunctionKind, ...]
    exponents: ArrayData
    coefficients: ArrayData

    def __post_init__(self):
        if (
            isinstance(self.center_atom, bool)
            or not isinstance(self.center_atom, int)
            or self.center_atom < 0
        ):
            raise ValueError("center_atom must be a non-negative integer")
        angular_momenta = tuple(self.angular_momenta)
        kinds = tuple(self.kinds)
        if not angular_momenta or len(angular_momenta) != len(kinds):
            raise ValueError("basis shell contractions must have angular momenta and kinds")
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in angular_momenta
        ):
            raise ValueError("basis angular momenta must be non-negative integers")
        if any(not isinstance(kind, BasisFunctionKind) for kind in kinds):
            raise TypeError("basis kinds must be BasisFunctionKind values")
        for angular_momentum, kind in zip(angular_momenta, kinds):
            _basis_function_count(angular_momentum, kind)
        if self.exponents.dims != ("primitive",) or self.exponents.unit != "inverse_square_bohr":
            raise ValueError("basis exponents must use (primitive,) and inverse_square_bohr")
        if (
            self.coefficients.dims != ("primitive", "contraction")
            or self.coefficients.unit != "dimensionless"
            or self.coefficients.shape
            != (self.exponents.shape[0], len(angular_momenta))
        ):
            raise ValueError("basis coefficients must match primitive and contraction counts")
        object.__setattr__(self, "angular_momenta", angular_momenta)
        object.__setattr__(self, "kinds", kinds)

    @property
    def basis_function_count(self):
        return sum(
            _basis_function_count(angular_momentum, kind)
            for angular_momentum, kind in zip(self.angular_momenta, self.kinds)
        )


@dataclass(frozen=True, slots=True)
class BasisConvention:
    angular_momentum: int
    kind: BasisFunctionKind
    functions: tuple[str, ...]

    def __post_init__(self):
        if (
            isinstance(self.angular_momentum, bool)
            or not isinstance(self.angular_momentum, int)
            or self.angular_momentum < 0
        ):
            raise ValueError("convention angular momentum must be non-negative")
        if not isinstance(self.kind, BasisFunctionKind):
            raise TypeError("convention kind must be a BasisFunctionKind")
        functions = tuple(self.functions)
        expected = _basis_function_count(self.angular_momentum, self.kind)
        if len(functions) != expected or any(
            not isinstance(function, str) or not function for function in functions
        ):
            raise ValueError("basis convention functions must match the function count")
        object.__setattr__(self, "functions", functions)

    @property
    def function_count(self):
        return len(self.functions)


@dataclass(frozen=True, slots=True)
class BasisSet:
    id: UUID
    revision: str
    structure_id: UUID
    name: str
    shells: tuple[BasisShell, ...]
    conventions: tuple[BasisConvention, ...]
    primitive_normalization: str
    provenance_ids: tuple[UUID, ...]

    def __post_init__(self):
        _require_uuid(self.id, "id")
        _require_text(self.revision, "revision")
        _require_uuid(self.structure_id, "structure_id")
        _require_text(self.name, "name")
        shells = tuple(self.shells)
        conventions = tuple(self.conventions)
        if not shells or any(not isinstance(shell, BasisShell) for shell in shells):
            raise ValueError("BasisSet requires BasisShell values")
        if not conventions or any(
            not isinstance(convention, BasisConvention) for convention in conventions
        ):
            raise ValueError("BasisSet requires BasisConvention values")
        if len({(item.angular_momentum, item.kind) for item in conventions}) != len(
            conventions
        ):
            raise ValueError("BasisSet conventions must have unique angular momentum and kind")
        if self.primitive_normalization not in {"l1", "l2"}:
            raise ValueError("primitive_normalization must be l1 or l2")
        object.__setattr__(self, "shells", shells)
        object.__setattr__(self, "conventions", conventions)
        object.__setattr__(
            self,
            "provenance_ids",
            _require_uuid_tuple(self.provenance_ids, "provenance_ids"),
        )

    @property
    def basis_function_count(self):
        return sum(shell.basis_function_count for shell in self.shells)


@dataclass(frozen=True, slots=True)
class OrbitalChannel:
    label: str
    coefficients: ArrayData
    energies: ArrayData | None
    occupations: ArrayData | None
    irreps: tuple[str, ...]

    def __post_init__(self):
        if self.label not in {"restricted", "alpha", "beta", "generalized"}:
            raise ValueError("invalid orbital channel label")
        expected_dims = (
            ("orbital", "spin_basis_function")
            if self.label == "generalized"
            else ("orbital", "basis_function")
        )
        if (
            self.coefficients.dims != expected_dims
            or self.coefficients.unit != "dimensionless"
            or any(size <= 0 for size in self.coefficients.shape)
        ):
            raise ValueError("orbital coefficients have invalid dimensions or unit")
        orbital_count = self.coefficients.shape[0]
        for name in ("energies", "occupations"):
            values = getattr(self, name)
            if values is not None and (
                values.dims != ("orbital",) or values.shape != (orbital_count,)
            ):
                raise ValueError(f"orbital {name} must match the orbital count")
        if self.energies is not None and self.energies.unit != "hartree":
            raise ValueError("orbital energies must use hartree")
        if self.occupations is not None and self.occupations.unit != "dimensionless":
            raise ValueError("orbital occupations must be dimensionless")
        irreps = tuple(self.irreps)
        if irreps and (
            len(irreps) != orbital_count
            or any(not isinstance(irrep, str) or not irrep for irrep in irreps)
        ):
            raise ValueError("orbital irreps must be empty or match the orbital count")
        object.__setattr__(self, "irreps", irreps)


@dataclass(frozen=True, slots=True)
class OrbitalSet:
    id: UUID
    revision: str
    structure_id: UUID
    basis_set_id: UUID
    kind: OrbitalKind
    channels: tuple[OrbitalChannel, ...]
    provenance_ids: tuple[UUID, ...]

    def __post_init__(self):
        _require_uuid(self.id, "id")
        _require_text(self.revision, "revision")
        _require_uuid(self.structure_id, "structure_id")
        _require_uuid(self.basis_set_id, "basis_set_id")
        if not isinstance(self.kind, OrbitalKind):
            raise TypeError("kind must be an OrbitalKind")
        channels = tuple(self.channels)
        if any(not isinstance(channel, OrbitalChannel) for channel in channels):
            raise TypeError("channels must contain OrbitalChannel values")
        expected = {
            OrbitalKind.RESTRICTED: ("restricted",),
            OrbitalKind.UNRESTRICTED: ("alpha", "beta"),
            OrbitalKind.GENERALIZED: ("generalized",),
        }[self.kind]
        if tuple(channel.label for channel in channels) != expected:
            raise ValueError("orbital channels do not match orbital kind")
        object.__setattr__(self, "channels", channels)
        object.__setattr__(
            self,
            "provenance_ids",
            _require_uuid_tuple(self.provenance_ids, "provenance_ids"),
        )


@dataclass(frozen=True, slots=True)
class DensityMatrix:
    id: UUID
    revision: str
    structure_id: UUID
    basis_set_id: UUID
    level: DensityMatrixLevel
    spin_role: DensityMatrixSpin
    data: ArrayData
    source_calculation: UUID | None
    provenance_ids: tuple[UUID, ...]

    def __post_init__(self):
        _require_uuid(self.id, "id")
        _require_text(self.revision, "revision")
        _require_uuid(self.structure_id, "structure_id")
        _require_uuid(self.basis_set_id, "basis_set_id")
        if not isinstance(self.level, DensityMatrixLevel):
            raise TypeError("level must be a DensityMatrixLevel")
        if not isinstance(self.spin_role, DensityMatrixSpin):
            raise TypeError("spin_role must be a DensityMatrixSpin")
        if (
            self.data.dims
            != ("basis_function_row", "basis_function_column")
            or len(self.data.shape) != 2
            or self.data.shape[0] <= 0
            or self.data.shape[0] != self.data.shape[1]
            or self.data.unit != "dimensionless"
            or "complex" in self.data.dtype.lower()
        ):
            raise ValueError("density matrix must be a real dimensionless square AO matrix")
        if self.source_calculation is not None:
            _require_uuid(self.source_calculation, "source_calculation")
        object.__setattr__(
            self,
            "provenance_ids",
            _require_uuid_tuple(self.provenance_ids, "provenance_ids"),
        )


@dataclass(frozen=True, slots=True)
class Grid3D(PropertyDataset):
    origin: tuple[float, float, float]
    step_vectors: tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ]
    coordinate_unit: str
    structure_id: UUID | None = None

    def __post_init__(self):
        super(Grid3D, self).__post_init__()
        if self.data.dims[-3:] != ("x", "y", "z"):
            raise ValueError("Grid3D data must end with dims (x, y, z)")
        if any(size <= 0 for size in self.grid_shape):
            raise ValueError("Grid3D spatial dimensions must be positive")
        origin = self._vector(self.origin, "origin")
        steps = tuple(self._vector(vector, "step_vector") for vector in self.step_vectors)
        if len(steps) != 3:
            raise ValueError("step_vectors must contain three vectors")
        determinant = (
            steps[0][0] * (steps[1][1] * steps[2][2] - steps[1][2] * steps[2][1])
            - steps[0][1] * (steps[1][0] * steps[2][2] - steps[1][2] * steps[2][0])
            + steps[0][2] * (steps[1][0] * steps[2][1] - steps[1][1] * steps[2][0])
        )
        if determinant == 0.0:
            raise ValueError("step_vectors must be linearly independent")
        _require_token(self.coordinate_unit, "coordinate_unit")
        if self.coordinate_unit == "dimensionless":
            raise ValueError("coordinate_unit must be dimensional length")
        if (
            self.coordinate_unit == "unknown"
            and self.status is not DatasetStatus.AMBIGUOUS
        ):
            raise ValueError("unknown coordinate unit requires ambiguous dataset status")
        if self.structure_id is not None:
            _require_uuid(self.structure_id, "structure_id")
        object.__setattr__(self, "origin", origin)
        object.__setattr__(self, "step_vectors", steps)

    @staticmethod
    def _vector(values, name):
        values = tuple(values)
        if len(values) != 3 or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(value)
            for value in values
        ):
            raise ValueError(f"{name} must contain three finite numbers")
        return tuple(float(value) for value in values)

    @property
    def grid_shape(self):
        return self.data.shape[-3:]


@dataclass(frozen=True, slots=True)
class ProvenanceRecord:
    id: UUID
    revision: str
    producer: str
    producer_version: str
    source: str
    source_hash: str
    parent_ids: tuple[UUID, ...]
    operation: str
    parameters: tuple[tuple[str, object], ...]

    def __post_init__(self):
        _require_uuid(self.id, "id")
        for name in ("revision", "producer", "producer_version", "operation"):
            _require_text(getattr(self, name), name)
        if not isinstance(self.source, str):
            raise TypeError("source must be a string")
        if self.source_hash and not re.fullmatch(r"[0-9a-f]{64}", self.source_hash):
            raise ValueError("source_hash must be an empty string or SHA-256 hex")
        object.__setattr__(
            self,
            "parent_ids",
            _require_uuid_tuple(self.parent_ids, "parent_ids"),
        )
        parameters = tuple(self.parameters)
        if any(
            not isinstance(item, tuple)
            or len(item) != 2
            or not isinstance(item[0], str)
            or not item[0]
            for item in parameters
        ):
            raise ValueError("parameters must contain non-empty string keys")
        object.__setattr__(self, "parameters", parameters)


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


@dataclass(frozen=True, slots=True)
class ImportBatch:
    structures: tuple[Structure, ...] = ()
    cif_envelopes: tuple[CIFEnvelope, ...] = ()
    symmetry_results: tuple[SymmetryResult, ...] = ()
    calculations: tuple[CalculationRecord, ...] = ()
    datasets: tuple[PropertyDataset | Grid3D, ...] = ()
    basis_sets: tuple[BasisSet, ...] = ()
    orbital_sets: tuple[OrbitalSet, ...] = ()
    density_matrices: tuple[DensityMatrix, ...] = ()
    provenance: tuple[ProvenanceRecord, ...] = ()
    report: ParserReport | None = None

    def __post_init__(self):
        groups = (
            ("structures", Structure),
            ("cif_envelopes", CIFEnvelope),
            ("symmetry_results", SymmetryResult),
            ("calculations", CalculationRecord),
            ("datasets", PropertyDataset),
            ("basis_sets", BasisSet),
            ("orbital_sets", OrbitalSet),
            ("density_matrices", DensityMatrix),
            ("provenance", ProvenanceRecord),
        )
        for name, entity_type in groups:
            values = tuple(getattr(self, name))
            if any(not isinstance(value, entity_type) for value in values):
                raise TypeError(f"{name} contains an invalid entity type")
            object.__setattr__(self, name, values)
        if self.report is not None and not isinstance(self.report, ParserReport):
            raise TypeError("report must be a ParserReport")


@dataclass(slots=True)
class QCProject:
    id: UUID
    schema_version: str
    structures: dict[UUID, Structure] = field(default_factory=dict)
    cif_envelopes: dict[UUID, CIFEnvelope] = field(default_factory=dict)
    symmetry_results: dict[UUID, SymmetryResult] = field(default_factory=dict)
    calculations: dict[UUID, CalculationRecord] = field(default_factory=dict)
    datasets: dict[UUID, PropertyDataset | Grid3D] = field(default_factory=dict)
    basis_sets: dict[UUID, BasisSet] = field(default_factory=dict)
    orbital_sets: dict[UUID, OrbitalSet] = field(default_factory=dict)
    density_matrices: dict[UUID, DensityMatrix] = field(default_factory=dict)
    provenance: dict[UUID, ProvenanceRecord] = field(default_factory=dict)

    def __post_init__(self):
        _require_uuid(self.id, "id")
        _require_text(self.schema_version, "schema_version")
        self._validate_registries()

    def commit(self, batch):
        if not isinstance(batch, ImportBatch):
            raise TypeError("batch must be an ImportBatch")

        incoming_groups = (
            batch.structures,
            batch.cif_envelopes,
            batch.symmetry_results,
            batch.calculations,
            batch.datasets,
            batch.basis_sets,
            batch.orbital_sets,
            batch.density_matrices,
            batch.provenance,
        )
        incoming = tuple(entity for group in incoming_groups for entity in group)
        incoming_ids = tuple(entity.id for entity in incoming)
        if len(set(incoming_ids)) != len(incoming_ids):
            raise ValueError("batch contains duplicate entity UUIDs")

        existing_ids = self._all_entity_ids()
        if existing_ids.intersection(incoming_ids):
            raise ValueError("batch UUID already exists in project")

        structures = dict(self.structures)
        structures.update(
            (structure.id, structure) for structure in batch.structures
        )
        structure_ids = set(structures)
        cif_envelope_ids = set(self.cif_envelopes).union(
            envelope.id for envelope in batch.cif_envelopes
        )
        symmetry_result_ids = set(self.symmetry_results).union(
            result.id for result in batch.symmetry_results
        )
        calculation_ids = set(self.calculations).union(
            calculation.id for calculation in batch.calculations
        )
        datasets = dict(self.datasets)
        datasets.update((dataset.id, dataset) for dataset in batch.datasets)
        dataset_ids = set(datasets)
        basis_sets = dict(self.basis_sets)
        basis_sets.update((basis.id, basis) for basis in batch.basis_sets)
        basis_set_ids = set(basis_sets)
        orbital_set_ids = set(self.orbital_sets).union(
            orbital_set.id for orbital_set in batch.orbital_sets
        )
        density_matrix_ids = set(self.density_matrices).union(
            matrix.id for matrix in batch.density_matrices
        )
        provenance_ids = set(self.provenance).union(
            record.id for record in batch.provenance
        )

        for structure in batch.structures:
            if (
                structure.periodic is not None
                and structure.periodic.cif_envelope_id is not None
                and structure.periodic.cif_envelope_id not in cif_envelope_ids
            ):
                raise ValueError(
                    "periodic structure has a dangling CIF envelope reference"
                )
        for envelope in batch.cif_envelopes:
            self._require_references(
                envelope.provenance_ids,
                provenance_ids,
                "CIF envelope provenance",
            )
        for result in batch.symmetry_results:
            try:
                input_structure = structures[result.structure_id]
            except KeyError as error:
                raise ValueError(
                    "SymmetryResult has a dangling input structure reference"
                ) from error
            try:
                standard_structure = structures[result.standardized_structure_id]
            except KeyError as error:
                raise ValueError(
                    "SymmetryResult has a dangling standardized structure reference"
                ) from error
            if result.equivalent_atoms.shape[0] != len(input_structure.atomic_numbers):
                raise ValueError(
                    "SymmetryResult input atom mappings do not match structure"
                )
            if result.std_mapping_to_primitive.shape[0] != len(
                standard_structure.atomic_numbers
            ):
                raise ValueError(
                    "SymmetryResult standard atom mapping does not match structure"
                )
            self._require_references(
                result.provenance_ids,
                provenance_ids,
                "symmetry provenance",
            )

        for calculation in batch.calculations:
            self._require_references(
                calculation.input_structure_ids + calculation.result_structure_ids,
                structure_ids,
                "calculation structure",
            )
            self._require_references(
                calculation.dataset_ids,
                dataset_ids,
                "calculation dataset",
            )
            self._require_references(
                calculation.provenance_ids,
                provenance_ids,
                "calculation provenance",
            )
        for dataset in batch.datasets:
            if (
                dataset.source_calculation is not None
                and dataset.source_calculation not in calculation_ids
            ):
                raise ValueError("dataset has a dangling calculation reference")
            self._require_references(
                dataset.provenance_ids,
                provenance_ids,
                "dataset provenance",
            )
            if isinstance(dataset, AtomicProperty):
                try:
                    reference = structures[dataset.structure_id]
                except KeyError as error:
                    raise ValueError(
                        "AtomicProperty has a dangling structure reference"
                    ) from error
                if dataset.data.shape[0] != len(reference.atomic_numbers):
                    raise ValueError(
                        "AtomicProperty atom dimension must match its structure"
                    )
            if isinstance(dataset, FrameSet):
                try:
                    reference = structures[dataset.structure_id]
                except KeyError as error:
                    raise ValueError(
                        "FrameSet has a dangling structure reference"
                    ) from error
                if dataset.data.shape[1] != len(reference.atomic_numbers):
                    raise ValueError(
                        "FrameSet atom dimension must match its structure"
                    )
                if dataset.data.unit != reference.coordinates.unit:
                    raise ValueError(
                        "FrameSet and structure coordinate units must match"
                    )
            if isinstance(dataset, VibrationalModeSet):
                try:
                    reference = structures[dataset.structure_id]
                except KeyError as error:
                    raise ValueError(
                        "VibrationalModeSet has a dangling structure reference"
                    ) from error
                if dataset.displacements.shape[1] != len(reference.atomic_numbers):
                    raise ValueError(
                        "VibrationalModeSet atom dimension must match its structure"
                    )
            if isinstance(dataset, ExcitedStateSet):
                if dataset.structure_id not in structure_ids:
                    raise ValueError(
                        "ExcitedStateSet has a dangling structure reference"
                    )
                referenced_ids = tuple(
                    reference_id
                    for references in dataset.state_references
                    for reference_id in references.referenced_ids
                )
                self._require_references(
                    referenced_ids,
                    dataset_ids,
                    "excited-state derived dataset",
                )
            if isinstance(dataset, Spectrum):
                source = datasets.get(dataset.source_dataset_id)
                expected_type = (
                    VibrationalModeSet
                    if dataset.kind in (SpectrumKind.IR, SpectrumKind.RAMAN)
                    else ExcitedStateSet
                )
                if not isinstance(source, expected_type):
                    raise ValueError(
                        f"Spectrum has a dangling {expected_type.__name__} reference"
                    )
            if (
                isinstance(dataset, Grid3D)
                and dataset.structure_id is not None
                and dataset.structure_id not in structure_ids
            ):
                raise ValueError("Grid3D has a dangling structure reference")
            if isinstance(dataset, (BandStructure, DensityOfStates)):
                try:
                    reference = structures[dataset.structure_id]
                except KeyError as error:
                    raise ValueError(
                        f"{type(dataset).__name__} has a dangling structure reference"
                    ) from error
                projections = dataset.projections
                if projections is not None:
                    atom_axis = 3 if isinstance(dataset, BandStructure) else 2
                    if projections.shape[atom_axis] != len(reference.atomic_numbers):
                        raise ValueError(
                            f"{type(dataset).__name__} projection atom dimension must match structure"
                        )
            if isinstance(dataset, PhononModeSet):
                try:
                    reference = structures[dataset.structure_id]
                except KeyError as error:
                    raise ValueError(
                        "PhononModeSet has a dangling structure reference"
                    ) from error
                if dataset.eigenvectors.shape[2] != len(reference.atomic_numbers):
                    raise ValueError(
                        "PhononModeSet atom dimension must match its structure"
                    )
            if isinstance(dataset, FermiSurfaceMesh):
                if dataset.structure_id not in structure_ids:
                    raise ValueError(
                        "FermiSurfaceMesh has a dangling structure reference"
                    )
                source = datasets.get(dataset.band_structure_id)
                if not isinstance(source, BandStructure):
                    raise ValueError(
                        "FermiSurfaceMesh has a dangling band structure reference"
                    )
                if source.structure_id != dataset.structure_id:
                    raise ValueError(
                        "FermiSurfaceMesh and BandStructure must use the same structure"
                    )
                if dataset.spin_index >= source.data.shape[0]:
                    raise ValueError("FermiSurfaceMesh spin index is outside BandStructure")
                if max(dataset.band_indices.values) >= source.data.shape[2]:
                    raise ValueError("FermiSurfaceMesh band index is outside BandStructure")
            if isinstance(dataset, TopologyGraph):
                if dataset.structure_id not in structure_ids:
                    raise ValueError("TopologyGraph has a dangling structure reference")
                if dataset.source_grid_id is not None:
                    source = datasets.get(dataset.source_grid_id)
                    if not isinstance(source, Grid3D):
                        raise ValueError("TopologyGraph has a dangling source grid reference")
                    if source.structure_id != dataset.structure_id:
                        raise ValueError("TopologyGraph and source grid must use the same structure")
        for basis in batch.basis_sets:
            try:
                reference = structures[basis.structure_id]
            except KeyError as error:
                raise ValueError("BasisSet has a dangling structure reference") from error
            if any(
                shell.center_atom >= len(reference.atomic_numbers)
                for shell in basis.shells
            ):
                raise ValueError("BasisSet shell center is outside its structure")
            self._require_references(
                basis.provenance_ids,
                provenance_ids,
                "basis provenance",
            )
        for orbital_set in batch.orbital_sets:
            if orbital_set.structure_id not in structure_ids:
                raise ValueError("OrbitalSet has a dangling structure reference")
            try:
                basis = basis_sets[orbital_set.basis_set_id]
            except KeyError as error:
                raise ValueError("OrbitalSet has a dangling basis reference") from error
            if basis.structure_id != orbital_set.structure_id:
                raise ValueError("OrbitalSet structure must match its BasisSet")
            expected_width = basis.basis_function_count * (
                2 if orbital_set.kind is OrbitalKind.GENERALIZED else 1
            )
            if any(
                channel.coefficients.shape[1] != expected_width
                for channel in orbital_set.channels
            ):
                raise ValueError("OrbitalSet coefficient width must match its BasisSet")
            self._require_references(
                orbital_set.provenance_ids,
                provenance_ids,
                "orbital provenance",
            )
        for matrix in batch.density_matrices:
            if matrix.structure_id not in structure_ids:
                raise ValueError("DensityMatrix has a dangling structure reference")
            try:
                basis = basis_sets[matrix.basis_set_id]
            except KeyError as error:
                raise ValueError("DensityMatrix has a dangling basis reference") from error
            if basis.structure_id != matrix.structure_id:
                raise ValueError("DensityMatrix structure must match its BasisSet")
            if matrix.data.shape != (
                basis.basis_function_count,
                basis.basis_function_count,
            ):
                raise ValueError("DensityMatrix width must match its BasisSet")
            if (
                matrix.source_calculation is not None
                and matrix.source_calculation not in calculation_ids
            ):
                raise ValueError("DensityMatrix has a dangling calculation reference")
            self._require_references(
                matrix.provenance_ids,
                provenance_ids,
                "density matrix provenance",
            )
        all_ids = (
            structure_ids
            | cif_envelope_ids
            | symmetry_result_ids
            | calculation_ids
            | dataset_ids
            | basis_set_ids
            | orbital_set_ids
            | density_matrix_ids
            | provenance_ids
        )
        for record in batch.provenance:
            self._require_references(record.parent_ids, all_ids, "provenance parent")
        if batch.report is not None and set(batch.report.created_entity_ids) != set(
            incoming_ids
        ):
            raise ValueError("parser report created IDs must match the import batch")

        self.structures.update((entity.id, entity) for entity in batch.structures)
        self.cif_envelopes.update(
            (entity.id, entity) for entity in batch.cif_envelopes
        )
        self.symmetry_results.update(
            (entity.id, entity) for entity in batch.symmetry_results
        )
        self.calculations.update((entity.id, entity) for entity in batch.calculations)
        self.datasets.update((entity.id, entity) for entity in batch.datasets)
        self.basis_sets.update((entity.id, entity) for entity in batch.basis_sets)
        self.orbital_sets.update((entity.id, entity) for entity in batch.orbital_sets)
        self.density_matrices.update(
            (entity.id, entity) for entity in batch.density_matrices
        )
        self.provenance.update((entity.id, entity) for entity in batch.provenance)

    def _all_entity_ids(self):
        groups = (
            self.structures,
            self.cif_envelopes,
            self.symmetry_results,
            self.calculations,
            self.datasets,
            self.basis_sets,
            self.orbital_sets,
            self.density_matrices,
            self.provenance,
        )
        ids = [entity_id for group in groups for entity_id in group]
        if len(set(ids)) != len(ids):
            raise ValueError("project registries contain duplicate entity UUIDs")
        return set(ids)

    def _validate_registries(self):
        groups = (
            (self.structures, Structure, "structures"),
            (self.cif_envelopes, CIFEnvelope, "cif_envelopes"),
            (self.symmetry_results, SymmetryResult, "symmetry_results"),
            (self.calculations, CalculationRecord, "calculations"),
            (self.datasets, PropertyDataset, "datasets"),
            (self.basis_sets, BasisSet, "basis_sets"),
            (self.orbital_sets, OrbitalSet, "orbital_sets"),
            (self.density_matrices, DensityMatrix, "density_matrices"),
            (self.provenance, ProvenanceRecord, "provenance"),
        )
        for registry, entity_type, name in groups:
            if not isinstance(registry, dict):
                raise TypeError(f"{name} must be a dict")
            if any(
                not isinstance(entity, entity_type) or entity_id != entity.id
                for entity_id, entity in registry.items()
            ):
                raise ValueError(f"{name} keys and entity IDs must match")
        self._all_entity_ids()

    @staticmethod
    def _require_references(references, valid_ids, name):
        if any(reference not in valid_ids for reference in references):
            raise ValueError(f"{name} reference is dangling")
