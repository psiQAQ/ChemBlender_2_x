import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy

from ChemBlender.core import CapabilitySupport, IssueKind, QCProject, SniffMatch
from ChemBlender.core.gemmi_adapter import (
    CIF_READER,
    GemmiDependencyError,
    parse_cif,
    sniff_cif,
)


ROOT = Path(__file__).resolve().parents[1]
CSCL = ROOT / "tests" / "fixtures" / "cif" / "cscl.cif"
PARTIAL = ROOT / "tests" / "fixtures" / "cif" / "partial-disorder.cif"
HAS_GEMMI = importlib.util.find_spec("gemmi") is not None


class GemmiAdapterTests(unittest.TestCase):
    def test_core_import_does_not_eagerly_load_gemmi(self):
        code = (
            "import sys; import ChemBlender.core; "
            "assert 'gemmi' not in sys.modules"
        )
        subprocess.run(
            [sys.executable, "-c", code],
            cwd=ROOT,
            check=True,
        )

    def test_reader_descriptor_and_sniff(self):
        result = sniff_cif(CSCL, CSCL.read_bytes())
        self.assertIs(result.match, SniffMatch.EXACT)
        self.assertEqual(CIF_READER.reader_id, "gemmi-cif")
        self.assertEqual(CIF_READER.reader_version, "1")
        self.assertEqual(CIF_READER.extensions, (".cif",))
        self.assertEqual(
            CIF_READER.capabilities,
            {
                "structure": CapabilitySupport.SUPPORTED,
                "crystal": CapabilitySupport.SUPPORTED,
                "cif_envelope": CapabilitySupport.SUPPORTED,
            },
        )

    def test_parse_reports_missing_dependency(self):
        if HAS_GEMMI:
            self.skipTest("Gemmi is installed in this interpreter")
        with self.assertRaises(GemmiDependencyError):
            parse_cif(CSCL)

    @unittest.skipUnless(HAS_GEMMI, "Gemmi integration dependency is unavailable")
    def test_parse_preserves_crystal_semantics_and_raw_envelope(self):
        batch = parse_cif(CSCL)
        self.assertEqual(len(batch.structures), 1)
        self.assertEqual(len(batch.cif_envelopes), 1)
        structure = batch.structures[0]
        envelope = batch.cif_envelopes[0]
        self.assertEqual(structure.atomic_numbers, (55, 17))
        self.assertTrue(numpy.allclose(structure.cell.values, numpy.eye(3) * 4.12))
        self.assertTrue(
            numpy.allclose(
                structure.periodic.fractional_coordinates.values,
                [[0.0, 0.0, 0.0], [0.5, 0.5, 0.5]],
            )
        )
        self.assertTrue(
            numpy.allclose(
                structure.coordinates.values,
                [[0.0, 0.0, 0.0], [2.06, 2.06, 2.06]],
            )
        )
        self.assertEqual(structure.periodic.site_labels, ("Cs1", "Cl1"))
        self.assertEqual(structure.periodic.declared_space_group_number, 221)
        self.assertEqual(structure.periodic.declared_space_group_name, "P m -3 m")
        self.assertEqual(structure.periodic.symmetry_operations, ("x,y,z",))
        self.assertTrue(
            numpy.allclose(
                structure.periodic.isotropic_displacements.values,
                [0.01, 0.012],
            )
        )
        self.assertTrue(
            numpy.allclose(
                structure.periodic.anisotropic_displacements.values[0],
                [0.01, 0.011, 0.012, 0.001, 0.002, 0.003],
            )
        )
        self.assertTrue(
            numpy.isnan(structure.periodic.anisotropic_displacements.values[1]).all()
        )
        self.assertEqual(envelope.source_bytes, CSCL.read_bytes())
        self.assertIn("_chemblender_unknown_tag", envelope.tag_names)
        self.assertEqual(structure.periodic.cif_envelope_id, envelope.id)
        self.assertEqual(
            batch.report.parsed_capabilities,
            ("structure", "crystal", "cif_envelope"),
        )
        QCProject(id=structure.id, schema_version="0.1").commit(batch)

    @unittest.skipUnless(HAS_GEMMI, "Gemmi integration dependency is unavailable")
    def test_partial_occupancy_and_disorder_are_explicit(self):
        batch = parse_cif(PARTIAL)
        periodic = batch.structures[0].periodic
        self.assertTrue(numpy.allclose(periodic.occupancies.values, [0.5]))
        self.assertEqual(periodic.disorder_groups, (1,))
        warning_paths = {
            issue.path
            for issue in batch.report.issues
            if issue.kind is IssueKind.WARNING
        }
        self.assertEqual(
            warning_paths,
            {"structure.periodic.occupancies", "structure.periodic.disorder_groups"},
        )
        self.assertIsNone(periodic.isotropic_displacements)
        self.assertIsNone(periodic.anisotropic_displacements)

    @unittest.skipUnless(HAS_GEMMI, "Gemmi integration dependency is unavailable")
    def test_multiple_blocks_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "multiple.cif"
            source.write_bytes(b"data_a\n_custom 1\ndata_b\n_custom 2\n")
            with self.assertRaisesRegex(ValueError, "exactly one data block"):
                parse_cif(source)


if __name__ == "__main__":
    unittest.main()
