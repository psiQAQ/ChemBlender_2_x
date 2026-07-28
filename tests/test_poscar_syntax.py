from pathlib import Path
import unittest

from ChemBlender.core.readers import SniffMatch


FIXTURES = Path(__file__).parent / "fixtures" / "poscar"


class PoscarSyntaxTests(unittest.TestCase):
    def test_sniff_requires_valid_structure_and_recognizes_canonical_basename(self):
        from ChemBlender.core.formats.poscar import sniff_poscar

        valid = (FIXTURES / "cscl.vasp").read_bytes()

        self.assertIs(
            sniff_poscar(Path("POSCAR"), valid).match,
            SniffMatch.EXACT,
        )
        self.assertIs(
            sniff_poscar(Path("ordinary.txt"), b"1\n2\n3\n4\n").match,
            SniffMatch.NONE,
        )

    def test_sniff_marks_valid_vasp_suffix_as_probable(self):
        from ChemBlender.core.formats.poscar import sniff_poscar

        result = sniff_poscar(
            FIXTURES / "cscl.vasp",
            (FIXTURES / "cscl.vasp").read_bytes(),
        )

        self.assertIs(result.match, SniffMatch.PROBABLE)

    def test_sniff_accepts_valid_truncated_large_poscar_prefix(self):
        from ChemBlender.core.formats.poscar import sniff_poscar
        from ChemBlender.core.readers import SNIFF_PREFIX_BYTES

        atom_count = 12000
        content = (
            "large\n"
            "1\n"
            "1 0 0\n"
            "0 1 0\n"
            "0 0 1\n"
            "H\n"
            f"{atom_count}\n"
            "Direct\n"
            + "0.125 0.25 0.5\n" * atom_count
        ).encode()

        self.assertGreater(len(content), SNIFF_PREFIX_BYTES)
        self.assertIs(
            sniff_poscar(Path("POSCAR"), content[:SNIFF_PREFIX_BYTES]).match,
            SniffMatch.EXACT,
        )

    def test_negative_scale_normalizes_lattice_and_cartesian_coordinates(self):
        from ChemBlender.core.formats.poscar import parse_poscar_document

        document = parse_poscar_document(
            (FIXTURES / "negative-scale.vasp").read_bytes()
        )

        self.assertEqual(document.scale, -8.0)
        self.assertEqual(document.scale_factor, 2.0)
        self.assertEqual(
            document.lattice,
            ((2.0, 0.0, 0.0), (0.0, 2.0, 0.0), (0.0, 0.0, 2.0)),
        )
        self.assertEqual(document.coordinates, ((0.5, 1.0, 1.5),))

    def test_negative_scale_with_singular_lattice_returns_invalid_diagnostic(self):
        from ChemBlender.core.formats.poscar import parse_poscar_document

        document = parse_poscar_document(
            b"singular\n-8\n0 0 0\n0 1 0\n0 0 1\nH\n1\nDirect\n0 0 0\n"
        )

        self.assertEqual(document.scale_factor, 1.0)
        self.assertEqual(
            [(issue.kind.value, issue.path) for issue in document.diagnostics],
            [("invalid", "lattice")],
        )

    def test_vasp4_counts_preserve_missing_species_identities(self):
        from ChemBlender.core.formats.poscar import parse_poscar_document

        document = parse_poscar_document(
            (FIXTURES / "vasp4-counts.POSCAR").read_bytes()
        )

        self.assertIsNone(document.species)
        self.assertEqual(document.counts, (2, 1))
        self.assertEqual(document.coordinates, ((0.0, 0.0, 0.0), (0.5, 0.5, 0.5), (0.25, 0.25, 0.25)))

    def test_selective_dynamics_and_direct_mode_are_parsed(self):
        from ChemBlender.core.formats.poscar import parse_poscar_document

        document = parse_poscar_document(
            (FIXTURES / "cscl-selective.vasp").read_bytes()
        )

        self.assertEqual(document.coordinate_mode, "direct")
        self.assertEqual(document.selective_dynamics, ((False, False, False), (True, False, True)))

    def test_coordinate_mode_uses_case_insensitive_first_character(self):
        from ChemBlender.core.formats.poscar import parse_poscar_document

        document = parse_poscar_document(
            b"k point mode\n1\n1 0 0\n0 1 0\n0 0 1\nH\n1\nk\n0.25 0.5 0.75\n"
        )

        self.assertEqual(document.coordinate_mode, "cartesian")

    def test_coordinate_count_and_selective_flags_are_strict(self):
        from ChemBlender.core.formats.poscar import PoscarSyntaxError, parse_poscar_document

        with self.assertRaisesRegex(PoscarSyntaxError, "coordinate rows"):
            parse_poscar_document(
                b"short\n1\n1 0 0\n0 1 0\n0 0 1\nH\n2\nDirect\n0 0 0\n"
            )
        with self.assertRaisesRegex(PoscarSyntaxError, "T/F"):
            parse_poscar_document(
                b"bad flags\n1\n1 0 0\n0 1 0\n0 0 1\nH\n1\nSelective\nDirect\n0 0 0 T F X\n"
            )

    def test_valid_velocity_block_is_preserved(self):
        from ChemBlender.core.formats.poscar import parse_poscar_document

        document = parse_poscar_document(
            (FIXTURES / "velocities.CONTCAR").read_bytes()
        )

        self.assertEqual(
            document.velocities,
            ((0.1, 0.2, 0.3), (-0.4, 0.5, 0.6)),
        )
        self.assertEqual(document.velocity_mode, "cartesian")

    def test_explicit_velocity_mode_uses_vasp_first_character_rule(self):
        from ChemBlender.core.formats.poscar import parse_poscar_document

        cases = {
            "Cartesian": "cartesian",
            "k": "cartesian",
            "Direct": "direct",
            "velocity mode": "direct",
        }
        for marker, expected in cases.items():
            with self.subTest(marker=marker):
                document = parse_poscar_document(
                    (
                        "explicit velocity mode\n"
                        "1\n"
                        "1 0 0\n"
                        "0 1 0\n"
                        "0 0 1\n"
                        "H\n"
                        "1\n"
                        "Direct\n"
                        "0 0 0\n"
                        f"{marker}\n"
                        "0.1 0.2 0.3\n"
                    ).encode()
                )

                self.assertEqual(document.velocity_mode, expected)
                self.assertEqual(document.velocities, ((0.1, 0.2, 0.3),))

    def test_velocity_triplets_without_mode_are_rejected(self):
        from ChemBlender.core.formats.poscar import (
            PoscarSyntaxError,
            parse_poscar_document,
        )

        with self.assertRaisesRegex(PoscarSyntaxError, "velocity"):
            parse_poscar_document(
                b"missing velocity mode\n"
                b"1\n"
                b"1 0 0\n"
                b"0 1 0\n"
                b"0 0 1\n"
                b"H\n"
                b"2\n"
                b"Direct\n"
                b"0 0 0\n"
                b"0.5 0.5 0.5\n"
                b"0.1 0.2 0.3\n"
                b"0.4 0.5 0.6\n"
            )

    def test_trailing_blank_lines_without_velocities_are_ignored(self):
        from ChemBlender.core.formats.poscar import parse_poscar_document

        document = parse_poscar_document(
            b"no velocities\n"
            b"1\n"
            b"1 0 0\n"
            b"0 1 0\n"
            b"0 0 1\n"
            b"H\n"
            b"1\n"
            b"Direct\n"
            b"0 0 0\n"
            b"\n\n"
        )

        self.assertIsNone(document.velocity_mode)
        self.assertIsNone(document.velocities)

    def test_trailing_blank_lines_after_complete_velocities_are_ignored(self):
        from ChemBlender.core.formats.poscar import parse_poscar_document

        document = parse_poscar_document(
            b"velocity tail\n"
            b"1\n"
            b"1 0 0\n"
            b"0 1 0\n"
            b"0 0 1\n"
            b"H\n"
            b"1\n"
            b"Direct\n"
            b"0 0 0\n"
            b"\n"
            b"0.1 0.2 0.3\n"
            b"\n\n"
        )

        self.assertEqual(document.velocity_mode, "cartesian")
        self.assertEqual(document.velocities, ((0.1, 0.2, 0.3),))

    def test_blank_line_inside_velocity_rows_is_rejected(self):
        from ChemBlender.core.formats.poscar import (
            PoscarSyntaxError,
            parse_poscar_document,
        )

        with self.assertRaisesRegex(PoscarSyntaxError, "velocity"):
            parse_poscar_document(
                b"internal velocity blank\n"
                b"1\n"
                b"1 0 0\n"
                b"0 1 0\n"
                b"0 0 1\n"
                b"H\n"
                b"2\n"
                b"Direct\n"
                b"0 0 0\n"
                b"0.5 0.5 0.5\n"
                b"\n"
                b"0.1 0.2 0.3\n"
                b"\n"
                b"0.4 0.5 0.6\n"
            )

    def test_invalid_velocity_block_is_rejected(self):
        from ChemBlender.core.formats.poscar import PoscarSyntaxError, parse_poscar_document

        with self.assertRaisesRegex(PoscarSyntaxError, "velocity"):
            parse_poscar_document(
                b"bad velocity\n1\n1 0 0\n0 1 0\n0 0 1\nH\n1\nDirect\n0 0 0\n\n1 2\n"
            )


if __name__ == "__main__":
    unittest.main()
