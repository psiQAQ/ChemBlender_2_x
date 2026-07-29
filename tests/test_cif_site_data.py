import math
import tempfile
import unittest
from pathlib import Path

import numpy

from ChemBlender.core import IssueKind, parse_cif


FIXTURES = Path(__file__).parent / "fixtures" / "cif"
CARTESIAN = FIXTURES / "cartesian-only.cif"
MIXED = FIXTURES / "mixed-site-data.cif"


class CIFSiteDataTests(unittest.TestCase):
    def test_cartesian_only_sites_derive_fractional_coordinates(self):
        batch = parse_cif(CARTESIAN)
        structure = batch.structures[0]
        self.assertTrue(
            numpy.allclose(
                structure.coordinates.values,
                [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]],
            )
        )
        self.assertTrue(
            numpy.allclose(
                structure.periodic.fractional_coordinates.values,
                [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
            )
        )
        self.assertIn(
            ("structure.periodic.fractional_coordinates", IssueKind.WARNING),
            {(issue.path, issue.kind) for issue in batch.report.issues},
        )
        normalizations = dict(batch.provenance[0].parameters)["normalizations"]
        self.assertIn("cartesian:cartesian_to_fractional", normalizations)

    def test_conflicting_coordinate_sets_prefer_fractional_and_report_ambiguity(self):
        content = CARTESIAN.read_text(encoding="utf-8").replace(
            "_atom_site_Cartn_x\n_atom_site_Cartn_y\n_atom_site_Cartn_z",
            (
                "_atom_site_fract_x\n_atom_site_fract_y\n_atom_site_fract_z\n"
                "_atom_site_Cartn_x\n_atom_site_Cartn_y\n_atom_site_Cartn_z"
            ),
        ).replace(
            "C1 C 1.0 2.0 3.0",
            "C1 C 0.1 0.2 0.3 9.0 9.0 9.0",
        ).replace(
            "O1 O 4.0 5.0 6.0",
            "O1 O 0.4 0.5 0.6 4.0 5.0 6.0",
        )
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "conflict.cif"
            source.write_text(content, encoding="utf-8")
            batch = parse_cif(source)

        self.assertTrue(
            numpy.allclose(batch.structures[0].coordinates.values[0], [1, 2, 3])
        )
        self.assertIn(
            ("structure.coordinates", IssueKind.AMBIGUOUS),
            {(issue.path, issue.kind) for issue in batch.report.issues},
        )

    def test_missing_occupancy_adp_and_disorder_are_explicit(self):
        batch = parse_cif(MIXED)
        periodic = batch.structures[0].periodic
        self.assertTrue(math.isnan(float(periodic.occupancies.values[0])))
        self.assertEqual(float(periodic.occupancies.values[1]), 0.5)
        self.assertEqual(periodic.disorder_groups, (1, 2))
        self.assertEqual(periodic.disorder_assemblies, ("A", "A"))
        self.assertAlmostEqual(
            float(periodic.isotropic_displacements.values[0]), 0.010
        )
        self.assertTrue(
            math.isnan(float(periodic.isotropic_displacements.values[1]))
        )
        self.assertTrue(
            numpy.allclose(
                periodic.anisotropic_displacements.values[0],
                [0.010, 0.011, 0.012, 0.001, 0.002, 0.003],
            )
        )
        self.assertTrue(
            numpy.isnan(periodic.anisotropic_displacements.values[1]).all()
        )
        self.assertEqual(
            batch.structures[0].atomic_identity.atom_names.categories,
            ("C1", "O1"),
        )
        issues = {(issue.path, issue.kind) for issue in batch.report.issues}
        self.assertIn(("structure.periodic.occupancies[0]", IssueKind.MISSING), issues)
        self.assertIn(
            ("structure.periodic.anisotropic_displacements[1]", IssueKind.INVALID),
            issues,
        )
        self.assertIn(b"0.010(2)", batch.cif_envelopes[0].source_bytes)

    def test_b_iso_conversion_is_explicit(self):
        content = MIXED.read_text(encoding="utf-8").replace(
            "_atom_site_U_iso_or_equiv",
            "_atom_site_B_iso_or_equiv",
        ).replace("0.010(2)", "0.789568")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "b-iso.cif"
            source.write_text(content, encoding="utf-8")
            batch = parse_cif(source)

        value = float(
            batch.structures[0].periodic.isotropic_displacements.values[0]
        )
        self.assertAlmostEqual(value, 0.789568 / (8.0 * math.pi**2))
        self.assertIn(
            ("structure.periodic.isotropic_displacements", IssueKind.WARNING),
            {(issue.path, issue.kind) for issue in batch.report.issues},
        )
        normalizations = dict(batch.provenance[0].parameters)["normalizations"]
        self.assertIn("mixed:b_iso_to_u_iso", normalizations)


if __name__ == "__main__":
    unittest.main()
