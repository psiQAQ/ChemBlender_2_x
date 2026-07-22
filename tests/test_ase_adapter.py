import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

import numpy

from ChemBlender.core import IssueKind, QCProject, SniffMatch
from ChemBlender.core.ase_adapter import (
    ASE_STRUCTURE_READER,
    ASEDependencyError,
    parse_ase_structure,
    sniff_ase_structure,
)


ROOT = Path(__file__).resolve().parents[1]
POSCAR = ROOT / "tests" / "fixtures" / "poscar" / "cscl-selective.vasp"
EXTXYZ = ROOT / "tests" / "fixtures" / "xyz" / "periodic-extra.extxyz"
HAS_ASE = importlib.util.find_spec("ase") is not None


class ASEAdapterTests(unittest.TestCase):
    def test_core_import_does_not_eagerly_load_ase(self):
        subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; import ChemBlender.core; assert 'ase' not in sys.modules",
            ],
            cwd=ROOT,
            check=True,
        )

    def test_reader_descriptor_and_sniff(self):
        result = sniff_ase_structure(POSCAR, POSCAR.read_bytes())
        self.assertIs(result.match, SniffMatch.EXACT)
        self.assertEqual(ASE_STRUCTURE_READER.reader_id, "ase-structure")
        self.assertEqual(
            set(ASE_STRUCTURE_READER.capabilities),
            {"structure", "crystal", "atomic_property"},
        )
        result = sniff_ase_structure(EXTXYZ, EXTXYZ.read_bytes())
        self.assertIs(result.match, SniffMatch.EXACT)

    def test_parse_reports_missing_dependency(self):
        if HAS_ASE:
            self.skipTest("ASE is installed in this interpreter")
        with self.assertRaises(ASEDependencyError):
            parse_ase_structure(POSCAR)

    @unittest.skipUnless(HAS_ASE, "ASE integration dependency is unavailable")
    def test_poscar_preserves_cell_fractional_coordinates_and_fixed_axes(self):
        batch = parse_ase_structure(POSCAR)
        structure = batch.structures[0]
        self.assertEqual(structure.atomic_numbers, (55, 17))
        self.assertEqual(structure.periodic.site_labels, ("Cs1", "Cl1"))
        self.assertEqual(structure.periodic.pbc, (True, True, True))
        self.assertTrue(
            numpy.allclose(
                structure.cell.values,
                [[4.12, 0.0, 0.0], [0.5, 4.0, 0.0], [0.0, 0.25, 3.8]],
            )
        )
        self.assertTrue(
            numpy.allclose(
                structure.periodic.fractional_coordinates.values,
                [[0.0, 0.0, 0.0], [0.5, 0.5, 0.5]],
            )
        )
        fixed = next(
            dataset
            for dataset in batch.datasets
            if dataset.semantic_role == "fixed_axes"
        )
        self.assertEqual(fixed.data.dims, ("atom", "xyz"))
        self.assertTrue(
            numpy.array_equal(
                fixed.data.values,
                [[True, True, True], [False, True, False]],
            )
        )
        QCProject(id=structure.id, schema_version="0.1").commit(batch)

    @unittest.skipUnless(HAS_ASE, "ASE integration dependency is unavailable")
    def test_extxyz_preserves_partial_pbc_and_reports_unknown_array(self):
        batch = parse_ase_structure(EXTXYZ)
        structure = batch.structures[0]
        self.assertEqual(structure.periodic.pbc, (True, False, True))
        self.assertTrue(
            numpy.allclose(
                structure.cell.values,
                [[4.0, 0.0, 0.0], [1.0, 3.0, 0.0], [0.0, 0.0, 5.0]],
            )
        )
        unsupported = {
            issue.path
            for issue in batch.report.issues
            if issue.kind is IssueKind.UNSUPPORTED
        }
        self.assertEqual(unsupported, {"atoms.arrays.foo"})


if __name__ == "__main__":
    unittest.main()
