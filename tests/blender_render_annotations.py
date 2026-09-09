"""Synthetic annotation QA only; no real calculation or user profile is changed."""

import json
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

from cbq_core.model import ImportBatch
from cbq_core.model import QCProject
from cbq_core.scene_preset import builtin_scene_presets
from cbq_core.scene_preset import plan_scene_preset
from ChemBlender import render_annotations as annotations
from ChemBlender.scene_preset_view import _remove_objects, apply_scene_preset
from tests.test_scene_preset import grid


scene = bpy.context.scene
for obj in tuple(scene.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
scene.render.engine = "CYCLES"
scene.cycles.samples = 16
scene.cycles.use_denoising = False
scene.render.resolution_x, scene.render.resolution_y = 800, 600
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.view_settings.view_transform = "Standard"
scene.view_settings.look = "None"
scene.view_settings.exposure = 0.
scene.view_settings.gamma = 1.
world = bpy.data.worlds.new("Synthetic Annotation Background")
world.use_nodes = True
world.node_tree.nodes.get("Background").inputs["Color"].default_value = (.86, .86, .86, 1.)
world.node_tree.nodes.get("Background").inputs["Strength"].default_value = 1.
scene.world = world
camera_data = bpy.data.cameras.new("Synthetic Annotation Camera")
camera = bpy.data.objects.new("Synthetic Annotation Camera", camera_data)
scene.collection.objects.link(camera)
camera.location = (0., 0., 10.)
camera.data.type = "ORTHO"
camera.data.ortho_scale = 5.
camera.data.clip_start = .01
scene.camera = camera
field = grid(None)
field = replace(field, semantic_role="scalar_field", revision="synthetic-annotation-test",
                data=replace(field.data, unit="dimensionless"))
project = QCProject(uuid4(), "0.2")
project.commit(ImportBatch(datasets=(field,)))

# Teaching's shared shaded setting must not claim lighting on the emission-only
# slice, colorbar, or profile. Inspect actual adapter shaders as well as metadata.
for kind in ("grid_slice", "grid_colorbar", "grid_profile"):
    teaching_plan = plan_scene_preset(builtin_scene_presets()[kind], project, {"grid": field.id},
                                      {"template": "teaching", "shaded": True})
    teaching_views = apply_scene_preset(teaching_plan, project)
    try:
        description = annotations._description(teaching_plan, project, teaching_views[0])
        assert not any("Morphology shading" in detail for detail in description["details"])
        materials = {material for obj in teaching_views for material in getattr(obj.data, "materials", ())}
        assert materials
        assert all(any(node.bl_idname == "ShaderNodeEmission" for node in material.node_tree.nodes)
                   and not any(node.bl_idname == "ShaderNodeBsdfPrincipled" for node in material.node_tree.nodes)
                   for material in materials)
    finally:
        _remove_objects(teaching_views)

plan = plan_scene_preset(builtin_scene_presets()["grid_slice"], project, {"grid": field.id},
    {"color_min": -2., "color_max": 1., "symmetric": False, "colormap": "nci"})
views = apply_scene_preset(plan, project)
root = views[0]
for obj in views:
    obj.hide_render = True


def inventory():
    return tuple(len(registry) for registry in (bpy.data.objects, bpy.data.meshes, bpy.data.curves, bpy.data.materials))


baseline = inventory()
output = private / "synthetic-annotations"
output.mkdir(parents=True, exist_ok=True)
for template, camera_type in (("research", "ORTHO"), ("teaching", "PERSP")):
    camera.data.type = camera_type
    world.node_tree.nodes.get("Background").inputs["Color"].default_value = (
        (.86, .86, .86, 1.) if template == "research" else (.012, .019, .032, 1.))
    made, metadata = annotations.create_render_annotations(plan, project, root, camera, template=template)
    try:
        assert metadata["scalar"]["zero_position"] == 2/3
        assert len(metadata["scalar"]["stops"]) == 3
        assert all(obj.get("cb_scientific_owned") and obj.parent is camera for obj in made)
        assert all(not obj.visible_shadow and not obj.visible_diffuse for obj in made)
        for obj in made:
            for material in obj.data.materials:
                assert any(node.bl_idname == "ShaderNodeEmission" for node in material.node_tree.nodes)
                assert not any(node.bl_idname == "ShaderNodeBsdfPrincipled" for node in material.node_tree.nodes)
        scene.render.filepath = str(output / (template + ".png"))
        bpy.ops.render.render(write_still=True)
        loaded = bpy.data.images.load(scene.render.filepath, check_existing=False)
        try:
            pixels = numpy.array(loaded.pixels[:]).reshape(600, 800, 4)
            y = round((.5 - .438) * 600)
            x0, x1 = round((.5 - .32) * 800), round((.5 + .32) * 800)
            zero = round(x0 + (x1 - x0) * 2/3)
            negative, neutral, positive = (pixels[y-2:y+2, x-2:x+2, :3].mean((0, 1))
                                           for x in (x0+5, zero, x1-5))
            # Standard view writes sRGB PNG values; compare with that transfer,
            # not the linear shader channel ratios.
            stops = metadata["scalar"]["stops"]
            for position, measured in zip((5/(x1-x0), 2/3, 1-5/(x1-x0)), (negative, neutral, positive)):
                linear = numpy.array([numpy.interp(position, [stop[0] for stop in stops],
                    [stop[1][channel] for stop in stops]) for channel in range(3)])
                expected = numpy.where(linear <= .0031308, 12.92 * linear,
                    1.055 * linear ** (1/2.4) - .055)
                numpy.testing.assert_allclose(measured, expected, atol=.025, rtol=0)
            metadata["synthetic_test_only"] = True
            metadata["pixel_probe_rgb"] = [value.tolist() for value in (negative, neutral, positive)]
        finally:
            bpy.data.images.remove(loaded)
        (output / (template + ".json")).write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    finally:
        _remove_objects(made)
    assert inventory() == baseline, (baseline, inventory())

# Match Blender's own camera frame in portrait/landscape and both sensor fits.
for aspect in (4/3, 3/4):
    scene.render.resolution_x, scene.render.resolution_y = (800, 600) if aspect > 1 else (600, 800)
    for camera_type in ("ORTHO", "PERSP"):
        camera.data.type = camera_type
        for fit in ("AUTO", "HORIZONTAL", "VERTICAL"):
            camera.data.sensor_fit = fit
            width, height, cx, cy = annotations._camera_plane(camera, aspect)
            points = camera.data.view_frame(scene=scene)
            projected = [point / -point.z if camera_type == "PERSP" else point for point in points]
            numpy.testing.assert_allclose([width, height], [max(point.x for point in projected)-min(point.x for point in projected),
                max(point.y for point in projected)-min(point.y for point in projected)], rtol=1e-6)

camera.data.sensor_fit = "AUTO"
with patch.object(annotations, "scalar_material", side_effect=RuntimeError("injected legend material failure")):
    try:
        annotations.create_render_annotations(plan, project, root, camera)
    except RuntimeError as error:
        assert "injected" in str(error)
    else:
        raise AssertionError("expected injected failure")
assert inventory() == baseline, (baseline, inventory())
_remove_objects(views)
print("RENDER_ANNOTATIONS_PASSED", output)
