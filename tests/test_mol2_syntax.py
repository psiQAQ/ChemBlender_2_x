import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ChemBlender.core.formats.mol2 import (
    iter_mol2_records,
    parse_mol2_record,
    sniff_mol2,
)
from ChemBlender.core.model import IssueKind
from ChemBlender.core.readers import SniffMatch


FIXTURES = Path(__file__).parent / "fixtures" / "mol2"


class Mol2SniffTests(unittest.TestCase):
    def test_complete_content_markers_are_exact_regardless_of_extension(self):
        source = FIXTURES / "small.mol2"
        with TemporaryDirectory() as directory:
            renamed = Path(directory) / "molecule.txt"
            renamed.write_bytes(source.read_bytes())
            result = sniff_mol2(renamed, renamed.read_bytes())
        self.assertIs(result.match, SniffMatch.EXACT)

    def test_bounded_valid_prefix_is_probable(self):
        source = FIXTURES / "aromatic.mol2"
        prefix = source.read_bytes().split(b"@<TRIPOS>BOND", 1)[0]
        result = sniff_mol2(source, prefix)
        self.assertIs(result.match, SniffMatch.PROBABLE)

    def test_extension_without_markers_is_none(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "notes.mol2"
            source.write_text("ordinary text\n", encoding="utf-8")
            result = sniff_mol2(source, source.read_bytes())
        self.assertIs(result.match, SniffMatch.NONE)

    def test_implausible_counts_are_none(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "bad-counts"
            source.write_bytes(
                b"@<TRIPOS>MOLECULE\nbad\n-1 0 0 0 0\nSMALL\nNO_CHARGES\n"
                b"@<TRIPOS>ATOM\n"
            )
            result = sniff_mol2(source, source.read_bytes())
        self.assertIs(result.match, SniffMatch.NONE)


class Mol2TokenizerTests(unittest.TestCase):
    def test_utf8_bom_is_only_accepted_on_first_source_header(self):
        raw = (
            b"\xef\xbb\xbf@<TRIPOS>MOLECULE\n"
            b"bom\n"
            b"1 0 0 0 0\n"
            b"SMALL\n"
            b"NO_CHARGES\n"
            b"@<TRIPOS>ATOM\n"
            b"5 He1 0 0 0 He\n"
        )
        with TemporaryDirectory() as directory:
            source = Path(directory) / "bom.data"
            source.write_bytes(raw)
            self.assertIs(sniff_mol2(source, raw).match, SniffMatch.EXACT)
        records = tuple(iter_mol2_records(raw))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].raw_block, raw)
        self.assertEqual(parse_mol2_record(records[0]).name, "bom")

        later_bom = raw[3:].replace(
            b"@<TRIPOS>ATOM",
            b"\xef\xbb\xbf@<TRIPOS>ATOM",
        )
        with self.assertRaisesRegex(ValueError, "one ATOM section"):
            parse_mol2_record(tuple(iter_mol2_records(later_bom))[0])

    def test_section_headers_are_case_insensitive_exact_markers(self):
        raw = (
            b"@<tripos>molecule\r\n"
            b"mixed case\r\n"
            b"1 0 0 0 0\r\n"
            b"SMALL\r\n"
            b"NO_CHARGES\r\n"
            b"@<TRIPOS>ATOM extra\r\n"
            b"@<TrIpOs>aToM\r\n"
            b"5 He1 0 0 0 He\r\n"
        )
        record = tuple(iter_mol2_records(raw))[0]
        self.assertEqual(tuple(section.name for section in record.sections), ("molecule", "aToM"))
        self.assertIn(b"@<TRIPOS>ATOM extra\r\n", record.sections[0].raw_lines)

    def test_unknown_section_preserves_name_and_raw_lines(self):
        raw = (FIXTURES / "small.mol2").read_bytes()
        record = tuple(iter_mol2_records(raw))[0]
        section = next(section for section in record.sections if section.name == "SET")
        self.assertEqual(
            section.raw_lines,
            (
                b"1 SELECTED ATOMS STATIC\n",
                b"2 10 42\n",
            ),
        )
        self.assertEqual(record.raw_block, raw)

    def test_new_molecule_starts_next_raw_record(self):
        raw = (FIXTURES / "multi.mol2").read_bytes()
        records = tuple(iter_mol2_records(raw))
        self.assertEqual(len(records), 2)
        self.assertTrue(records[0].raw_block.startswith(b"@<TRIPOS>MOLECULE\nfirst\n"))
        self.assertTrue(records[1].raw_block.startswith(b"@<TRIPOS>MOLECULE\nsecond\n"))
        self.assertEqual(b"".join(record.raw_block for record in records), raw)


class Mol2MoleculeAndAtomTests(unittest.TestCase):
    def test_molecule_header_and_optional_status_comment_are_parsed(self):
        record = parse_mol2_record(
            tuple(iter_mol2_records((FIXTURES / "small.mol2").read_bytes()))[0]
        )
        self.assertEqual(record.name, "methane fragment")
        self.assertEqual(
            (
                record.counts.atom_count,
                record.counts.bond_count,
                record.counts.substructure_count,
                record.counts.feature_count,
                record.counts.set_count,
            ),
            (2, 1, 1, 0, 0),
        )
        self.assertEqual(record.molecule_type, "SMALL")
        self.assertEqual(record.charge_type, "USER_CHARGES")
        self.assertEqual(record.status_bits, "INVALID_CHARGES")
        self.assertEqual(record.comment_lines, ("hand-authored fixture",))

    def test_atom_fields_preserve_ids_types_substructures_and_charges(self):
        record = parse_mol2_record(
            tuple(iter_mol2_records((FIXTURES / "small.mol2").read_bytes()))[0]
        )
        self.assertEqual(tuple(atom.atom_id for atom in record.atoms), (10, 42))
        self.assertEqual(record.atoms[0].name, "C1")
        self.assertEqual(record.atoms[0].coordinates, (0.0, 0.0, 0.0))
        self.assertEqual(record.atoms[0].atom_type, "C.3")
        self.assertEqual(record.atoms[0].element, "C")
        self.assertEqual(record.atoms[0].substructure_id, 101)
        self.assertEqual(record.atoms[0].substructure_name, "METHANE")
        self.assertEqual(record.atoms[0].charge, -0.12)

    def test_unknown_element_is_none_with_diagnostic_and_raw_type_preserved(self):
        raw = (
            b"@<TRIPOS>MOLECULE\nunknown\n1 0 0 0 0\nSMALL\nNO_CHARGES\n"
            b"@<TRIPOS>ATOM\n91 X1 0 0 0 Qq.fake\n"
        )
        record = parse_mol2_record(tuple(iter_mol2_records(raw))[0])
        self.assertEqual(record.atoms[0].atom_type, "Qq.fake")
        self.assertIsNone(record.atoms[0].element)
        self.assertEqual(
            tuple((issue.kind, issue.path) for issue in record.issues),
            ((IssueKind.AMBIGUOUS, "atom[0].element"),),
        )

    def test_empty_required_molecule_metadata_is_rejected(self):
        cases = (
            ("molecule type", b"", b"NO_CHARGES"),
            ("charge type", b"SMALL", b""),
        )
        for field, molecule_type, charge_type in cases:
            with self.subTest(field=field):
                raw = (
                    b"@<TRIPOS>MOLECULE\n"
                    b"empty metadata\n"
                    b"1 0 0 0 0\n"
                    + molecule_type
                    + b"\n"
                    + charge_type
                    + b"\n"
                    b"@<TRIPOS>ATOM\n"
                    b"1 He1 0 0 0 He\n"
                )
                with self.assertRaisesRegex(
                    ValueError,
                    f"MOL2 {field} must be non-empty",
                ):
                    parse_mol2_record(tuple(iter_mol2_records(raw))[0])


class Mol2BondAndSubstructureTests(unittest.TestCase):
    def parse_fixture(self, name):
        syntax = tuple(iter_mol2_records((FIXTURES / name).read_bytes()))[0]
        return parse_mol2_record(syntax)

    def test_arbitrary_atom_ids_resolve_to_indices_and_bond_semantics(self):
        record = self.parse_fixture("substructure.mol2")
        self.assertEqual(
            tuple(
                (
                    bond.bond_id,
                    bond.atom_ids,
                    bond.atom_indices,
                    bond.bond_type,
                    bond.order,
                    bond.aromatic,
                    bond.amide,
                    bond.unknown,
                )
                for bond in record.bonds
            ),
            (
                (80, (11, 22), (0, 1), "am", 1.0, False, True, False),
                (90, (22, 33), (1, 2), "2", 2.0, False, False, False),
            ),
        )
        aromatic = self.parse_fixture("aromatic.mol2")
        self.assertTrue(aromatic.topology_valid)
        self.assertTrue(all(bond.aromatic for bond in aromatic.bonds))
        self.assertTrue(all(bond.order == 1.5 for bond in aromatic.bonds))

    def test_unknown_bond_type_is_preserved_and_reported(self):
        raw = (
            b"@<TRIPOS>MOLECULE\nunknown bond\n2 1 0 0 0\nSMALL\nNO_CHARGES\n"
            b"@<TRIPOS>ATOM\n1 C1 0 0 0 C.3\n2 C2 1 0 0 C.3\n"
            b"@<TRIPOS>BOND\n8 1 2 du\n"
        )
        record = parse_mol2_record(tuple(iter_mol2_records(raw))[0])
        self.assertEqual(record.bonds[0].bond_type, "du")
        self.assertIsNone(record.bonds[0].order)
        self.assertTrue(record.bonds[0].unknown)
        self.assertFalse(record.topology_valid)
        self.assertIn(
            (IssueKind.UNSUPPORTED, "bond[0].type"),
            tuple((issue.kind, issue.path) for issue in record.issues),
        )

    def test_unknown_reference_invalidates_topology_but_preserves_atoms(self):
        record = self.parse_fixture("malformed.mol2")
        self.assertEqual(tuple(atom.atom_id for atom in record.atoms), (10, 42))
        self.assertIsNone(record.bonds[0].atom_indices)
        self.assertFalse(record.topology_valid)
        self.assertIn(
            (IssueKind.INVALID, "bond[0].atom_references"),
            tuple((issue.kind, issue.path) for issue in record.issues),
        )

    def test_common_substructure_fields_and_roots_are_parsed(self):
        record = self.parse_fixture("substructure.mol2")
        self.assertEqual(
            tuple(
                (
                    substructure.substructure_id,
                    substructure.name,
                    substructure.root_atom_id,
                    substructure.root_atom_index,
                    substructure.substructure_type,
                )
                for substructure in record.substructures
            ),
            (
                (5, "RES_A", 11, 0, "RESIDUE"),
                (9, "RES_B", 33, 2, "RESIDUE"),
            ),
        )

    def test_dangling_atom_substructure_reference_does_not_invalidate_topology(self):
        raw = (
            b"@<TRIPOS>MOLECULE\n"
            b"dangling substructure\n"
            b"1 0 1 0 0\n"
            b"SMALL\n"
            b"NO_CHARGES\n"
            b"@<TRIPOS>ATOM\n"
            b"1 C1 0 0 0 C.3 9 GHOST\n"
            b"@<TRIPOS>SUBSTRUCTURE\n"
            b"5 REAL 1 GROUP\n"
        )
        record = parse_mol2_record(tuple(iter_mol2_records(raw))[0])
        self.assertTrue(record.topology_valid)
        self.assertFalse(record.substructure_valid)
        self.assertIn(
            (IssueKind.INVALID, "atom[0].substructure_reference"),
            tuple((issue.kind, issue.path) for issue in record.issues),
        )

    def test_malformed_optional_substructure_keeps_valid_bond_topology(self):
        raw = (
            b"@<TRIPOS>MOLECULE\n"
            b"optional metadata failure\n"
            b"2 1 1 0 0\n"
            b"SMALL\n"
            b"NO_CHARGES\n"
            b"@<TRIPOS>ATOM\n"
            b"1 C1 0 0 0 C.3\n"
            b"2 H1 1 0 0 H\n"
            b"@<TRIPOS>BOND\n"
            b"1 1 2 1\n"
            b"@<TRIPOS>SUBSTRUCTURE\n"
            b"broken\n"
        )

        record = parse_mol2_record(tuple(iter_mol2_records(raw))[0])

        self.assertTrue(record.topology_valid)
        self.assertFalse(record.substructure_valid)
        self.assertIn(
            (IssueKind.INVALID, "substructure[0].syntax"),
            tuple((issue.kind, issue.path) for issue in record.issues),
        )

    def test_atom_bond_and_substructure_source_ids_must_be_positive(self):
        atom = (
            b"@<TRIPOS>MOLECULE\natom id\n1 0 0 0 0\nSMALL\nNO_CHARGES\n"
            b"@<TRIPOS>ATOM\n0 C1 0 0 0 C.3\n"
        )
        with self.assertRaisesRegex(ValueError, "atom 0 ID must be positive"):
            parse_mol2_record(tuple(iter_mol2_records(atom))[0])

        bond = (
            b"@<TRIPOS>MOLECULE\nbond id\n2 1 0 0 0\nSMALL\nNO_CHARGES\n"
            b"@<TRIPOS>ATOM\n1 C1 0 0 0 C.3\n2 H1 1 0 0 H\n"
            b"@<TRIPOS>BOND\n0 1 2 1\n"
        )
        bond_record = parse_mol2_record(tuple(iter_mol2_records(bond))[0])
        self.assertFalse(bond_record.topology_valid)
        self.assertIn(
            (IssueKind.INVALID, "bond[0].syntax"),
            tuple((issue.kind, issue.path) for issue in bond_record.issues),
        )

        substructure = (
            b"@<TRIPOS>MOLECULE\nsubstructure id\n1 0 1 0 0\nSMALL\n"
            b"NO_CHARGES\n@<TRIPOS>ATOM\n1 C1 0 0 0 C.3\n"
            b"@<TRIPOS>SUBSTRUCTURE\n0 RES 1 GROUP\n"
        )
        substructure_record = parse_mol2_record(
            tuple(iter_mol2_records(substructure))[0]
        )
        self.assertTrue(substructure_record.topology_valid)
        self.assertFalse(substructure_record.substructure_valid)
        self.assertIn(
            (IssueKind.INVALID, "substructure[0].syntax"),
            tuple((issue.kind, issue.path) for issue in substructure_record.issues),
        )

    def test_unknown_sections_are_preserved_and_reported(self):
        record = self.parse_fixture("small.mol2")
        self.assertEqual(tuple(section.name for section in record.unknown_sections), ("SET",))
        self.assertEqual(
            record.unknown_sections[0].raw_lines,
            (b"1 SELECTED ATOMS STATIC\n", b"2 10 42\n"),
        )
        self.assertIn(
            (IssueKind.UNSUPPORTED, "section.set"),
            tuple((issue.kind, issue.path) for issue in record.issues),
        )


if __name__ == "__main__":
    unittest.main()
