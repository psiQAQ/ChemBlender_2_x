from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ChemBlender.core.model import IssueKind
from ChemBlender.core.readers import SniffMatch


FIXTURES = Path(__file__).parent / "fixtures" / "pdb"


def atom_line(
    serial,
    atom_name_field,
    *,
    record_name=b"ATOM  ",
    residue_name=b"GLY",
    model_coordinate=0.0,
    element_field=b"  ",
):
    line = bytearray(b" " * 80)
    line[0:6] = record_name
    line[6:11] = f"{serial:5d}".encode()
    line[12:16] = atom_name_field
    line[17:20] = residue_name
    line[21:22] = b"A"
    line[22:26] = b"   1"
    line[30:38] = f"{model_coordinate:8.3f}".encode()
    line[38:46] = b"   2.000"
    line[46:54] = b"   3.000"
    line[54:60] = b"  1.00"
    line[60:66] = b" 10.00"
    line[76:78] = element_field
    return bytes(line)


def conect_line(source_serial, *target_serials):
    return b"CONECT" + b"".join(
        f"{serial:5d}".encode()
        for serial in (source_serial, *target_serials)
    )


def cryst1_line(
    *,
    a=42.0,
    b=43.0,
    c=44.0,
    alpha=90.0,
    beta=100.0,
    gamma=120.0,
    space_group="P 21 21 21",
    z_value=4,
):
    line = bytearray(b" " * 80)
    line[0:6] = b"CRYST1"
    line[6:15] = f"{a:9.3f}".encode()
    line[15:24] = f"{b:9.3f}".encode()
    line[24:33] = f"{c:9.3f}".encode()
    line[33:40] = f"{alpha:7.2f}".encode()
    line[40:47] = f"{beta:7.2f}".encode()
    line[47:54] = f"{gamma:7.2f}".encode()
    line[55:66] = space_group.ljust(11).encode()
    if z_value is not None:
        line[66:70] = f"{z_value:4d}".encode()
    return bytes(line)


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

    def test_element_column_requires_right_alignment_before_becoming_authoritative(self):
        from ChemBlender.core.formats.pdb import parse_pdb_records

        parsed = parse_pdb_records(
            atom_line(1, b" N  ", element_field=b" C")
            + b"\n"
            + atom_line(2, b" N  ", element_field=b"C ")
            + b"\n"
        )

        authoritative, misaligned = parsed.atoms
        self.assertEqual(
            (authoritative.element, authoritative.element_inferred),
            ("C", False),
        )
        self.assertEqual(
            (misaligned.element, misaligned.element_inferred),
            ("N", True),
        )
        self.assertEqual(
            tuple((issue.kind, issue.path) for issue in parsed.issues),
            (
                (IssueKind.INVALID, "record[1].element_column"),
                (IssueKind.WARNING, "record[1].element"),
            ),
        )

    def test_element_inference_uses_exact_alignment_and_narrow_context(self):
        from ChemBlender.core.formats.pdb import parse_pdb_records

        cases = (
            (b" C  ", b"ALA", b"ATOM  ", "C"),
            (b" CA ", b"ALA", b"ATOM  ", "C"),
            (b"CA  ", b"ALA", b"ATOM  ", "C"),
            (b"CD  ", b"GLU", b"ATOM  ", "C"),
            (b"CE  ", b"LYS", b"ATOM  ", "C"),
            (b"ND  ", b"ASN", b"ATOM  ", "N"),
            (b"NE  ", b"GLN", b"ATOM  ", "N"),
            (b"SG  ", b"CYS", b"ATOM  ", "S"),
            (b"OG  ", b"SER", b"ATOM  ", "O"),
            (b"HG  ", b"CYS", b"ATOM  ", "H"),
            (b"HA  ", b"ALA", b"ATOM  ", "H"),
            (b"NA  ", b"ALA", b"ATOM  ", "N"),
            (b"OA  ", b"ALA", b"ATOM  ", "O"),
            (b"PA  ", b"ALA", b"ATOM  ", "P"),
            (b"SA  ", b"ALA", b"ATOM  ", "S"),
            (b"FE  ", b"ALA", b"ATOM  ", None),
            (b"BR  ", b"ALA", b"ATOM  ", None),
            (b"FA  ", b"ALA", b"ATOM  ", None),
            (b"CA  ", b"CA ", b"HETATM", "Ca"),
            (b"FE  ", b"HEM", b"HETATM", "Fe"),
            (b"1HG2", b"GLY", b"ATOM  ", "H"),
            (b"SE  ", b"SEC", b"ATOM  ", "Se"),
            (b"  CA", b"ALA", b"ATOM  ", None),
            (b" QX ", b"UNK", b"ATOM  ", None),
        )
        for atom_name, residue, record_name, expected in cases:
            with self.subTest(
                atom_name=atom_name,
                residue=residue,
                record_name=record_name,
            ):
                parsed = parse_pdb_records(
                    atom_line(
                        1,
                        atom_name,
                        residue_name=residue,
                        record_name=record_name,
                    )
                    + b"\n"
                )

                self.assertEqual(parsed.atoms[0].element, expected)
                self.assertEqual(
                    parsed.atoms[0].element_inferred,
                    expected is not None,
                )
                if expected is None:
                    self.assertIn(
                        (IssueKind.INVALID, "record[0].element"),
                        tuple(
                            (issue.kind, issue.path)
                            for issue in parsed.issues
                        ),
                    )

    def test_sniff_requires_fixed_column_coordinate_content(self):
        from ChemBlender.core.formats.pdb import sniff_pdb

        shifted = b"ATOM 1 CA GLY 1 0 0 0\n"

        self.assertIs(
            sniff_pdb(Path("sample.pdb"), shifted).match,
            SniffMatch.NONE,
        )

    def test_sniff_is_exact_only_for_clean_complete_atom_or_cryst1_content(self):
        from ChemBlender.core.formats.pdb import sniff_pdb

        clean_atom = atom_line(1, b" N  ", element_field=b" N") + b"\n"
        with TemporaryDirectory() as temporary:
            atom_source = Path(temporary) / "clean.pdb"
            atom_source.write_bytes(clean_atom)

            self.assertIs(
                sniff_pdb(atom_source, clean_atom).match,
                SniffMatch.EXACT,
            )
        crystal_source = FIXTURES / "cryst1.pdb"
        crystal = crystal_source.read_bytes()
        self.assertIs(
            sniff_pdb(crystal_source, crystal).match,
            SniffMatch.EXACT,
        )

    def test_sniff_truncated_or_recoverably_invalid_content_is_probable(self):
        from ChemBlender.core.formats.pdb import sniff_pdb

        first = atom_line(1, b" N  ", element_field=b" N") + b"\n"
        complete = first + atom_line(2, b" C  ", element_field=b" C") + b"\n"
        invalid_tail = first + b"\xff\n"
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            truncated_source = root / "truncated.pdb"
            truncated_source.write_bytes(complete)
            invalid_source = root / "invalid-tail.pdb"
            invalid_source.write_bytes(invalid_tail)

            self.assertIs(
                sniff_pdb(truncated_source, first).match,
                SniffMatch.PROBABLE,
            )
            self.assertIs(
                sniff_pdb(invalid_source, invalid_tail).match,
                SniffMatch.PROBABLE,
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

    def test_malformed_ter_still_advances_the_segment_boundary(self):
        from ChemBlender.core.formats.pdb import parse_pdb_records

        parsed = parse_pdb_records(
            atom_line(1, b" N  ", element_field=b" N")
            + b"\nTER   \n"
            + atom_line(2, b" C  ", element_field=b" C")
            + b"\nTER   XXXXX      GLY A   1\n"
            + atom_line(3, b" O  ", element_field=b" O")
            + b"\n"
        )

        self.assertEqual(
            tuple(atom.segment_index for atom in parsed.atoms),
            (0, 1, 2),
        )
        self.assertEqual(
            tuple((issue.kind, issue.path) for issue in parsed.issues),
            (
                (IssueKind.INVALID, "record[1].length"),
                (IssueKind.INVALID, "record[3].syntax"),
            ),
        )

    def test_model_marker_recovery_keeps_per_model_segment_state(self):
        from ChemBlender.core.formats.pdb import parse_pdb_records

        parsed = parse_pdb_records(
            b"MODEL        2\n"
            + atom_line(1, b" N  ", element_field=b" N")
            + b"\nMODEL        3\n"
            + atom_line(1, b" N  ", element_field=b" N")
            + b"\nTER   \n"
            + atom_line(2, b" C  ", element_field=b" C")
            + b"\nENDMDL\nENDMDL\nMODEL        4\n"
            + atom_line(1, b" N  ", element_field=b" N")
            + b"\n"
        )

        self.assertEqual(
            tuple(
                (atom.model_number, atom.segment_index)
                for atom in parsed.atoms
            ),
            ((2, 0), (3, 0), (3, 1), (4, 0)),
        )
        self.assertEqual(
            tuple((issue.kind, issue.path) for issue in parsed.issues),
            (
                (IssueKind.INVALID, "record[2].model"),
                (IssueKind.INVALID, "record[4].length"),
                (IssueKind.INVALID, "record[7].model"),
                (IssueKind.INVALID, "document.model"),
            ),
        )


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
            (IssueKind.AMBIGUOUS, "bond[model=1,2,3].order"),
            tuple((issue.kind, issue.path) for issue in parsed.issues),
        )

    def test_conect_resolves_reused_serials_within_each_model(self):
        from ChemBlender.core.formats.pdb import parse_pdb_records

        parsed = parse_pdb_records(
            b"MODEL        1\n"
            + atom_line(10, b" C  ", element_field=b" C")
            + b"\n"
            + atom_line(20, b" O  ", element_field=b" O")
            + b"\nENDMDL\nMODEL        2\n"
            + atom_line(10, b" C  ", model_coordinate=1.0, element_field=b" C")
            + b"\n"
            + atom_line(20, b" O  ", model_coordinate=1.0, element_field=b" O")
            + b"\nENDMDL\n"
            + conect_line(20, 10)
            + b"\n"
            + conect_line(10, 20)
            + b"\n"
        )

        self.assertEqual(
            tuple(
                (
                    bond.model_number,
                    bond.atom_serials,
                    bond.atom_indices,
                    bond.order,
                )
                for bond in parsed.bonds
            ),
            (
                (1, (10, 20), (0, 1), None),
                (2, (10, 20), (2, 3), None),
            ),
        )
        self.assertFalse(
            any(issue.kind is IssueKind.INVALID for issue in parsed.issues)
        )

    def test_conect_never_builds_a_cross_model_bond(self):
        from ChemBlender.core.formats.pdb import parse_pdb_records

        parsed = parse_pdb_records(
            b"MODEL        1\n"
            + atom_line(1, b" C  ", element_field=b" C")
            + b"\nENDMDL\nMODEL        2\n"
            + atom_line(2, b" O  ", element_field=b" O")
            + b"\nENDMDL\n"
            + conect_line(1, 2)
            + b"\n"
        )

        self.assertEqual(parsed.bonds, ())
        self.assertEqual(
            tuple(
                (issue.kind, issue.path)
                for issue in parsed.issues
                if issue.kind is IssueKind.INVALID
            ),
            (
                (IssueKind.INVALID, "bond[model=1,1,2].atom_references"),
                (IssueKind.INVALID, "bond[model=2,1,2].atom_references"),
            ),
        )

    def test_conect_validates_self_dangling_duplicates_and_multiplicity(self):
        from ChemBlender.core.formats.pdb import parse_pdb_records

        raw = b"\n".join(
            (
                atom_line(1, b" C  ", element_field=b" C"),
                atom_line(2, b" O  ", element_field=b" O"),
                atom_line(3, b" N  ", element_field=b" N"),
                conect_line(1, 1),
                conect_line(1, 9),
                conect_line(1, 2),
                conect_line(1, 2),
                conect_line(2, 1),
                conect_line(2, 1),
                conect_line(2, 3, 3),
                conect_line(3, 2),
                conect_line(1, 3, 3),
                conect_line(3, 1, 1),
            )
        )

        parsed = parse_pdb_records(raw + b"\n")

        self.assertEqual(
            tuple((bond.atom_serials, bond.order) for bond in parsed.bonds),
            (((1, 2), None), ((1, 3), 2), ((2, 3), None)),
        )
        issue_keys = tuple((issue.kind, issue.path) for issue in parsed.issues)
        self.assertIn(
            (IssueKind.INVALID, "bond[model=1,1,1].self_reference"),
            issue_keys,
        )
        self.assertIn(
            (IssueKind.INVALID, "bond[model=1,1,9].atom_references"),
            issue_keys,
        )
        self.assertIn(
            (IssueKind.AMBIGUOUS, "bond[model=1,1,2].order"),
            issue_keys,
        )
        self.assertIn(
            (IssueKind.AMBIGUOUS, "bond[model=1,2,3].order"),
            issue_keys,
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
        self.assertEqual(parsed.cryst1.space_group_field, "P 21 21 21 ")
        self.assertEqual(parsed.cryst1.z_value, 4)
        self.assertEqual(parsed.cryst1.source_record, "CRYST1")

    def test_cryst1_reports_blank_or_nonpositive_z(self):
        from ChemBlender.core.formats.pdb import parse_pdb_records

        cases = (
            (None, IssueKind.MISSING),
            (0, IssueKind.INVALID),
            (-2, IssueKind.INVALID),
        )
        for z_value, kind in cases:
            with self.subTest(z_value=z_value):
                parsed = parse_pdb_records(cryst1_line(z_value=z_value) + b"\n")

                self.assertIsNotNone(parsed.cryst1)
                self.assertEqual(parsed.cryst1.z_value, z_value)
                self.assertIn(
                    (kind, "record[0].z_value"),
                    tuple((issue.kind, issue.path) for issue in parsed.issues),
                )

    def test_cryst1_validates_space_group_envelope_and_preserves_raw_slice(self):
        from ChemBlender.core.formats.pdb import parse_pdb_records

        cases = (
            ("", IssueKind.MISSING),
            ("NOT A GROUP", IssueKind.INVALID),
            ("X 1", IssueKind.INVALID),
        )
        for space_group, kind in cases:
            with self.subTest(space_group=space_group):
                parsed = parse_pdb_records(
                    cryst1_line(space_group=space_group) + b"\n"
                )

                self.assertIsNotNone(parsed.cryst1)
                self.assertEqual(
                    parsed.cryst1.space_group_field,
                    space_group.ljust(11),
                )
                self.assertEqual(
                    parsed.cryst1.declared_space_group,
                    space_group,
                )
                self.assertIn(
                    (kind, "record[0].space_group"),
                    tuple((issue.kind, issue.path) for issue in parsed.issues),
                )

        valid = parse_pdb_records(
            cryst1_line(space_group="P 21/c") + b"\n"
        )
        self.assertEqual(valid.issues, ())

    def test_cryst1_rejects_nonphysical_or_nonfinite_cell_parameters(self):
        from ChemBlender.core.formats.pdb import parse_pdb_records

        cases = (
            (
                cryst1_line(alpha=10.0, beta=10.0, gamma=170.0),
                "cell",
            ),
            (cryst1_line(a=-1.0), "cell"),
            (cryst1_line(a=float("nan")), "syntax"),
        )
        for raw, field in cases:
            with self.subTest(field=field, raw=raw):
                parsed = parse_pdb_records(raw + b"\n")

                self.assertIsNone(parsed.cryst1)
                self.assertIn(
                    (IssueKind.INVALID, f"record[0].{field}"),
                    tuple((issue.kind, issue.path) for issue in parsed.issues),
                )


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
