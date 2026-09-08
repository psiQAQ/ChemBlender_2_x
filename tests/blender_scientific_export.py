"""Actual Cycles/FFmpeg export and restoration in a private Blender profile."""

import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
private = Path(os.environ["BLENDER_USER_RESOURCES"]).resolve()
assert ROOT / ".agents" / "cache" in private.parents

from ChemBlender.core import ImportBatch, builtin_scene_presets, create_session, plan_scene_preset
from ChemBlender.scene_preset_view import apply_scene_preset, _remove_objects
from ChemBlender.ui.scientific_export import export_scientific_images, _encode_video
from ChemBlender.ui import scientific_export as ui
from tests.test_periodic_electronic_model import periodic_structure, band_structure


def state():
    scene = bpy.context.scene
    return (scene.camera, scene.world, scene.render.engine, scene.render.resolution_x,
            scene.render.resolution_y, scene.render.filepath, scene.cycles.samples,
            scene.view_settings.view_transform, scene.view_settings.look,
            tuple((obj, obj.hide_render) for obj in scene.objects),
            {name: {block.as_pointer() for block in getattr(bpy.data, name)} for name in
             ("objects", "meshes", "curves", "materials", "node_groups", "lights", "cameras", "worlds", "scenes")})


session = create_session(temp_parent=private.parent)
structure = periodic_structure()
band = band_structure(structure.id)
session.project.commit(ImportBatch(structures=(structure,), datasets=(band,)))
plan = plan_scene_preset(builtin_scene_presets()["band_structure"], session.project, {"band": band.id}, {})
objects = apply_scene_preset(plan, session.project)
objects[0].location = (2., -3., 1.)
objects[0].rotation_euler.z = .35
bpy.context.view_layer.update()
source_matrix = [list(row) for row in objects[0].matrix_world]
classes = (ui.CHEMBLENDER_PG_scientific_export, ui.CHEMBLENDER_OT_export_scientific)
try:
    for cls in classes:
        bpy.utils.register_class(cls)
    ui.register()
    before = state()
    with TemporaryDirectory(prefix="export-check-", dir=private.parent) as temporary:
        directory = Path(temporary)
        result = export_scientific_images(bpy.context, session, roots=(objects[0],), destination=directory / "images",
                                         width=160, height=120, samples=8)
        assert state() == before
        images = sorted((result / "images").glob("*.png"))
        assert len(images) == 2
        display = json.loads((result / "display.json").read_text())
        assert [view["display"]["template"] for view in display["views"]] == ["research", "teaching"]
        assert all(view["source_matrix_world"] == source_matrix for view in display["views"])
        assert [list(row) for row in objects[0].matrix_world] == source_matrix
        assert all(view["display"]["render"]["engine"] == "CYCLES" for view in display["views"])
        assert all(view["display"]["display_coordinate_unit"] is None for view in display["views"])
        assert all(view["display"]["scientific_axes"][0]["x_unit"] == "inverse_angstrom"
                   and view["display"]["scientific_axes"][0]["y_unit"] == "electron_volt"
                   for view in display["views"])
        _encode_video(images, directory / "sample.mp4", 160, 120, 24)
        assert (directory / "sample.mp4").stat().st_size > 100
        assert state() == before
        with patch("ChemBlender.render_scene.RenderScope.render", side_effect=RuntimeError("injected")):
            try:
                export_scientific_images(bpy.context, session, roots=(objects[0],), destination=directory / "failed",
                                         width=160, height=120, samples=8)
            except RuntimeError as error:
                assert str(error) == "injected"
            else:
                raise AssertionError("failed render was published")
        assert not (directory / "failed").exists()
        assert state() == before
        assert not list(directory.glob("*.images"))
    print("SCIENTIFIC_EXPORT_PASSED: two Cycles templates, FFmpeg, RNA, atomic failure, full display restoration")
finally:
    ui.unregister()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    _remove_objects(objects)
