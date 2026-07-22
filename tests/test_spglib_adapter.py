import importlib.util
from dataclasses import replace
from pathlib import Path
import subprocess
import sys
import unittest

import numpy

from ChemBlender.core import ArrayData, QCProject, parse_cif
from ChemBlender.core.spglib_adapter import (
    SpglibDependencyError,
    derive_symmetry,
)


ROOT = Path(__file__).resolve().parents[1]
CSCL = ROOT / "tests" / "fixtures" / "cif" / "cscl.cif"
PARTIAL = ROOT / "tests" / "fixtures" / "cif" / "partial-disorder.cif"
HAS_GEMMI = importlib.util.find_spec("gemmi") is not None
HAS_SPGLIB = importlib.util.find_spec("spglib") is not None
HAS_INTEGRATION = HAS_GEMMI and HAS_SPGLIB


class SpglibAdapterTests(unittest.TestCase):
    def test_core_import_does_not_eagerly_load_spglib(self):
        code = (
            "import sys; import ChemBlender.core; "
            "assert 'spglib' not in sys.modules"
        )
        subprocess.run(
            [sys.executable, "-c", code],
            cwd=ROOT,
            check=True,
        )

    def test_derive_reports_missing_dependency(self):
        if HAS_SPGLIB:
            self.skipTest("spglib is installed in this interpreter")
        with self.assertRaises(SpglibDependencyError):
            derive_symmetry(object())

    @unittest.skipUnless(HAS_INTEGRATION, "Gemmi/spglib dependencies unavailable")
    def test_cscl_symmetry_and_standard_structure(self):
        parsed = parse_cif(CSCL)
        original = parsed.structures[0]
        project = QCProject(id=original.id, schema_version="0.1")
        project.commit(parsed)
        derived = derive_symmetry(original)
        self.assertEqual(len(derived.structures), 1)
        self.assertEqual(len(derived.symmetry_results), 1)
        result = derived.symmetry_results[0]
        standard = derived.structures[0]
        self.assertEqual(result.structure_id, original.id)
        self.assertEqual(result.standardized_structure_id, standard.id)
        self.assertEqual(result.international_number, 221)
        self.assertEqual(result.international_symbol, "Pm-3m")
        self.assertEqual(result.hall_number, 517)
        self.assertEqual(result.pointgroup, "m-3m")
        self.assertEqual(result.wyckoffs, ("a", "b"))
        self.assertEqual(result.equivalent_atoms.values.tolist(), [0, 1])
        self.assertEqual(result.rotations.shape, (48, 3, 3))
        self.assertEqual(result.translations.shape, (48, 3))
        self.assertTrue(
            numpy.allclose(result.transformation_matrix.values, numpy.eye(3))
        )
        self.assertTrue(numpy.allclose(result.origin_shift.values, numpy.zeros(3)))
        self.assertTrue(numpy.allclose(standard.cell.values, numpy.eye(3) * 4.12))
        self.assertTrue(
            numpy.allclose(
                standard.coordinates.values,
                standard.periodic.fractional_coordinates.values
                @ standard.cell.values,
            )
        )
        self.assertEqual(
            standard.periodic.cif_envelope_id,
            original.periodic.cif_envelope_id,
        )
        project.commit(derived)
        self.assertIs(project.symmetry_results[result.id], result)

    @unittest.skipUnless(HAS_INTEGRATION, "Gemmi/spglib dependencies unavailable")
    def test_partial_occupancy_is_not_silently_ignored(self):
        structure = parse_cif(PARTIAL).structures[0]
        with self.assertRaisesRegex(ValueError, "partial occupancy"):
            derive_symmetry(structure)

    @unittest.skipUnless(HAS_INTEGRATION, "Gemmi/spglib dependencies unavailable")
    def test_bohr_cell_is_converted_before_symmetry_search(self):
        structure = parse_cif(CSCL).structures[0]
        scale = 1.0 / 0.529177210903
        bohr_structure = replace(
            structure,
            coordinates=ArrayData(
                numpy.asarray(structure.coordinates.values) * scale,
                ("atom", "xyz"),
                "bohr",
            ),
            cell=ArrayData(
                numpy.asarray(structure.cell.values) * scale,
                ("cell_vector", "xyz"),
                "bohr",
            ),
        )
        standard = derive_symmetry(bohr_structure).structures[0]
        self.assertEqual(standard.cell.unit, "angstrom")
        self.assertTrue(numpy.allclose(standard.cell.values, numpy.eye(3) * 4.12))

    @unittest.skipUnless(HAS_INTEGRATION, "Gemmi/spglib dependencies unavailable")
    def test_nonzero_origin_shift_obeys_spglib_change_of_basis(self):
        structure = parse_cif(CSCL).structures[0]
        shift = numpy.asarray([0.1, 0.2, 0.3])
        fractional = (
            numpy.asarray(structure.periodic.fractional_coordinates.values) + shift
        ) % 1.0
        shifted_periodic = replace(
            structure.periodic,
            fractional_coordinates=ArrayData(
                fractional, ("atom", "xyz"), "dimensionless"
            ),
        )
        shifted = replace(
            structure,
            coordinates=ArrayData(
                fractional @ numpy.asarray(structure.cell.values),
                ("atom", "xyz"),
                "angstrom",
            ),
            periodic=shifted_periodic,
        )
        derived = derive_symmetry(shifted)
        result = derived.symmetry_results[0]
        standard = derived.structures[0]
        self.assertFalse(numpy.allclose(result.origin_shift.values, 0.0))
        transformed = (
            fractional @ numpy.asarray(result.transformation_matrix.values).T
            + numpy.asarray(result.origin_shift.values)
        ) % 1.0
        standard_positions = numpy.asarray(
            standard.periodic.fractional_coordinates.values
        )
        for position in transformed:
            delta = standard_positions - position
            delta -= numpy.rint(delta)
            self.assertEqual(
                numpy.count_nonzero(numpy.linalg.norm(delta, axis=1) < 1.0e-8),
                1,
            )

    @unittest.skipUnless(HAS_INTEGRATION, "Gemmi/spglib dependencies unavailable")
    def test_tolerance_validation(self):
        structure = parse_cif(CSCL).structures[0]
        for value in (0.0, -1.0, float("nan"), True):
            with self.subTest(symprec=value):
                with self.assertRaises(ValueError):
                    derive_symmetry(structure, symprec=value)


if __name__ == "__main__":
    unittest.main()
