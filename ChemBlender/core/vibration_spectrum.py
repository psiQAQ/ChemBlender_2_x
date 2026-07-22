import hashlib
import json
from math import isfinite, log
from uuid import uuid4

from .model import (
    ArrayData,
    DatasetStatus,
    ExcitedStateSet,
    ImportBatch,
    ProvenanceRecord,
    Spectrum,
    SpectrumKind,
    SpectrumProfile,
    VibrationalModeSet,
)


DERIVATION_VERSION = "2"


def _identity(source_dataset, operation, parameters):
    payload = {
        "parent": [str(source_dataset.id), source_dataset.revision],
        "operation": operation,
        "operation_version": DERIVATION_VERSION,
        "parameters": parameters,
    }
    encoded = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _derive_spectrum(
    source_dataset,
    *,
    frequencies,
    intensities,
    intensity_unit,
    kind,
    profile,
    axis,
    fwhm,
    selection_policy,
    status,
    operation,
):
    import numpy

    frequencies = numpy.asarray(frequencies)
    intensities = numpy.asarray(intensities)
    if (
        frequencies.ndim != 1
        or intensities.shape != frequencies.shape
        or frequencies.size == 0
        or numpy.iscomplexobj(frequencies)
        or numpy.iscomplexobj(intensities)
        or not numpy.all(numpy.isfinite(frequencies))
        or not numpy.all(numpy.isfinite(intensities))
    ):
        raise ValueError("spectrum frequencies and intensities must be finite vectors")

    if profile is SpectrumProfile.STICK:
        if axis is not None or fwhm is not None:
            raise ValueError("stick spectrum does not accept axis or fwhm")
        sample_axis = numpy.asarray(frequencies, dtype=float)
        values = numpy.asarray(intensities, dtype=float)
        normalized_fwhm = None
    else:
        if (
            isinstance(fwhm, bool)
            or not isinstance(fwhm, (int, float))
            or not isfinite(fwhm)
            or fwhm <= 0.0
        ):
            raise ValueError("broadened spectrum requires positive finite fwhm")
        sample_axis = numpy.asarray(axis)
        if (
            sample_axis.ndim != 1
            or sample_axis.size == 0
            or numpy.iscomplexobj(sample_axis)
            or not numpy.all(numpy.isfinite(sample_axis))
            or (sample_axis.size > 1 and not numpy.all(numpy.diff(sample_axis) > 0.0))
        ):
            raise ValueError("spectrum axis must be a finite increasing vector")
        sample_axis = numpy.asarray(sample_axis, dtype=float)
        delta = (sample_axis[:, None] - frequencies[None, :]) / float(fwhm)
        if profile is SpectrumProfile.GAUSSIAN:
            lines = numpy.exp(-4.0 * log(2.0) * delta**2)
        else:
            lines = 1.0 / (1.0 + 4.0 * delta**2)
        values = lines @ intensities
        normalized_fwhm = float(fwhm)

    axis_hash = hashlib.sha256(
        numpy.asarray(sample_axis, dtype="<f8").tobytes(order="C")
    ).hexdigest()
    parameters = {
        "kind": kind.value,
        "profile": profile.value,
        "fwhm": normalized_fwhm,
        "selection_policy": selection_policy,
        "axis_hash": axis_hash,
        "sample_count": int(sample_axis.size),
    }
    revision = _identity(source_dataset, operation, parameters)
    provenance_id = uuid4()
    provenance = ProvenanceRecord(
        id=provenance_id,
        revision=revision,
        producer="ChemBlender spectrum derivation",
        producer_version=DERIVATION_VERSION,
        source="",
        source_hash=revision,
        parent_ids=(source_dataset.id,),
        operation=operation,
        parameters=tuple(parameters.items()),
    )
    spectrum = Spectrum(
        id=uuid4(),
        revision=revision,
        semantic_role=f"{kind.value}_spectrum",
        domain="frequency",
        data=ArrayData(numpy.asarray(values, dtype=float), ("sample",), intensity_unit),
        status=status,
        source_calculation=source_dataset.source_calculation,
        provenance_ids=(provenance_id,),
        axis=ArrayData(
            numpy.asarray(sample_axis, dtype=float),
            ("sample",),
            "inverse_centimeter",
        ),
        kind=kind,
        profile=profile,
        source_dataset_id=source_dataset.id,
        fwhm=normalized_fwhm,
        selection_policy=selection_policy,
    )
    return ImportBatch(datasets=(spectrum,), provenance=(provenance,))


def derive_vibrational_spectrum(
    mode_set,
    *,
    kind,
    profile,
    axis=None,
    fwhm=None,
    include_imaginary=True,
):
    import numpy

    if not isinstance(mode_set, VibrationalModeSet):
        raise TypeError("mode_set must be a VibrationalModeSet")
    if kind not in (SpectrumKind.IR, SpectrumKind.RAMAN):
        raise ValueError("vibrational spectra support only IR and Raman kinds")
    if not isinstance(profile, SpectrumProfile):
        raise TypeError("profile must be a SpectrumProfile")
    if not isinstance(include_imaginary, bool):
        raise TypeError("include_imaginary must be a bool")
    if kind is SpectrumKind.IR:
        source = mode_set.ir_intensities
        intensity_unit = "kilometer_per_mole"
    else:
        source = mode_set.raman_activities
        intensity_unit = "angstrom_four_per_dalton"
    if source is None:
        raise ValueError(f"mode_set does not contain {kind.value} intensities")
    frequencies = numpy.asarray(mode_set.data.values)
    intensities = numpy.asarray(source.values)
    mask = numpy.ones(frequencies.shape, dtype=bool)
    if not include_imaginary:
        mask = frequencies >= 0.0
    frequencies = frequencies[mask]
    intensities = intensities[mask]
    if frequencies.size == 0:
        raise ValueError("spectrum selection contains no modes")
    return _derive_spectrum(
        mode_set,
        frequencies=frequencies,
        intensities=intensities,
        intensity_unit=intensity_unit,
        kind=kind,
        profile=profile,
        axis=axis,
        fwhm=fwhm,
        selection_policy=(
            "all_modes" if include_imaginary else "nonnegative_modes"
        ),
        status=DatasetStatus.COMPLETE,
        operation="derive_vibrational_spectrum",
    )


def derive_electronic_spectrum(
    state_set,
    *,
    kind,
    profile,
    axis=None,
    fwhm=None,
):
    if not isinstance(state_set, ExcitedStateSet):
        raise TypeError("state_set must be an ExcitedStateSet")
    if kind not in (SpectrumKind.UV_VIS, SpectrumKind.ECD):
        raise ValueError("electronic spectra support only UV-Vis and ECD kinds")
    if not isinstance(profile, SpectrumProfile):
        raise TypeError("profile must be a SpectrumProfile")
    if kind is SpectrumKind.UV_VIS:
        strengths = state_set.oscillator_strengths
        intensity_unit = "dimensionless"
        status = DatasetStatus.COMPLETE
    else:
        strengths = state_set.rotatory_strengths
        intensity_unit = "unknown"
        status = DatasetStatus.AMBIGUOUS
    if strengths is None:
        raise ValueError(f"state_set does not contain {kind.value} strengths")
    return _derive_spectrum(
        state_set,
        frequencies=state_set.data.values,
        intensities=strengths.values,
        intensity_unit=intensity_unit,
        kind=kind,
        profile=profile,
        axis=axis,
        fwhm=fwhm,
        selection_policy="all_states",
        status=status,
        operation="derive_electronic_spectrum",
    )
