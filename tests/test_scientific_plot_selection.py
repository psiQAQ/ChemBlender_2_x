"""Scientific adapter selections run without a Blender installation."""

import importlib
import sys
import types
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import numpy

import ChemBlender.core as core
from tests.test_fermi_surface_model import fermi_surface
from tests.test_periodic_electronic_model import band_structure, density_of_states


def adapters():
    package = types.ModuleType("_scientific_adapter_test")
    package.__path__ = [str(Path(__file__).resolve().parents[1] / "ChemBlender")]
    with patch.dict(sys.modules, {
        "_scientific_adapter_test": package,
        "_scientific_adapter_test.core": core,
        "_scientific_adapter_test.core.model": importlib.import_module("ChemBlender.core.model"),
        "bpy": types.ModuleType("bpy"),
    }):
        return (importlib.import_module("_scientific_adapter_test.electronic_plot"),
                importlib.import_module("_scientific_adapter_test.fermi_surface_view"))


electronic, fermi = adapters()


class ScientificSelectionTests(unittest.TestCase):
    def test_shared_energy_frame_preserves_all_samples_without_clipping(self):
        self.assertEqual(electronic._energy_plot_range((-1., 2.), (-5., 5.)), (-5., 5.))
        for limits in ((0., 5.), (-5., 1.), (numpy.nan, 5.), (5., -5.)):
            with self.subTest(limits=limits), self.assertRaisesRegex(ValueError, "contain all"):
                electronic._energy_plot_range((-1., 2.), limits)

    def test_spectral_display_frame_preserves_real_units_and_zero(self):
        metadata = {}
        x_range, y_range = electronic._plot_frame(metadata, (20000., 30000.), (-.02, .08))
        self.assertEqual(electronic._plot_position(20000., -.02, x_range, y_range), (0., 0., 0.))
        self.assertEqual(electronic._plot_position(30000., .08, x_range, y_range), (8., 5., 0.))
        numpy.testing.assert_allclose(electronic._plot_position(25000., 0., x_range, y_range), (4., 1., 0.))
        self.assertEqual(metadata["cb_plot_x_range"], [20000., 30000.])
        self.assertEqual(metadata["cb_plot_y_range"], [-.02, .08])
        self.assertEqual(metadata["cb_plot_coordinate_system"], "normalized_axes_v1")

    def test_degenerate_plot_range_is_finite_and_invalid_limits_fail(self):
        metadata = {}
        x_range, y_range = electronic._plot_frame(metadata, (20000., 20000.), (0., 0.))
        self.assertEqual(electronic._plot_position(20000., 0., x_range, y_range), (4., 2.5, 0.))
        for limits in ((numpy.nan, 1.), (0., numpy.inf), (1., -1.)):
            with self.subTest(limits=limits), self.assertRaises(ValueError):
                electronic._plot_frame({}, limits, (0., 1.))

    def test_uniform_mesh_cannot_be_plotted_as_a_band_path(self):
        band = replace(band_structure(uuid4()), branches=())
        with self.assertRaisesRegex(ValueError, "explicit kpoint path"):
            electronic.create_band_structure_plot(band)

    def setUp(self):
        self.dos = density_of_states(uuid4())
        values = numpy.arange(60., dtype=float).reshape(2, 5, 2, 3)
        self.dos = replace(self.dos, projections=core.ArrayData(
            values, ("spin", "energy", "atom", "orbital"), self.dos.data.unit))

    def test_partial_selection_sums_only_exact_atom_orbital_and_preserves_spin(self):
        before = self.dos.projections.values.copy()
        values, spins, atoms, labels = electronic.select_dos_data(
            self.dos, atom_indices=(1,), orbital_labels=("pz", "s"), spin_indices=(1,))
        numpy.testing.assert_array_equal(values[0], before[1, :, 1, 2] + before[1, :, 1, 0])
        self.assertEqual((spins, atoms, labels), ((1,), (1,), ("pz", "s")))
        numpy.testing.assert_array_equal(self.dos.projections.values, before)

    def test_total_dos_remains_distinct_from_sum_of_projections(self):
        total, spins, atoms, labels = electronic.select_dos_data(self.dos, spin_indices=(1, 0))
        numpy.testing.assert_array_equal(total, self.dos.data.values[[1, 0]])
        self.assertIsNone(atoms)
        self.assertIsNone(labels)
        projected, *_ = electronic.select_dos_data(self.dos, orbital_labels=("s",))
        numpy.testing.assert_array_equal(projected, self.dos.projections.values[:, :, :, 0].sum(axis=2))

    def test_invalid_or_duplicate_selection_fails_without_allocating_blender_data(self):
        for kwargs in ({"atom_indices": ()}, {"atom_indices": (True,)},
                       {"atom_indices": (0, 0)}, {"atom_indices": (2,)},
                       {"orbital_labels": ("p",)}, {"orbital_labels": "s"},
                       {"orbital_labels": ("s", "s")}, {"spin_indices": ()},
                       {"spin_indices": (2,)}):
            with self.subTest(kwargs=kwargs), self.assertRaises((ValueError, TypeError, IndexError)):
                electronic.select_dos_data(self.dos, **kwargs)
        no_projections = replace(self.dos, projections=None, orbital_labels=())
        with self.assertRaisesRegex(ValueError, "requires explicit"):
            electronic.select_dos_data(no_projections, atom_indices=(0,))

    def test_surface_scalar_vector_components_are_source_values(self):
        dataset = fermi_surface(uuid4(), uuid4())
        prop, values = fermi.surface_property_values(dataset, "orbital_contribution")
        numpy.testing.assert_array_equal(values, [.2, .4, .6])
        self.assertEqual(prop.data.unit, "dimensionless")
        prop, values = fermi.surface_property_values(dataset, "fermi_velocity")
        numpy.testing.assert_allclose(values, numpy.sqrt(3.))
        _, values = fermi.surface_property_values(dataset, "fermi_velocity", component="x")
        numpy.testing.assert_array_equal(values, numpy.ones(3))
        _, values = fermi.surface_property_values(dataset, "fermi_velocity", vector=True)
        self.assertEqual(values.shape, (3, 3))

    def test_surface_unavailable_invalid_or_complex_vectors_are_rejected(self):
        dataset = fermi_surface(uuid4(), uuid4())
        for name, kwargs in (("missing", {}), ("orbital_contribution", {"vector": True}),
                             ("orbital_contribution", {"component": "x"}),
                             ("fermi_velocity", {"component": "bad"})):
            with self.subTest(name=name, kwargs=kwargs), self.assertRaises(ValueError):
                fermi.surface_property_values(dataset, name, **kwargs)
        for values in (numpy.ones((3, 3), dtype=complex), numpy.full((3, 3), numpy.nan), numpy.ones((3, 2))):
            invalid = replace(dataset, properties=(core.SurfaceProperty(
                semantic_role="invalid", domain="vertex", data=core.ArrayData(values, ("vertex", "xyz"), "unknown")),))
            with self.assertRaises(ValueError):
                fermi.surface_property_values(invalid, "invalid", vector=True)


if __name__ == "__main__":
    unittest.main()
