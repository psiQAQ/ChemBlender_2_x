from dataclasses import dataclass
from math import isfinite
from uuid import UUID

from .arrays import ArrayData
from .common import EnergyReference, _require_token, _require_uuid
from .properties import PropertyDataset


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
