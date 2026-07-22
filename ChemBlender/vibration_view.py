import operator
from math import isfinite, sin

import bpy

from .core import VibrationalModeSet


_GROUP_NAME = "ChemBlender Vibration Arrows"
_MODIFIER_NAME = "ChemBlender Vibration Arrows"
_CONTRACT = "vibration_arrow_v1"
_DISPLACEMENT_ATTRIBUTE = "cbq_vibration_displacement"
_MAGNITUDE_ATTRIBUTE = "cbq_vibration_magnitude"
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


def _float_attribute(mesh, name, values):
    import numpy

    values = numpy.asarray(values, dtype=float)
    if values.shape != (len(mesh.vertices),) or not numpy.all(numpy.isfinite(values)):
        raise ValueError(f"{name} must contain one finite value per mesh vertex")
    attribute = mesh.attributes.get(name)
    if attribute is not None and (
        attribute.data_type != "FLOAT" or attribute.domain != "POINT"
    ):
        mesh.attributes.remove(attribute)
        attribute = None
    if attribute is None:
        attribute = mesh.attributes.new(name, "FLOAT", "POINT")
    attribute.data.foreach_set("value", values)
    return attribute


def _read_vector_attribute(mesh, name):
    import numpy

    attribute = mesh.attributes.get(name)
    if attribute is None or attribute.data_type != "FLOAT_VECTOR":
        raise ValueError(f"mesh does not contain {name}")
    values = numpy.empty(len(mesh.vertices) * 3, dtype=float)
    attribute.data.foreach_get("vector", values)
    return values.reshape((len(mesh.vertices), 3))


def _ensure_arrow_node_group():
    group = bpy.data.node_groups.get(_GROUP_NAME)
    if group is not None:
        if (
            group.bl_idname != "GeometryNodeTree"
            or group.get("cbq_contract") != _CONTRACT
        ):
            raise RuntimeError(f"incompatible node group already uses {_GROUP_NAME}")
        return group

    group = bpy.data.node_groups.new(_GROUP_NAME, "GeometryNodeTree")
    try:
        group.is_modifier = True
        group.interface.new_socket(
            name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry"
        )
        group.interface.new_socket(
            name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry"
        )
        nodes = group.nodes
        links = group.links
        group_input = nodes.new("NodeGroupInput")
        group_output = nodes.new("NodeGroupOutput")
        mesh_to_points = nodes.new("GeometryNodeMeshToPoints")
        mesh_to_points.mode = "VERTICES"
        named = nodes.new("GeometryNodeInputNamedAttribute")
        named.data_type = "FLOAT_VECTOR"
        named.inputs["Name"].default_value = _DISPLACEMENT_ATTRIBUTE
        length = nodes.new("ShaderNodeVectorMath")
        length.operation = "LENGTH"
        align = nodes.new("FunctionNodeAlignEulerToVector")
        align.axis = "Z"
        cone = nodes.new("GeometryNodeMeshCone")
        cone.inputs["Vertices"].default_value = 12
        cone.inputs["Radius Top"].default_value = 0.0
        cone.inputs["Radius Bottom"].default_value = 1.0
        cone.inputs["Depth"].default_value = 1.0
        transform = nodes.new("GeometryNodeTransform")
        transform.inputs["Translation"].default_value = (0.0, 0.0, 0.5)
        combine = nodes.new("ShaderNodeCombineXYZ")
        combine.inputs["X"].default_value = 0.08
        combine.inputs["Y"].default_value = 0.08
        instance = nodes.new("GeometryNodeInstanceOnPoints")
        join = nodes.new("GeometryNodeJoinGeometry")

        links.new(group_input.outputs["Geometry"], mesh_to_points.inputs["Mesh"])
        links.new(named.outputs["Attribute"], length.inputs[0])
        links.new(named.outputs["Attribute"], align.inputs["Vector"])
        links.new(cone.outputs["Mesh"], transform.inputs["Geometry"])
        links.new(transform.outputs["Geometry"], instance.inputs["Instance"])
        links.new(mesh_to_points.outputs["Points"], instance.inputs["Points"])
        links.new(align.outputs["Rotation"], instance.inputs["Rotation"])
        links.new(length.outputs["Value"], combine.inputs["Z"])
        links.new(combine.outputs["Vector"], instance.inputs["Scale"])
        links.new(group_input.outputs["Geometry"], join.inputs["Geometry"])
        links.new(instance.outputs["Instances"], join.inputs["Geometry"])
        links.new(join.outputs["Geometry"], group_output.inputs["Geometry"])
        group["cbq_contract"] = _CONTRACT
        return group
    except Exception:
        bpy.data.node_groups.remove(group)
        raise


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
    display_vectors = numpy.asarray(displacements, dtype=float) * arrow_scale
    _vector_attribute(obj.data, _DISPLACEMENT_ATTRIBUTE, display_vectors)
    _float_attribute(
        obj.data,
        _MAGNITUDE_ATTRIBUTE,
        numpy.linalg.norm(display_vectors, axis=1),
    )

    group = _ensure_arrow_node_group()
    modifier = obj.modifiers.get(_MODIFIER_NAME)
    if modifier is not None and modifier.type != "NODES":
        raise RuntimeError(f"incompatible modifier already uses {_MODIFIER_NAME}")
    if modifier is None:
        modifier = obj.modifiers.new(_MODIFIER_NAME, "NODES")
    elif (
        modifier.node_group is not None
        and modifier.node_group.get("cbq_contract") != _CONTRACT
    ):
        raise RuntimeError(f"incompatible modifier already uses {_MODIFIER_NAME}")
    modifier.node_group = group
    modifier["cbq_contract"] = _CONTRACT
    obj["cb_vibration_mode_set_id"] = str(mode_set.id)
    obj["cb_vibration_mode_set_revision"] = mode_set.revision
    obj["cb_vibration_mode_index"] = int(mode_index)
    obj["cb_vibration_arrow_scale"] = arrow_scale
    obj["cb_vibration_phase"] = 0.0
    obj["cb_vibration_amplitude_scale"] = 0.0
    obj["cb_vibration_attribute_contract"] = _CONTRACT
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
    reference = _read_vector_attribute(obj.data, _REFERENCE_ATTRIBUTE)
    displayed = _read_vector_attribute(obj.data, _DISPLACEMENT_ATTRIBUTE)
    positions = reference + displayed / arrow_scale * (amplitude_scale * sin(phase))
    if not numpy.all(numpy.isfinite(positions)):
        raise ValueError("vibration phase produced non-finite positions")
    obj.data.vertices.foreach_set("co", positions.reshape(-1))
    obj["cb_vibration_phase"] = phase
    obj["cb_vibration_amplitude_scale"] = amplitude_scale
    obj.data.update()
