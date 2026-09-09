"""Run with a private BLENDER_USER_RESOURCES; exercise actual Cycles shaders."""

import os
import sys
from pathlib import Path
from uuid import uuid4

import bpy
import numpy as np
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
private = Path(os.environ["BLENDER_USER_RESOURCES"]).resolve()
assert ROOT / ".agents" / "cache" in private.parents, "private test profile required"

from cbq_core.model import ArrayData
from cbq_core.model import DatasetStatus
from cbq_core.model import Grid3D
from ChemBlender.grid_volume import create_grid_volume
from ChemBlender.scientific_materials import flat_material, scalar_material, volume_material

scene = bpy.context.scene
for obj in tuple(scene.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
scene.render.engine = "CYCLES"
scene.cycles.samples = 32
scene.cycles.use_denoising = False
scene.render.resolution_x = 160
scene.render.resolution_y = 120
scene.render.resolution_percentage = 100
scene.view_settings.view_transform = "Standard"
scene.view_settings.look = "None"
scene.view_settings.exposure = 0
scene.view_settings.gamma = 1
world = bpy.data.worlds.new("Private shader test")
world.use_nodes = True
world.node_tree.nodes.get("Background").inputs[0].default_value = (.01, .01, .01, 1.)
scene.world = world

camera_data = bpy.data.cameras.new("Camera")
camera = bpy.data.objects.new("Camera", camera_data)
scene.collection.objects.link(camera)
camera.location = (0., -7., 0.)
camera.rotation_euler = (Vector((0., 0., 0.)) - camera.location).to_track_quat('-Z', 'Y').to_euler()
camera_data.type = "ORTHO"
camera_data.ortho_scale = 5.6
scene.camera = camera
light_data = bpy.data.lights.new("Light", "AREA")
light_data.energy, light_data.shape, light_data.size = 1500., "DISK", 5.
light = bpy.data.objects.new("Light", light_data)
scene.collection.objects.link(light)
light.location = (0., -3., 3.)
light.rotation_euler = (-light.location).to_track_quat('-Z', 'Y').to_euler()

axis = np.linspace(-2., 2., 41)
x, y, z = np.meshgrid(axis, axis, axis, indexing="ij")
values = np.exp(-4 * ((x - .85)**2 + y*y + z*z)) - np.exp(-4 * ((x + .85)**2 + y*y + z*z))
grid = Grid3D(id=uuid4(), revision="material-test", semantic_role="spin_density",
              domain="grid", data=ArrayData(values, ("x", "y", "z"), "electron_per_cubic_angstrom"),
              status=DatasetStatus.COMPLETE, source_calculation=None, provenance_ids=(),
              origin=(-2., -2., -2.), step_vectors=((.1, 0, 0), (0, .1, 0), (0, 0, .1)),
              coordinate_unit="angstrom")
cache = private.parent / "material-render"
cache.mkdir(exist_ok=True)
volume = create_grid_volume(grid, cache, collection=scene.collection)
material = volume_material("Signed", signed=True, density_scale=6.,
                           positive_color=(.01, .08, .9, 1.), negative_color=(.9, .03, .01, 1.))
volume.data.materials.append(material)
assert len([n for n in material.node_tree.nodes if n.type == "PRINCIPLED_VOLUME"]) == 2
assert len([n for n in material.node_tree.nodes if n.type == "MATH" and n.operation == "MAXIMUM"]) == 2
scene.render.filepath = str(cache / "signed-cloud.png")
bpy.ops.render.render(write_still=True)
rendered = bpy.data.images.load(scene.render.filepath, check_existing=False)
pixels = np.array(rendered.pixels[:]).reshape(120, 160, 4)
left, right = pixels[30:90, 30:75, :3], pixels[30:90, 85:130, :3]
assert left[..., 0].sum() > left[..., 2].sum() * 1.2, left.mean((0, 1))
assert right[..., 2].sum() > right[..., 0].sum() * 1.2, right.mean((0, 1))
assert np.array_equal(values, grid.data.values)

# Emission transfer and legend expose one true-zero ramp under both illumination levels.
scalar = scalar_material("NCI", -2., 1., colormap="nci", attribute_name="value")
ramp = next(n for n in scalar.node_tree.nodes if n.type == "VALTORGB")
assert abs(ramp.color_ramp.elements[1].position - 2/3) < 1e-6
assert scalar["cb_quantitative_color"] is True
assert flat_material("Axis", (.1, .1, .1, 1.))["cb_quantitative_color"] is True
print("SCIENTIFIC_MATERIALS_PASSED", scene.render.filepath)
