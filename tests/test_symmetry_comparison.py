import tempfile
import unittest
from pathlib import Path

import numpy

from ChemBlender.core import (
    ArrayData,
    DeclaredSymmetry,
    IssueKind,
    SymmetryResult,
    compare_symmetry,
    parse_cif,
)


def derived(number=221, symbol="Pm-3m", hall="-P 4 2 3"):
    result = object.__new__(SymmetryResult)
    object.__setattr__(result, "international_number", number)
    object.__setattr__(result, "international_symbol", symbol)
    object.__setattr__(result, "hall_symbol", hall)
    return result


class SymmetryComparisonTests(unittest.TestCase):
    def test_exact_declared_and_derived_symmetry_match(self):
        declared = DeclaredSymmetry(
            name="P m -3 m",
            international_number=221,
            hall_symbol="-P 4 2 3",
            operations=("x,y,z",),
        )
        comparison = compare_symmetry(declared, derived())
        self.assertEqual(comparison.status, "match")

    def test_setting_equivalence_requires_explicit_transformation(self):
        declared = DeclaredSymmetry(
            name="P n n n:1",
            international_number=48,
            hall_symbol=None,
            operations=(),
        )
        candidate = derived(48, "Pnnn", "-P 2ab 2bc")
        self.assertEqual(
            compare_symmetry(declared, candidate).status,
            "different",
        )
        transformation = ArrayData(
            numpy.eye(3),
            ("output_axis", "input_axis"),
            "dimensionless",
        )
        self.assertEqual(
            compare_symmetry(
                declared,
                candidate,
                setting_transformation=transformation,
            ).status,
            "equivalent_after_setting",
        )

    def test_different_number_and_insufficient_data_are_distinct(self):
        self.assertEqual(
            compare_symmetry(
                DeclaredSymmetry(None, 1, None, ()),
                derived(2, "P-1", "-P 1"),
            ).status,
            "different",
        )
        self.assertEqual(
            compare_symmetry(
                DeclaredSymmetry(None, None, None, ()),
                derived(),
            ).status,
            "insufficient_data",
        )

    def test_cif_preserves_declared_hall_and_inconsistent_fields(self):
        content = b"""data_declared
_cell_length_a 4
_cell_length_b 4
_cell_length_c 4
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_space_group_name_H-M_alt 'P 1'
_space_group_IT_number 2
_space_group_name_Hall 'P 1'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
C1 C 0 0 0
"""
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "declared.cif"
            source.write_bytes(content)
            batch = parse_cif(source)
        declared = batch.structures[0].periodic.declared_symmetry
        self.assertEqual(declared.name, "P 1")
        self.assertEqual(declared.international_number, 2)
        self.assertEqual(declared.hall_symbol, "P 1")
        self.assertEqual(declared.operations, ())
        self.assertIn(
            ("structure.periodic.declared_symmetry", IssueKind.AMBIGUOUS),
            {(issue.path, issue.kind) for issue in batch.report.issues},
        )


if __name__ == "__main__":
    unittest.main()
