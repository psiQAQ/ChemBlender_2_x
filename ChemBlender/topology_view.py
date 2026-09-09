import bpy

from cbq_core.model import CriticalPointKind
from cbq_core.model import TopologyGraph
from cbq_core.grid_cache_service import _ANGSTROM_SCALE
from .fermi_surface_view import _range
from .spectrum_plot import _flat_material, _positive, _remove_objects


_KIND_CODE = {
    CriticalPointKind.NUCLEAR: 0,
    CriticalPointKind.ATTRACTOR: 1,
    CriticalPointKind.BOND: 2,
    CriticalPointKind.RING: 3,
    CriticalPointKind.CAGE: 4,
}
_KIND_COLORS = ((.22, .22, .22, 1.), (.55, .2, .65, 1.),
                (.02, .5, .4, 1.), (.95, .65, .05, 1.), (.85, .12, .12, 1.))


def _point_glyphs(obj, radius, material):
    group = bpy.data.node_groups.new(obj.name + " Spheres", "GeometryNodeTree")
    group["cb_scientific_owned"] = True
    try:
        group.is_modifier = True
        group.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
        source = group.nodes.new("NodeGroupInput")
        output = group.nodes.new("NodeGroupOutput")
        sphere = group.nodes.new("GeometryNodeMeshIcoSphere")
        sphere.inputs["Radius"].default_value = radius
        sphere.inputs["Subdivisions"].default_value = 2
        instance = group.nodes.new("GeometryNodeInstanceOnPoints")
        realize = group.nodes.new("GeometryNodeRealizeInstances")
        assign = group.nodes.new("GeometryNodeSetMaterial")
        assign.inputs["Material"].default_value = material
        group.links.new(source.outputs["Geometry"], instance.inputs["Points"])
        group.links.new(sphere.outputs["Mesh"], instance.inputs["Instance"])
        group.links.new(instance.outputs["Instances"], realize.inputs["Geometry"])
        group.links.new(realize.outputs["Geometry"], assign.inputs["Geometry"])
        group.links.new(assign.outputs["Geometry"], output.inputs["Geometry"])
        modifier = obj.modifiers.new("ChemBlender Critical Point Spheres", "NODES")
        modifier.node_group = group
        group["cbq_contract"] = "topology_point_spheres_v1"
        return group
    except Exception:
        bpy.data.node_groups.remove(group)
        raise


def _attribute(mesh, name, data_type, values):
    attribute = mesh.attributes.new(name, data_type, "POINT")
    field = "value"
    attribute.data.foreach_set(field, values)


def create_topology_view(
    dataset,
    *,
    name="ChemBlender Topology",
    collection=None,
    point_radius=0.10,
    path_radius=0.025,
    material=None,
    path_material=None,
    color_property="kind",
    color_min=None,
    color_max=None,
):
    import numpy

    if not isinstance(dataset, TopologyGraph):
        raise TypeError("dataset must be a TopologyGraph")
    if not isinstance(name, str) or not name:
        raise ValueError("name must be non-empty")
    point_radius = _positive(point_radius, "point_radius")
    path_radius = _positive(path_radius, "path_radius")
    if color_property not in {"kind", "field_value", "laplacian"}:
        raise ValueError("color_property must be kind, field_value or laplacian")
    if color_property == "kind" and (color_min is not None or color_max is not None):
        raise ValueError("categorical critical point kinds do not use a scalar range")
    if color_property != "kind":
        color_values = dataset.field_values.values if color_property == "field_value" else dataset.laplacians.values
        color_min, color_max = _range(color_values, color_min, color_max)
    try:
        scale = _ANGSTROM_SCALE[dataset.data.unit]
    except KeyError as error:
        raise ValueError("topology view requires angstrom or bohr coordinates") from error
    collection = collection or bpy.context.collection
    if collection is None:
        raise ValueError("a Blender collection is required")

    positions = numpy.asarray(dataset.data.values, dtype=float) * scale
    mesh = bpy.data.meshes.new(f"{name} Critical Points")
    mesh["cb_scientific_owned"] = True
    points = None
    paths = None
    curve = None
    made, materials, groups = [], [], []
    try:
        mesh.from_pydata(positions.tolist(), [], [])
        points = bpy.data.objects.new(f"{name} Critical Points", mesh)
        made.append(points)
        collection.objects.link(points)
        _attribute(mesh, "cbq_critical_point_index", "INT", range(len(dataset.critical_point_ids)))
        _attribute(mesh, "cbq_critical_point_kind", "INT", tuple(_KIND_CODE[value] for value in dataset.kinds))
        _attribute(mesh, "cbq_critical_point_signature", "INT", dataset.signatures)
        _attribute(mesh, "cbq_critical_point_multiplicity", "INT", dataset.multiplicities)
        _attribute(mesh, "cbq_field_value", "FLOAT", dataset.field_values.values)
        _attribute(mesh, "cbq_laplacian", "FLOAT", dataset.laplacians.values)
        if material is None:
            if color_property == "kind":
                colors = mesh.attributes.new("cbq_kind_color", "FLOAT_COLOR", "POINT")
                colors.data.foreach_set("color", numpy.asarray([_KIND_COLORS[_KIND_CODE[kind]] for kind in dataset.kinds]).ravel())
                material = _flat_material("ChemBlender Critical Point Kinds", (1., 1., 1., 1.))
                attribute = material.node_tree.nodes.new("ShaderNodeAttribute")
                attribute.attribute_name = "cbq_kind_color"
                shader = next(node for node in material.node_tree.nodes if node.bl_idname == "ShaderNodeEmission")
                material.node_tree.links.new(attribute.outputs["Color"], shader.inputs["Color"])
            else:
                from .scientific_materials import scalar_material

                material = scalar_material("ChemBlender Critical Point Property", color_min, color_max,
                                           attribute_name="cbq_" + color_property)
            material["cb_scientific_owned"] = True
            materials.append(material)
        mesh.materials.append(material)
        groups.append(_point_glyphs(points, point_radius, material))
        mesh.update()
        points["cb_dataset_id"] = str(dataset.id)
        points["cb_dataset_revision"] = dataset.revision
        points["cb_structure_id"] = str(dataset.structure_id)
        points["cb_topology_contract"] = "topology_graph_v1"
        points["cb_source_coordinate_unit"] = dataset.data.unit
        points["cb_display_coordinate_unit"] = "angstrom"
        points["cb_coordinate_scale"] = scale
        points["cb_field_unit"] = dataset.field_values.unit
        points["cb_field_semantic_role"] = dataset.field_semantic_role
        points["cb_laplacian_unit"] = dataset.laplacians.unit
        points["cb_critical_point_ids"] = [str(value) for value in dataset.critical_point_ids]
        points["cb_critical_point_names"] = list(dataset.names)
        points["cb_point_radius"] = point_radius
        points["cb_color_property"] = color_property
        points["cb_connection_count"] = len(dataset.connections)
        points["cb_sampled_path_count"] = len(dataset.paths)
        if color_property != "kind":
            points["cb_color_min"], points["cb_color_max"] = color_min, color_max
        else:
            points["cb_kind_legend"] = [f"{code}={kind.value}" for kind, code in _KIND_CODE.items()]

        if dataset.paths:
            curve = bpy.data.curves.new(f"{name} Paths", "CURVE")
            curve["cb_scientific_owned"] = True
            curve.dimensions = "3D"
            curve.bevel_depth = path_radius
            curve.bevel_resolution = 3
            curve.use_fill_caps = True
            if path_material is None:
                path_material = _flat_material("ChemBlender Topology Paths", (.12, .25, .3, 1.))
                materials.append(path_material)
            curve.materials.append(path_material)
            for path in dataset.paths:
                values = numpy.asarray(path.samples.values, dtype=float) * scale
                spline = curve.splines.new("POLY")
                spline.points.add(values.shape[0] - 1)
                homogeneous = numpy.column_stack(
                    (values, numpy.ones(values.shape[0], dtype=float))
                )
                spline.points.foreach_set("co", homogeneous.reshape(-1))
            paths = bpy.data.objects.new(f"{name} Paths", curve)
            made.append(paths)
            collection.objects.link(paths)
            paths.parent = points
            paths["cb_scientific_component"] = "topology_paths"
            paths["cb_dataset_id"] = str(dataset.id)
            paths["cb_dataset_revision"] = dataset.revision
            paths["cb_topology_contract"] = "topology_paths_v1"
            paths["cb_path_ids"] = [str(path.id) for path in dataset.paths]
            paths["cb_path_start_ids"] = [str(path.start_id) for path in dataset.paths]
            paths["cb_path_end_ids"] = [str(path.end_id) for path in dataset.paths]
            paths["cb_source_coordinate_unit"] = dataset.data.unit
            paths["cb_display_coordinate_unit"] = "angstrom"
            paths["cb_path_radius"] = path_radius
            paths["cb_path_representation"] = "ordered_samples"
        return points, paths
    except Exception:
        if curve is not None and paths is None:
            bpy.data.curves.remove(curve)
        _remove_objects(made, materials=materials, groups=groups)
        if points is None:
            bpy.data.meshes.remove(mesh)
        raise
