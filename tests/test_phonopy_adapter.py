import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

import numpy

from ChemBlender.core import IssueKind, QCProject
from ChemBlender.core.phonopy_adapter import (
    PhonopyDependencyError,
    adapt_phonopy_qpoints,
)


ROOT = Path(__file__).resolve().parents[1]
HAS_PHONOPY = importlib.util.find_spec("phonopy") is not None


@unittest.skipUnless(HAS_PHONOPY, "phonopy dependency is unavailable")
class PhonopyIntegrationTests(unittest.TestCase):
    @staticmethod
    def phonon():
        from phonopy import Phonopy
        from phonopy.structure.atoms import PhonopyAtoms

        unitcell = PhonopyAtoms(
            symbols=["Si"],
            cell=numpy.eye(3) * 4.0,
            scaled_positions=[[0.0, 0.0, 0.0]],
            masses=[4.0],
        )
        phonon = Phonopy(unitcell, numpy.eye(3, dtype=int))
        phonon.force_constants = numpy.diag([1.0, 4.0, 9.0]).reshape((1, 1, 3, 3))
        phonon.run_qpoints(
            [[0.0, 0.0, 0.0], [0.5, 0.0, 0.0]],
            with_eigenvectors=True,
        )
        return phonon

    def test_maps_real_qpoints_result_and_axis_order(self):
        phonon = self.phonon()
        batch = adapt_phonopy_qpoints(phonon)
        structure = batch.structures[0]
        modes = batch.datasets[0]
        raw = phonon.qpoints.eigenvectors
        expected = raw.transpose(0, 2, 1).reshape((2, 3, 1, 3))
        self.assertTrue(numpy.allclose(modes.eigenvectors.values, expected))
        self.assertTrue(numpy.allclose(modes.data.values, phonon.qpoints.frequencies))
        self.assertTrue(numpy.allclose(modes.qpoints.values, phonon.qpoints.qpoints))
        self.assertEqual(modes.structure_id, structure.id)
        self.assertEqual(modes.masses.values.tolist(), [4.0])
        missing = {
            issue.path for issue in batch.report.issues if issue.kind is IssueKind.MISSING
        }
        self.assertEqual(missing, {"phonon.group_velocities", "phonon.qpoint_weights"})
        QCProject(id=structure.id, schema_version="0.1").commit(batch)

    def test_requires_qpoints_and_eigenvectors(self):
        from phonopy import Phonopy
        from phonopy.structure.atoms import PhonopyAtoms

        phonon = Phonopy(
            PhonopyAtoms(
                symbols=["Si"],
                cell=numpy.eye(3),
                scaled_positions=[[0.0, 0.0, 0.0]],
            ),
            numpy.eye(3, dtype=int),
        )
        with self.assertRaisesRegex(ValueError, "run_qpoints"):
            adapt_phonopy_qpoints(phonon)


class PhonopyAdapterTests(unittest.TestCase):
    def test_core_import_does_not_eagerly_load_phonopy(self):
        subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; import ChemBlender.core; assert 'phonopy' not in sys.modules",
            ],
            cwd=ROOT,
            check=True,
        )

    def test_missing_dependency_is_explicit(self):
        if HAS_PHONOPY:
            self.skipTest("phonopy is installed in this interpreter")
        with self.assertRaises(PhonopyDependencyError):
            adapt_phonopy_qpoints(object())


if __name__ == "__main__":
    unittest.main()
