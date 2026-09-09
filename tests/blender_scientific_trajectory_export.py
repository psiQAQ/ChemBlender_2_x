"""Native trajectory images/video preserve source time, fixed framing and transactions."""

import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import bpy
import numpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
private = Path(os.environ["BLENDER_USER_RESOURCES"]).resolve()
assert ROOT / ".agents" / "cache" in private.parents
private.mkdir(parents=True, exist_ok=True)

from cbq_core.model import ArrayData
from cbq_core.model import DatasetStatus
from cbq_core.model import ImportBatch
from cbq_core.session import create_session
from cbq_core.scene_preset import builtin_scene_presets
from cbq_core.scene_preset import plan_scene_preset
from ChemBlender.render_scene import RenderScope, RenderCancelled
from ChemBlender.scene_preset_view import apply_scene_preset, _remove_objects
from ChemBlender.ui.scientific_export import export_scientific_images, iter_scientific_images
from ChemBlender.ui.orbital_export import _EXPORTS
from ChemBlender import trajectory_view
from tests.test_trajectory_scene_preset import trajectory_fixture


def state():
    scene = bpy.context.scene
    return (scene.camera, scene.world, scene.render.engine, scene.render.resolution_x,
            scene.render.resolution_y, scene.render.filepath, scene.cycles.samples,
            scene.view_settings.view_transform, scene.view_settings.look,
            tuple((obj, obj.hide_render) for obj in scene.objects),
            tuple(trajectory_view._BINDINGS),
            {name: {block.as_pointer() for block in getattr(bpy.data, name)} for name in
             ("objects", "meshes", "curves", "materials", "node_groups", "lights", "cameras", "worlds", "scenes")})


session = create_session(temp_parent=private.parent)
project, structure, frames, force, time, _source = trajectory_fixture(lazy=False)
force = replace(force, status=DatasetStatus.COMPLETE, validity_mask=None,
                data=ArrayData(numpy.arange(18, dtype=float).reshape(3, 2, 3) * .015,
                               ("frame", "atom", "xyz"), force.data.unit))
session.project.commit(ImportBatch(structures=(structure,), datasets=(frames, force, time)))
plan = plan_scene_preset(builtin_scene_presets()["trajectory_force"], session.project,
                         {"structure": structure.id, "frames": frames.id, "force": force.id},
                         {"frame_index": 1, "frame_start": 12, "frame_step": 3})
objects = apply_scene_preset(plan, session.project)
before_arrays = (frames.data.values.copy(), force.data.values.copy())
original_render = RenderScope.render
displays = []


def capture_render(renderer, *args, **kwargs):
    result = original_render(renderer, *args, **kwargs)
    displays.append(result)
    return result


try:
    before = state()
    with TemporaryDirectory(prefix="trajectory-export-", dir=private.parent) as temporary:
        directory = Path(temporary)
        with patch.object(RenderScope, "render", capture_render):
            result = export_scientific_images(bpy.context, session, roots=(objects[0],),
                destination=directory / "complete", width=240, height=180, samples=8,
                animation=True, fps=24, direction=(0., 0., 1.), framing_margin=1.5)
        after = state()
        if after != before:
            print("NEW_NODE_GROUPS", [(value.name, value.get("cbq_contract"), value.users,
                value.get("cb_scientific_owned")) for value in bpy.data.node_groups
                if value.as_pointer() not in before[-1]["node_groups"]])
        assert after == before, [(index, old, new) for index, (old, new) in enumerate(zip(before, after)) if old != new]
        assert session.id not in _EXPORTS
        display = json.loads((result / "display.json").read_text(encoding="utf-8"))
        assert len(displays) == 6
        assert len(list((result / "images").glob("*.png"))) == 6
        for index, view in enumerate(display["views"]):
            rendered = displays[index * 3:(index + 1) * 3]
            assert all(item["camera"] == rendered[0]["camera"] for item in rendered)
            assert all(item["lights"] == rendered[0]["lights"] for item in rendered)
            assert [item["trajectory_frame"]["frame_index"] for item in rendered] == [0, 1, 2]
            assert len(view["images"]) == 3 and view["fps"] == 24
            assert (result / view["video"]).read_bytes()[4:8] == b"ftyp"
            for frame, image in enumerate(view["images"]):
                source = image["trajectory_frame"]
                assert source == rendered[frame]["trajectory_frame"]
                assert source["frame_label"] == frames.comments[frame]
                assert source["time"] == time.data.values[frame]
                assert source["time_unit"] == "femtosecond"
                assert source["time_dataset_id"] == str(time.id)
                assert source["time_dataset_revision"] == time.revision
                assert image["phase_radians"] is None
        # Cancellation during envelope scanning never starts a render or publishes.
        bounds_calls = [0]
        original_bounds = RenderScope._bounds

        def counted_bounds(renderer, *args, **kwargs):
            bounds_calls[0] += 1
            return original_bounds(renderer, *args, **kwargs)

        with patch.object(RenderScope, "_bounds", counted_bounds):
            try:
                export_scientific_images(bpy.context, session, roots=(objects[0],),
                    destination=directory / "cancel-envelope", width=240, height=180, samples=8,
                    animation=True, is_cancelled=lambda: bounds_calls[0] >= 2)
            except RenderCancelled:
                pass
            else:
                raise AssertionError("cancelled trajectory was published")
        assert bounds_calls[0] == 2
        assert not (directory / "cancel-envelope").exists()
        assert state() == before and session.id not in _EXPORTS
        # Close after one successfully written PNG: the staging package disappears.
        iterator = iter_scientific_images(bpy.context, session, roots=(objects[0],),
            destination=directory / "cancel-written-frame", width=240, height=180,
            samples=8, animation=True, templates=("research",))
        next(iterator)
        next(iterator)
        iterator.close()
        assert not (directory / "cancel-written-frame").exists()
        assert not list(directory.glob("*.images"))
        assert {path.name for path in directory.iterdir()} == {"complete"}
        assert state() == before and session.id not in _EXPORTS
    numpy.testing.assert_array_equal(frames.data.values, before_arrays[0])
    numpy.testing.assert_array_equal(force.data.values, before_arrays[1])
    print("SCIENTIFIC_TRAJECTORY_EXPORT_PASSED: fixed camera/light, per-image source time, two native MP4s, cancellation before/after PNG, resource restoration")
finally:
    _remove_objects(objects)
