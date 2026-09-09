"""Native local editing regression; run in a private factory-startup profile."""
import importlib
import builtins
import json
from pathlib import Path
import platform
import sys
from uuid import uuid4

import bpy
import bmesh

root = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
sys.path.insert(0, str(root))
assert bpy.app.version >= (5, 1, 0)
original_import = builtins.__import__
def local_only(name, *args, **kwargs):
    if name.split(".")[0] in {"chemblender_prepare", "rdkit", "gemmi"}:
        raise AssertionError("Local editing imported scientific processor: " + name)
    return original_import(name, *args, **kwargs)
builtins.__import__ = local_only
module = importlib.import_module("ChemBlender.ui.mesh_edit")
print(json.dumps({"blender": bpy.app.version_string, "executable": bpy.app.binary_path,
                  "python": sys.version, "system": platform.system(),
                  "repos": [r.directory for r in bpy.context.preferences.extensions.repos]}))
bpy.utils.register_class(module.CHEMBLENDER_OT_mesh_edit)
mesh = bpy.data.meshes.new("edit-contract")
mesh.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0)], [(0, 1), (1, 2)], [])
for name, kind, domain, values in (
    ("atomic_num", "INT", "POINT", [6, 6, 1]),
    ("cbq_atom_id", "INT", "POINT", [0, 1, 2]),
    ("bond_order", "INT", "EDGE", [1, 1]),
    ("cbq_bond_order", "FLOAT", "EDGE", [1.5, 1.5]),
    ("is_aromatic", "BOOLEAN", "EDGE", [True, True]),
):
    mesh.attributes.new(name, kind, domain).data.foreach_set("value", values)
obj = bpy.data.objects.new("edit-contract", mesh)
bpy.context.collection.objects.link(obj)
obj["cb_structure_id"] = str(uuid4())
obj["cb_structure_contract"] = "structure_view_v1"
obj["cb_display_coordinate_unit"] = "angstrom"
bpy.context.view_layer.objects.active = obj
obj.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
try:
    bm = bmesh.from_edit_mesh(mesh)
    for edge in bm.edges:
        edge.select_set(True)
    assert bpy.ops.chemblender.mesh_edit(action="BOND", bond_order=2, scale=.75) == {"FINISHED"}
    bpy.ops.object.mode_set(mode="OBJECT")
    assert [v.value for v in mesh.attributes["bond_order"].data] == [2, 2]
    assert [v.value for v in mesh.attributes["cbq_bond_order"].data] == [2, 2]
    assert [v.value for v in mesh.attributes["is_aromatic"].data] == [False, False]
    bpy.ops.object.mode_set(mode="EDIT")
    assert bpy.ops.chemblender.mesh_edit(action="SELECT", atomic_number=1) == {"FINISHED"}
    bm = bmesh.from_edit_mesh(mesh)
    assert sum(v.select for v in bm.verts) == 1
    assert bpy.ops.chemblender.mesh_edit(action="ATOM", atomic_number=8, scale=1.25) == {"FINISHED"}
    bpy.ops.object.mode_set(mode="OBJECT")
    assert [v.value for v in mesh.attributes["atomic_num"].data] == [6, 6, 8]
    bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(mesh)
    for vertex in bm.verts:
        vertex.select_set(True)
    assert bpy.ops.chemblender.mesh_edit(action="MEASURE") == {"FINISHED"}
    print("MESH_EDIT_PASSED")
finally:
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.utils.unregister_class(module.CHEMBLENDER_OT_mesh_edit)


# Exercise the real Apply operator and native Mesh/View APIs with a private session.
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import numpy
from cbq_core.model import ArrayData, ImportBatch, QCProject, Structure
from cbq_core.session import create_session, close_session
from cbq_core.sidecar import open_project, close_project
from ChemBlender.ui import session as session_ui

source = Structure(uuid4(), "source", (6, 6, 1),
    ArrayData(numpy.array([[0., 0., 0.], [1., 0., 0.], [1., 1., 0.]]),
              ("atom", "xyz"), "angstrom"))
project = QCProject(uuid4(), "1.1")
project.commit(ImportBatch(structures=(source,)))
obj["cb_structure_id"] = str(source.id)
obj["cb_structure_revision"] = source.revision
obj.location = (10, 20, 30)
bpy.context.view_layer.update()
class MeshApplyBrowserSettings(bpy.types.PropertyGroup):
    active_entity_id: bpy.props.StringProperty()
bpy.utils.register_class(MeshApplyBrowserSettings)
bpy.types.Scene.chemblender_project_browser = bpy.props.PointerProperty(type=MeshApplyBrowserSettings)
bpy.utils.register_class(module.CHEMBLENDER_OT_apply_mesh_edits)
with TemporaryDirectory() as temporary:
    session = create_session(temp_parent=Path(temporary), project=project)
    context = SimpleNamespace(active_object=obj, collection=bpy.context.collection,
        scene=SimpleNamespace(chemblender_project_browser=SimpleNamespace(active_entity_id="")),
        selected_objects=(obj,), view_layer=bpy.context.view_layer)
    operator = SimpleNamespace(report=lambda level, message: print(level, message))
    try:
        with patch.object(session_ui, "get_scene_session", return_value=session), \
             patch.object(session_ui, "_notify_session_mutation"):
            with patch("cbq_core.package_import.solidify_session", side_effect=OSError("disk full")):
                assert module.CHEMBLENDER_OT_apply_mesh_edits.execute(operator, context) == {"CANCELLED"}
            assert session.project is project and session.sidecar_path is None
            assert obj.get("cbq_mesh_edit_pending") is True
            assert bpy.ops.chemblender.apply_mesh_edits() == {"FINISHED"}
            derived = session.project.structures[session.active_entity_id]
            assert derived.id != source.id and source.id in session.project.structures
            assert derived.atomic_numbers == (6, 6, 8)
            numpy.testing.assert_array_equal(derived.coordinates.values, source.coordinates.values)
            topology = session.project.topologies[derived.topology_ids[0]]
            numpy.testing.assert_array_equal(topology.bond_orders.values, [2, 2])
            view = bpy.context.view_layer.objects.active
            assert view is not obj and obj.name in bpy.data.objects
            assert view.get("cb_structure_id") == str(derived.id)
            assert view.get("cb_scene_preset_id") == "structure_publication"
            assert view.matrix_world == obj.matrix_world
            assert obj.get("cb_structure_id") == str(source.id)
            assert obj.get("cbq_mesh_edit_pending") is False
            reopened = open_project(session.sidecar_path, verify_arrays=True)
            try:
                assert source.id in reopened.structures and derived.id in reopened.structures
            finally:
                close_project(reopened)
            # A second edit commits even if its subsequent display cannot be created.
            obj.data.vertices[0].co.x = .5
            before = set(session.project.structures)
            with patch("ChemBlender.scene_preset_view.apply_scene_preset", side_effect=RuntimeError("view failure")):
                assert module.CHEMBLENDER_OT_apply_mesh_edits.execute(operator, context) == {"FINISHED"}
            assert len(set(session.project.structures) - before) == 1
            assert obj.name in bpy.data.objects and view.name in bpy.data.objects
            print("MESH_APPLY_PASSED")
    finally:
        close_session(session)
        bpy.utils.unregister_class(module.CHEMBLENDER_OT_apply_mesh_edits)
        del bpy.types.Scene.chemblender_project_browser
        bpy.utils.unregister_class(MeshApplyBrowserSettings)
