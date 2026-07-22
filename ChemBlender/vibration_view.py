import operator
from math import isfinite, sin

import bpy

from .core import VibrationalModeSet
from .dataset_view import _read_vector_values, write_vector_view


_REFERENCE_ATTRIBUTE = "cbq_vibration_reference_position"


def _require_number(value, name, *, positive=False):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or (positive and value <= 0.0)
    ):
        requirement = "positive finite" if positive else "finite"
        raise ValueError(f"{name} must be a {requirement} number")
    return float(value)


def _vector_attribute(mesh, name, values):
    import numpy

    values = numpy.asarray(values, dtype=float)
    if values.shape != (len(mesh.vertices), 3) or not numpy.all(numpy.isfinite(values)):
        raise ValueError(f"{name} must contain one finite vector per mesh vertex")
    attribute = mesh.attributes.get(name)
    if attribute is not None and (
        attribute.data_type != "FLOAT_VECTOR" or attribute.domain != "POINT"
    ):
        mesh.attributes.remove(attribute)
        attribute = None
    if attribute is None:
        attribute = mesh.attributes.new(name, "FLOAT_VECTOR", "POINT")
    attribute.data.foreach_set("vector", values.reshape(-1))
    return attribute


def _read_reference_positions(mesh):
    import numpy

    attribute = mesh.attributes.get(_REFERENCE_ATTRIBUTE)
    if (
        attribute is None
        or attribute.data_type != "FLOAT_VECTOR"
        or attribute.domain != "POINT"
    ):
        raise ValueError("mesh does not contain vibration reference positions")
    values = numpy.empty(len(mesh.vertices) * 3, dtype=float)
    attribute.data.foreach_get("vector", values)
    return values.reshape((len(mesh.vertices), 3))


def create_vibration_view(
    obj,
    mode_set,
    *,
    mode_index,
    arrow_scale=1.0,
):
    import numpy

    if not isinstance(obj, bpy.types.Object) or obj.type != "MESH":
        raise TypeError("obj must be a Blender Mesh object")
    if not isinstance(mode_set, VibrationalModeSet):
        raise TypeError("mode_set must be a VibrationalModeSet")
    if isinstance(mode_index, bool):
        raise TypeError("mode_index must be an integer")
    try:
        mode_index = operator.index(mode_index)
    except TypeError as error:
        raise TypeError("mode_index must be an integer") from error
    if not 0 <= mode_index < mode_set.data.shape[0]:
        raise IndexError("mode_index is outside the VibrationalModeSet")
    arrow_scale = _require_number(arrow_scale, "arrow_scale", positive=True)
    if len(obj.data.vertices) != mode_set.displacements.shape[1]:
        raise ValueError("mesh vertex count must match vibration atom count")

    reference = obj.data.attributes.get(_REFERENCE_ATTRIBUTE)
    if reference is None:
        positions = numpy.empty(len(obj.data.vertices) * 3, dtype=float)
        obj.data.vertices.foreach_get("co", positions)
        _vector_attribute(
            obj.data,
            _REFERENCE_ATTRIBUTE,
            positions.reshape((len(obj.data.vertices), 3)),
        )
    elif reference.data_type != "FLOAT_VECTOR" or reference.domain != "POINT":
        raise ValueError("mesh has an incompatible vibration reference attribute")
    displacements = numpy.asarray(mode_set.displacements.values)[mode_index]
    modifier = write_vector_view(
        obj,
        displacements,
        dataset_id=mode_set.id,
        revision=mode_set.revision,
        semantic_role="vibration_displacement",
        unit=mode_set.displacements.unit,
        display_scale=arrow_scale,
    )
    obj["cb_vibration_mode_set_id"] = str(mode_set.id)
    obj["cb_vibration_mode_set_revision"] = mode_set.revision
    obj["cb_vibration_mode_index"] = int(mode_index)
    obj["cb_vibration_arrow_scale"] = arrow_scale
    obj["cb_vibration_phase"] = 0.0
    obj["cb_vibration_amplitude_scale"] = 0.0
    obj["cb_vibration_attribute_contract"] = "vector_arrow_v1"
    obj.data.update()
    return modifier


def apply_vibration_phase(obj, phase, *, amplitude_scale=1.0):
    import numpy

    if not isinstance(obj, bpy.types.Object) or obj.type != "MESH":
        raise TypeError("obj must be a Blender Mesh object")
    phase = _require_number(phase, "phase")
    amplitude_scale = _require_number(amplitude_scale, "amplitude_scale")
    try:
        arrow_scale = float(obj["cb_vibration_arrow_scale"])
    except KeyError as error:
        raise ValueError("object is not configured as a vibration view") from error
    if not isfinite(arrow_scale) or arrow_scale <= 0.0:
        raise ValueError("object has invalid vibration arrow scale")
    reference = _read_reference_positions(obj.data)
    displayed = _read_vector_values(obj.data)
    positions = reference + displayed / arrow_scale * (amplitude_scale * sin(phase))
    if not numpy.all(numpy.isfinite(positions)):
        raise ValueError("vibration phase produced non-finite positions")
    obj.data.vertices.foreach_set("co", positions.reshape(-1))
    obj["cb_vibration_phase"] = phase
    obj["cb_vibration_amplitude_scale"] = amplitude_scale
    obj.data.update()
