import json
import unittest
from dataclasses import replace
from uuid import uuid4

import numpy

from ChemBlender.core import (
    ArrayData,
    DatasetStatus,
    Grid3D,
    ImportBatch,
    QCProject,
    ScenePresetError,
    builtin_recipes,
    builtin_scene_presets,
    plan_scene_preset,
    scene_plan_document,
    scene_preset_document,
    scene_preset_from_document,
    scene_preset_for_recipe_view,
)
from tests.test_periodic_electronic_model import (
    band_structure,
    density_of_states,
    periodic_structure,
)
from tests.test_vibration_model import mode_set, structure
from tests.test_excited_state_model import state_set
from ChemBlender.core import (
    SpectrumKind,
    SpectrumProfile,
    derive_electronic_spectrum,
    derive_vibrational_spectrum,
)


def grid(structure_id, role="electron_density", *, origin=(0.0, 0.0, 0.0)):
    return Grid3D(
        id=uuid4(),
        revision=f"{role}-r1",
        semantic_role=role,
        domain="grid",
        data=ArrayData(numpy.zeros((3, 3, 3)), ("x", "y", "z"), "electron_per_cubic_bohr"),
        status=DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(),
        origin=origin,
        step_vectors=((0.2, 0.0, 0.0), (0.0, 0.2, 0.0), (0.0, 0.0, 0.2)),
        coordinate_unit="bohr",
        structure_id=structure_id,
    )


class ScenePresetTests(unittest.TestCase):
    def test_builtin_presets_are_versioned_pure_data(self):
        presets = builtin_scene_presets()
        self.assertEqual(
            set(presets),
            {
                "band_dos_linked",
                "electronic_spectrum_linked",
                "property_on_surface",
                "signed_isosurface",
                "structure_publication",
                "vibration_spectrum_linked",
            },
        )
        for preset in presets.values():
            document = scene_preset_document(preset)
            json.dumps(document, allow_nan=False)
            self.assertEqual(document["version"], "1")
            self.assertNotIn("callable", repr(document).lower())
            self.assertEqual(scene_preset_from_document(document), preset)
            document["unexpected"] = True
            with self.assertRaises(ScenePresetError):
                scene_preset_from_document(document)

    def test_structure_plan_is_deterministic_and_revision_bound(self):
        reference = structure()
        project = QCProject(uuid4(), "0.1")
        project.commit(ImportBatch(structures=(reference,)))
        preset = builtin_scene_presets()["structure_publication"]

        first = plan_scene_preset(
            preset, project, {"structure": reference.id}, {}
        )
        second = plan_scene_preset(
            preset, project, {"structure": reference.id}, {}
        )
        self.assertEqual(scene_plan_document(first), scene_plan_document(second))
        self.assertEqual(len(first.render_identity), 64)
        self.assertEqual(dict(first.settings)["display_coordinate_unit"], "angstrom")

        project.structures[reference.id] = replace(reference, revision="changed")
        changed = plan_scene_preset(
            preset, project, {"structure": reference.id}, {}
        )
        self.assertNotEqual(first.render_identity, changed.render_identity)

    def test_signed_and_property_surface_validate_grid_contracts_and_settings(self):
        reference = structure()
        density = grid(reference.id)
        potential = grid(reference.id, "electrostatic_potential")
        project = QCProject(uuid4(), "0.1")
        project.commit(ImportBatch(structures=(reference,), datasets=(density, potential)))
        presets = builtin_scene_presets()

        signed = plan_scene_preset(
            presets["signed_isosurface"],
            project,
            {"grid": density.id},
            {"isovalue": 0.05},
        )
        self.assertEqual(dict(signed.settings)["negative_isovalue"], -0.05)
        with self.assertRaises(ScenePresetError):
            plan_scene_preset(
                presets["signed_isosurface"],
                project,
                {"grid": density.id},
                {"isovalue": -0.05},
            )

        mapped = plan_scene_preset(
            presets["property_on_surface"],
            project,
            {"surface_grid": density.id, "property_grid": potential.id},
            {"surface_isovalue": 0.001, "color_min": -0.1, "color_max": 0.1},
        )
        self.assertEqual(mapped.view_kind, "property_on_surface")
        shifted = replace(potential, id=uuid4(), origin=(0.1, 0.0, 0.0))
        shifted_project = QCProject(uuid4(), "0.1")
        shifted_project.commit(
            ImportBatch(structures=(reference,), datasets=(density, shifted))
        )
        with self.assertRaisesRegex(ScenePresetError, "affine"):
            plan_scene_preset(
                presets["property_on_surface"],
                shifted_project,
                {"surface_grid": density.id, "property_grid": shifted.id},
                {},
            )

    def test_vibration_spectrum_and_band_dos_require_linked_datasets(self):
        reference = structure()
        modes = mode_set(reference.id)
        spectrum_batch = derive_vibrational_spectrum(
            modes, kind=SpectrumKind.IR, profile=SpectrumProfile.STICK
        )
        spectrum = spectrum_batch.datasets[0]
        project = QCProject(uuid4(), "0.1")
        project.commit(ImportBatch(structures=(reference,), datasets=(modes,)))
        project.commit(spectrum_batch)
        plan = plan_scene_preset(
            builtin_scene_presets()["vibration_spectrum_linked"],
            project,
            {"structure": reference.id, "modes": modes.id, "spectrum": spectrum.id},
            {"selection_index": 1, "arrow_scale": 2.0},
        )
        self.assertEqual(dict(plan.settings)["selection_index"], 1)
        with self.assertRaises(ScenePresetError):
            plan_scene_preset(
                builtin_scene_presets()["vibration_spectrum_linked"],
                project,
                {"structure": reference.id, "modes": modes.id, "spectrum": spectrum.id},
                {"selection_index": 5},
            )

        periodic = periodic_structure()
        band = band_structure(periodic.id)
        dos = density_of_states(periodic.id)
        periodic_project = QCProject(uuid4(), "0.1")
        periodic_project.commit(
            ImportBatch(structures=(periodic,), datasets=(band, dos))
        )
        band_plan = plan_scene_preset(
            builtin_scene_presets()["band_dos_linked"],
            periodic_project,
            {"band": band.id, "dos": dos.id},
            {},
        )
        self.assertEqual(dict(band_plan.settings)["energy_reference"], "fermi_shifted")

        other_structure = periodic_structure()
        other = replace(dos, id=uuid4(), structure_id=other_structure.id)
        invalid_project = QCProject(uuid4(), "0.1")
        invalid_project.commit(
            ImportBatch(
                structures=(periodic, other_structure), datasets=(band, other)
            )
        )
        with self.assertRaisesRegex(ScenePresetError, "one structure"):
            plan_scene_preset(
                builtin_scene_presets()["band_dos_linked"],
                invalid_project,
                {"band": band.id, "dos": other.id},
                {},
            )

    def test_recipe_views_map_only_to_supported_presets(self):
        recipes = builtin_recipes()
        self.assertEqual(
            scene_preset_for_recipe_view(recipes["wavefunction_molecular_orbital_grid"]),
            "signed_isosurface",
        )
        self.assertEqual(
            scene_preset_for_recipe_view(recipes["vibrational_ir_spectrum"]),
            "vibration_spectrum_linked",
        )
        self.assertEqual(
            scene_preset_for_recipe_view(recipes["tddft_uvvis"]),
            "electronic_spectrum_linked",
        )

        reference = structure()
        states = state_set(reference.id)
        spectrum_batch = derive_electronic_spectrum(
            states, kind=SpectrumKind.UV_VIS, profile=SpectrumProfile.STICK
        )
        spectrum = spectrum_batch.datasets[0]
        project = QCProject(uuid4(), "0.1")
        project.commit(ImportBatch(structures=(reference,), datasets=(states,)))
        project.commit(spectrum_batch)
        plan = plan_scene_preset(
            builtin_scene_presets()["electronic_spectrum_linked"],
            project,
            {
                "structure": reference.id,
                "states": states.id,
                "spectrum": spectrum.id,
            },
            {"selection_index": 0},
        )
        self.assertEqual(plan.view_kind, "electronic_spectrum_linked")


if __name__ == "__main__":
    unittest.main()
