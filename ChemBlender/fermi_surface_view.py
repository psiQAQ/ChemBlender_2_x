import operator

import bpy

from .core.model import FermiSurfaceMesh


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
    domain = "POINT" if prop.domain == "vertex" else "FACE"
    name = f"cbq_{prop.semantic_role}"
    if values.ndim == 1:
        attribute = _attribute(mesh, name, "FLOAT", domain)
        attribute.data.foreach_set("value", values)
    else:
        attribute = _attribute(mesh, name, "FLOAT_VECTOR", domain)
        attribute.data.foreach_set("vector", values.reshape(-1))


def create_fermi_surface_view(
    dataset,
    *,
    name="ChemBlender Fermi Surface",
    collection=None,
):
    import numpy

    if not isinstance(dataset, FermiSurfaceMesh):
        raise TypeError("dataset must be a FermiSurfaceMesh")
    mesh = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, mesh)
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
        (collection or bpy.context.collection).objects.link(obj)
    except Exception:
        bpy.data.objects.remove(obj)
        bpy.data.meshes.remove(mesh)
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
