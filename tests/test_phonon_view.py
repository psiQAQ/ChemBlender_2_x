import math
from dataclasses import replace
import unittest

import numpy

from cbq_core.model import ArrayData
from cbq_core.model import DatasetStatus
from ChemBlender.phonon_view import _display_frame, _reference_supercell, _repetitions
from tests.test_periodic_electronic_model import periodic_structure
from tests.test_phonon_model import phonon_modes


def normalized_modes(structure):
    modes = phonon_modes(structure.id)
    eigenvectors = modes.eigenvectors.values.copy()
    eigenvectors[0, 0] /= numpy.linalg.norm(eigenvectors[0, 0])
    return replace(modes, eigenvectors=ArrayData(eigenvectors, modes.eigenvectors.dims, "dimensionless"))


class PhononViewDataTests(unittest.TestCase):
    def test_three_axis_supercell_keeps_atom_mapping_and_scientific_inputs(self):
        structure = periodic_structure()
        before = structure.coordinates.values.copy()
        reference, indices, translations = _reference_supercell(structure, (2, 3, 2))
        self.assertEqual(len(indices), 24)
        self.assertEqual(indices.tolist(), [0, 1] * 12)
        numpy.testing.assert_array_equal(translations[-1], [1, 2, 1])
        numpy.testing.assert_allclose(reference.cell.values, numpy.diag([6, 9, 6]))
        numpy.testing.assert_allclose(reference.coordinates.values,
            before[indices] + translations @ structure.cell.values)
        numpy.testing.assert_array_equal(structure.coordinates.values, before)
        self.assertNotEqual(reference.id, structure.id)

    def test_complex_translation_mass_and_unit_match_in_display_space(self):
        structure = periodic_structure()
        modes = normalized_modes(structure)
        before = modes.eigenvectors.values.copy()
        scale = .529177210903
        bohr = replace(structure,
            coordinates=ArrayData(structure.coordinates.values / scale, ("atom", "xyz"), "bohr"),
            cell=ArrayData(structure.cell.values / scale, ("cell_vector", "xyz"), "bohr"))
        a = _display_frame(structure, modes, (2, 1, 1), 0, 0, 0., .4)[-1]
        b = _display_frame(bohr, modes, (2, 1, 1), 0, 0, 0., .4)[-1]
        numpy.testing.assert_allclose(a, b)
        self.assertAlmostEqual(a[0, 0], .4 / (2 * math.sqrt(5)))
        self.assertAlmostEqual(a[2, 0], 3 - a[0, 0])
        quarter = _display_frame(structure, modes, (2, 1, 1), 0, 0, math.pi / 2, .4)[-1]
        self.assertAlmostEqual(quarter[0, 0], .4 / math.sqrt(5))
        numpy.testing.assert_array_equal(modes.eigenvectors.values, before)

    def test_rejects_unnormalized_incomplete_and_nonperiodic(self):
        structure = periodic_structure()
        modes = normalized_modes(structure)
        with self.assertRaisesRegex(ValueError, "normalized"):
            _display_frame(structure, phonon_modes(structure.id), (1, 1, 1), 0, 0, 0, .4)
        with self.assertRaisesRegex(ValueError, "complete"):
            _display_frame(structure, replace(modes, status=DatasetStatus.PARTIAL), (1, 1, 1), 0, 0, 0, .4)
        with self.assertRaisesRegex(ValueError, "periodic"):
            _reference_supercell(replace(structure, periodic=None), (1, 1, 1))
        with self.assertRaisesRegex(ValueError, "periodic"):
            _reference_supercell(replace(structure,
                periodic=replace(structure.periodic, pbc=(True, False, True))), (1, 1, 1))
        for invalid in ((1, 0, 1), (1, True, 1), (1, 1), (1., 1, 1)):
            with self.assertRaises(ValueError):
                _repetitions(invalid)


if __name__ == "__main__":
    unittest.main()
