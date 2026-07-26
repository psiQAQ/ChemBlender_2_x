from dataclasses import dataclass
from math import isfinite
from uuid import UUID

from .arrays import ArrayData
from .common import _require_text, _require_uuid, _require_uuid_tuple


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
class MolecularTopology:
    bond_indices: ArrayData
    bond_orders: ArrayData

    def __post_init__(self):
        import numpy

        indices = numpy.asarray(self.bond_indices.values)
        orders = numpy.asarray(self.bond_orders.values)
        if (
            self.bond_indices.dims != ("bond", "endpoint")
            or len(self.bond_indices.shape) != 2
            or self.bond_indices.shape[1] != 2
            or self.bond_indices.unit != "dimensionless"
            or indices.dtype.kind not in "iu"
            or numpy.any(indices < 0)
        ):
            raise ValueError("bond_indices must contain non-negative integer pairs")
        if (
            self.bond_orders.dims != ("bond",)
            or self.bond_orders.shape != (self.bond_indices.shape[0],)
            or self.bond_orders.unit != "dimensionless"
            or orders.dtype.kind not in "iuf"
            or not numpy.all(numpy.isfinite(orders))
            or numpy.any(orders <= 0.0)
        ):
            raise ValueError("bond_orders must contain one positive value per bond")


@dataclass(frozen=True, slots=True)
class Structure:
    id: UUID
    revision: str
    atomic_numbers: tuple[int, ...]
    coordinates: ArrayData
    cell: ArrayData | None = None
    periodic: PeriodicSiteData | None = None
    molecular_charge: int | None = None
    molecular_multiplicity: int | None = None
    topology: MolecularTopology | None = None

    def __post_init__(self):
        import numpy

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
        if self.molecular_charge is not None and (
            isinstance(self.molecular_charge, bool)
            or not isinstance(self.molecular_charge, int)
        ):
            raise TypeError("molecular_charge must be an integer or None")
        if self.molecular_multiplicity is not None and (
            isinstance(self.molecular_multiplicity, bool)
            or not isinstance(self.molecular_multiplicity, int)
            or self.molecular_multiplicity <= 0
        ):
            raise ValueError("molecular_multiplicity must be positive or None")
        if self.topology is not None:
            if not isinstance(self.topology, MolecularTopology):
                raise TypeError("topology must be MolecularTopology or None")
            indices = numpy.asarray(self.topology.bond_indices.values)
            if indices.size and int(indices.max()) >= len(atomic_numbers):
                raise ValueError("topology bond index is outside the structure")
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
