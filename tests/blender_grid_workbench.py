"""Full registered Grid workbench UI regression in a disposable Blender process."""

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
parser = argparse.ArgumentParser()
parser.add_argument("--existing-libraries", required=True)
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
sys.path.append(args.existing_libraries)

import ChemBlender
from ChemBlender.core import ArrayData, ImportBatch
from ChemBlender.ui.session import get_scene_session, close_scene_session
from ChemBlender.ui.view_cache import plan_grid_sample_view
from tests.test_grid_sampling import grid


ChemBlender.register()
try:
    scene = bpy.context.scene
    session = get_scene_session(scene)
    source = replace(grid(multidataset=True), structure_id=None, provenance_ids=())
    density_values = np.zeros(source.data.shape)
    density_values[:, 1:-1, 1:-1, 1:-1] = .7
    density = replace(source, id=uuid4(), revision="density-fixture", semantic_role="electron_density",
        data=ArrayData(density_values, source.data.dims, "electron_per_bohr_cubed"))
    session.project.commit(ImportBatch(datasets=(source, density)))
    session.active_entity_id = source.id
    scene.chemblender_project_browser.active_entity_id = str(source.id)
    settings = scene.chemblender_grid
    settings.dataset_index = 1
    settings.symmetric = False
    settings.color_min, settings.color_max = -20., 40.
    assert bpy.ops.chemblender.create_grid_view(mode="fit_sampling") == {"FINISHED"}
    settings.slice_counts = (13, 11)
    settings.profile_samples = 19
    roots = {}
    with TemporaryDirectory(prefix="cb-grid-ui-") as temporary:
        for mode in ("slice", "profile", "colorbar"):
            assert bpy.ops.chemblender.create_grid_view(mode=mode) == {"FINISHED"}
            obj = scene.objects[session.active_view_object_name]
            roots[mode] = obj
            assert obj.get("cb_grid_sample_root")
            plan = plan_grid_sample_view(obj, session.project)
            assert dict(plan.settings)["dataset_index"] == 1
            if mode == "colorbar":
                assert np.isclose(obj["cb_color_zero_fraction"], 1 / 3)
                continue
            path = str(Path(temporary) / (mode + ".csv"))
            assert bpy.ops.chemblender.create_grid_view(mode="export_sample",
                object_name=obj.name, filepath=path) == {"FINISHED"}
            exported = Path(path).read_bytes()
            obj.location, obj.rotation_euler, obj.scale = (7., -4., 3.), (.2, .3, .4), (2., 3., 1.)
            bpy.context.view_layer.update()
            assert bpy.ops.chemblender.create_grid_view(mode="export_sample",
                object_name=obj.name, filepath=path) == {"FINISHED"}
            assert Path(path).read_bytes() == exported
            settings.dataset_index = 0
            assert bpy.ops.chemblender.create_grid_view(mode="load_view",
                object_name=obj.name) == {"FINISHED"}
            assert settings.dataset_index == 1
            user = None
            if mode == "profile":
                user = bpy.data.objects.new("User annotation", None)
                scene.collection.objects.link(user)
                user.parent = next(iter(obj.children))
                user.location = (.3, -.2, .8)
                bpy.context.view_layer.update()
                user_transform = user.matrix_world.copy()
            pointer, transform, old_data = obj.as_pointer(), obj.matrix_world.copy(), obj.data
            with patch("ChemBlender.scene_preset_view.apply_scene_preset", side_effect=RuntimeError("injected")):
                try:
                    bpy.ops.chemblender.create_grid_view(mode="rebuild_sample", object_name=obj.name)
                except RuntimeError as error:
                    assert "injected" in str(error)
            assert obj.data == old_data
            assert bpy.ops.chemblender.create_grid_view(mode="rebuild_sample",
                object_name=obj.name) == {"FINISHED"}
            assert obj.as_pointer() == pointer and obj.data != old_data
            bpy.context.view_layer.update()
            np.testing.assert_allclose(obj.matrix_world, transform)
            if user is not None:
                np.testing.assert_allclose(user.matrix_world, user_transform, atol=2.e-6)
                bpy.data.objects.remove(user, do_unlink=True)
            assert bpy.ops.chemblender.create_grid_view(mode="export_sample",
                object_name=obj.name, filepath=path) == {"FINISHED"}
            assert Path(path).read_bytes() == exported

        session.active_entity_id = density.id
        scene.chemblender_project_browser.active_entity_id = str(density.id)
        settings.dataset_index = settings.property_dataset_index = 1
        settings.isovalue = .3
        assert bpy.ops.chemblender.create_grid_view(mode="property_surface",
            property_grid_id=str(source.id)) == {"FINISHED"}
        surface = scene.objects[session.active_view_object_name]
        saved = json.loads(surface["cb_scene_settings_json"])
        assert saved["surface_dataset_index"] == saved["property_dataset_index"] == 1
        assert saved["color_min"] == -20 and saved["color_max"] == 40
        assert bpy.ops.chemblender.create_grid_view(mode="colorbar",
            property_grid_id=str(source.id)) == {"FINISHED"}
        legend = scene.objects[session.active_view_object_name]
        assert legend["cb_dataset_id"] == str(source.id)
        assert legend["cb_value_unit"] == source.data.unit
        assert legend["cb_dataset_index"] == 1
        before = {name: {value.as_pointer() for value in getattr(bpy.data, name)}
                  for name in ("objects", "meshes", "curves", "materials")}
        with patch("ChemBlender.scene_preset_view._write_plan_metadata", side_effect=RuntimeError("metadata failure")):
            try:
                bpy.ops.chemblender.create_grid_view(mode="colorbar", property_grid_id=str(source.id))
            except RuntimeError as error:
                assert "metadata failure" in str(error)
            else:
                raise AssertionError("metadata failure was not raised")
        after = {name: {value.as_pointer() for value in getattr(bpy.data, name)} for name in before}
        assert after == before, "preset metadata failure leaked owned components"
    session.mark_clean()
    close_scene_session(scene)
    print("GRID_WORKBENCH_UI_PASSED")
finally:
    ChemBlender.unregister()
