"""Scientific panel plans preserve source identity without reading display data."""

from dataclasses import replace
from types import SimpleNamespace
import unittest
from uuid import uuid4

import numpy

from ChemBlender.core import (
    ArrayData, AtomicProperty, ImportBatch, QCProject, SpectrumKind, SpectrumProfile,
    builtin_scene_presets, derive_vibrational_spectrum, plan_scene_preset,
)
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

    def test_derived_spectrum_uses_exact_core_units_and_keeps_source_unchanged(self):
        before = self.modes.data.values.copy()
        settings = SimpleNamespace(spectrum_profile="stick", include_imaginary=False)
        batch = ui.spectrum_batch(self.modes, "raman", settings)
        self.assertEqual(batch.datasets[0].data.unit, "angstrom_four_per_dalton")
        self.assertEqual(batch.datasets[0].source_dataset_id, self.modes.id)
        numpy.testing.assert_array_equal(batch.datasets[0].data.values, [30.])
        numpy.testing.assert_array_equal(self.modes.data.values, before)
        self.assertNotIn(batch.datasets[0].id, self.project.datasets)

    def test_invalid_broadening_is_rejected_before_core_allocation(self):
        settings = SimpleNamespace(spectrum_profile="gaussian", include_imaginary=True,
                                   axis_start=0., axis_end=4000., axis_points=1001, fwhm=20.)
        for name, value in (("axis_end", float("nan")), ("fwhm", 0.), ("axis_points", 100_001)):
            bad = SimpleNamespace(**vars(settings))
            setattr(bad, name, value)
            with self.subTest(name=name), self.assertRaises(ValueError):
                ui.spectrum_batch(self.modes, "ir", bad)

    def test_difference_selection_is_stricter_than_tolerant_surface_matching(self):
        right = replace(self.field, id=uuid4(), data=ArrayData(numpy.ones((3, 3, 3)),
                         ("x", "y", "z"), self.field.data.unit))
        near = replace(right, id=uuid4(), origin=(1.e-12, 0., 0.))
        self.project.commit(ImportBatch(datasets=(right, near)))
        self.assertNotIn(near.id, {item.id for item in ui.difference_candidates(self.project, self.field)})
        settings = SimpleNamespace(difference_source_uuid=str(right.id), dataset_index=0, difference_dataset_index=0)
        batch = ui.difference_batch(self.project, self.field, settings)
        numpy.testing.assert_array_equal(batch.datasets[0].data.values, -numpy.ones((3, 3, 3)))
        self.assertEqual(batch.datasets[0].semantic_role, "difference_density")
        self.assertNotIn(batch.datasets[0].id, self.project.datasets)
        settings.difference_source_uuid = str(near.id)
        with self.assertRaisesRegex(ValueError, "identical"):
            ui.difference_batch(self.project, self.field, settings)

    def test_timeline_uses_saved_phase_offset_and_exact_period(self):
        self.assertEqual(ui.timeline_phase(12, 12, 48, .2), .2)
        self.assertAlmostEqual(ui.timeline_phase(24, 12, 48, .2), .2 + numpy.pi / 2.)
        self.assertAlmostEqual(ui.timeline_phase(60, 12, 48), 2. * numpy.pi)
        for count in (0, 1, True, 48.0):
            with self.assertRaises(ValueError):
                ui.timeline_phase(12, 12, count)


if __name__ == "__main__":
    unittest.main()
