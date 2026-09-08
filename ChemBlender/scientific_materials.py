"""Owned native shaders for quantitative surfaces, plots and signed volume clouds."""

from contextlib import contextmanager
from math import isfinite

import bpy

from .core.color_mapping import color_stops


def _color(value):
    value = tuple(value)
    if len(value) != 4 or any(not isfinite(x) or not 0 <= x <= 1 for x in value):
        raise ValueError("color must contain four finite values between zero and one")
    return value


def _scale(value, name, *, positive=False, maximum=None):
    if (isinstance(value, bool) or not isfinite(value)
            or value < 0 or (positive and value == 0)
            or (maximum is not None and value > maximum)):
        raise ValueError(f"{name} is outside its supported range")
    return float(value)


@contextmanager
def _nodes(name):
    material = bpy.data.materials.new(name)
    try:
        material.use_nodes = True
        material["cb_scientific_owned"] = True
        material["cb_scientific_material_contract"] = "scientific_material_v1"
        material.node_tree.nodes.clear()
        yield material, material.node_tree.nodes, material.node_tree.links
    except BaseException:
        if material.users == 0:
            bpy.data.materials.remove(material)
        raise


def _surface(nodes, links, *, shaded, opacity):
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled" if shaded else "ShaderNodeEmission")
    if shaded:
        shader.inputs["Roughness"].default_value = .65
        shader.inputs["Specular IOR Level"].default_value = .15
    socket = shader.outputs[0]
    if opacity < 1.:
        transparent = nodes.new("ShaderNodeBsdfTransparent")
        mix = nodes.new("ShaderNodeMixShader")
        mix.inputs[0].default_value = opacity
        links.new(transparent.outputs[0], mix.inputs[1])
        links.new(socket, mix.inputs[2])
        socket = mix.outputs[0]
    links.new(socket, output.inputs["Surface"])
    return shader.inputs["Base Color" if shaded else "Color"]


def flat_material(name, color, *, opacity=1.):
    """Create an emission material; scene color management remains explicit."""
    color, opacity = _color(color), _scale(opacity, "opacity", maximum=1.)
    with _nodes(name) as (material, nodes, links):
        material.diffuse_color = (*color[:3], opacity)
        _surface(nodes, links, shaded=False, opacity=opacity).default_value = color
        material["cb_quantitative_color"] = True
        return material


def matte_material(name, color, *, opacity=1.):
    color, opacity = _color(color), _scale(opacity, "opacity", maximum=1.)
    with _nodes(name) as (material, nodes, links):
        material.diffuse_color = (*color[:3], opacity)
        _surface(nodes, links, shaded=True, opacity=opacity).default_value = color
        material["cb_quantitative_color"] = False
        return material


def scalar_material(name, color_min, color_max, *,
                    attribute_name="cbq_surface_property", colormap="coolwarm",
                    shaded=False, opacity=1.):
    """Map an unchanged named scalar attribute to the same stops as its legend."""
    stops = color_stops(color_min, color_max, colormap)
    opacity = _scale(opacity, "opacity", maximum=1.)
    if not isinstance(attribute_name, str) or not attribute_name:
        raise ValueError("attribute_name must be non-empty")
    with _nodes(name) as (material, nodes, links):
        color_input = _surface(nodes, links, shaded=shaded, opacity=opacity)
        attribute = nodes.new("ShaderNodeAttribute")
        attribute.attribute_name = attribute_name
        mapping = nodes.new("ShaderNodeMapRange")
        mapping.inputs["From Min"].default_value = color_min
        mapping.inputs["From Max"].default_value = color_max
        mapping.clamp = True
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.interpolation = "LINEAR"
        ramp.color_ramp.elements[0].color = stops[0][1]
        ramp.color_ramp.elements[1].color = stops[-1][1]
        for position, color in stops[1:-1]:
            ramp.color_ramp.elements.new(position).color = color
        links.new(attribute.outputs["Fac"], mapping.inputs["Value"])
        links.new(mapping.outputs["Result"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], color_input)
        material["cb_property_attribute"] = attribute_name
        material["cb_color_min"], material["cb_color_max"] = color_min, color_max
        material["cb_colormap"] = colormap
        material["cb_quantitative_color"] = not shaded and opacity == 1.
        return material


def volume_material(name, *, density_scale=10., signed=False,
                    positive_color=(.04, .45, .80, 1.),
                    negative_color=(1., .30, .04, 1.), anisotropy=0.):
    """Use max(f,0) and max(-f,0) as separate nonnegative extinction channels.

    The VDB retains signed scientific f. Extinction scale is an optical display
    transfer function, not a change of units or a newly derived electron density.
    """
    density_scale = _scale(density_scale, "density_scale", positive=True)
    positive_color, negative_color = _color(positive_color), _color(negative_color)
    if not isfinite(anisotropy) or not -.9 <= anisotropy <= .9:
        raise ValueError("anisotropy must be between -.9 and .9")
    if type(signed) is not bool:
        raise TypeError("signed must be boolean")
    with _nodes(name) as (material, nodes, links):
        source = nodes.new("ShaderNodeAttribute")
        source.attribute_name = "density"
        shaders = []
        for sign, color in ((1., positive_color), (-1., negative_color))[:2 if signed else 1]:
            scale = nodes.new("ShaderNodeMath")
            scale.operation = "MULTIPLY"
            scale.inputs[1].default_value = sign * density_scale
            links.new(source.outputs["Fac"], scale.inputs[0])
            nonnegative = nodes.new("ShaderNodeMath")
            nonnegative.operation = "MAXIMUM"
            nonnegative.inputs[1].default_value = 0.
            links.new(scale.outputs[0], nonnegative.inputs[0])
            volume = nodes.new("ShaderNodeVolumePrincipled")
            volume.inputs["Color"].default_value = color
            volume.inputs["Anisotropy"].default_value = anisotropy
            volume.inputs["Density Attribute"].default_value = ""
            links.new(nonnegative.outputs[0], volume.inputs["Density"])
            shaders.append(volume.outputs[0])
        output = nodes.new("ShaderNodeOutputMaterial")
        if signed:
            add = nodes.new("ShaderNodeAddShader")
            links.new(shaders[0], add.inputs[0])
            links.new(shaders[1], add.inputs[1])
            links.new(add.outputs[0], output.inputs["Volume"])
        else:
            links.new(shaders[0], output.inputs["Volume"])
        material["cb_density_scale"] = density_scale
        material["cb_signed_extinction"] = signed
        material["cb_display_mapping"] = "positive_negative_parts" if signed else "positive_part"
        return material


def _atom_attribute_material(*, quantitative, shaded, opacity):
    with _nodes("ChemBlender Atom Colors") as (material, nodes, links):
        attribute = nodes.new("ShaderNodeAttribute")
        attribute.attribute_name = "cbq_scientific_atom_color"
        color = _surface(nodes, links, shaded=shaded and not quantitative, opacity=opacity)
        links.new(attribute.outputs["Color"], color)
        material["cb_property_attribute"] = "cbq_scientific_atom_color"
        material["cb_color_source_attribute"] = "colour"
        material["cb_quantitative_color"] = quantitative and opacity == 1.
        material["cb_structure_material_role"] = "atom_colors"
        return material


def _bind_atom_group(group, material):
    """Bind the copied atom wrapper without changing its display geometry."""
    nodes, links = group.nodes, group.links
    existing = nodes.get("ChemBlender Scientific Atom Material")
    if existing is not None:
        if existing.bl_idname != "GeometryNodeSetMaterial":
            raise ValueError("incompatible scientific atom material node")
        existing.inputs["Material"].default_value = material
        return
    if group.get("cbq_contract") == "biological_points_v1":
        outputs = [node for node in nodes if node.bl_idname == "NodeGroupOutput"
                   and node.is_active_output]
        if len(outputs) != 1 or len(outputs[0].inputs["Geometry"].links) != 1:
            raise ValueError("canonical biological point output is unavailable")
        target = outputs[0].inputs["Geometry"]
        source = target.links[0].from_socket
        assign = nodes.new("GeometryNodeSetMaterial")
        assign.name = "ChemBlender Scientific Atom Material"
        assign.inputs["Material"].default_value = material
        links.new(source, assign.inputs["Geometry"])
        links.new(assign.outputs["Geometry"], target)
        return
    stages = [node for node in nodes if node.bl_idname == "GeometryNodeGroup"
              and node.node_tree is not None
              and node.node_tree.get("cbq_contract") == "legacy_molecule_material_asset_v1"]
    if len(stages) != 1 or len(stages[0].inputs[0].links) != 1:
        raise ValueError("canonical atom material stage is unavailable")
    stage = stages[0]
    source = stage.inputs[0].links[0].from_socket
    targets = tuple(link.to_socket for link in stage.outputs[0].links)
    realized = nodes.new("GeometryNodeRealizeInstances")
    realized.name = "ChemBlender Scientific Atom Geometry"
    assign = nodes.new("GeometryNodeSetMaterial")
    assign.name = "ChemBlender Scientific Atom Material"
    assign.inputs["Material"].default_value = material
    links.new(source, realized.inputs["Geometry"])
    links.new(realized.outputs["Geometry"], assign.inputs["Geometry"])
    for target in targets:
        links.new(assign.outputs["Geometry"], target)
    nodes.remove(stage)


def _bind_vector_group(group, material):
    nodes, links = group.nodes, group.links
    assign = nodes.get("ChemBlender Scientific Vector Material")
    if assign is not None:
        if assign.bl_idname != "GeometryNodeSetMaterial":
            raise ValueError("incompatible scientific vector material node")
        assign.inputs["Material"].default_value = material
        return
    cones = [node for node in nodes if node.bl_idname == "GeometryNodeMeshCone"]
    if len(cones) != 1:
        raise ValueError("canonical vector arrow primitive is unavailable")
    source = cones[0].outputs["Mesh"]
    targets = tuple(link.to_socket for link in source.links)
    assign = nodes.new("GeometryNodeSetMaterial")
    assign.name = "ChemBlender Scientific Vector Material"
    assign.inputs["Material"].default_value = material
    links.new(source, assign.inputs["Geometry"])
    for target in targets:
        links.new(assign.outputs["Geometry"], target)


def _remove_unused(blocks):
    for block in blocks:
        try:
            if block.users == 0:
                bpy.data.batch_remove(ids=(block,))
        except ReferenceError:
            pass


def apply_structure_materials(
    root, *, quantitative=False, shaded=True, opacity=1.,
    vector_color=(1., .72, .04, 1.),
):
    """Bind independent atom/vector shaders without editing shared legacy assets.

    Call after atomic scalar/vector attributes are configured. The existing
    colour attribute includes the selected scalar transfer and missing mask.
    Quantitative colors always use emission; transparency still blends colors.
    """
    if not isinstance(root, bpy.types.Object) or root.type != "MESH" or root.get("cb_structure_contract") != "structure_view_v1":
        raise ValueError("root must be a canonical structure Mesh view")
    if type(quantitative) is not bool or type(shaded) is not bool:
        raise TypeError("quantitative and shaded must be bool")
    opacity = _scale(opacity, "opacity", maximum=1.)
    vector_color = _color(vector_color)
    colour = root.data.attributes.get("colour")
    if colour is None or colour.data_type != "FLOAT_COLOR" or colour.domain != "POINT":
        raise ValueError("canonical atom colour attribute is unavailable")
    if quantitative:
        for name, kind in (("cbq_atom_scalar", "FLOAT"), ("cbq_atom_scalar_valid", "BOOLEAN")):
            attribute = root.data.attributes.get(name)
            if attribute is None or attribute.data_type != kind or attribute.domain != "POINT":
                raise ValueError("quantitative atom colors require scalar values and validity mask")
    modifiers = [(modifier, modifier.node_group) for modifier in root.modifiers
                 if modifier.type == "NODES" and modifier.node_group is not None
                 and modifier.node_group.get("cbq_contract") in ("structure_ball_stick_v1", "biological_points_v1", "vector_arrow_v1")]
    if sum(group.get("cbq_contract") != "vector_arrow_v1" for _, group in modifiers) != 1:
        raise ValueError("one canonical atom display modifier is required")
    old_mesh = root.data
    old_materials = tuple(material for material in old_mesh.materials
                          if material is not None and material.get("cb_scientific_owned"))
    groups, materials = [], []
    mesh = None
    try:
        atoms = _atom_attribute_material(quantitative=quantitative, shaded=shaded, opacity=opacity)
        materials.append(atoms)
        vectors = None
        if any(group.get("cbq_contract") == "vector_arrow_v1" for _, group in modifiers):
            vectors = flat_material("ChemBlender Vector Color", vector_color, opacity=opacity)
            vectors["cb_structure_material_role"] = "vector_arrows"
            materials.append(vectors)
        for modifier, original in modifiers:
            group = original.copy()
            group.name = root.name + " Scientific " + original.name
            group["cb_scientific_owned"] = True
            groups.append((modifier, original, group))
            if original.get("cbq_contract") != "vector_arrow_v1":
                _bind_atom_group(group, atoms)
            else:
                _bind_vector_group(group, vectors)
        mesh = old_mesh.copy()
        mesh["cb_scientific_owned"] = True
        # Legacy molecule assets overwrite colour. Preserve the selected
        # View transfer under an attribute the shared assets do not modify.
        import numpy

        values = numpy.empty(len(mesh.vertices) * 4, dtype=float)
        mesh.attributes["colour"].data.foreach_get("color", values)
        stored = mesh.attributes.get("cbq_scientific_atom_color")
        if stored is not None:
            mesh.attributes.remove(stored)
        stored = mesh.attributes.new("cbq_scientific_atom_color", "FLOAT_COLOR", "POINT")
        stored.data.foreach_set("color", values)
        mesh.materials.clear()
        for material in materials:
            mesh.materials.append(material)
        # No live datablock changes until every independent branch is ready.
        root.data = mesh
        for modifier, original, group in groups:
            modifier.node_group = group
    except BaseException:
        root.data = old_mesh
        for modifier, original, group in groups:
            modifier.node_group = original
        _remove_unused(([mesh] if mesh is not None else []) + [group for _, _, group in groups] + materials)
        raise
    _remove_unused([old_mesh] + [original for _, original, _ in groups] + list(old_materials))
