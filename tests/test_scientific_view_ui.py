"""Scientific panel plans preserve source identity without reading display data."""

from dataclasses import replace
from types import SimpleNamespace
import unittest
from uuid import uuid4

import numpy

from cbq_core.model import ArrayData
from cbq_core.model import AtomicProperty
from cbq_core.model import ImportBatch
from cbq_core.model import QCProject
from cbq_core.model import SpectrumKind
from cbq_core.model import SpectrumProfile
from cbq_core.scene_preset import builtin_scene_presets
from chemblender_prepare.core.vibration_spectrum import derive_vibrational_spectrum
from cbq_core.scene_preset import plan_scene_preset
from ChemBlender.ui import scientific_view as ui
from tests.test_scene_preset import grid
from tests.test_vibration_model import structure, mode_set


class ScientificViewUITests(unittest.TestCase):
    def setUp(self):
        self.structure = structure()
        self.modes = mode_set(self.structure.id)
        self.field = grid(self.structure.id)
        self.project = QCProject(uuid4(), "0.1")
        self.project.commit(ImportBatch(structures=(self.structure,), datasets=(self.modes, self.field)))

    def test_automatic_grid_representation_uses_shared_scientific_roles(self):
        from cbq_core.grid_semantics import builtin_grid_semantic_presets
        from cbq_core.model import DatasetStatus
        from ChemBlender.ui.default_views import default_grid_preset
        for semantic in builtin_grid_semantic_presets().values():
            field = replace(self.field, semantic_role=semantic.semantic_role,
                            status=DatasetStatus.COMPLETE)
            with self.subTest(role=semantic.semantic_role):
                expected = ("nci_surface" if field.semantic_role == "reduced_density_gradient"
                            else semantic.default_surface_mode)
                self.assertEqual(ui.selected_preset(field, SimpleNamespace(preset_id="AUTO")).preset_id,
                                 expected)
                self.assertEqual(default_grid_preset(field), semantic.default_surface_mode)
                self.assertEqual(ui.selected_preset(field, SimpleNamespace(preset_id="grid_volume")).preset_id,
                                 "grid_volume")
                ambiguous = replace(field, status=DatasetStatus.AMBIGUOUS)
                if semantic.signed:
                    self.assertEqual(ui.selected_preset(ambiguous, SimpleNamespace(preset_id="AUTO")).preset_id,
                                     "grid_volume")

    def test_shape_metadata_dispatches_scalar_vector_without_values(self):
        scalar = AtomicProperty(uuid4(), "charge-1", "atomic_charge", "atom",
                                ArrayData(numpy.zeros(2), ("atom",), "elementary_charge"),
                                self.field.status, None, (), self.structure.id)
        vector = replace(scalar, semantic_role="gradient", data=ArrayData(
            numpy.ones((2, 3)), ("atom", "xyz"), "hartree_per_bohr"))
        self.assertEqual(ui.available_presets(scalar), ("atomic_scalar",))
        self.assertEqual(ui.available_presets(vector), ("atomic_vector",))
        preset = builtin_scene_presets()["atomic_vector"]
        self.project.commit(ImportBatch(datasets=(vector,)))
        self.assertEqual(ui.scientific_bindings(self.project, vector, preset),
                         {"structure": self.structure.id, "property": vector.id})

    def test_property_binding_requires_explicit_uuid_and_same_affine(self):
        prop = replace(self.field, id=uuid4(), semantic_role="electrostatic_potential")
        foreign = replace(prop, id=uuid4(), origin=(10., 0., 0.))
        self.project.commit(ImportBatch(datasets=(prop, foreign)))
        preset = builtin_scene_presets()["property_on_surface"]
        bound, choices = ui.binding_candidates(self.project, self.field, preset)
        self.assertEqual(bound, {"surface_grid": self.field.id})
        self.assertNotIn(foreign.id, {value.id for value in choices["property_grid"]})
        for selection in ("", str(foreign.id), str(uuid4())):
            with self.assertRaisesRegex(ValueError, "compatible"):
                ui.scientific_bindings(self.project, self.field, preset, selection)
        self.assertEqual(ui.scientific_bindings(self.project, self.field, preset, str(prop.id)),
                         {"surface_grid": self.field.id, "property_grid": prop.id})

    def test_linked_spectrum_selection_does_not_use_another_modeset(self):
        first = derive_vibrational_spectrum(self.modes, kind=SpectrumKind.IR, profile=SpectrumProfile.STICK)
        other = replace(self.modes, id=uuid4())
        self.project.commit(ImportBatch(datasets=(other,)))
        foreign = derive_vibrational_spectrum(other, kind=SpectrumKind.IR, profile=SpectrumProfile.STICK)
        self.project.commit(first)
        self.project.commit(foreign)
        preset = builtin_scene_presets()["vibration_spectrum_linked"]
        _, choices = ui.binding_candidates(self.project, self.modes, preset)
        self.assertEqual(tuple(value.id for value in choices["spectrum"]), (first.datasets[0].id,))
        bound = ui.scientific_bindings(self.project, first.datasets[0], preset)
        self.assertEqual(bound["modes"], self.modes.id)
        self.assertEqual(bound["spectrum"], first.datasets[0].id)

    def test_load_dos_selection_roundtrip_preserves_labels_and_indices(self):
        preset = builtin_scene_presets()["density_of_states"]
        settings = SimpleNamespace(**dict(preset.default_settings))
        settings.preset_id = "AUTO"
        plan = SimpleNamespace(preset_id=preset.preset_id, settings=(
            ("atom_indices", (2, 0)), ("orbital_labels", ("pz", "s")), ("spin_indices", (1,))))
        ui.load_settings(settings, plan)
        result = ui.preset_settings(settings, preset)
        self.assertEqual(result["atom_indices"], (2, 0))
        self.assertEqual(result["orbital_labels"], ("pz", "s"))
        self.assertEqual(result["spin_indices"], (1,))
        settings.atom_indices = "0, 0"
        with self.assertRaisesRegex(ValueError, "duplicate"):
            ui.preset_settings(settings, preset)
        settings.atom_indices = "0,"
        with self.assertRaisesRegex(ValueError, "empty"):
            ui.preset_settings(settings, preset)

    def test_wrong_representation_does_not_follow_new_active_entity(self):
        settings = SimpleNamespace(preset_id="atomic_vector")
        with self.assertRaisesRegex(ValueError, "does not match"):
            ui.selected_preset(self.field, settings)
        settings.preset_id = "AUTO"
        self.assertEqual(ui.selected_preset(self.field, settings).preset_id, "grid_volume")

    def test_viewer_exposes_no_scientific_derivation_helpers(self):
        self.assertFalse(hasattr(ui, "spectrum_batch"))
        self.assertFalse(hasattr(ui, "difference_batch"))
        self.assertFalse(hasattr(ui, "difference_candidates"))

    def test_timeline_uses_saved_phase_offset_and_exact_period(self):
        self.assertEqual(ui.timeline_phase(12, 12, 48, .2), .2)
        self.assertAlmostEqual(ui.timeline_phase(24, 12, 48, .2), .2 + numpy.pi / 2.)
        self.assertAlmostEqual(ui.timeline_phase(60, 12, 48), 2. * numpy.pi)
        for count in (0, 1, True, 48.0):
            with self.assertRaises(ValueError):
                ui.timeline_phase(12, 12, count)


if __name__ == "__main__":
    unittest.main()
