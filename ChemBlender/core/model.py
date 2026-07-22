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
class Structure:
    id: UUID
    revision: str
    atomic_numbers: tuple[int, ...]
    coordinates: ArrayData
    cell: ArrayData | None = None

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
        object.__setattr__(self, "atomic_numbers", atomic_numbers)


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
