import hashlib
import json
from math import isfinite, log
from uuid import uuid4

from .model import (
    ArrayData,
    DatasetStatus,
    ImportBatch,
    ProvenanceRecord,
    Spectrum,
    SpectrumKind,
    SpectrumProfile,
    VibrationalModeSet,
)


DERIVATION_VERSION = "1"


def _identity(mode_set, parameters):
    payload = {
        "parent": [str(mode_set.id), mode_set.revision],
        "operation": "derive_vibrational_spectrum",
        "operation_version": DERIVATION_VERSION,
        "parameters": parameters,
    }
    encoded = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_intensities(mode_set, kind):
    if kind is SpectrumKind.IR:
        return mode_set.ir_intensities, "kilometer_per_mole"
    return mode_set.raman_activities, "angstrom_four_per_dalton"


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
    if not isinstance(kind, SpectrumKind):
        raise TypeError("kind must be a SpectrumKind")
    if not isinstance(profile, SpectrumProfile):
        raise TypeError("profile must be a SpectrumProfile")
    if not isinstance(include_imaginary, bool):
        raise TypeError("include_imaginary must be a bool")
    source, intensity_unit = _source_intensities(mode_set, kind)
    if source is None:
        raise ValueError(f"mode_set does not contain {kind.value} intensities")
    frequencies = numpy.asarray(mode_set.data.values)
    intensities = numpy.asarray(source.values)
    if (
        numpy.iscomplexobj(frequencies)
        or numpy.iscomplexobj(intensities)
        or not numpy.all(numpy.isfinite(frequencies))
        or not numpy.all(numpy.isfinite(intensities))
    ):
        raise ValueError("mode frequencies and intensities must be finite and real")
    mask = numpy.ones(frequencies.shape, dtype=bool)
    if not include_imaginary:
        mask = frequencies >= 0.0
    frequencies = numpy.asarray(frequencies[mask], dtype=float)
    intensities = numpy.asarray(intensities[mask], dtype=float)
    if frequencies.size == 0:
        raise ValueError("spectrum selection contains no modes")

    if profile is SpectrumProfile.STICK:
        if axis is not None or fwhm is not None:
            raise ValueError("stick spectrum does not accept axis or fwhm")
        sample_axis = frequencies
        values = intensities
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
        "include_imaginary": include_imaginary,
        "axis_hash": axis_hash,
        "sample_count": int(sample_axis.size),
    }
    revision = _identity(mode_set, parameters)
    provenance_id = uuid4()
    provenance = ProvenanceRecord(
        id=provenance_id,
        revision=revision,
        producer="ChemBlender spectrum derivation",
        producer_version=DERIVATION_VERSION,
        source="",
        source_hash=revision,
        parent_ids=(mode_set.id,),
        operation="derive_vibrational_spectrum",
        parameters=tuple(parameters.items()),
    )
    spectrum = Spectrum(
        id=uuid4(),
        revision=revision,
        semantic_role=f"{kind.value}_spectrum",
        domain="frequency",
        data=ArrayData(
            numpy.asarray(values, dtype=float),
            ("sample",),
            intensity_unit,
        ),
        status=DatasetStatus.COMPLETE,
        source_calculation=mode_set.source_calculation,
        provenance_ids=(provenance_id,),
        axis=ArrayData(
            numpy.asarray(sample_axis, dtype=float),
            ("sample",),
            "inverse_centimeter",
        ),
        kind=kind,
        profile=profile,
        source_dataset_id=mode_set.id,
        fwhm=normalized_fwhm,
        include_imaginary=include_imaginary,
    )
    return ImportBatch(datasets=(spectrum,), provenance=(provenance,))
