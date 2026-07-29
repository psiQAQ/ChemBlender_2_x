import unittest
from unittest.mock import patch
from uuid import uuid4

import numpy

from ChemBlender.core import (
    ArrayData,
    DeclaredSymmetry,
    PeriodicSiteData,
    Structure,
    SymmetryResult,
)
from ChemBlender.core.symmetry_service import (
    derive_structure_symmetry,
    symmetry_availability,
    symmetry_comparison_rows,
)
from ChemBlender.core.spglib_adapter import SpglibDependencyError


def _array(values, dims):
    return ArrayData(numpy.asarray(values), dims, "dimensionless")


def _structure():
    cell = numpy.eye(3) * 3.0
    return Structure(
        id=uuid4(),
        revision="source-r1",
        atomic_numbers=(14,),
        coordinates=ArrayData(
            numpy.zeros((1, 3)),
            ("atom", "xyz"),
            "angstrom",
        ),
        cell=ArrayData(cell, ("cell_vector", "xyz"), "angstrom"),
        periodic=PeriodicSiteData(
            fractional_coordinates=_array(
                numpy.zeros((1, 3)),
                ("atom", "xyz"),
            ),
            site_labels=("Si1",),
            occupancies=_array(numpy.ones(1), ("atom",)),
            isotropic_displacements=None,
            anisotropic_displacements=None,
            adp_types=("none",),
            disorder_groups=(0,),
            declared_space_group_name="P 1",
            declared_space_group_number=1,
            symmetry_operations=("x,y,z",),
            cif_envelope_id=None,
            declared_hall_symbol="P 1",
        ),
    )


def _derived(structure_id):
    result = object.__new__(SymmetryResult)
    values = {
        "structure_id": structure_id,
        "standardized_structure_id": uuid4(),
        "international_number": 1,
        "international_symbol": "P1",
        "hall_symbol": "P 1",
        "symprec": 2.0e-5,
        "angle_tolerance": 0.5,
        "transformation_matrix": _array(
            numpy.eye(3),
            ("standard_axis", "input_axis"),
        ),
    }
    for name, value in values.items():
        object.__setattr__(result, name, value)
    return result


class SymmetryServiceTests(unittest.TestCase):
    def test_missing_dependency_is_a_nonfatal_capability_state(self):
        with patch(
            "ChemBlender.core.spglib_adapter._spglib",
            side_effect=SpglibDependencyError("spglib is missing"),
        ):
            available, reason = symmetry_availability()

        self.assertFalse(available)
        self.assertIn("missing", reason)

    def test_broken_native_dependency_is_unavailable(self):
        with patch(
            "ChemBlender.core.spglib_adapter._spglib",
            side_effect=OSError("spglib DLL load failed"),
        ):
            available, reason = symmetry_availability()

        self.assertFalse(available)
        self.assertIn("DLL load failed", reason)

    def test_derive_delegates_to_the_adapter_without_mutating_source(self):
        source = _structure()
        batch = object()
        with patch(
            "ChemBlender.core.symmetry_service.derive_symmetry",
            return_value=batch,
        ) as derive:
            result = derive_structure_symmetry(
                source,
                symprec=2.0e-5,
                angle_tolerance=0.5,
                hall_number=1,
            )

        self.assertIs(result, batch)
        derive.assert_called_once_with(
            source,
            symprec=2.0e-5,
            angle_tolerance=0.5,
            hall_number=1,
        )
        self.assertEqual(
            source.periodic.declared_symmetry,
            DeclaredSymmetry("P 1", 1, "P 1", ("x,y,z",)),
        )

    def test_comparison_rows_include_status_tolerances_and_standard_link(self):
        source = _structure()
        derived = _derived(source.id)

        rows = symmetry_comparison_rows(source, derived)

        self.assertEqual(
            rows,
            (
                ("Status", "Match"),
                ("Symprec", "2e-05 Å"),
                ("Angle tolerance", "0.5°"),
                (
                    "Standardized Structure",
                    str(derived.standardized_structure_id),
                ),
                (
                    "Details",
                    "declared and derived group identity match",
                ),
            ),
        )

    def test_comparison_rows_reject_result_for_another_structure(self):
        with self.assertRaisesRegex(ValueError, "belong"):
            symmetry_comparison_rows(_structure(), _derived(uuid4()))


if __name__ == "__main__":
    unittest.main()
