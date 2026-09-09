"""Native installed-Extension smoke in a new private BLENDER_USER_RESOURCES profile.

Run install once, then cold in a fresh process. Input is a small explicitly
synthetic CBQ fixture; real scientific acceptance is a separate corpus gate.
This validates a candidate without scientific wheels, not formal dependency removal.
"""

import argparse
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
from uuid import uuid4
from zipfile import ZipFile

import bpy
import numpy


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--mode", choices=("install", "cold"), required=True)
parser.add_argument("--zip", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
ROOT = Path(__file__).resolve().parents[1]
output = args.output.resolve(strict=True)
profile = Path(os.environ["BLENDER_USER_RESOURCES"]).resolve(strict=True)
assert output.is_relative_to(ROOT / ".blend-analysis"), output
assert profile.is_relative_to(output), profile
assert os.environ.get("PYTHONNOUSERSITE") == "1"
assert not os.environ.get("PYTHONPATH")
assert bpy.app.version >= (5, 1, 0)
KEY = "bl_ext.user_default.chemblender"
package = args.zip.resolve(strict=True)
FORBIDDEN = ("chemblender_prepare", "cbq_core", "rdkit", "gemmi", "gbasis", "iodata",
             "scipy", "pyscf", "cclib", "phonopy", "pyprocar")


def no_external_dependencies():
    for name in FORBIDDEN:
        assert importlib.util.find_spec(name) is None, (name, "unexpected loadable dependency")
        assert not any(key == name or key.startswith(name + ".") for key in sys.modules), name


no_external_dependencies()
repository = next(repo for repo in bpy.context.preferences.extensions.repos if repo.module == "user_default")
extension = Path(repository.directory).resolve() / "chemblender"
assert extension.is_relative_to(profile), extension
if args.mode == "install":
    assert not extension.exists(), extension
    assert bpy.ops.extensions.package_install_files(filepath=str(package), repo="user_default",
        enable_on_install=True, overwrite=False) == {"FINISHED"}
assert KEY in bpy.context.preferences.addons
addon = importlib.import_module(KEY)
assert Path(addon.__file__).resolve().parent == extension
registration = importlib.import_module(KEY + ".runtime.registration")
session_ui = importlib.import_module(KEY + ".ui.session")
view_ui = importlib.import_module(KEY + ".ui.scientific_view")
core = importlib.import_module(KEY + "._cbq_core.model")
sidecar = importlib.import_module(KEY + "._cbq_core.sidecar")
scene_preset = importlib.import_module(KEY + "._cbq_core.scene_preset")
properties = ("chemblender_cbq", "chemblender_project_browser", "chemblender_topology",
              "chemblender_grid", "chemblender_wavefunction", "chemblender_scientific_view",
              "chemblender_scientific_export")


def inventory():
    assert all(hasattr(bpy.types.Scene, name) for name in properties)
    assert "chemblender.reader_api.v1" not in bpy.app.driver_namespace
    assert not any(hasattr(bpy.types.Scene, "chemblender_" + name)
                   for name in ("quick_import", "scientific_import", "topology_import"))
    assert registration._registered_classes
    assert all(cls.is_registered for cls in registration._registered_classes)
    return sorted(cls.__name__ for cls in registration._registered_classes)


initial = inventory()
if args.mode == "install":
    for iteration in range(2):
        owned = tuple(registration._registered_classes)
        assert bpy.ops.preferences.addon_disable(module=KEY) == {"FINISHED"}
        assert all(not cls.is_registered for cls in owned)
        assert not any(hasattr(bpy.types.Scene, name) for name in properties)
        assert not any(getattr(handler, "__module__", "").startswith(KEY + ".")
            for name in ("load_pre", "load_post", "save_pre", "save_post", "frame_change_post")
            for handler in getattr(bpy.app.handlers, name))
        if iteration:
            addon = importlib.reload(addon)
        assert bpy.ops.preferences.addon_enable(module=KEY) == {"FINISHED"}
        assert inventory() == initial
    # Exercise native RNA property ownership and rollback on failed identity probes.
    from unittest.mock import patch
    cbq_ui = importlib.import_module(KEY + ".ui.cbq_import")
    property_ui = importlib.import_module(KEY + ".ui.properties")
    cbq_ui.unregister()
    for probe_failure in (None, RuntimeError("identity probe failed")):
        with patch.object(property_ui, "_scene_property_identity", side_effect=(None, probe_failure)):
            try:
                cbq_ui.register()
            except RuntimeError:
                pass
            else:
                raise AssertionError("invalid property identity was accepted")
        assert not hasattr(bpy.types.Scene, "chemblender_cbq")
        assert cbq_ui._OWNED_SCENE_PROPERTY is None
    bpy.types.Scene.chemblender_cbq = bpy.props.StringProperty(default="foreign")
    foreign = property_ui._scene_property_identity("chemblender_cbq")
    try:
        cbq_ui.register()
    except RuntimeError as error:
        assert "already owned" in str(error)
    else:
        raise AssertionError("foreign property was overwritten")
    cbq_ui.unregister()
    assert property_ui._same_scene_property(foreign, property_ui._scene_property_identity("chemblender_cbq"))
    del bpy.types.Scene.chemblender_cbq
    cbq_ui.register()
    bpy.types.Scene.chemblender_cbq = bpy.props.StringProperty(default="replacement")
    replacement = property_ui._scene_property_identity("chemblender_cbq")
    cbq_ui.unregister()
    assert property_ui._same_scene_property(replacement, property_ui._scene_property_identity("chemblender_cbq"))
    del bpy.types.Scene.chemblender_cbq
    cbq_ui.register()
    assert bpy.ops.wm.save_userpref() == {"FINISHED"}
    for obj in tuple(bpy.context.scene.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    # Use the bundled canonical model to create a fixture, never the repository.
    structure = core.Structure(uuid4(), "smoke-h2", (1, 1),
        core.ArrayData(numpy.array([[-.7, 0., 0.], [.7, 0., 0.]]), ("atom", "xyz"), "bohr"),
        topology=core.MolecularTopology(
            core.ArrayData(numpy.array([[0, 1]], dtype=numpy.int64), ("bond", "endpoint"), "dimensionless"),
            core.ArrayData(numpy.array([1.]), ("bond",), "dimensionless")))
    axis = numpy.linspace(-3., 3., 17)
    x, y, z = numpy.meshgrid(axis, axis, axis, indexing="ij")
    values = numpy.exp(-(x*x + y*y + z*z))
    grid = core.Grid3D(uuid4(), "smoke-density", "electron_density", "real_space",
        core.ArrayData(values, ("x", "y", "z"), "electron_per_cubic_bohr"),
        core.DatasetStatus.COMPLETE, None, (), (-3., -3., -3.),
        ((.375, 0., 0.), (0., .375, 0.), (0., 0., .375)), "bohr", structure.id)
    project = core.QCProject(uuid4(), "1.1")
    project.commit(core.ImportBatch(structures=(structure,), datasets=(grid,)))
    source = sidecar.save_project(output / "source.cbq", project)
    scene = bpy.context.scene
    scene.chemblender_cbq.input_path = str(source)
    assert bpy.ops.chemblender.preview_cbq() == {"FINISHED"}
    preview = json.loads(scene.chemblender_cbq.preview_json)
    assert preview["counts"]["structures"] == 1
    assert preview["counts"]["datasets"] == 1
    assert preview["counts"]["new"] >= 2  # Canonical inline topology may add a record.
    assert bpy.ops.chemblender.import_cbq() == {"FINISHED"}
    session = session_ui.get_scene_session(scene)
    assert isinstance(session.project, core.QCProject)
    assert type(session.project.structures[structure.id]) is core.Structure
    assert type(session.project.datasets[grid.id]) is core.Grid3D
    numpy.testing.assert_allclose(session.project.datasets[grid.id].data.values, values)

    def create(identity, preset_id):
        session.active_entity_id = identity
        scene.chemblender_project_browser.active_entity_id = str(identity)
        settings = scene.chemblender_scientific_view
        settings.preset_id = preset_id
        assert bpy.ops.chemblender.scientific_view(action="DEFAULTS") == {"FINISHED"}
        assert bpy.ops.chemblender.scientific_view(action="CREATE") == {"FINISHED"}
        obj = bpy.data.objects[session.active_view_object_name]
        assert obj.get("cb_scene_preset_id") == preset_id
        return obj

    structure_view = create(structure.id, "structure_publication")
    assert len(structure_view.data.edges) == 1, (session.project.structures[structure.id].topology_ids, list(session.project.topologies))
    # Pure Mesh controls leave the authoritative Structure and Topology intact.
    import bmesh
    mesh_edit = importlib.import_module(KEY + '.ui.mesh_edit')
    bpy.context.view_layer.objects.active = structure_view
    structure_view.select_set(True)
    structure_view.location = (4., 5., 6.)
    structure_view.scale = (2., 3., 4.)
    assert bpy.ops.object.mode_set(mode='EDIT') == {'FINISHED'}
    assert bpy.ops.chemblender.mesh_edit(action='SELECT', atomic_number=1) == {'FINISHED'}
    bm = bmesh.from_edit_mesh(structure_view.data)
    assert sum(v.select for v in bm.verts) == 2
    measurement, kind = mesh_edit.measure_points(v.co for v in bm.verts)
    assert kind == 'distance' and abs(measurement - 1.4 * structure_view['cb_coordinate_scale']) < 1.e-6
    assert bpy.ops.chemblender.mesh_edit(action='MEASURE') == {'FINISHED'}
    assert bpy.ops.chemblender.mesh_edit(action='ATOM', atomic_number=8, scale=1.25) == {'FINISHED'}
    bm = bmesh.from_edit_mesh(structure_view.data)
    assert all(v[bm.verts.layers.int['atomic_num']] == 8 for v in bm.verts)
    for edge in bm.edges:
        edge.select_set(True)
        edge[bm.edges.layers.bool['is_aromatic']] = True
    assert bpy.ops.chemblender.mesh_edit(action='BOND', bond_order=2, scale=0.75) == {'FINISHED'}
    assert bpy.ops.object.mode_set(mode='OBJECT') == {'FINISHED'}
    assert all(item.value == 2. for item in structure_view.data.attributes['cbq_bond_order'].data)
    assert session.project.structures[structure.id].atomic_numbers == (1, 1)
    assert structure_view['cbq_mesh_edit_pending']
    assert all(not item.value for item in structure_view.data.attributes['is_aromatic'].data)
    # Apply once the scene already has a persistent CBQ link.
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "workbench.blend"))
    assert bpy.ops.chemblender.apply_mesh_edits() == {'FINISHED'}
    edited_id = session.active_entity_id
    edited_view = bpy.data.objects[session.active_view_object_name]
    assert edited_id != structure.id
    assert session.project.structures[edited_id].atomic_numbers == (8, 8)
    assert session.project.structures[structure.id].atomic_numbers == (1, 1)
    assert edited_view != structure_view and structure_view.name in bpy.data.objects
    assert edited_view.get("cb_scene_preset_id") == "structure_publication"
    assert edited_view.matrix_world == structure_view.matrix_world
    numpy.testing.assert_allclose(session.project.structures[edited_id].coordinates.values,
        numpy.asarray(structure.coordinates.values) * .529177210903, atol=1.e-7)
    surface_view = create(grid.id, "signed_isosurface")
    volume_view = create(grid.id, "grid_volume")
    bpy.context.view_layer.update()
    views = [obj.name for obj in (structure_view, edited_view, surface_view, volume_view)]
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "workbench.blend"))
    assert (output / "workbench.cbq/manifest.json").is_file()
    scene.chemblender_cbq.output_path = str(output / "export.cbq")
    assert bpy.ops.chemblender.export_cbq() == {"FINISHED"}
    exported = sidecar.open_project(output / "export.cbq", verify_arrays=True)
    assert exported.id == session.project.id
    sidecar.close_project(exported)
    fixture = {"project_id": str(session.project.id), "structure_id": str(structure.id),
               "grid_id": str(grid.id), "edited_id": str(edited_id), "edited_view": edited_view.name, "views": views, "grid_sum": float(values.sum())}
    (output / "fixture.json").write_text(json.dumps(fixture, indent=2), encoding="utf-8")
    # Source removal cannot invalidate owned scientific arrays or persisted Views.
    assert source.resolve().is_relative_to(output)
    shutil.rmtree(source)
    bpy.ops.wm.open_mainfile(filepath=str(output / "workbench.blend"))
else:
    bpy.ops.wm.open_mainfile(filepath=str(output / "workbench.blend"))

fixture = json.loads((output / "fixture.json").read_text(encoding="utf-8"))
session = session_ui.get_scene_session(bpy.context.scene)
assert str(session.project.id) == fixture["project_id"]
assert session_ui.get_scene_session_status(bpy.context.scene)[0] == "connected"
grid = next(value for value in session.project.datasets.values() if str(value.id) == fixture["grid_id"])
assert abs(float(numpy.asarray(grid.data.values).sum()) - fixture["grid_sum"]) < 1.e-10
for name in fixture["views"]:
    obj = bpy.data.objects.get(name)
    assert obj is not None and not obj.get("cb_view_stale"), (name, obj.get("cb_view_diagnostic") if obj else "missing")
    assert obj.get("cb_scene_preset_id")
if args.mode == "cold":
    from uuid import UUID
    assert session.project.structures[UUID(fixture["edited_id"])].atomic_numbers == (8, 8)
    obj = bpy.data.objects[fixture["edited_view"]]
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    assert bpy.ops.chemblender.scientific_view(action="REBUILD") == {'FINISHED'}
    assert session.project.structures[UUID(fixture["structure_id"])].atomic_numbers == (1, 1)
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "save-as.blend"))
    assert (output / "save-as.cbq/manifest.json").is_file()
    bpy.ops.wm.open_mainfile(filepath=str(output / "save-as.blend"))
    assert session_ui.get_scene_session_status(bpy.context.scene)[0] == "connected"
    assert str(session_ui.get_scene_session(bpy.context.scene).project.id) == fixture["project_id"]

no_external_dependencies()
with ZipFile(package) as archive:
    assert not any(name.endswith(".whl") for name in archive.namelist())
    for name in archive.namelist():
        if name.endswith(".py"):
            assert hashlib.sha256(archive.read(name)).digest() == hashlib.sha256((extension/name).read_bytes()).digest()
report = {"status": "Passed", "scope": "candidate without scientific wheels; not a release/dependency-removal gate",
          "mode": args.mode, "version": bpy.app.version_string,
          "executable": bpy.app.binary_path, "profile": str(profile), "extension": str(extension),
          "module_key": KEY, "classes": inventory(), "fixture": fixture,
          "external_dependencies_absent": list(FORBIDDEN), "numpy": numpy.__file__}
(output / (args.mode + ".json")).write_text(json.dumps(report, indent=2), encoding="utf-8")
print("CBQ_VIEWER_SMOKE_PASSED", args.mode, flush=True)
