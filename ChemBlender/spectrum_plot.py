"""Blender Curve adapter for normalized spectrum datasets."""

import bpy

from .core import Spectrum, SpectrumProfile


def _poly_spline(curve, coordinates):
    spline = curve.splines.new("POLY")
    spline.points.add(len(coordinates) - 1)
    for point, coordinate in zip(spline.points, coordinates):
        point.co = (*coordinate, 1.0)


def create_spectrum_plot(
    spectrum,
    *,
    name="ChemBlender Spectrum",
    collection=None,
):
    """Create a 2D curve without changing camera, lights, or render state."""
    import numpy

    if not isinstance(spectrum, Spectrum):
        raise TypeError("spectrum must be a Spectrum")
    axis = numpy.asarray(spectrum.axis.values, dtype=float)
    values = numpy.asarray(spectrum.data.values, dtype=float)
    if not numpy.all(numpy.isfinite(axis)) or not numpy.all(numpy.isfinite(values)):
        raise ValueError("spectrum samples must be finite")
    target = collection or bpy.context.collection
    if target is None:
        raise ValueError("a Blender collection is required")

    curve = bpy.data.curves.new(name=name, type="CURVE")
    curve.dimensions = "2D"
    obj = None
    try:
        obj = bpy.data.objects.new(name, curve)
        target.objects.link(obj)
        if spectrum.profile is SpectrumProfile.STICK:
            for x, y in zip(axis, values):
                _poly_spline(curve, ((float(x), 0.0, 0.0), (float(x), float(y), 0.0)))
        else:
            _poly_spline(
                curve,
                tuple((float(x), float(y), 0.0) for x, y in zip(axis, values)),
            )
        obj["cb_dataset_id"] = str(spectrum.id)
        obj["cb_dataset_revision"] = spectrum.revision
        obj["cb_semantic_role"] = spectrum.semantic_role
        obj["cb_spectrum_kind"] = spectrum.kind.value
        obj["cb_spectrum_profile"] = spectrum.profile.value
        obj["cb_axis_unit"] = spectrum.axis.unit
        obj["cb_intensity_unit"] = spectrum.data.unit
        obj["cb_source_dataset_id"] = str(spectrum.source_dataset_id)
        obj["cb_plot_contract"] = "spectrum_curve_v1"
        return obj
    except Exception:
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.curves.remove(curve)
        raise
