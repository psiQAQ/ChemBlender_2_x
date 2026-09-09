"""Trajectory View lifecycle in a private native Blender process."""

import os
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import bpy
import numpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
private = Path(os.environ["BLENDER_USER_RESOURCES"]).resolve()
assert ROOT / ".agents" / "cache" in private.parents
private.mkdir(parents=True, exist_ok=True)

from cbq_core.model import ArrayData
from cbq_core.model import ImportBatch
from cbq_core.session import create_session
from cbq_core.scene_preset import builtin_scene_presets
from cbq_core.scene_preset import plan_scene_preset
from cbq_core.sidecar import save_project
from cbq_core.sidecar import open_project
from ChemBlender.dataset_view import _MODIFIER_NAME, _coordinate_scale
from ChemBlender.scene_preset_view import apply_scene_preset, apply_scientific_frame, _remove_objects
from ChemBlender import trajectory_view
from ChemBlender.ui import scientific_view as ui, session as session_ui
from ChemBlender.ui.project_browser import panel
from ChemBlender.ui.view_cache import scene_plan_from_view
from tests.test_trajectory_scene_preset import trajectory_fixture
from tests.test_scene_preset import grid

classes = (panel.CHEMBLENDER_PG_project_browser_row, panel.CHEMBLENDER_PG_project_browser,
           ui.CHEMBLENDER_PG_scientific_view, ui.CHEMBLENDER_OT_scientific_view)
for cls in classes:
    bpy.utils.register_class(cls)
bpy.types.Scene.chemblender_project_browser = bpy.props.PointerProperty(type=panel.CHEMBLENDER_PG_project_browser)
ui.register()
trajectory_view.register()
scene = bpy.context.scene
session = create_session(temp_parent=private.parent)
session_ui._FILE_SESSION = session_ui._SessionEntry(session)
project, reference, frames, force, time, _ = trajectory_fixture(lazy=False)
session.project.commit(ImportBatch(structures=(reference,), datasets=tuple(project.datasets.values())))
project = session.project
before = frames.data.values.copy()
settings = scene.chemblender_scientific_view
session.active_entity_id = frames.id
scene.chemblender_project_browser.active_entity_id = str(frames.id)
settings.preset_id = "trajectory_force"


def coordinates(obj):
    result = numpy.empty(6)
    obj.data.vertices.foreach_get("co", result)
    return result.reshape(2, 3)


def assert_frame(obj, index):
    numpy.testing.assert_allclose(coordinates(obj), before[index] * _coordinate_scale("bohr"), atol=1.e-7)
    assert obj["cb_trajectory_frame_index"] == index
    assert obj["cb_trajectory_frame_label"] == frames.comments[index]
    assert obj["cb_trajectory_time"] == time.data.values[index]
    assert obj["cb_trajectory_time_unit"] == "femtosecond"


try:
    assert bpy.ops.chemblender.scientific_view(action="DEFAULTS") == {"FINISHED"}
    settings.secondary_source_uuid = str(force.id)
    settings.frame_index, settings.frame_start, settings.frame_step = 0, 10, 4
    scene.frame_set(100)
    assert bpy.ops.chemblender.scientific_view(action="CREATE") == {"FINISHED"}
    obj = bpy.context.active_object
    assert_frame(obj, 0)
    assert "missing" in obj["cb_trajectory_force_status"]
    assert not obj.get("cb_report_eligible")  # Partial force dataset remains partial.
    scene.frame_set(18)
    assert_frame(obj, 0)  # A static View never follows an unrelated timeline.
    settings.frame_index = 1
    assert bpy.ops.chemblender.scientific_view(action="FRAME") == {"FINISHED"}
    assert_frame(obj, 1)
    modifier = obj.modifiers[_MODIFIER_NAME]
    group = modifier.node_group
    assert group["cb_scientific_owned"]
    assert modifier.show_render
    apply_scientific_frame(obj, project, 2)
    assert not modifier.show_render
    apply_scientific_frame(obj, project, 1)
    assert modifier.node_group == group and modifier.show_render
    assert dict(scene_plan_from_view(obj, project).settings)["frame_index"] == 0
    assert bpy.ops.chemblender.scientific_view(action="PLAY") == {"FINISHED"}
    assert (scene.frame_start, scene.frame_end) == (10, 18)
    scene.frame_set(14)
    assert_frame(obj, 1)
    assert bpy.ops.chemblender.scientific_view(action="PAUSE") == {"FINISHED"}
    scene.frame_set(18)
    assert_frame(obj, 1)
    obj.location = (5., 6., 7.)
    identity, old_key = obj["cb_view_instance_id"], obj.as_pointer()
    old_manager = trajectory_view._BINDINGS[old_key].manager
    user = bpy.data.objects.new("User Annotation", None)
    scene.collection.objects.link(user)
    user.parent = obj
    user.location = (1., 2., 3.)
    bpy.context.view_layer.update()
    user_pose = user.matrix_world.copy()
    assert bpy.ops.chemblender.scientific_view(action="LOAD") == {"FINISHED"}
    settings.frame_index = 1
    settings.material_opacity = .7
    assert bpy.ops.chemblender.scientific_view(action="UPDATE") == {"FINISHED"}
    obj = bpy.context.active_object
    assert obj["cb_view_instance_id"] == identity and tuple(obj.location) == (5., 6., 7.)
    bpy.context.view_layer.update()
    assert all(abs(user.matrix_world[i][j] - user_pose[i][j]) < 1.e-6 for i in range(4) for j in range(4))
    assert old_key not in trajectory_view._BINDINGS and old_manager._closed
    assert_frame(obj, 1)
    plan = scene_plan_from_view(obj, project)
    count = len(trajectory_view._BINDINGS)
    original = trajectory_view.apply_trajectory_frame

    def fail_after_manager(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("injected trajectory create failure")

    with patch.object(trajectory_view, "apply_trajectory_frame", side_effect=fail_after_manager):
        try:
            apply_scene_preset(plan, project)
        except RuntimeError as error:
            assert "injected" in str(error)
        else:
            raise AssertionError("expected injected failure")
    assert len(trajectory_view._BINDINGS) == count
    assert_frame(obj, 1)
    extra_time = replace(time, id=uuid4())
    project.commit(ImportBatch(datasets=(extra_time,)))
    metadata = apply_scientific_frame(obj, project, 1)
    assert "time" not in metadata and "cb_trajectory_time" not in obj
    numpy.testing.assert_array_equal(frames.data.values, before)
    # NCI reuses the exact density-grid-to-mesh contract and a real zero transfer.
    # These arrays are synthetic adapter checks, never example scientific results.
    base = grid(reference.id)
    rdg_values = numpy.zeros(base.grid_shape)
    rdg_values[1, 1, 1] = 1.
    rdg = replace(base, semantic_role="reduced_density_gradient",
        data=ArrayData(rdg_values, ("x", "y", "z"), "dimensionless"))
    signed = replace(base, id=uuid4(), semantic_role="sign_lambda2_rho",
        data=ArrayData(numpy.linspace(-.05, .05, 27).reshape(3, 3, 3), ("x", "y", "z"), base.data.unit))
    project.commit(ImportBatch(datasets=(rdg, signed)))
    nci_plan = plan_scene_preset(builtin_scene_presets()["nci_surface"], project,
        {"surface_grid": rdg.id, "property_grid": signed.id}, {"pairing_confirmed": True})
    nci = apply_scene_preset(nci_plan, project, cache_root=private.parent / "nci-cache")[0]
    group = next(mod.node_group for mod in nci.modifiers if mod.type == "NODES")
    assert group["cbq_contract"] == "property_surface_v2"
    assert any(node.bl_idname == "GeometryNodeGridToMesh" for node in group.nodes)
    assert not any(node.bl_idname == "GeometryNodeVolumeToMesh" for node in group.nodes)
    assert scene_plan_from_view(nci, project).render_identity == nci_plan.render_identity
    _remove_objects((nci,))
    output = private.parent / "trajectory-output"
    output.mkdir(exist_ok=True)
    save_project(output / "trajectory.cbq", project)
    obj_name = obj.name
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "trajectory.blend"))
    bpy.ops.wm.open_mainfile(filepath=str(output / "trajectory.blend"))
    assert not trajectory_view._BINDINGS
    reopened = open_project(output / "trajectory.cbq")
    obj = bpy.data.objects[obj_name]
    assert scene_plan_from_view(obj, reopened).render_identity == plan.render_identity
    apply_scientific_frame(obj, reopened, 2)
    numpy.testing.assert_allclose(coordinates(obj), before[2] * _coordinate_scale("bohr"), atol=1.e-7)
    assert not obj.modifiers[_MODIFIER_NAME].show_render
    manager = trajectory_view._BINDINGS[obj.as_pointer()].manager
    _remove_objects((obj,))
    assert manager._closed and not trajectory_view._BINDINGS
    assert bpy.data.objects.get("User Annotation") is not None
    print("TRAJECTORY_SCENE_PASSED: static frame, force masks/materials, timeline, replacement, rollback, time provenance, reopen, cleanup")
finally:
    trajectory_view.unregister()
    ui.unregister()
    session_ui.close_scene_session(bpy.context.scene)
    del bpy.types.Scene.chemblender_project_browser
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
