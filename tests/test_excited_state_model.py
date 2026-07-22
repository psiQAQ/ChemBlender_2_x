import unittest
from uuid import uuid4

import numpy

from ChemBlender.core import (
    ArrayData,
    DatasetStatus,
    ExcitationContribution,
    ExcitedStateReferences,
    ExcitedStateSet,
    ImportBatch,
    PropertyDataset,
    QCProject,
    SpinChannel,
)
from tests.test_vibration_model import structure


def contribution(**overrides):
    fields = {
        "occupied_orbital": 2,
        "occupied_spin": SpinChannel.ALPHA,
        "virtual_orbital": 5,
        "virtual_spin": SpinChannel.ALPHA,
        "coefficient": -0.8,
    }
    fields.update(overrides)
    return ExcitationContribution(**fields)


def state_set(structure_id, **overrides):
    fields = {
        "id": uuid4(),
        "revision": "e1",
        "semantic_role": "excited_states",
        "domain": "state",
        "data": ArrayData(
            numpy.asarray([20000.0, 30000.0]),
            ("state",),
            "inverse_centimeter",
        ),
        "status": DatasetStatus.COMPLETE,
        "source_calculation": None,
        "provenance_ids": (),
        "structure_id": structure_id,
        "oscillator_strengths": ArrayData(
            numpy.asarray([0.1, 0.2]), ("state",), "dimensionless"
        ),
        "rotatory_strengths": None,
        "electric_transition_dipoles": ArrayData(
            numpy.zeros((2, 3)),
            ("state", "xyz"),
            "elementary_charge_bohr",
        ),
        "velocity_transition_dipoles": None,
        "magnetic_transition_dipoles": None,
        "symmetries": ("Singlet-A", "Triplet-B"),
        "multiplicities": (1, 3),
        "configurations": ((contribution(),), (contribution(coefficient=0.6),)),
        "state_references": (
            ExcitedStateReferences(),
            ExcitedStateReferences(),
        ),
    }
    fields.update(overrides)
    return ExcitedStateSet(**fields)


class ExcitedStateModelTests(unittest.TestCase):
    def test_contribution_preserves_signed_coefficient_and_spin(self):
        item = contribution(
            occupied_spin=SpinChannel.BETA,
            virtual_spin=SpinChannel.ALPHA,
        )
        self.assertEqual(item.occupied_orbital, 2)
        self.assertIs(item.occupied_spin, SpinChannel.BETA)
        self.assertEqual(item.coefficient, -0.8)
        self.assertAlmostEqual(item.weight, 0.64)

    def test_invalid_contribution_fields_fail(self):
        invalid = (
            {"occupied_orbital": -1},
            {"virtual_orbital": True},
            {"occupied_spin": "alpha"},
            {"coefficient": float("nan")},
        )
        for values in invalid:
            with self.subTest(values=values):
                with self.assertRaises((TypeError, ValueError)):
                    contribution(**values)

    def test_excited_state_set_preserves_optional_state_data(self):
        reference = structure()
        states = state_set(reference.id)
        self.assertEqual(states.data.shape, (2,))
        self.assertEqual(states.oscillator_strengths.unit, "dimensionless")
        self.assertEqual(states.electric_transition_dipoles.shape, (2, 3))
        self.assertEqual(states.multiplicities, (1, 3))
        self.assertAlmostEqual(states.configurations[0][0].weight, 0.64)

        project = QCProject(id=uuid4(), schema_version="0.1")
        project.commit(ImportBatch(structures=(reference,), datasets=(states,)))
        self.assertIs(project.datasets[states.id], states)

    def test_unknown_rotatory_unit_requires_ambiguous_status(self):
        reference = structure()
        rotatory = ArrayData(numpy.asarray([-0.4, 0.2]), ("state",), "unknown")
        with self.assertRaises(ValueError):
            state_set(reference.id, rotatory_strengths=rotatory)
        states = state_set(
            reference.id,
            rotatory_strengths=rotatory,
            status=DatasetStatus.AMBIGUOUS,
        )
        self.assertEqual(states.rotatory_strengths.unit, "unknown")

    def test_invalid_state_shapes_units_and_multiplicities_fail(self):
        reference = structure()
        invalid = (
            {"data": ArrayData(numpy.zeros((2, 1)), ("state", "extra"), "inverse_centimeter")},
            {"data": ArrayData(numpy.asarray([-1.0, 2.0]), ("state",), "inverse_centimeter")},
            {"oscillator_strengths": ArrayData(numpy.zeros(1), ("state",), "dimensionless")},
            {"electric_transition_dipoles": ArrayData(numpy.zeros((2, 2)), ("state", "xyz"), "elementary_charge_bohr")},
            {"symmetries": ("Singlet",)},
            {"multiplicities": (1, 0)},
            {"configurations": ((contribution(),),)},
            {"state_references": (ExcitedStateReferences(),)},
        )
        for values in invalid:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    state_set(reference.id, **values)

    def test_project_validates_structure_and_derived_references_atomically(self):
        reference = structure()
        target_id = uuid4()
        references = (
            ExcitedStateReferences(nto_hole=target_id),
            ExcitedStateReferences(),
        )
        dangling = state_set(reference.id, state_references=references)
        project = QCProject(id=uuid4(), schema_version="0.1")
        with self.assertRaises(ValueError):
            project.commit(ImportBatch(structures=(reference,), datasets=(dangling,)))
        self.assertEqual(project.datasets, {})

        target = PropertyDataset(
            id=target_id,
            revision="g1",
            semantic_role="nto_hole",
            domain="grid",
            data=ArrayData(numpy.asarray([1.0]), ("sample",), "dimensionless"),
            status=DatasetStatus.COMPLETE,
            source_calculation=None,
            provenance_ids=(),
        )
        valid = state_set(reference.id, state_references=references)
        project.commit(
            ImportBatch(structures=(reference,), datasets=(target, valid))
        )
        self.assertIs(project.datasets[valid.id], valid)


if __name__ == "__main__":
    unittest.main()
