"""Private Blender/Cycles regression for per-View canonical structure materials."""

import os
from dataclasses import replace
from pathlib import Path
import sys
from unittest.mock import patch
from uuid import uuid4

import bpy
import numpy as np
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ChemBlender import scientific_materials as material_view
from cbq_core.model import ArrayData
from cbq_core.model import AtomicProperty
from cbq_core.model import CategoricalData
from cbq_core.model import DatasetStatus
from cbq_core.model import Structure
from ChemBlender.dataset_view import apply_atomic_scalar, write_vector_view
from ChemBlender.views.structure import create_structure_view

private = Path(os.environ["BLENDER_USER_RESOURCES"]).resolve()
assert private.is_relative_to(ROOT / ".agents/cache")
private.mkdir(parents=True, exist_ok=True)
scene = bpy.context.scene
for obj in tuple(scene.objects):
    obj.hide_render = True


def inventory():
    return {key: {item.as_pointer() for item in getattr(bpy.data, key)}
            for key in ("objects", "meshes", "node_groups", "materials")}


def attributes(obj):
    scalar = np.empty(2)
    color = np.empty(8)
    obj.data.attributes["cbq_atom_scalar"].data.foreach_get("value", scalar)
    obj.data.attributes["colour"].data.foreach_get("color", color)
    return scalar, color


structure = Structure(id=uuid4(), revision="structure", atomic_numbers=(1, 1),
    coordinates=ArrayData(np.array([[-1., 0., 0.], [1., 0., 0.]]), ("atom", "xyz"), "angstrom"))
scalar = AtomicProperty(id=uuid4(), revision="scalar", semantic_role="partial_charge", domain="atom",
    data=ArrayData(np.array([-1., 1.]), ("atom",), "elementary_charge"),
    status=DatasetStatus.COMPLETE, source_calculation=None, provenance_ids=(), structure_id=structure.id)
first = create_structure_view(structure)
apply_atomic_scalar(first, scalar, display_min=-1, display_max=1, colormap="coolwarm")
assert first.data.attributes.get("cbq_scientific_atom_color") is None
write_vector_view(first, np.array([[0., 0., 1.5], [0., 0., 1.5]]),
    dataset_id=uuid4(), revision="vectors", semantic_role="force", unit="hartree_per_bohr")
second = first.copy()
second.name = "Shared scientific view"
scene.collection.objects.link(second)
second.hide_render = True
shared_mesh = second.data
shared_groups = tuple(mod.node_group for mod in second.modifiers)
shared_group_content = tuple((len(group.nodes), len(group.links)) for group in shared_groups)
original_values = attributes(first)
material_view.apply_structure_materials(first, quantitative=True, shaded=True,
    vector_color=(1., .72, .04, 1.))
assert first.data != shared_mesh and second.data == shared_mesh
assert tuple(mod.node_group for mod in second.modifiers) == shared_groups
assert tuple((len(group.nodes), len(group.links)) for group in shared_groups) == shared_group_content
for before, after in zip(original_values, attributes(first)):
    np.testing.assert_array_equal(before, after)
assert scalar.data.values.tolist() == [-1., 1.]
atom_material = next(mat for mat in first.data.materials if mat.get("cb_structure_material_role") == "atom_colors")
vector_material = next(mat for mat in first.data.materials if mat.get("cb_structure_material_role") == "vector_arrows")
assert atom_material["cb_quantitative_color"]
assert any(node.bl_idname == "ShaderNodeEmission" for node in atom_material.node_tree.nodes)
assert not any(node.bl_idname == "ShaderNodeBsdfPrincipled" for node in atom_material.node_tree.nodes)
assert any(node.bl_idname == "ShaderNodeAttribute" and node.attribute_name == "cbq_scientific_atom_color" for node in atom_material.node_tree.nodes)
for modifier in first.modifiers:
    group = modifier.node_group
    if group.get("cbq_contract") == "vector_arrow_v1":
        assert group.nodes["ChemBlender Scientific Vector Material"].inputs["Material"].default_value == vector_material
    if group.get("cbq_contract") == "structure_ball_stick_v1":
        assert group.nodes.get("ChemBlender Vector Instances") is not None
        assert group.nodes["ChemBlender Scientific Atom Material"].inputs["Material"].default_value == atom_material
material_view.apply_structure_materials(second, quantitative=False, shaded=True,
    vector_color=(.02, 1., .3, 1.))
assert first.data.materials[0] != second.data.materials[0]
assert any(node.bl_idname == "ShaderNodeBsdfPrincipled" for node in second.data.materials[0].node_tree.nodes)
assert any(node.bl_idname == "ShaderNodeEmission" for node in first.data.materials[0].node_tree.nodes)
# Repeated changes retire only the previous owned materials and wrappers.
before_count = {key: len(value) for key, value in inventory().items()}
material_view.apply_structure_materials(first, quantitative=True, shaded=False)
assert before_count == {key: len(value) for key, value in inventory().items()}
# A failure after the atom branch was prepared leaves data and shared groups intact.
before = inventory()
mesh = first.data
groups = tuple(mod.node_group for mod in first.modifiers)
with patch.object(material_view, "_bind_vector_group", side_effect=RuntimeError("forced vector failure")):
    try:
        material_view.apply_structure_materials(first, quantitative=True)
    except RuntimeError as error:
        assert "forced" in str(error)
    else:
        raise AssertionError("expected rollback")
assert inventory() == before
assert first.data == mesh and tuple(mod.node_group for mod in first.modifiers) == groups

# The native biological fallback has points instead of a ball-and-stick wrapper.
# Default publication Views must still receive independent template materials.
from cbq_core.model import QCProject
from cbq_core.scene_preset import builtin_scene_presets
from cbq_core.scene_preset import plan_scene_preset
from chemblender_prepare.core.formats.pdb import parse_pdb
from ChemBlender.scene_preset_view import apply_scene_preset

batch = parse_pdb(ROOT / "tests/fixtures/pdb/altloc.pdb")
project = QCProject(id=uuid4(), schema_version="0.1")
project.commit(batch)
biological = batch.structures[0]
source_coordinates = np.asarray(biological.coordinates.values).copy()
biological_views = []
for template in ("research", "teaching"):
    plan = plan_scene_preset(builtin_scene_presets()["structure_publication"], project,
        {"structure": biological.id}, {"template": template})
    root = apply_scene_preset(plan, project)[0]
    root.hide_render = True
    biological_views.append(root)
    group = root.modifiers[0].node_group
    assert group["cbq_contract"] == "biological_points_v1"
    assert group.nodes["ChemBlender Scientific Atom Material"].inputs["Material"].default_value == root.data.materials[0]
    evaluated = root.evaluated_get(bpy.context.evaluated_depsgraph_get())
    evaluated_mesh = evaluated.to_mesh()
    try:
        visible = sum(item.value for item in root.data.attributes["cbq_visible"].data)
        assert len(evaluated_mesh.polygons) == visible * 20
        assert all(evaluated_mesh.materials[face.material_index].original == root.data.materials[0]
                   for face in evaluated_mesh.polygons)
    finally:
        evaluated.to_mesh_clear()
np.testing.assert_array_equal(biological.coordinates.values, source_coordinates)
bio = biological_views[0]
sibling = bio.copy()
sibling.name = "Shared biological points"
scene.collection.objects.link(sibling)
biological_views.append(sibling)
shared_mesh = sibling.data
shared_group = sibling.modifiers[0].node_group
shared_material = sibling.data.materials[0]
material_view.apply_structure_materials(bio, shaded=False)
assert sibling.data == shared_mesh and sibling.modifiers[0].node_group == shared_group
assert sibling.data.materials[0] == shared_material
assert bio.data != shared_mesh and bio.modifiers[0].node_group != shared_group
assert any(node.bl_idname == "ShaderNodeEmission" for node in bio.data.materials[0].node_tree.nodes)
assert any(node.bl_idname == "ShaderNodeBsdfPrincipled" for node in sibling.data.materials[0].node_tree.nodes)
before_count = {key: len(value) for key, value in inventory().items()}
material_view.apply_structure_materials(bio, shaded=False)
assert before_count == {key: len(value) for key, value in inventory().items()}
# A malformed points output fails before assigning any live mesh or wrapper.
before = inventory()
original_binder = material_view._bind_atom_group
mesh, group = bio.data, bio.modifiers[0].node_group
def broken_points_output(candidate, material):
    output = next(node for node in candidate.nodes if node.bl_idname == "NodeGroupOutput")
    candidate.links.remove(output.inputs["Geometry"].links[0])
    candidate.nodes.remove(candidate.nodes["ChemBlender Scientific Atom Material"])
    original_binder(candidate, material)
with patch.object(material_view, "_bind_atom_group", side_effect=broken_points_output):
    try:
        material_view.apply_structure_materials(bio)
    except ValueError as error:
        assert "biological point output" in str(error)
    else:
        raise AssertionError("expected biological material rollback")
assert inventory() == before
assert bio.data == mesh and bio.modifiers[0].node_group == group

scene.render.engine = "CYCLES"
scene.cycles.samples = 8
scene.cycles.use_denoising = False
scene.cycles.use_adaptive_sampling = False
scene.cycles.seed = 7
scene.render.resolution_x = 160
scene.render.resolution_y = 100
scene.render.resolution_percentage = 100
scene.view_settings.view_transform = "Standard"
scene.view_settings.look = "None"
scene.view_settings.exposure = 0
scene.view_settings.gamma = 1
world = bpy.data.worlds.new("Private atom shader world")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (.005, .005, .005, 1.)
scene.world = world
camera_data = bpy.data.cameras.new("Scientific camera")
camera_data.type = "ORTHO"
camera_data.ortho_scale = 4.
camera = bpy.data.objects.new("Scientific camera", camera_data)
scene.collection.objects.link(camera)
camera.location = (0., -7., .7)
camera.rotation_euler = (Vector((0., 0., .7)) - camera.location).to_track_quat('-Z', 'Y').to_euler()
scene.camera = camera
light_data = bpy.data.lights.new("Scientific area", "AREA")
light_data.size = 4.
light = bpy.data.objects.new("Scientific area", light_data)
scene.collection.objects.link(light)
light.location = (0., -3., 3.)
light.rotation_euler = (-light.location).to_track_quat('-Z', 'Y').to_euler()


def render(name, energy):
    light_data.energy = energy
    scene.render.filepath = str(private / name)
    bpy.ops.render.render(write_still=True)
    image = bpy.data.images.load(scene.render.filepath, check_existing=False)
    values = np.asarray(image.pixels[:]).reshape((100, 160, 4))
    bpy.data.images.remove(image)
    return values


low = render("quantitative-dark.png", 0.)
high = render("quantitative-lit.png", 2500.)
np.testing.assert_allclose(low, high, atol=.01, rtol=0)
blue = (low[..., 2] > low[..., 0] * 1.4) & (low[..., 2] > .3)
red = (low[..., 0] > low[..., 2] * 1.4) & (low[..., 0] > .3)
yellow = (low[..., 0] > .6) & (low[..., 1] > .5) & (low[..., 2] < .3)
assert blue.sum() > 30 and red.sum() > 30 and yellow.sum() > 30, (blue.sum(), red.sum(), yellow.sum())
# Existing Browser scalar/category actions update the material's real input,
# including after the per-View material has already been bound.
bound_material = first.data.materials[0]
bound_group = first.modifiers[0].node_group
shader_attribute = next(node.attribute_name for node in bound_material.node_tree.nodes
                        if node.bl_idname == "ShaderNodeAttribute")
def assert_shader_colors():
    actual, expected = np.empty(8), np.empty(8)
    first.data.attributes[shader_attribute].data.foreach_get("color", actual)
    first.data.attributes["colour"].data.foreach_get("color", expected)
    np.testing.assert_array_equal(actual, expected)
    assert first.data.materials[0] == bound_material
    assert first.modifiers[0].node_group == bound_group

flipped = replace(scalar, id=uuid4(), revision="flipped",
    data=ArrayData(np.array([1., -1.]), ("atom",), "elementary_charge"))
apply_atomic_scalar(first, flipped, display_min=-1, display_max=1, colormap="coolwarm")
assert_shader_colors()
changed = render("scalar-updated.png", 0.)
changed_blue = (changed[..., 2] > changed[..., 0] * 1.4) & (changed[..., 2] > .3)
assert changed_blue.sum() > 30
assert abs(np.nonzero(changed_blue)[1].mean() - np.nonzero(blue)[1].mean()) > 20
category = replace(scalar, id=uuid4(), revision="category", semantic_role="substructure_name",
    data=CategoricalData(ArrayData(np.array([0, 1]), ("atom",), "dimensionless"), ("A", "B"), -1))
apply_atomic_scalar(first, category, presentation_only=True)
assert first.data.attributes.get("cbq_atom_scalar") is None
assert_shader_colors()
categorical_image = render("category-updated.png", 0.)
changed_red = (changed[..., 0] > changed[..., 2] * 1.4) & (changed[..., 0] > .3)
assert np.abs(categorical_image - changed)[changed_blue | changed_red, :3].mean() > .1
np.testing.assert_array_equal(scalar.data.values, [-1., 1.])
np.testing.assert_array_equal(category.data.codes.values, [0, 1])
for before, after in zip(original_values, attributes(second)):
    np.testing.assert_array_equal(before, after)
from ChemBlender.scene_preset_view import _remove_objects
all_views = (first, second, *biological_views)
owned_groups = tuple(mod.node_group for obj in all_views for mod in obj.modifiers)
owned_materials = tuple(mat for obj in all_views for mat in obj.data.materials)
_remove_objects(all_views)
for block in (*owned_groups, *owned_materials):
    try:
        assert block.users > 0, "unused owned resource leaked"
    except ReferenceError:
        pass
print("STRUCTURE_MATERIALS_PASSED: isolated Views, biological point templates, unlit quantitative colors, arrow colors, shared assets, rollback, cleanup, Cycles lighting invariance")
