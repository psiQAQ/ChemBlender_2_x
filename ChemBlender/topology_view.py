import bpy

from .core import CriticalPointKind, TopologyGraph


_ANGSTROM_SCALE = {"angstrom": 1.0, "bohr": 0.529177210903}
_KIND_CODE = {
    CriticalPointKind.NUCLEAR: 0,
    CriticalPointKind.ATTRACTOR: 1,
    CriticalPointKind.BOND: 2,
    CriticalPointKind.RING: 3,
    CriticalPointKind.CAGE: 4,
}


def _attribute(mesh, name, data_type, values):
    attribute = mesh.attributes.new(name, data_type, "POINT")
    field = "value"
    attribute.data.foreach_set(field, values)


def create_topology_view(
    dataset,
    *,
    name="ChemBlender Topology",
    collection=None,
):
    import numpy

    if not isinstance(dataset, TopologyGraph):
        raise TypeError("dataset must be a TopologyGraph")
    if not isinstance(name, str) or not name:
        raise ValueError("name must be non-empty")
    try:
        scale = _ANGSTROM_SCALE[dataset.data.unit]
    except KeyError as error:
        raise ValueError("topology view requires angstrom or bohr coordinates") from error
    collection = collection or bpy.context.collection
    if collection is None:
        raise ValueError("a Blender collection is required")

    positions = numpy.asarray(dataset.data.values, dtype=float) * scale
    mesh = bpy.data.meshes.new(f"{name} Critical Points")
    points = None
    paths = None
    curve = None
    try:
        mesh.from_pydata(positions.tolist(), [], [])
        points = bpy.data.objects.new(f"{name} Critical Points", mesh)
        collection.objects.link(points)
        _attribute(mesh, "cbq_critical_point_index", "INT", range(len(dataset.critical_point_ids)))
        _attribute(mesh, "cbq_critical_point_kind", "INT", tuple(_KIND_CODE[value] for value in dataset.kinds))
        _attribute(mesh, "cbq_critical_point_signature", "INT", dataset.signatures)
        _attribute(mesh, "cbq_critical_point_multiplicity", "INT", dataset.multiplicities)
        _attribute(mesh, "cbq_field_value", "FLOAT", dataset.field_values.values)
        _attribute(mesh, "cbq_laplacian", "FLOAT", dataset.laplacians.values)
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

        if dataset.paths:
            curve = bpy.data.curves.new(f"{name} Paths", "CURVE")
            curve.dimensions = "3D"
            for path in dataset.paths:
                values = numpy.asarray(path.samples.values, dtype=float) * scale
                spline = curve.splines.new("POLY")
                spline.points.add(values.shape[0] - 1)
                homogeneous = numpy.column_stack(
                    (values, numpy.ones(values.shape[0], dtype=float))
                )
                spline.points.foreach_set("co", homogeneous.reshape(-1))
            paths = bpy.data.objects.new(f"{name} Paths", curve)
            collection.objects.link(paths)
            paths["cb_dataset_id"] = str(dataset.id)
            paths["cb_dataset_revision"] = dataset.revision
            paths["cb_topology_contract"] = "topology_paths_v1"
            paths["cb_path_ids"] = [str(path.id) for path in dataset.paths]
        return points, paths
    except Exception:
        if paths is not None:
            bpy.data.objects.remove(paths, do_unlink=True)
        if curve is not None:
            bpy.data.curves.remove(curve)
        if points is not None:
            bpy.data.objects.remove(points, do_unlink=True)
        bpy.data.meshes.remove(mesh)
        raise
