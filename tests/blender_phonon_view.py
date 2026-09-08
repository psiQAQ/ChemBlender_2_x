"""Private-profile Blender checks for phonon phases and canonical vibration units."""

import math
import os
from dataclasses import replace
from pathlib import Path
import sys
from unittest.mock import patch

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ChemBlender.core import ArrayData
from ChemBlender import phonon_view, vibration_view
from ChemBlender.views.structure import create_structure_view, remove_structure_view
from tests.test_periodic_electronic_model import periodic_structure
from tests.test_phonon_view import normalized_modes
from tests.test_vibration_model import mode_set


def coordinates(obj):
    values = np.empty(len(obj.data.vertices) * 3)
    obj.data.vertices.foreach_get("co", values)
    return values.reshape((-1, 3))


def check_phonon():
    structure = periodic_structure()
    modes = normalized_modes(structure)
    scientific_before = (structure.coordinates.values.tobytes(), modes.eigenvectors.values.tobytes())
    scale = .529177210903
    bohr = replace(structure,
        coordinates=ArrayData(structure.coordinates.values / scale, ("atom", "xyz"), "bohr"),
        cell=ArrayData(structure.cell.values / scale, ("cell_vector", "xyz"), "bohr"))
    first = phonon_view.create_phonon_view(structure, modes,
        qpoint_index=0, mode_index=0, repetitions=(2, 2, 2))
    second = phonon_view.create_phonon_view(bohr, modes,
        qpoint_index=0, mode_index=0, repetitions=(2, 2, 2))
    assert len(first.data.vertices) == 16
    np.testing.assert_allclose(coordinates(first), coordinates(second))
    assert first["cb_scientific_component"] == "phonon_atoms"
    assert first.data["cb_scientific_owned"]
    assert all(child.get("cb_scientific_component") for child in first.children_recursive)
    bpy.context.view_layer.update()
    evaluated = first.evaluated_get(bpy.context.evaluated_depsgraph_get())
    assert len(evaluated.evaluated_geometry().instance_references()) > 0
    first.location = (2, 3, 4)
    first.rotation_euler = (.2, .3, .4)
    first.scale = (1.2, .8, 1.5)
    bpy.context.view_layer.update()
    world = first.matrix_world.copy()
    phonon_view.apply_phonon_phase(first, structure, modes, math.pi / 2)
    expected = phonon_view._display_frame(structure, modes, (2, 2, 2), 0, 0, math.pi / 2, .4)[-1]
    np.testing.assert_allclose(coordinates(first), expected, rtol=1e-6, atol=1e-6)
    assert first.matrix_world == world
    assert scientific_before == (structure.coordinates.values.tobytes(), modes.eigenvectors.values.tobytes())
    shared = bpy.data.objects.new("phonon user mesh copy", first.data)
    bpy.context.scene.collection.objects.link(shared)
    unchanged = coordinates(shared).copy()
    phonon_view.apply_phonon_phase(first, structure, modes, math.pi)
    assert first.data != shared.data
    np.testing.assert_array_equal(coordinates(shared), unchanged)
    bpy.data.objects.remove(shared, do_unlink=True)
    previous = coordinates(first).copy()
    try:
        phonon_view.apply_phonon_phase(first, structure, replace(modes, revision="updated"), 0)
    except ValueError as error:
        assert "revision" in str(error)
    else:
        raise AssertionError("stale source must reject phase update")
    np.testing.assert_array_equal(coordinates(first), previous)
    profile = Path(os.environ["BLENDER_USER_RESOURCES"]).resolve()
    assert profile.is_relative_to(ROOT / ".agents/cache")
    profile.mkdir(parents=True, exist_ok=True)
    saved = profile / "phonon-view.blend"
    name = first.name
    bpy.ops.wm.save_as_mainfile(filepath=str(saved), check_existing=False)
    bpy.ops.wm.open_mainfile(filepath=str(saved))
    restored = bpy.data.objects[name]
    phonon_view.apply_phonon_phase(restored, structure, modes, 0)
    expected = phonon_view._display_frame(structure, modes, (2, 2, 2), 0, 0, 0, .4)[-1]
    np.testing.assert_allclose(coordinates(restored), expected, rtol=1e-6, atol=1e-6)
    # This tests the durable scientific-owned contract used by the shared dispatcher.
    from ChemBlender.scene_preset_view import _remove_objects
    _remove_objects(tuple(obj for obj in bpy.data.objects if obj.get("cb_phonon_contract")))


def check_vibration_units():
    structure = periodic_structure()
    scale = .529177210903
    bohr = replace(structure,
        coordinates=ArrayData(structure.coordinates.values / scale, ("atom", "xyz"), "bohr"),
        cell=ArrayData(structure.cell.values / scale, ("cell_vector", "xyz"), "bohr"))
    displacement = np.zeros((2, 2, 3))
    displacement[0, 0, 0] = 1.
    modes = mode_set(structure.id,
        displacements=ArrayData(displacement, ("mode", "atom", "xyz"), "angstrom"))
    obj = create_structure_view(bohr)
    try:
        vibration_view.create_vibration_view(obj, modes, mode_index=0, arrow_scale=2.)
        vibration_view.apply_vibration_phase(obj, math.pi / 2, amplitude_scale=.5)
        expected = structure.coordinates.values.copy()
        expected[0, 0] += .5
        np.testing.assert_allclose(coordinates(obj), expected)
        try:
            replace(modes, displacements=ArrayData(displacement, modes.displacements.dims, "bohr"))
        except ValueError as error:
            assert "angstrom" in str(error)
        else:
            raise AssertionError("noncanonical vibration unit must reject")
    finally:
        remove_structure_view(obj)


def check_rollback():
    structure = periodic_structure()
    modes = normalized_modes(structure)
    before = {obj.as_pointer() for obj in bpy.data.objects}
    meshes = {item.as_pointer() for item in bpy.data.meshes}
    with patch.object(phonon_view, "_attribute", side_effect=RuntimeError("forced attribute failure")):
        try:
            phonon_view.create_phonon_view(structure, modes, qpoint_index=0, mode_index=0)
        except RuntimeError as error:
            assert "forced" in str(error)
        else:
            raise AssertionError("forced failure must propagate")
    assert before == {obj.as_pointer() for obj in bpy.data.objects}
    assert meshes == {item.as_pointer() for item in bpy.data.meshes}


assert bpy.app.version[:2] == (5, 1)
check_phonon()
check_vibration_units()
check_rollback()
print("PHONON_VIEW_PASSED: supercell, complex phases, Angstrom/bohr, shared mesh, stale source, save/reopen, vibration units, rollback")
