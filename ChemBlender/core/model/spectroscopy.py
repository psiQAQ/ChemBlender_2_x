from dataclasses import dataclass
from math import isfinite
from uuid import UUID

from .arrays import ArrayData
from .common import (
    DatasetStatus,
    SpectrumKind,
    SpectrumProfile,
    SpinChannel,
    _require_token,
    _require_uuid,
)
from .properties import PropertyDataset


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
