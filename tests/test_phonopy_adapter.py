import importlib.util
import hashlib
from concurrent.futures import CancelledError
from pathlib import Path
import subprocess
import sys
import unittest

import numpy

from ChemBlender.core import IssueKind, QCProject, SniffMatch
from ChemBlender.core.phonopy_adapter import (
    PhonopyDependencyError,
    adapt_phonopy_qpoints,
    parse_phonopy_file,
    sniff_phonopy_file,
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

    def test_real_nacl_files_preserve_complex_modes_and_raw_sources(self):
        folder = ROOT / "examples/scientific-visualization/inputs/phonopy/NaCl"
        batch = parse_phonopy_file(folder / "phonopy_disp.yaml",
            born_filename=folder / "BORN", qpoints=((0, 0, 0), (.25, 0, 0)),
            nac_q_direction=(1, 0, 0))
        modes = batch.datasets[0]
        self.assertEqual(modes.data.shape, (2, 6))
        self.assertEqual(modes.eigenvectors.shape, (2, 6, 2, 3))
        self.assertEqual(modes.structure_id, batch.structures[0].id)
        self.assertEqual(modes.data.unit, "terahertz")
        self.assertTrue(numpy.isfinite(modes.data.values).all())
        self.assertTrue(numpy.iscomplexobj(modes.eigenvectors.values))
        files = batch.provenance[:-1]
        self.assertEqual(len(files), 3)
        for source in files:
            self.assertEqual(source.source_hash, hashlib.sha256(Path(source.source).read_bytes()).hexdigest())
        self.assertEqual(batch.provenance[-1].parent_ids, tuple(source.id for source in files))
        self.assertEqual(dict(batch.provenance[-1].parameters)["nac_q_direction"], (1., 0., 0.))
        QCProject(id=batch.structures[0].id, schema_version="0.1").commit(batch)

    def test_file_reader_rejects_wrong_declared_units_and_ignores_ambient_files(self):
        import tempfile
        from unittest.mock import patch
        folder = ROOT / "examples/scientific-visualization/inputs/phonopy/NaCl"
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            source = target / "phonopy_disp.yaml"
            original = (folder / source.name).read_bytes()
            source.write_bytes(original.replace(b"length: angstrom", b"length: bohr"))
            (target / "FORCE_SETS").write_bytes((folder / "FORCE_SETS").read_bytes())
            with self.assertRaisesRegex(ValueError, "units"):
                parse_phonopy_file(source)
            source.write_bytes(original)
            (target / "BORN").write_text("invalid", encoding="utf-8")
            (target / "FORCE_CONSTANTS").write_text("invalid", encoding="utf-8")
            with patch("phonopy.load", side_effect=AssertionError("ambient loader must not run")):
                batch = parse_phonopy_file(source)
            self.assertEqual(len(batch.provenance), 3)
            self.assertIsNone(dict(batch.provenance[-1].parameters)["nac_q_direction"])

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
    def test_file_preflight_rejects_ambiguous_nac_and_invalid_points(self):
        for kwargs in (
            {"qpoints": []}, {"qpoints": [[float("nan"), 0, 0]]},
            {"qpoints": [[1j, 0, 0]]}, {"nac_q_direction": (1, 0, 0)},
            {"born_filename": "BORN"},
            {"born_filename": "BORN", "nac_q_direction": (0, 0, 0)},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                parse_phonopy_file("missing.yaml", **kwargs)
        with self.assertRaises(CancelledError):
            parse_phonopy_file("missing.yaml", cancel_check=lambda: True)

    def test_file_sniffing_does_not_accept_unrelated_yaml(self):
        self.assertEqual(sniff_phonopy_file(Path("phonopy_disp.yaml"),
            b"phonopy: {}\nsupercell_matrix: []").match, SniffMatch.EXACT)
        self.assertEqual(sniff_phonopy_file(Path("config.yaml"), b"hello").match, SniffMatch.NONE)

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
