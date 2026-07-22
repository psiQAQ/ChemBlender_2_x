"""OpenVDB-backed isosurface adapters for Grid3D datasets."""

import hashlib
import os
from pathlib import Path
from uuid import uuid4

import bpy

from .core import Grid3D
from .grid_volume import _ANGSTROM_SCALE, _selected_values, _transform_matrix


_PROPERTY_ATTRIBUTE = "cbq_surface_property"


def _cache_path(cache_root, render_identity, variant):
    root = Path(cache_root).resolve() / "surface"
    root.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(f"{render_identity}:{variant}".encode("utf-8")).hexdigest()
    return root / f"{key}.vdb", key


def _vdb_grid(name, values, grid, scale):
    import openvdb

    result = openvdb.FloatGrid()
    result.name = name
    result.copyFromArray(values)
    result.transform = openvdb.createLinearTransform(_transform_matrix(grid, scale))
    return result


def _write_vdb(path, grids, metadata):
    import openvdb

    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        openvdb.write(str(temporary), list(grids), metadata=metadata)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _material(name, color, opacity):
    material = bpy.data.materials.new(name)
    material.diffuse_color = (*color[:3], opacity)
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = color
    principled.inputs["Alpha"].default_value = opacity
    if opacity < 1.0 and hasattr(material, "surface_render_method"):
        material.surface_render_method = "DITHERED"
    return material


def _property_material(name, color_min, color_max):
    material = _material(name, (0.8, 0.8, 0.8, 1.0), 1.0)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    principled = nodes.get("Principled BSDF")
    attribute = nodes.new("ShaderNodeAttribute")
    attribute.attribute_name = _PROPERTY_ATTRIBUTE
    mapping = nodes.new("ShaderNodeMapRange")
    mapping.inputs["From Min"].default_value = float(color_min)
    mapping.inputs["From Max"].default_value = float(color_max)
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.23, 0.30, 0.75, 1.0)
    ramp.color_ramp.elements[1].color = (0.70, 0.02, 0.15, 1.0)
    middle = ramp.color_ramp.elements.new(0.5)
    middle.color = (0.95, 0.95, 0.95, 1.0)
    links.new(attribute.outputs["Fac"], mapping.inputs["Value"])
    links.new(mapping.outputs["Result"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], principled.inputs["Base Color"])
    material["cbq_contract"] = "property_colormap_v1"
    material["cb_property_attribute"] = _PROPERTY_ATTRIBUTE
    material["cb_color_min"] = float(color_min)
    material["cb_color_max"] = float(color_max)
    material["cb_colormap"] = "coolwarm"
    return material


def _surface_group(name, threshold, material, *, property_grid=False):
    group = bpy.data.node_groups.new(name, "GeometryNodeTree")
    try:
        group.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
        nodes = group.nodes
        links = group.links
        group_input = nodes.new("NodeGroupInput")
        group_output = nodes.new("NodeGroupOutput")
        volume_to_mesh = nodes.new("GeometryNodeVolumeToMesh")
        volume_to_mesh.inputs["Threshold"].default_value = float(threshold)
        links.new(group_input.outputs["Geometry"], volume_to_mesh.inputs["Volume"])
        geometry = volume_to_mesh.outputs["Mesh"]
        if property_grid:
            named_grid = nodes.new("GeometryNodeGetNamedGrid")
            named_grid.data_type = "FLOAT"
            named_grid.inputs["Name"].default_value = "property"
            sample = nodes.new("GeometryNodeSampleGrid")
            sample.data_type = "FLOAT"
            position = nodes.new("GeometryNodeInputPosition")
            store = nodes.new("GeometryNodeStoreNamedAttribute")
            store.data_type = "FLOAT"
            store.domain = "POINT"
            store.inputs["Name"].default_value = _PROPERTY_ATTRIBUTE
            links.new(group_input.outputs["Geometry"], named_grid.inputs["Volume"])
            links.new(named_grid.outputs["Grid"], sample.inputs["Grid"])
            links.new(position.outputs["Position"], sample.inputs["Position"])
            links.new(geometry, store.inputs["Geometry"])
            links.new(sample.outputs["Value"], store.inputs["Value"])
            geometry = store.outputs["Geometry"]
        set_material = nodes.new("GeometryNodeSetMaterial")
        set_material.inputs["Material"].default_value = material
        links.new(geometry, set_material.inputs["Geometry"])
        links.new(set_material.outputs["Geometry"], group_output.inputs["Geometry"])
        group["cbq_contract"] = (
            "property_surface_v1" if property_grid else "isosurface_v1"
        )
        return group
    except Exception:
        bpy.data.node_groups.remove(group)
        raise


def _volume_surface(
    path,
    name,
    threshold,
    color,
    opacity,
    collection,
    property_grid,
    property_range=None,
):
    volume = bpy.data.volumes.new(name)
    obj = material = group = None
    try:
        volume.filepath = str(path)
        volume.grids.load()
        if volume.grids["density"] is None:
            raise RuntimeError("surface VDB does not contain density")
        obj = bpy.data.objects.new(name, volume)
        collection.objects.link(obj)
        material = (
            _property_material(f"{name} Material", *property_range)
            if property_range is not None
            else _material(f"{name} Material", color, opacity)
        )
        group = _surface_group(
            f"{name} Geometry", threshold, material, property_grid=property_grid
        )
        modifier = obj.modifiers.new("ChemBlender Surface", "NODES")
        modifier.node_group = group
        modifier["cbq_contract"] = group["cbq_contract"]
        return obj
    except Exception:
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)
        if group is not None:
            bpy.data.node_groups.remove(group)
        if material is not None:
            bpy.data.materials.remove(material)
        bpy.data.volumes.remove(volume)
        raise


def remove_surface_object(obj):
    groups = [modifier.node_group for modifier in obj.modifiers if modifier.node_group]
    materials = [
        node.inputs["Material"].default_value
        for group in groups
        for node in group.nodes
        if node.bl_idname == "GeometryNodeSetMaterial"
        and node.inputs["Material"].default_value is not None
    ]
    volume = obj.data
    bpy.data.objects.remove(obj, do_unlink=True)
    if volume.users == 0:
        bpy.data.volumes.remove(volume)
    for group in groups:
        if group.users == 0:
            bpy.data.node_groups.remove(group)
    for material in materials:
        if material.users == 0:
            bpy.data.materials.remove(material)


def _metadata(obj, grid, dataset_index, path, cache_key, render_identity):
    obj["cb_dataset_id"] = str(grid.id)
    obj["cb_dataset_revision"] = grid.revision
    obj["cb_dataset_index"] = int(dataset_index)
    obj["cb_structure_id"] = str(grid.structure_id) if grid.structure_id else ""
    obj["cb_semantic_role"] = grid.semantic_role
    obj["cb_value_unit"] = grid.data.unit
    obj["cb_source_coordinate_unit"] = grid.coordinate_unit
    obj["cb_display_coordinate_unit"] = "angstrom"
    obj["cb_cache_path"] = str(path)
    obj["cb_render_cache_key"] = cache_key
    obj["cb_scene_render_identity"] = render_identity


def create_signed_isosurfaces(
    grid,
    cache_root,
    *,
    isovalue,
    positive_color,
    negative_color,
    opacity,
    dataset_index,
    render_identity,
    collection=None,
):
    import numpy

    if not isinstance(grid, Grid3D):
        raise TypeError("grid must be a Grid3D")
    target = collection or bpy.context.collection
    if target is None:
        raise ValueError("a Blender collection is required")
    scale = _ANGSTROM_SCALE[grid.coordinate_unit]
    values = _selected_values(grid, dataset_index)
    if not numpy.all(numpy.isfinite(values)):
        raise ValueError("surface grid values must be finite")
    created = []
    try:
        for phase, factor, color in (
            ("positive", 1.0, positive_color),
            ("negative", -1.0, negative_color),
        ):
            path, key = _cache_path(cache_root, render_identity, phase)
            density = _vdb_grid("density", numpy.asarray(values * factor), grid, scale)
            _write_vdb(path, (density,), {"chemblender_render_cache_key": key})
            obj = _volume_surface(
                path,
                f"ChemBlender {phase.title()} Surface",
                isovalue,
                color,
                opacity,
                target,
                False,
            )
            created.append(obj)
            _metadata(obj, grid, dataset_index, path, key, render_identity)
            obj["cb_surface_phase"] = phase
            obj["cb_surface_isovalue"] = float(isovalue if factor > 0 else -isovalue)
            obj["cb_surface_color"] = tuple(color)
            obj["cb_surface_opacity"] = float(opacity)
        return tuple(created)
    except Exception:
        for obj in reversed(created):
            remove_surface_object(obj)
        raise


def create_property_surface(
    surface_grid,
    property_grid,
    cache_root,
    *,
    isovalue,
    color_min,
    color_max,
    colormap,
    surface_dataset_index,
    property_dataset_index,
    render_identity,
    collection=None,
):
    if not isinstance(surface_grid, Grid3D) or not isinstance(property_grid, Grid3D):
        raise TypeError("surface_grid and property_grid must be Grid3D")
    if (
        surface_grid.grid_shape != property_grid.grid_shape
        or surface_grid.origin != property_grid.origin
        or surface_grid.step_vectors != property_grid.step_vectors
        or surface_grid.coordinate_unit != property_grid.coordinate_unit
        or surface_grid.structure_id != property_grid.structure_id
    ):
        raise ValueError("surface and property grids must share one affine grid")
    target = collection or bpy.context.collection
    if target is None:
        raise ValueError("a Blender collection is required")
    scale = _ANGSTROM_SCALE[surface_grid.coordinate_unit]
    path, key = _cache_path(cache_root, render_identity, "property")
    import numpy

    density_values = _selected_values(surface_grid, surface_dataset_index)
    property_values = _selected_values(property_grid, property_dataset_index)
    if not numpy.all(numpy.isfinite(density_values)) or not numpy.all(
        numpy.isfinite(property_values)
    ):
        raise ValueError("surface and property grid values must be finite")
    density = _vdb_grid("density", density_values, surface_grid, scale)
    prop = _vdb_grid("property", property_values, property_grid, scale)
    _write_vdb(path, (density, prop), {"chemblender_render_cache_key": key})
    obj = _volume_surface(
        path,
        "ChemBlender Property Surface",
        isovalue,
        (0.8, 0.8, 0.8, 1.0),
        1.0,
        target,
        True,
        (color_min, color_max),
    )
    _metadata(
        obj, surface_grid, surface_dataset_index, path, key, render_identity
    )
    obj["cb_property_dataset_id"] = str(property_grid.id)
    obj["cb_property_dataset_revision"] = property_grid.revision
    obj["cb_property_dataset_index"] = int(property_dataset_index)
    obj["cb_property_semantic_role"] = property_grid.semantic_role
    obj["cb_property_unit"] = property_grid.data.unit
    obj["cb_surface_isovalue"] = float(isovalue)
    obj["cb_property_attribute"] = _PROPERTY_ATTRIBUTE
    obj["cb_property_color_min"] = float(color_min)
    obj["cb_property_color_max"] = float(color_max)
    obj["cb_property_colormap"] = colormap
    return obj
