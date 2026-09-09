"""Blender Curve adapter for normalized spectrum datasets."""

import bpy
from math import isfinite

from cbq_core.model import Spectrum
from cbq_core.model import SpectrumProfile


_PLOT_WIDTH = 8.0
_PLOT_HEIGHT = 5.0


def _plot_range(values):
    lower, upper = map(float, values)
    if not isfinite(lower) or not isfinite(upper) or lower > upper:
        raise ValueError("plot limits must be finite and ordered")
    if lower == upper:
        padding = max(abs(lower) * .05, .5)
        lower, upper = lower - padding, upper + padding
    if not isfinite(upper - lower):
        raise ValueError("plot span must be finite")
    return lower, upper


def _plot_position(x, y, x_range, y_range):
    """Map scientific values to a fixed display frame without rescaling source arrays."""
    return ((float(x) - x_range[0]) / (x_range[1] - x_range[0]) * _PLOT_WIDTH,
            (float(y) - y_range[0]) / (y_range[1] - y_range[0]) * _PLOT_HEIGHT, 0.)


def _plot_frame(obj, x_range, y_range):
    x_range, y_range = _plot_range(x_range), _plot_range(y_range)
    obj["cb_plot_coordinate_system"] = "normalized_axes_v1"
    obj["cb_plot_x_range"] = list(x_range)
    obj["cb_plot_y_range"] = list(y_range)
    obj["cb_plot_width"] = _PLOT_WIDTH
    obj["cb_plot_height"] = _PLOT_HEIGHT
    return x_range, y_range


def _poly_spline(curve, coordinates):
    spline = curve.splines.new("POLY")
    spline.points.add(len(coordinates) - 1)
    for point, coordinate in zip(spline.points, coordinates):
        point.co = (*coordinate, 1.0)
    return spline


def _positive(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return float(value)


def _flat_material(name, color):
    from .scientific_materials import flat_material

    material = flat_material(name, color)
    material["cb_scientific_owned"] = True
    return material


def _curve_object(name, collection, *, radius=0.01, material=None):
    curve = bpy.data.curves.new(name=name, type="CURVE")
    curve["cb_scientific_owned"] = True
    curve.dimensions = "3D"
    curve.bevel_depth = radius
    curve.bevel_resolution = 2
    curve.use_fill_caps = True
    obj = None
    try:
        obj = bpy.data.objects.new(name, curve)
        collection.objects.link(obj)
        if material is not None:
            curve.materials.append(material)
        return obj
    except Exception:
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.curves.remove(curve)
        raise


def _remove_objects(objects, *, materials=(), groups=()):
    """Rollback only the listed objects and unused resources owned by this adapter."""
    objects = set(objects)
    data = {obj.data for obj in objects if obj.data is not None}
    materials = set(materials) | {mat for block in data for mat in getattr(block, "materials", ()) if mat}
    groups = set(groups) | {modifier.node_group for obj in objects for modifier in obj.modifiers
                           if modifier.type == "NODES" and modifier.node_group is not None}
    for obj in objects:
        for child in tuple(obj.children):
            if child not in objects:
                transform = child.matrix_world.copy()
                child.parent = None
                child.matrix_world = transform
        bpy.data.objects.remove(obj, do_unlink=True)
    for block in data | groups:
        if block.users == 0 and block.get("cb_scientific_owned"):
            bpy.data.batch_remove(ids=(block,))
    for material in materials:
        if material.users == 0 and material.get("cb_scientific_owned"):
            bpy.data.materials.remove(material)


def _plot_axes(root, collection, x_range, y_range, x_label, y_label, *,
               x_ticks=None, material=None, note=""):
    """Draw readable native axes; tick labels retain the original scientific values."""
    import numpy

    x_range, y_range = _plot_range(x_range), _plot_range(y_range)
    x_min, x_max = x_range
    y_min, y_max = y_range
    dx, dy, size = _PLOT_WIDTH, _PLOT_HEIGHT, .20
    made = []
    created_material = None
    try:
        if material is None:
            created_material = material = _flat_material("ChemBlender Plot Axes", (.12, .12, .12, 1.))
        axes = _curve_object(root.name + " Axes", collection, radius=min(dx, dy) * .0015, material=material)
        made.append(axes)
        axes.parent = root
        axes["cb_scientific_component"] = "plot_axes"
        _poly_spline(axes.data, ((0., dy, 0.), (0., 0., 0.), (dx, 0., 0.)))
        if y_min < 0 < y_max:
            y_zero = _plot_position(x_min, 0., x_range, y_range)[1]
            _poly_spline(axes.data, ((0., y_zero, 0.), (dx, y_zero, 0.)))
        if x_min < 0 < x_max:
            x_zero = _plot_position(0., y_min, x_range, y_range)[0]
            _poly_spline(axes.data, ((x_zero, 0., 0.), (x_zero, dy, 0.)))

        def label(body, x, y, align="CENTER", rotation=0.):
            text = bpy.data.curves.new(root.name + " Label", "FONT")
            text["cb_scientific_owned"] = True
            obj = None
            try:
                obj = bpy.data.objects.new(root.name + " Label", text)
                made.append(obj)
                collection.objects.link(obj)
                obj.parent = root
                obj["cb_scientific_component"] = "plot_label"
                text.body, text.size, text.align_x = body, size, align
                text.materials.append(material)
                obj.location = (x, y, 0.)
                obj.rotation_euler.z = rotation
            except Exception:
                if obj is None:
                    bpy.data.curves.remove(text)
                raise

        if x_ticks is None:
            x_ticks = tuple((float(x), f"{x:.4g}") for x in numpy.linspace(x_min, x_max, 5))
        # Consecutive branch endpoints may share a distance but have different labels.
        combined = {}
        for position, text in x_ticks:
            if text not in combined.setdefault(float(position), []):
                combined[float(position)].append(text)
        for x, names in combined.items():
            position = _plot_position(x, y_min, x_range, y_range)[0]
            _poly_spline(axes.data, ((position, 0., 0.), (position, -dy * .018, 0.)))
            label(" | ".join(names), position, -dy * .07)
        y_ticks = list(numpy.linspace(y_min, y_max, 5))
        if y_min < 0 < y_max:
            # Label the actual zero line, leaving room between neighboring labels.
            y_ticks = sorted([value for value in y_ticks if abs(value) > (y_max - y_min) * .06] + [0.])
        for y in y_ticks:
            position = _plot_position(x_min, y, x_range, y_range)[1]
            _poly_spline(axes.data, ((0., position, 0.), (-dx * .012, position, 0.)))
            label(f"{y:.4g}", -dx * .025, position - size * .35, "RIGHT")
        label(x_label, dx / 2., -dy * .16)
        label(y_label, -dx * .16, dy / 2., rotation=1.5707963267948966)
        if note:
            label(note, 0., dy * 1.07, "LEFT")
        return tuple(made)
    except Exception:
        _remove_objects(made, materials=(() if created_material is None else (created_material,)))
        raise


def create_spectrum_plot(
    spectrum,
    *,
    name="ChemBlender Spectrum",
    collection=None,
    material=None,
    axis_material=None,
    axes=True,
    line_radius=0.01,
):
    """Create a 2D curve without changing camera, lights, or render state."""
    import numpy

    if not isinstance(spectrum, Spectrum):
        raise TypeError("spectrum must be a Spectrum")
    line_radius = _positive(line_radius, "line_radius")
    if not isinstance(axes, bool):
        raise TypeError("axes must be a bool")
    axis = numpy.asarray(spectrum.axis.values, dtype=float)
    values = numpy.asarray(spectrum.data.values, dtype=float)
    if not numpy.all(numpy.isfinite(axis)) or not numpy.all(numpy.isfinite(values)):
        raise ValueError("spectrum samples must be finite")
    target = collection or bpy.context.collection
    if target is None:
        raise ValueError("a Blender collection is required")

    curve = None
    obj = None
    made = []
    created_material = None
    try:
        if material is None:
            created_material = material = _flat_material("ChemBlender Spectrum", (.08, .25, .65, 1.))
        obj = _curve_object(name, target, radius=line_radius, material=material)
        made.append(obj)
        curve = obj.data
        x_low, x_high = _plot_range((axis.min(), axis.max()))
        padding = (x_high - x_low) * .05
        # Edge sticks must remain distinct from the vertical axis.
        x_range, y_range = _plot_frame(obj, (x_low - padding, x_high + padding),
                                      (min(0., values.min()), max(0., values.max())))
        if spectrum.profile is SpectrumProfile.STICK:
            for x, y in zip(axis, values):
                _poly_spline(curve, (_plot_position(x, 0., x_range, y_range),
                                     _plot_position(x, y, x_range, y_range)))
        else:
            _poly_spline(
                curve,
                tuple(_plot_position(x, y, x_range, y_range) for x, y in zip(axis, values)),
            )
        obj["cb_dataset_id"] = str(spectrum.id)
        obj["cb_dataset_revision"] = spectrum.revision
        obj["cb_semantic_role"] = spectrum.semantic_role
        obj["cb_spectrum_kind"] = spectrum.kind.value
        obj["cb_spectrum_profile"] = spectrum.profile.value
        obj["cb_axis_unit"] = spectrum.axis.unit
        obj["cb_intensity_unit"] = spectrum.data.unit
        obj["cb_plot_x_unit"] = spectrum.axis.unit
        obj["cb_plot_y_unit"] = spectrum.data.unit
        obj["cb_source_dataset_id"] = str(spectrum.source_dataset_id)
        obj["cb_plot_contract"] = "spectrum_curve_v1"
        if axes:
            made.extend(_plot_axes(obj, target, x_range, y_range,
                                  spectrum.axis.unit, spectrum.data.unit,
                                  material=axis_material,
                                  note=f"{spectrum.kind.value} / {spectrum.profile.value}"))
        return obj
    except Exception:
        _remove_objects(made, materials=(() if created_material is None else (created_material,)))
        raise
