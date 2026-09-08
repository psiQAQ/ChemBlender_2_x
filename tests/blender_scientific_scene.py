"""Private-profile native checks for independent views, rebuild and rollback."""

import os
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ChemBlender.core import ImportBatch, QCProject, builtin_scene_presets, plan_scene_preset
from ChemBlender.scene_preset_view import apply_scene_preset, scene_view_objects, _remove_objects
from ChemBlender.ui.view_cache import scene_plan_from_view, rebuild_scene_view
from tests.test_periodic_electronic_model import periodic_structure, band_structure, density_of_states


def inventory():
    return {name: {block.as_pointer() for block in getattr(bpy.data, name)}
            for name in ("objects", "meshes", "curves", "materials", "node_groups")}


def run():
    private = Path(os.environ.get("BLENDER_USER_RESOURCES", "")).resolve()
    assert ROOT / ".agents" / "cache" in private.parents
    structure = periodic_structure()
    band, dos = band_structure(structure.id), density_of_states(structure.id)
    project = QCProject(uuid4(), "0.2")
    project.commit(ImportBatch(structures=(structure,), datasets=(band, dos)))
    plan = plan_scene_preset(builtin_scene_presets()["band_structure"], project, {"band": band.id}, {})
    baseline = inventory()
    first = apply_scene_preset(plan, project)[0]
    second = apply_scene_preset(plan, project)[0]
    assert first["cb_scene_render_identity"] == second["cb_scene_render_identity"]
    assert first["cb_view_instance_id"] != second["cb_view_instance_id"]
    assert len(scene_view_objects(first)) > 1
    assert scene_plan_from_view(first, project) == plan
    first.location = (4., 3., 2.)
    first.rotation_euler = (.2, .4, .1)
    bpy.context.view_layer.update()
    original_matrix = first.matrix_world.copy()
    annotation = bpy.data.objects.new("User annotation", None)
    bpy.context.collection.objects.link(annotation)
    annotation.parent = first.children[0]
    annotation.location = (1., 2., 3.)
    bpy.context.view_layer.update()
    annotation_matrix = annotation.matrix_world.copy()
    with patch("ChemBlender.scene_preset_view.create_band_structure_plot", side_effect=RuntimeError("injected")):
        try:
            rebuild_scene_view(first, project)
        except RuntimeError as error:
            assert str(error) == "injected"
        else:
            raise AssertionError("failure was swallowed")
    assert first.name in bpy.data.objects and first["cb_view_stale"]
    assert second.name in bpy.data.objects
    instance = first["cb_view_instance_id"]
    rebuilt = rebuild_scene_view(first, project)
    bpy.context.view_layer.update()
    assert rebuilt["cb_view_instance_id"] == instance
    assert not rebuilt["cb_view_stale"]
    assert np.allclose(rebuilt.matrix_world, original_matrix)
    assert np.allclose(annotation.matrix_world, annotation_matrix)
    assert annotation.parent is None
    _remove_objects(scene_view_objects(rebuilt))
    _remove_objects(scene_view_objects(second))
    bpy.data.objects.remove(annotation, do_unlink=True)
    assert inventory() == baseline, (inventory(), baseline)
    print("SCIENTIFIC_SCENE_PASS")


if __name__ == "__main__":
    run()
