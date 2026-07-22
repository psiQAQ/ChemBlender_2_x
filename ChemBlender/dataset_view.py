import operator
from math import isfinite

import bpy

from .core import (
    AtomicProperty,
    DatasetStatus,
    ExcitedStateSet,
    Spectrum,
    SpectrumKind,
    SpectrumProfile,
    Structure,
    VibrationalModeSet,
)


_ANGSTROM_SCALE = {"angstrom": 1.0, "bohr": 0.529177210903}
_GROUP_NAME = "ChemBlender Vector Arrows"
_MODIFIER_NAME = "ChemBlender Vector Arrows"
_VECTOR_CONTRACT = "vector_arrow_v1"
_VECTOR_ATTRIBUTE = "cbq_vector"
_VECTOR_MAGNITUDE_ATTRIBUTE = "cbq_vector_magnitude"
_STRUCTURE_CONTRACT = "structure_view_v1"


def _require_mesh_object(obj):
    if not isinstance(obj, bpy.types.Object) or obj.type != "MESH":
        raise TypeError("obj must be a Blender Mesh object")


def _coordinate_scale(unit):
    try:
        return _ANGSTROM_SCALE[unit]
    except KeyError as error:
        raise ValueError(f"unsupported coordinate unit: {unit}") from error


def _require_structure_match(obj, structure_id, atom_count):
    _require_mesh_object(obj)
    if obj.get("cb_structure_id") != str(structure_id):
        raise ValueError("dataset structure does not match the Blender object")
    if len(obj.data.vertices) != atom_count:
        raise ValueError("dataset atom count does not match the Blender mesh")


def _attribute(mesh, name, data_type):
    value = mesh.attributes.get(name)
    if value is not None and (
        value.data_type != data_type or value.domain != "POINT"
    ):
        mesh.attributes.remove(value)
        value = None
    if value is None:
        value = mesh.attributes.new(name, data_type, "POINT")
    return value


def _write_attribute(mesh, name, data_type, field, values):
    value = _attribute(mesh, name, data_type)
    value.data.foreach_set(field, values)
    return value


def _ensure_vector_arrow_group():
    group = bpy.data.node_groups.get(_GROUP_NAME)
    if group is not None:
        if (
            group.bl_idname != "GeometryNodeTree"
            or group.get("cbq_contract") != _VECTOR_CONTRACT
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
        named.inputs["Name"].default_value = _VECTOR_ATTRIBUTE
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
        group["cbq_contract"] = _VECTOR_CONTRACT
        return group
    except Exception:
        bpy.data.node_groups.remove(group)
        raise


def create_structure_view(structure, *, name="ChemBlender Structure", collection=None):
    import numpy

    if not isinstance(structure, Structure):
        raise TypeError("structure must be a Structure")
    if not isinstance(name, str) or not name:
        raise ValueError("name must be a non-empty string")
    if collection is None:
        collection = bpy.context.collection
    if collection is None:
        raise ValueError("a Blender collection is required")
    scale = _coordinate_scale(structure.coordinates.unit)
    coordinates = numpy.asarray(structure.coordinates.values, dtype=float)
    if numpy.iscomplexobj(coordinates) or not numpy.all(numpy.isfinite(coordinates)):
        raise ValueError("structure coordinates must be finite and real")

    mesh = bpy.data.meshes.new(name)
    obj = None
    try:
        mesh.from_pydata((coordinates * scale).tolist(), [], [])
        obj = bpy.data.objects.new(name, mesh)
        collection.objects.link(obj)
        _write_attribute(
            mesh,
            "atomic_num",
            "INT",
            "value",
            tuple(structure.atomic_numbers),
        )
        _write_attribute(
            mesh,
            "cbq_atom_id",
            "INT",
            "value",
            tuple(range(len(structure.atomic_numbers))),
        )
        obj["cb_structure_id"] = str(structure.id)
        obj["cb_structure_revision"] = structure.revision
        obj["cb_structure_contract"] = _STRUCTURE_CONTRACT
        obj["cb_source_coordinate_unit"] = structure.coordinates.unit
        obj["cb_display_coordinate_unit"] = "angstrom"
        obj["cb_coordinate_scale"] = scale
        mesh.update()
        return obj
    except Exception:
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(mesh)
        raise


def _display_range(values, valid, display_min, display_max, symmetric):
    import numpy

    if (display_min is None) != (display_max is None):
        raise ValueError("display_min and display_max must be provided together")
    if display_min is None:
        lower = float(numpy.min(values[valid]))
        upper = float(numpy.max(values[valid]))
    else:
        lower = float(display_min)
        upper = float(display_max)
        if not isfinite(lower) or not isfinite(upper) or lower >= upper:
            raise ValueError("display range must be finite and increasing")
    if symmetric:
        extent = max(abs(lower), abs(upper))
        if extent == 0.0:
            extent = 1.0
        return -extent, extent
    if lower == upper:
        width = max(abs(lower) * 0.1, 0.5)
        return lower - width, upper + width
    return lower, upper


def _scalar_colors(values, valid, lower, upper, symmetric):
    import numpy

    normalized = numpy.clip((values - lower) / (upper - lower), 0.0, 1.0)
    colors = numpy.empty((values.size, 4), dtype=float)
    if symmetric:
        blue = numpy.asarray((0.23, 0.30, 0.75))
        white = numpy.asarray((0.95, 0.95, 0.95))
        red = numpy.asarray((0.70, 0.02, 0.15))
        low = normalized <= 0.5
        colors[low, :3] = blue + (white - blue) * (normalized[low, None] * 2.0)
        colors[~low, :3] = white + (red - white) * (
            (normalized[~low, None] - 0.5) * 2.0
        )
    else:
        dark = numpy.asarray((0.267, 0.005, 0.329))
        light = numpy.asarray((0.993, 0.906, 0.144))
        colors[:, :3] = dark + (light - dark) * normalized[:, None]
    colors[:, 3] = 1.0
    colors[~valid] = (0.5, 0.5, 0.5, 1.0)
    return colors


def apply_atomic_scalar(
    obj,
    dataset,
    *,
    display_min=None,
    display_max=None,
    symmetric=False,
):
    import numpy

    if not isinstance(dataset, AtomicProperty):
        raise TypeError("dataset must be an AtomicProperty")
    if dataset.data.dims != ("atom",):
        raise ValueError("atomic scalar data must have dims (atom,)")
    if not isinstance(symmetric, bool):
        raise TypeError("symmetric must be a bool")
    _require_structure_match(obj, dataset.structure_id, dataset.data.shape[0])
    values = numpy.asarray(dataset.data.values)
    if numpy.iscomplexobj(values) or numpy.any(numpy.isinf(values)):
        raise ValueError("atomic scalar values must be real and not infinite")
    valid = numpy.isfinite(values)
    if not numpy.any(valid):
        raise ValueError("atomic scalar data must contain at least one value")
    if not numpy.all(valid) and dataset.status is not DatasetStatus.PARTIAL:
        raise ValueError("missing atomic scalar values require partial status")
    stored = numpy.where(valid, values, 0.0).astype(float)
    lower, upper = _display_range(
        stored, valid, display_min, display_max, symmetric
    )
    colors = _scalar_colors(stored, valid, lower, upper, symmetric)
    _write_attribute(obj.data, "cbq_atom_scalar", "FLOAT", "value", stored)
    _write_attribute(
        obj.data,
        "cbq_atom_scalar_valid",
        "BOOLEAN",
        "value",
        valid.tolist(),
    )
    _write_attribute(
        obj.data,
        "colour",
        "FLOAT_COLOR",
        "color",
        colors.reshape(-1),
    )
    obj["cb_scalar_dataset_id"] = str(dataset.id)
    obj["cb_scalar_dataset_revision"] = dataset.revision
    obj["cb_scalar_semantic_role"] = dataset.semantic_role
    obj["cb_scalar_unit"] = dataset.data.unit
    obj["cb_scalar_display_min"] = lower
    obj["cb_scalar_display_max"] = upper
    obj["cb_scalar_symmetric"] = symmetric
    obj["cb_scalar_missing_policy"] = "mask_nan"
    obj.data.update()


def write_vector_view(
    obj,
    values,
    *,
    dataset_id,
    revision,
    semantic_role,
    unit,
    display_scale=1.0,
):
    import numpy

    _require_mesh_object(obj)
    if (
        isinstance(display_scale, bool)
        or not isinstance(display_scale, (int, float))
        or not isfinite(display_scale)
        or display_scale <= 0.0
    ):
        raise ValueError("display_scale must be positive and finite")
    vectors = numpy.asarray(values)
    if (
        vectors.shape != (len(obj.data.vertices), 3)
        or numpy.iscomplexobj(vectors)
        or not numpy.all(numpy.isfinite(vectors))
    ):
        raise ValueError("vector data must contain one finite xyz vector per atom")
    displayed = numpy.asarray(vectors, dtype=float) * float(display_scale)
    _write_attribute(
        obj.data,
        _VECTOR_ATTRIBUTE,
        "FLOAT_VECTOR",
        "vector",
        displayed.reshape(-1),
    )
    _write_attribute(
        obj.data,
        _VECTOR_MAGNITUDE_ATTRIBUTE,
        "FLOAT",
        "value",
        numpy.linalg.norm(displayed, axis=1),
    )
    group = _ensure_vector_arrow_group()
    modifier = obj.modifiers.get(_MODIFIER_NAME)
    if modifier is not None and modifier.type != "NODES":
        raise RuntimeError(f"incompatible modifier already uses {_MODIFIER_NAME}")
    if modifier is None:
        modifier = obj.modifiers.new(_MODIFIER_NAME, "NODES")
    elif (
        modifier.node_group is not None
        and modifier.node_group.get("cbq_contract") != _VECTOR_CONTRACT
    ):
        raise RuntimeError(f"incompatible modifier already uses {_MODIFIER_NAME}")
    modifier.node_group = group
    modifier["cbq_contract"] = _VECTOR_CONTRACT
    obj["cb_vector_dataset_id"] = str(dataset_id)
    obj["cb_vector_dataset_revision"] = revision
    obj["cb_vector_semantic_role"] = semantic_role
    obj["cb_vector_unit"] = unit
    obj["cb_vector_display_scale"] = float(display_scale)
    obj["cb_vector_attribute_contract"] = _VECTOR_CONTRACT
    obj.data.update()
    return modifier


def _read_vector_values(mesh):
    import numpy

    value = mesh.attributes.get(_VECTOR_ATTRIBUTE)
    if (
        value is None
        or value.data_type != "FLOAT_VECTOR"
        or value.domain != "POINT"
    ):
        raise ValueError(f"mesh does not contain {_VECTOR_ATTRIBUTE}")
    values = numpy.empty(len(mesh.vertices) * 3, dtype=float)
    value.data.foreach_get("vector", values)
    return values.reshape((len(mesh.vertices), 3))


def apply_atomic_vector(obj, dataset, *, display_scale=1.0):
    if not isinstance(dataset, AtomicProperty):
        raise TypeError("dataset must be an AtomicProperty")
    if dataset.data.dims != ("atom", "xyz") or dataset.data.shape[1] != 3:
        raise ValueError("atomic vector data must have dims (atom, xyz)")
    _require_structure_match(obj, dataset.structure_id, dataset.data.shape[0])
    return write_vector_view(
        obj,
        dataset.data.values,
        dataset_id=dataset.id,
        revision=dataset.revision,
        semantic_role=dataset.semantic_role,
        unit=dataset.data.unit,
        display_scale=display_scale,
    )


def apply_atom_selection(obj, indices, *, name="selection"):
    _require_mesh_object(obj)
    if not isinstance(name, str) or not name:
        raise ValueError("selection name must be a non-empty string")
    selected = [False] * len(obj.data.vertices)
    for value in indices:
        if isinstance(value, bool):
            raise TypeError("atom selection indices must be integers")
        try:
            index = operator.index(value)
        except TypeError as error:
            raise TypeError("atom selection indices must be integers") from error
        if not 0 <= index < len(selected):
            raise IndexError("atom selection index is outside the mesh")
        selected[index] = True
    _write_attribute(
        obj.data, "cbq_selected", "BOOLEAN", "value", selected
    )
    obj["cb_selection_name"] = name
    obj["cb_selection_domain"] = "atom"
    obj.data.update()


def link_stick_spectrum_selection(obj, spectrum, source_dataset, sample_index):
    _require_mesh_object(obj)
    if not isinstance(spectrum, Spectrum):
        raise TypeError("spectrum must be a Spectrum")
    if spectrum.profile is not SpectrumProfile.STICK:
        raise ValueError("only stick spectrum samples map to one source entity")
    if spectrum.source_dataset_id != getattr(source_dataset, "id", None):
        raise ValueError("spectrum source dataset does not match")
    if spectrum.kind in (SpectrumKind.UV_VIS, SpectrumKind.ECD):
        if not isinstance(source_dataset, ExcitedStateSet):
            raise TypeError("electronic spectrum source must be an ExcitedStateSet")
        domain = "state"
    else:
        if not isinstance(source_dataset, VibrationalModeSet):
            raise TypeError("vibrational spectrum source must be a VibrationalModeSet")
        domain = "mode"
    _require_structure_match(
        obj, source_dataset.structure_id, len(obj.data.vertices)
    )
    if spectrum.data.shape[0] != source_dataset.data.shape[0]:
        raise ValueError("stick spectrum sample count does not match its source")
    if isinstance(sample_index, bool):
        raise TypeError("sample_index must be an integer")
    try:
        sample_index = operator.index(sample_index)
    except TypeError as error:
        raise TypeError("sample_index must be an integer") from error
    if not 0 <= sample_index < spectrum.data.shape[0]:
        raise IndexError("sample_index is outside the stick spectrum")
    obj["cb_selection_spectrum_id"] = str(spectrum.id)
    obj["cb_selection_dataset_id"] = str(source_dataset.id)
    obj["cb_selection_domain"] = domain
    obj["cb_selection_index"] = int(sample_index)
