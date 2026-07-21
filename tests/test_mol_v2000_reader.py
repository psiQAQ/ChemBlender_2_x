from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ChemBlender.core import IssueKind, ReaderRegistry, SniffMatch, XYZ_READER
from ChemBlender.core.mol_v2000 import (
    MOL_V2000_READER,
    sniff_mol_v2000,
)


ROOT = Path(__file__).resolve().parents[1]
MOL_FIXTURE = ROOT / "tests" / "fixtures" / "mol" / "water.mol"
XYZ_FIXTURE = ROOT / "tests" / "fixtures" / "xyz" / "water.xyz"


class MolV2000ReaderTests(unittest.TestCase):
    def test_sniff_and_registry_recognize_v2000(self):
        result = sniff_mol_v2000(MOL_FIXTURE, MOL_FIXTURE.read_bytes())
        self.assertEqual(result.match, SniffMatch.EXACT)
        self.assertIs(
            ReaderRegistry((MOL_V2000_READER,)).select(MOL_FIXTURE),
            MOL_V2000_READER,
        )

    def test_parse_normalizes_structure_and_reports_topology(self):
        batch = MOL_V2000_READER.parse(MOL_FIXTURE)
        structure = batch.structures[0]
        self.assertEqual(structure.atomic_numbers, (8, 1, 1))
        self.assertEqual(structure.coordinates.shape, (3, 3))
        self.assertEqual(structure.coordinates.unit, "angstrom")
        self.assertEqual(batch.report.parsed_capabilities, ("structure",))
        self.assertEqual(
            {(issue.kind, issue.path) for issue in batch.report.issues},
            {(IssueKind.UNSUPPORTED, "topology")},
        )
        self.assertEqual(
            set(batch.report.created_entity_ids),
            {structure.id, batch.provenance[0].id},
        )
        self.assertEqual(len(batch.provenance[0].source_hash), 64)

    def test_xyz_and_mol_normalize_the_same_structure(self):
        xyz = XYZ_READER.parse(XYZ_FIXTURE).structures[0]
        mol = MOL_V2000_READER.parse(MOL_FIXTURE).structures[0]
        self.assertEqual(mol.atomic_numbers, xyz.atomic_numbers)
        self.assertEqual(mol.coordinates.shape, xyz.coordinates.shape)
        self.assertEqual(mol.coordinates.dims, xyz.coordinates.dims)
        self.assertEqual(mol.coordinates.unit, xyz.coordinates.unit)
        for mol_value, xyz_value in zip(
            mol.coordinates.values.tolist(),
            xyz.coordinates.values.tolist(),
        ):
            self.assertEqual(len(mol_value), len(xyz_value))
            for actual, expected in zip(mol_value, xyz_value):
                self.assertAlmostEqual(actual, expected, places=4)

    def test_parse_rejects_unsupported_or_truncated_records(self):
        cases = (
            MOL_FIXTURE.read_bytes().replace(b"V2000", b"V3000"),
            MOL_FIXTURE.read_bytes() + b"$$$$\nsecond\n",
            b"water\nChemBlender\n\n  1  0  0  0  0  0  0  0  0  0  0 V2000\n",
            MOL_FIXTURE.read_bytes().replace(b" O  ", b" Xx ", 1),
            MOL_FIXTURE.read_bytes().replace(b"    0.0000", b"       nan", 1),
            MOL_FIXTURE.read_bytes().replace(b"M  END", b"", 1),
        )
        for content in cases:
            with self.subTest(content=content[:80]):
                with TemporaryDirectory() as directory:
                    source = Path(directory) / "bad.mol"
                    source.write_bytes(content)
                    with self.assertRaises(ValueError):
                        MOL_V2000_READER.parse(source)

    def test_unmapped_property_records_are_reported(self):
        content = MOL_FIXTURE.read_bytes().replace(
            b"M  END",
            b"M  CHG  1   1  -1\nM  END",
        )
        with TemporaryDirectory() as directory:
            source = Path(directory) / "charged.mol"
            source.write_bytes(content)
            batch = MOL_V2000_READER.parse(source)
        self.assertIn(
            (IssueKind.UNSUPPORTED, "atom_properties"),
            {(issue.kind, issue.path) for issue in batch.report.issues},
        )


if __name__ == "__main__":
    unittest.main()
