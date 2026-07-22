import unittest
from uuid import uuid4

import numpy

from ChemBlender.core import (
    ArrayData,
    DatasetStatus,
    ImportBatch,
    QCProject,
    Structure,
    VibrationalModeSet,
)


def structure(atom_count=2):
    return Structure(
        id=uuid4(),
        revision="s1",
        atomic_numbers=tuple(1 for _ in range(atom_count)),
        coordinates=ArrayData(
            numpy.zeros((atom_count, 3)),
            ("atom", "xyz"),
            "angstrom",
        ),
    )


def mode_set(structure_id, atom_count=2, **overrides):
    fields = {
        "id": uuid4(),
        "revision": "v1",
        "semantic_role": "vibrational_modes",
        "domain": "mode",
        "data": ArrayData(
            numpy.asarray([-120.0, 1600.0]),
            ("mode",),
            "inverse_centimeter",
        ),
        "status": DatasetStatus.COMPLETE,
        "source_calculation": None,
        "provenance_ids": (),
        "structure_id": structure_id,
        "displacements": ArrayData(
            numpy.zeros((2, atom_count, 3)),
            ("mode", "atom", "xyz"),
            "angstrom",
        ),
        "reduced_masses": ArrayData(numpy.asarray([1.0, 2.0]), ("mode",), "dalton"),
        "force_constants": ArrayData(
            numpy.asarray([0.1, 1.2]),
            ("mode",),
            "millidyne_per_angstrom",
        ),
        "ir_intensities": ArrayData(
            numpy.asarray([2.0, 20.0]),
            ("mode",),
            "kilometer_per_mole",
        ),
        "raman_activities": ArrayData(
            numpy.asarray([3.0, 30.0]),
            ("mode",),
            "angstrom_four_per_dalton",
        ),
        "symmetries": ("A1", "B2"),
        "displacement_convention": "cclib_cartesian",
    }
    fields.update(overrides)
    return VibrationalModeSet(**fields)


class VibrationalModeSetTests(unittest.TestCase):
    def test_signed_modes_and_optional_quantities_have_explicit_semantics(self):
        reference = structure()
        modes = mode_set(reference.id)
        self.assertEqual(modes.data.values[0], -120.0)
        self.assertEqual(modes.displacements.shape, (2, 2, 3))
        self.assertEqual(modes.ir_intensities.unit, "kilometer_per_mole")
        self.assertEqual(modes.symmetries, ("A1", "B2"))

        project = QCProject(id=uuid4(), schema_version="0.1")
        project.commit(ImportBatch(structures=(reference,), datasets=(modes,)))
        self.assertIs(project.datasets[modes.id], modes)

    def test_optional_quantities_may_be_absent(self):
        reference = structure()
        modes = mode_set(
            reference.id,
            reduced_masses=None,
            force_constants=None,
            ir_intensities=None,
            raman_activities=None,
            symmetries=None,
        )
        self.assertIsNone(modes.ir_intensities)
        self.assertIsNone(modes.symmetries)

    def test_invalid_frequency_displacement_and_optional_shapes_fail(self):
        reference = structure()
        invalid = (
            {
                "data": ArrayData(
                    numpy.zeros((2, 1)), ("mode", "extra"), "inverse_centimeter"
                )
            },
            {"data": ArrayData(numpy.zeros(2), ("mode",), "unknown")},
            {
                "displacements": ArrayData(
                    numpy.zeros((1, 2, 3)), ("mode", "atom", "xyz"), "angstrom"
                )
            },
            {
                "displacements": ArrayData(
                    numpy.zeros((2, 2, 2)), ("mode", "atom", "xyz"), "angstrom"
                )
            },
            {
                "ir_intensities": ArrayData(
                    numpy.zeros(1), ("mode",), "kilometer_per_mole"
                )
            },
            {"symmetries": ("A1",)},
        )
        for overrides in invalid:
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    mode_set(reference.id, **overrides)

    def test_project_checks_structure_reference_and_atom_count_atomically(self):
        reference = structure()
        invalid = (
            mode_set(uuid4()),
            mode_set(reference.id, atom_count=3),
        )
        for modes in invalid:
            with self.subTest(modes=modes):
                project = QCProject(id=uuid4(), schema_version="0.1")
                with self.assertRaises(ValueError):
                    project.commit(
                        ImportBatch(structures=(reference,), datasets=(modes,))
                    )
                self.assertEqual(project.structures, {})
                self.assertEqual(project.datasets, {})


if __name__ == "__main__":
    unittest.main()
