import colorsys
import json
import operator

import bpy

from cbq_core.model import FermiSurfaceMesh
from .spectrum_plot import _flat_material, _positive, _remove_objects


def _attribute(mesh, name, data_type, domain):
    attribute = mesh.attributes.get(name)
    if attribute is not None and (
        attribute.data_type != data_type or attribute.domain != domain
    ):
        mesh.attributes.remove(attribute)
        attribute = None
    if attribute is None:
        attribute = mesh.attributes.new(name, data_type, domain)
    return attribute


def _write_property(mesh, prop):
    import numpy

    values = numpy.asarray(prop.data.values)
    if (numpy.iscomplexobj(values) or not numpy.all(numpy.isfinite(values))
            or (values.ndim != 1 and (values.ndim != 2 or values.shape[1] != 3))):
        raise ValueError("surface properties must contain finite real scalars or xyz vectors")
    domain = "POINT" if prop.domain == "vertex" else "FACE"
    name = f"cbq_{prop.semantic_role}"
    if values.ndim == 1:
        attribute = _attribute(mesh, name, "FLOAT", domain)
        attribute.data.foreach_set("value", values)
    else:
        attribute = _attribute(mesh, name, "FLOAT_VECTOR", domain)
        attribute.data.foreach_set("vector", values.reshape(-1))


def surface_property_values(dataset, name, *, component="magnitude", vector=False):
    """Select an explicitly supplied property; never infer velocity from mesh geometry."""
    import numpy

    matches = [prop for prop in dataset.properties if prop.semantic_role == name]
    if len(matches) != 1:
        raise ValueError("surface property is unavailable")
    prop = matches[0]
    values = numpy.asarray(prop.data.values)
    if numpy.iscomplexobj(values) or not numpy.all(numpy.isfinite(values)):
        raise ValueError("surface property must contain finite real values")
    if values.ndim == 1 and not vector:
        if component != "magnitude":
            raise ValueError("scalar surface property has no vector component")
        return prop, values
    if values.ndim != 2 or values.shape[1] != 3:
        raise ValueError("vector surface property must contain xyz vectors")
    if vector:
        return prop, values
    if component == "magnitude":
        return prop, numpy.linalg.norm(values, axis=1)
    if component not in {"x", "y", "z"}:
        raise ValueError("vector_component must be magnitude, x, y or z")
    return prop, values[:, {"x": 0, "y": 1, "z": 2}[component]]


def _range(values, lower, upper):
    import numpy

    if (lower is None) != (upper is None):
        raise ValueError("color_min and color_max must be provided together")
    if lower is None:
        lower, upper = float(numpy.min(values)), float(numpy.max(values))
        if lower == upper:
            margin = max(abs(lower) * .1, .5)
            lower, upper = lower - margin, upper + margin
    if isinstance(lower, bool) or isinstance(upper, bool) or not numpy.isfinite([lower, upper]).all() or lower >= upper:
        raise ValueError("color range must be finite and increasing")
    return float(lower), float(upper)


def _vector_arrows(root, dataset, prop, values, collection, scale, stride, radius, material):
    import numpy
    from .dataset_view import _ensure_vector_arrow_group

    positions = numpy.asarray(dataset.data.values)
    if prop.domain == "face":
        positions = positions[numpy.asarray(dataset.faces.values)].mean(axis=1)
    indices = numpy.arange(len(positions))[::stride]
    nonzero = numpy.linalg.norm(values[indices], axis=1) > 0.
    indices = indices[nonzero]
    mesh = bpy.data.meshes.new(root.name + " Vector Samples")
    mesh["cb_scientific_owned"] = True
    obj, group = None, None
    try:
        mesh.from_pydata(positions[indices].tolist(), [], [])
        _attribute(mesh, "cbq_vector", "FLOAT_VECTOR", "POINT").data.foreach_set("vector", (values[indices] * scale).ravel())
        _attribute(mesh, "cbq_source_sample_index", "INT", "POINT").data.foreach_set("value", indices)
        obj = bpy.data.objects.new(root.name + " Vectors", mesh)
        collection.objects.link(obj)
        obj.parent = root
        obj["cb_scientific_component"] = "fermi_vectors"
        obj["cb_vector_property"] = prop.semantic_role
        obj["cb_vector_unit"] = prop.data.unit
        obj["cb_vector_scale"] = scale
        obj["cb_vector_stride"] = stride
        # Copy the existing arrow recipe so per-view radius/material never mutates other views.
        existing_groups = {item.as_pointer() for item in bpy.data.node_groups}
        template = _ensure_vector_arrow_group()
        group = template.copy()
        if template.as_pointer() not in existing_groups and template.users == 0:
            bpy.data.node_groups.remove(template)
        group["cb_scientific_owned"] = True
        for node in group.nodes:
            if node.bl_idname == "ShaderNodeCombineXYZ":
                node.inputs["X"].default_value = radius
                node.inputs["Y"].default_value = radius
        cone = next(node for node in group.nodes if node.bl_idname == "GeometryNodeMeshCone")
        old_links = tuple(cone.outputs["Mesh"].links)
        assign = group.nodes.new("GeometryNodeSetMaterial")
        assign.inputs["Material"].default_value = material
        group.links.new(cone.outputs["Mesh"], assign.inputs["Geometry"])
        for link in old_links:
            group.links.new(assign.outputs["Geometry"], link.to_socket)
        output = next(node for node in group.nodes if node.bl_idname == "NodeGroupOutput")
        source = output.inputs["Geometry"].links[0].from_socket
        realize = group.nodes.new("GeometryNodeRealizeInstances")
        group.links.new(source, realize.inputs["Geometry"])
        group.links.new(realize.outputs["Geometry"], output.inputs["Geometry"])
        modifier = obj.modifiers.new("ChemBlender Fermi Vectors", "NODES")
        modifier.node_group = group
        mesh.materials.append(material)
        return obj
    except Exception:
        if obj is not None:
            _remove_objects((obj,), groups=(() if group is None else (group,)))
        else:
            bpy.data.meshes.remove(mesh)
        raise


def create_fermi_surface_view(
    dataset,
    *,
    name="ChemBlender Fermi Surface",
    collection=None,
    material=None,
    color_property=None,
    vector_component="magnitude",
    color_min=None,
    color_max=None,
    vector_property=None,
    vector_scale=1.0,
    vector_stride=1,
    arrow_radius=0.025,
    arrow_material=None,
):
    import numpy

    if not isinstance(dataset, FermiSurfaceMesh):
        raise TypeError("dataset must be a FermiSurfaceMesh")
    vector_scale = _positive(vector_scale, "vector_scale")
    arrow_radius = _positive(arrow_radius, "arrow_radius")
    if isinstance(vector_stride, bool):
        raise TypeError("vector_stride must be a positive integer")
    vector_stride = operator.index(vector_stride)
    if vector_stride < 1:
        raise ValueError("vector_stride must be a positive integer")
    color_values = vector_values = color_prop = vector_prop = None
    if color_property is not None:
        color_prop, color_values = surface_property_values(dataset, color_property, component=vector_component)
        color_min, color_max = _range(color_values, color_min, color_max)
    elif color_min is not None or color_max is not None:
        raise ValueError("color bounds require color_property")
    if vector_property is not None:
        vector_prop, vector_values = surface_property_values(dataset, vector_property, vector=True)
    target = collection or bpy.context.collection
    mesh = bpy.data.meshes.new(name)
    mesh["cb_scientific_owned"] = True
    obj = bpy.data.objects.new(name, mesh)
    made, materials = [obj], []
    try:
        mesh.from_pydata(
            numpy.asarray(dataset.data.values, dtype=float).tolist(),
            [],
            numpy.asarray(dataset.faces.values, dtype=int).tolist(),
        )
        mesh.update()
        band_attribute = _attribute(mesh, "cbq_band_index", "INT", "FACE")
        band_attribute.data.foreach_set("value", dataset.band_indices.values)
        for prop in dataset.properties:
            _write_property(mesh, prop)
        target.objects.link(obj)
        if color_prop is not None:
            domain = "POINT" if color_prop.domain == "vertex" else "FACE"
            _attribute(mesh, "cbq_color_value", "FLOAT", domain).data.foreach_set("value", color_values)
            if material is None:
                from .scientific_materials import scalar_material

                material = scalar_material("ChemBlender Fermi Property", color_min, color_max,
                                           attribute_name="cbq_color_value")
                material["cb_scientific_owned"] = True
                materials.append(material)
            obj["cb_color_property"] = color_property
            obj["cb_color_component"] = vector_component
            obj["cb_color_unit"] = color_prop.data.unit
            obj["cb_color_min"], obj["cb_color_max"] = color_min, color_max
        elif material is None:
            # Colors follow original 0-based band identities, even when only a
            # subset crosses E_F. They do not encode a quantitative scalar.
            bands = sorted(set(int(value) for value in dataset.band_indices.values))
            legend = []
            slots = {}
            for slot, band in enumerate(bands):
                color = (*colorsys.hsv_to_rgb((.58 + band * .61803398875) % 1., .72, .7), 1.)
                band_material = _flat_material(f"ChemBlender Band {band + 1}", color)
                materials.append(band_material)
                mesh.materials.append(band_material)
                slots[band] = slot
                legend.append({"band_index": band, "band_number": band + 1, "color": color})
            for face, band in zip(mesh.polygons, dataset.band_indices.values):
                face.material_index = slots[int(band)]
            obj["cb_color_property"] = "band_index"
            obj["cb_color_mapping"] = "categorical_band_index"
            obj["cb_band_legend"] = json.dumps(legend, separators=(",", ":"))
            obj["cb_band_index_base"] = 0
        if material is not None:
            mesh.materials.append(material)
        if vector_prop is not None:
            if arrow_material is None:
                arrow_material = _flat_material("ChemBlender Fermi Arrows", (.05, .05, .05, 1.))
                materials.append(arrow_material)
            made.append(_vector_arrows(obj, dataset, vector_prop, vector_values, target,
                                       vector_scale, vector_stride, arrow_radius, arrow_material))
    except Exception:
        _remove_objects(made, materials=materials)
        raise
    obj["cb_dataset_id"] = str(dataset.id)
    obj["cb_dataset_revision"] = dataset.revision
    obj["cb_structure_id"] = str(dataset.structure_id)
    obj["cb_band_structure_id"] = str(dataset.band_structure_id)
    obj["cb_spin_index"] = dataset.spin_index
    obj["cb_fermi_energy"] = dataset.fermi_energy
    obj["cb_coordinate_convention"] = dataset.coordinate_convention
    obj["cb_property_units"] = [
        f"{prop.semantic_role}={prop.data.unit}" for prop in dataset.properties
    ]
    obj["cb_surface_contract"] = "fermi_surface_mesh_v1"
    return obj


def select_fermi_face(obj, dataset, face_index):
    if not isinstance(dataset, FermiSurfaceMesh):
        raise TypeError("dataset must be a FermiSurfaceMesh")
    if getattr(obj, "type", None) != "MESH":
        raise TypeError("obj must be a Blender Mesh object")
    if (
        obj.get("cb_surface_contract") != "fermi_surface_mesh_v1"
        or obj.get("cb_dataset_id") != str(dataset.id)
    ):
        raise ValueError("Fermi-surface object does not match dataset")
    if isinstance(face_index, bool):
        raise TypeError("face_index must be an integer")
    try:
        face_index = operator.index(face_index)
    except TypeError as error:
        raise TypeError("face_index must be an integer") from error
    if not 0 <= face_index < dataset.faces.shape[0]:
        raise IndexError("face_index is outside the Fermi surface")
    obj["cb_selected_face"] = int(face_index)
    obj["cb_selected_band"] = int(dataset.band_indices.values[face_index])
