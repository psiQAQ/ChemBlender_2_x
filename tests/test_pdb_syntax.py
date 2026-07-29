from pathlib import Path
import unittest

from ChemBlender.core.model import IssueKind
from ChemBlender.core.readers import SniffMatch


FIXTURES = Path(__file__).parent / "fixtures" / "pdb"


class PDBFixedColumnTests(unittest.TestCase):
    def test_atom_and_hetatm_use_exact_columns_and_element_rules(self):
        from ChemBlender.core.formats.pdb import parse_pdb_records

        parsed = parse_pdb_records((FIXTURES / "atom-hetatm.pdb").read_bytes())
        atom, iron, alpha_carbon = parsed.atoms

        self.assertEqual(
            (
                atom.record_kind,
                atom.serial,
                atom.atom_name_field,
                atom.atom_name,
                atom.alternate_location,
                atom.residue_name,
                atom.chain_id,
                atom.residue_number,
                atom.insertion_code,
                atom.coordinates,
                atom.occupancy,
                atom.b_factor,
                atom.element,
                atom.formal_charge,
                atom.element_inferred,
            ),
            (
                "atom",
                32,
                " N  ",
                "N",
                "A",
                "ARG",
                "A",
                -3,
                "B",
                (11.281, 86.699, 94.383),
                0.5,
                35.88,
                "N",
                2,
                False,
            ),
        )
        self.assertEqual(
            (
                iron.record_kind,
                iron.atom_name_field,
                iron.atom_name,
                iron.element,
                iron.element_inferred,
            ),
            ("hetatm", "FE  ", "FE", "Fe", True),
        )
        self.assertEqual(
            (
                alpha_carbon.atom_name_field,
                alpha_carbon.atom_name,
                alpha_carbon.element,
                alpha_carbon.element_inferred,
            ),
            (" CA ", "CA", "C", True),
        )
        self.assertEqual(
            tuple((issue.kind, issue.path) for issue in parsed.issues),
            (
                (IssueKind.MISSING, "record[1].element"),
                (IssueKind.INVALID, "record[2].element_column"),
                (IssueKind.WARNING, "record[2].element"),
            ),
        )
        altlocs = parse_pdb_records((FIXTURES / "altloc.pdb").read_bytes())
        self.assertEqual(
            tuple(atom.alternate_location for atom in altlocs.atoms),
            ("A", "B"),
        )

    def test_raw_source_and_line_endings_are_preserved(self):
        from ChemBlender.core.formats.pdb import parse_pdb_records

        raw = (
            b"ATOM      1  N   GLY A   1      11.000  12.000  13.000"
            b"  1.00 20.00           N  \r\n"
        )

        parsed = parse_pdb_records(raw)

        self.assertEqual(parsed.raw_source, raw)
        self.assertEqual(parsed.atoms[0].raw_line, raw)

    def test_standard_residue_context_disambiguates_left_aligned_ca(self):
        from ChemBlender.core.formats.pdb import parse_pdb_records

        template = bytearray(
            (FIXTURES / "atom-hetatm.pdb").read_bytes().splitlines()[0]
        )
        template[12:16] = b"CA  "
        template[16:17] = b" "
        template[76:80] = b"    "
        protein = template.copy()
        protein[0:6] = b"ATOM  "
        protein[17:20] = b"ALA"
        calcium = template.copy()
        calcium[0:6] = b"HETATM"
        calcium[17:20] = b"CA "

        parsed = parse_pdb_records(bytes(protein) + b"\n" + bytes(calcium) + b"\n")

        self.assertEqual(
            tuple((atom.element, atom.element_inferred) for atom in parsed.atoms),
            (("C", True), ("Ca", True)),
        )

    def test_sniff_requires_fixed_column_coordinate_content(self):
        from ChemBlender.core.formats.pdb import sniff_pdb

        valid = (FIXTURES / "atom-hetatm.pdb").read_bytes()

        self.assertIs(sniff_pdb(Path("sample.pdb"), valid).match, SniffMatch.EXACT)
        self.assertIs(
            sniff_pdb(Path("sample.pdb"), b"ATOM 1 CA GLY 1 0 0 0\n").match,
            SniffMatch.NONE,
        )

    def test_fatal_exceptions_propagate_from_parse_and_sniff(self):
        from ChemBlender.core.formats.pdb import parse_pdb_records, sniff_pdb

        for exception_type in (
            KeyboardInterrupt,
            SystemExit,
            GeneratorExit,
            MemoryError,
        ):
            with self.subTest(exception=exception_type.__name__):
                class FatalBytes(bytes):
                    def splitlines(self, *args, **kwargs):
                        raise exception_type

                raw = FatalBytes(b"ATOM  ")
                with self.assertRaises(exception_type):
                    parse_pdb_records(raw)
                with self.assertRaises(exception_type):
                    sniff_pdb(Path("fatal.pdb"), raw)


class PDBModelAndSegmentTests(unittest.TestCase):
    def test_model_endmdl_and_ter_assign_models_and_segments(self):
        from ChemBlender.core.formats.pdb import parse_pdb_records

        parsed = parse_pdb_records((FIXTURES / "multimodel.pdb").read_bytes())

        self.assertEqual(
            tuple(
                (atom.serial, atom.model_number, atom.segment_index)
                for atom in parsed.atoms
            ),
            ((1, 4, 0), (2, 4, 1), (1, 7, 0)),
        )
        self.assertEqual(
            tuple(
                (ter.serial, ter.model_number, ter.segment_index)
                for ter in parsed.ters
            ),
            ((2, 4, 0),),
        )
        self.assertEqual(parsed.issues, ())

    def test_atoms_outside_model_default_to_model_one(self):
        from ChemBlender.core.formats.pdb import parse_pdb_records

        parsed = parse_pdb_records(
            b"ATOM      1  O   HOH A   1       1.000   2.000   3.000"
            b"  1.00 10.00           O  \n"
        )

        self.assertEqual(parsed.atoms[0].model_number, 1)


class PDBConnectivityTests(unittest.TestCase):
    def test_conect_resolves_after_atoms_and_only_unambiguous_repetition_is_order(self):
        from ChemBlender.core.formats.pdb import parse_pdb_records

        parsed = parse_pdb_records((FIXTURES / "conect.pdb").read_bytes())

        self.assertEqual(
            tuple(
                (bond.atom_serials, bond.atom_indices, bond.order)
                for bond in parsed.bonds
            ),
            (
                ((1, 2), (0, 1), 2),
                ((2, 3), (1, 2), None),
            ),
        )
        self.assertIn(
            (IssueKind.AMBIGUOUS, "bond[2,3].order"),
            tuple((issue.kind, issue.path) for issue in parsed.issues),
        )


class PDBCrystalTests(unittest.TestCase):
    def test_cryst1_parses_cell_declared_space_group_and_source_metadata(self):
        from ChemBlender.core.formats.pdb import parse_pdb_records

        parsed = parse_pdb_records((FIXTURES / "cryst1.pdb").read_bytes())

        self.assertEqual(
            parsed.cryst1.cell_parameters,
            (42.0, 43.0, 44.0, 90.0, 100.0, 120.0),
        )
        self.assertEqual(parsed.cryst1.declared_space_group, "P 21 21 21")
        self.assertEqual(parsed.cryst1.z_value, 4)
        self.assertEqual(parsed.cryst1.source_record, "CRYST1")


class PDBMalformedRecoveryTests(unittest.TestCase):
    def test_short_unknown_and_mismatched_records_report_and_recover(self):
        from ChemBlender.core.formats.pdb import parse_pdb_records

        raw = (FIXTURES / "malformed.pdb").read_bytes()
        parsed = parse_pdb_records(raw)

        self.assertEqual(tuple(atom.serial for atom in parsed.atoms), (2, 3))
        self.assertIsNone(parsed.atoms[0].element)
        self.assertEqual(parsed.atoms[1].model_number, 3)
        self.assertEqual(parsed.raw_source, raw)
        self.assertEqual(
            tuple((issue.kind, issue.path) for issue in parsed.issues),
            (
                (IssueKind.INVALID, "record[0].length"),
                (IssueKind.MISSING, "record[1].element"),
                (IssueKind.INVALID, "record[1].element"),
                (IssueKind.INVALID, "record[3].model"),
                (IssueKind.INVALID, "record[6].model"),
            ),
        )


if __name__ == "__main__":
    unittest.main()
