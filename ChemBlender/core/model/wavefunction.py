from dataclasses import dataclass
from uuid import UUID

from .arrays import ArrayData
from .common import (
    BasisFunctionKind,
    DensityMatrixLevel,
    DensityMatrixSpin,
    OrbitalKind,
    _require_text,
    _require_uuid,
    _require_uuid_tuple,
)


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
