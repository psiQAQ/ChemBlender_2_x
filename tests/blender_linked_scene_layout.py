"""Private native linked-layout, public selection/rebuild and ownership checks."""

import argparse
from dataclasses import replace
import os
from pathlib import Path
import sys
from unittest.mock import patch
from uuid import uuid4

import bpy
import numpy as np
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))


def inventory():
    return {name: {block.as_pointer() for block in getattr(bpy.data, name)}
            for name in ("objects", "meshes", "curves", "materials", "node_groups")}


def assert_separation(left, right):
    from ChemBlender.scene_preset_view import _owned_components

    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    right_objects = set(_owned_components((right,)))
    left_objects = set(_owned_components((left,))) - right_objects

    def extent(objects):
        coordinates = [obj.evaluated_get(depsgraph).matrix_world @ Vector(corner)
                       for obj in objects if obj.type in {"MESH", "CURVE", "FONT"}
                       for corner in obj.evaluated_get(depsgraph).bound_box]
        return min(p.x for p in coordinates), max(p.x for p in coordinates)

    assert extent(right_objects)[0] - extent(left_objects)[1] >= .999, (extent(left_objects), extent(right_objects))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--existing-libraries", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    assert bpy.app.background
    assert ROOT / ".agents/cache" in Path(os.environ["BLENDER_USER_RESOURCES"]).resolve().parents
    libraries = args.existing_libraries.resolve(strict=True)
    assert ROOT / ".agents/cache" in libraries.parents
    sys.path.append(str(libraries))

    import ChemBlender
    from ChemBlender import scene_preset_view as views
    from ChemBlender.core import (ArrayData, ImportBatch, SpectrumKind, SpectrumProfile,
        builtin_scene_presets, derive_electronic_spectrum, derive_vibrational_spectrum, plan_scene_preset)
    from ChemBlender.ui import session as session_ui
    from tests.test_excited_state_model import state_set
    from tests.test_periodic_electronic_model import periodic_structure, band_structure, density_of_states
    from tests.test_vibration_model import structure, mode_set

    ChemBlender.register()
    try:
        session = session_ui.get_scene_session(bpy.context.scene)
        project = session.project
        molecule = structure()
        molecule = replace(molecule, coordinates=ArrayData(np.asarray(((3., -2., .5), (4., -2., .5))),
                                                           ("atom", "xyz"), "angstrom"))
        modes = mode_set(molecule.id, displacements=ArrayData(np.full((2, 2, 3), .2),
                                                              ("mode", "atom", "xyz"), "angstrom"))
        states = state_set(molecule.id)
        periodic = periodic_structure()
        band, dos = band_structure(periodic.id), density_of_states(periodic.id)
        project.commit(ImportBatch(structures=(molecule, periodic), datasets=(modes, states, band, dos)))
        vibration = derive_vibrational_spectrum(modes, kind=SpectrumKind.IR, profile=SpectrumProfile.STICK)
        electronic = derive_electronic_spectrum(states, kind=SpectrumKind.UV_VIS, profile=SpectrumProfile.STICK)
        project.commit(vibration)
        project.commit(electronic)
        spectra = (vibration.datasets[0], electronic.datasets[0])
        source_arrays = [molecule.coordinates.values, modes.data.values, modes.displacements.values,
                         states.data.values, states.oscillator_strengths.values, band.data.values,
                         band.distances.values, dos.data.values, dos.energies.values]
        source_arrays.extend(array.values for spectrum in spectra for array in (spectrum.axis, spectrum.data))
        original = tuple(array.tobytes() for array in source_arrays)
        specs = (
            ("vibration_spectrum_linked", {"structure": molecule.id, "modes": modes.id, "spectrum": spectra[0].id},
             {"selection_index": 1, "phase": .7, "amplitude_scale": .4}),
            ("electronic_spectrum_linked", {"structure": molecule.id, "states": states.id, "spectrum": spectra[1].id},
             {"selection_index": 1}),
            ("band_dos_linked", {"band": band.id, "dos": dos.id}, {}),
        )
        # Load reusable canonical assets before counting owned resources.
        warm = views.apply_scene_preset(plan_scene_preset(builtin_scene_presets()[specs[0][0]], project,
                                                         specs[0][1], specs[0][2]), project)
        views._remove_objects(warm)
        baseline = inventory()
        for kind, bindings, settings in specs:
            for template in ("research", "teaching"):
                plan = plan_scene_preset(builtin_scene_presets()[kind], project, bindings,
                                         {**settings, "template": template})
                left, right = views.apply_scene_preset(plan, project)
                try:
                    assert_separation(left, right)
                    np.testing.assert_allclose(left.matrix_world, np.eye(4), atol=1e-7)
                    assert right.parent == left
                    assert right["cb_view_instance_id"] == left["cb_view_instance_id"]
                    assert right["cb_plot_width"] == 8 and right["cb_plot_height"] == 5
                    assert right["cb_scene_bindings_json"] == left["cb_scene_bindings_json"]
                    assert right["cb_dataset_id"] == str(bindings.get("spectrum", bindings.get("dos")))
                    if kind == "band_dos_linked":
                        limits = (min(band.data.values.min() - band.fermi_energy, dos.energies.values.min() - dos.fermi_energy),
                                  max(band.data.values.max() - band.fermi_energy, dos.energies.values.max() - dos.fermi_energy))
                        np.testing.assert_allclose(left["cb_plot_y_range"], limits)
                        np.testing.assert_allclose(right["cb_plot_y_range"], limits)
                        assert left["cb_plot_y_unit"] == right["cb_plot_y_unit"] == "electron_volt"
                        assert left["cb_plot_x_unit"] == band.distances.unit
                        assert right["cb_plot_x_unit"] == dos.data.unit
                        assert abs(right.location.y) < 1e-7
                    for plot in ((left, right) if kind == "band_dos_linked" else (right,)):
                        expected_color = (.1, .6, 1., 1.) if template == "teaching" else (.015, .21, .48, 1.)
                        shader = next(n for n in plot.data.materials[0].node_tree.nodes if n.bl_idname == "ShaderNodeEmission")
                        np.testing.assert_allclose(shader.inputs["Color"].default_value, expected_color, atol=1e-7)
                        axis = next(child for child in plot.children if child.get("cb_scientific_component") == "plot_axes")
                        expected_axis = (.78, .84, .92, 1.) if template == "teaching" else (.045, .06, .08, 1.)
                        shader = next(n for n in axis.data.materials[0].node_tree.nodes if n.bl_idname == "ShaderNodeEmission")
                        np.testing.assert_allclose(shader.inputs["Color"].default_value, expected_axis, atol=1e-7)
                    if kind != "band_dos_linked":
                        assert left["cb_selection_index"] == 1
                        assert left["cb_selection_dataset_id"] == str(modes.id if kind.startswith("vibration") else states.id)
                        expected_positions = molecule.coordinates.values.copy()
                        if kind.startswith("vibration"):
                            expected_positions += modes.displacements.values[1] * (.4 * np.sin(.7))
                            assert left["cb_vibration_phase"] == .7
                        np.testing.assert_allclose([v.co[:] for v in left.data.vertices], expected_positions, atol=1e-6)
                    identity = left["cb_view_instance_id"]
                    session.active_view_object_name = right.name
                    bpy.context.view_layer.objects.active = right
                    right.select_set(True)
                    assert bpy.ops.chemblender.scientific_view(action="LOAD") == {"FINISHED"}
                    assert bpy.context.scene.chemblender_scientific_view.template == template
                    assert bpy.ops.chemblender.scientific_view(action="REBUILD") == {"FINISHED"}
                    left = bpy.context.active_object
                    assert left["cb_view_instance_id"] == identity
                    right = next(child for child in left.children if child.get("cb_plot_contract"))
                    assert_separation(left, right)
                    assert tuple(array.tobytes() for array in source_arrays) == original
                finally:
                    views._remove_objects(views.scene_view_objects(left))
                assert inventory() == baseline, (kind, template, inventory(), baseline)
                print("LINKED_LAYOUT_PASSED", kind, template, flush=True)
        plan = plan_scene_preset(builtin_scene_presets()[specs[2][0]], project, specs[2][1], {"template": "teaching"})
        with patch.object(views, "_place_linked_plot", side_effect=RuntimeError("injected layout failure")):
            try:
                views.apply_scene_preset(plan, project)
            except RuntimeError as error:
                assert "injected" in str(error)
            else:
                raise AssertionError("expected injected layout failure")
        assert inventory() == baseline
        print("LINKED_LAYOUT_ROLLBACK_PASSED", flush=True)
    finally:
        ChemBlender.unregister()
    print("LINKED_SCENE_LAYOUT_PASSED", flush=True)


if __name__ == "__main__":
    main()
