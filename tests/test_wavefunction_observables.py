import importlib.util
from pathlib import Path
import unittest
from concurrent.futures import CancelledError
from dataclasses import replace
from unittest import mock
from uuid import uuid4

import numpy

from ChemBlender.core import (
    ArrayData,
    AtomicProperty,
    DatasetStatus,
    DensityMatrixSpin,
    DensityMatrixLevel,
    ImportBatch,
    QCProject,
    ProvenanceRecord,
    evaluate_density_matrix_grid,
    evaluate_electrostatic_potential_grid,
)
from ChemBlender.core.wavefunction_observables import derive_density_matrix_from_orbitals
from tests.test_wavefunction_grid import entities as orbital_entities
from tests.test_density_matrix_model import density_matrix, entities, values


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "submodules" / "iodata" / "iodata" / "test" / "data"
WATER_FCHK = DATA_ROOT / "water_sto3g_hf_g03.fchk"
CH3_FCHK = DATA_ROOT / "ch3_hf_sto3g.fchk"
HAS_INTEGRATION = (
    importlib.util.find_spec("gbasis") is not None
    and importlib.util.find_spec("iodata") is not None
    and WATER_FCHK.is_file()
    and CH3_FCHK.is_file()
)


GRID = {
    "origin": (1.0, 2.0, 3.0),
    "step_vectors": ((0.5, 0.0, 0.0), (0.1, 0.4, 0.0), (0.0, 0.2, 0.3)),
    "shape": (2, 1, 1),
}


def nuclear_charges(structure, charges=None, **overrides):
    charges = charges or tuple(float(number) for number in structure.atomic_numbers)
    fields = {
        "id": uuid4(),
        "revision": "n1",
        "semantic_role": "nuclear_charge",
        "domain": "atom",
        "data": ArrayData(
            numpy.asarray(charges, dtype=float), ("atom",), "elementary_charge"
        ),
        "status": DatasetStatus.COMPLETE,
        "source_calculation": None,
        "provenance_ids": (),
        "structure_id": structure.id,
    }
    fields.update(overrides)
    return AtomicProperty(**fields)


class WavefunctionObservableTests(unittest.TestCase):
    @mock.patch("ChemBlender.core.wavefunction_observables._evaluate_stored_basis")
    @mock.patch("ChemBlender.core.wavefunction_observables._evaluate_esp")
    def test_density_and_esp_evaluate_only_bounded_point_blocks(self, esp, basis_values):
        structure, basis = entities()
        matrix = density_matrix(structure.id, basis.id)
        basis_values.side_effect = lambda _s, _b, points: points[:, 0][None, :]
        esp.side_effect = lambda _s, _b, _d, _q, points: points.sum(axis=1)
        geometry = {**GRID, "shape": (3, 2, 2)}
        rdm = evaluate_density_matrix_grid(structure, basis, matrix, chunk_size=5, **geometry)
        potential = evaluate_electrostatic_potential_grid(
            structure, basis, matrix, nuclear_charges(structure, (0.8,)),
            chunk_size=5, **geometry,
        )
        self.assertEqual([len(call.args[2]) for call in basis_values.call_args_list], [5, 5, 2])
        self.assertEqual([len(call.args[4]) for call in esp.call_args_list], [5, 5, 2])
        points = numpy.concatenate([call.args[2] for call in basis_values.call_args_list])
        numpy.testing.assert_allclose(rdm.datasets[0].data.values.ravel(), points[:, 0]**2)
        numpy.testing.assert_allclose(potential.datasets[0].data.values.ravel(), points.sum(axis=1))

    @mock.patch("ChemBlender.core.wavefunction_observables._batch")
    @mock.patch("ChemBlender.core.wavefunction_observables._evaluate_esp")
    def test_esp_cancellation_after_first_block_discards_output(self, evaluate, batch):
        structure, basis = entities()
        matrix = density_matrix(structure.id, basis.id)
        state = {"cancel": False}

        def evaluate_then_cancel(_s, _b, _d, _q, points):
            state["cancel"] = True
            return numpy.zeros(len(points))

        evaluate.side_effect = evaluate_then_cancel
        with self.assertRaises(CancelledError):
            evaluate_electrostatic_potential_grid(
                structure, basis, matrix, nuclear_charges(structure),
                chunk_size=1, cancel_check=lambda: state["cancel"], **GRID,
            )
        self.assertEqual(evaluate.call_count, 1)
        batch.assert_not_called()

    def test_orbital_rdm_requires_level_and_preserves_derived_source(self):
        structure, basis, orbitals = orbital_entities()
        with self.assertRaises(TypeError):
            derive_density_matrix_from_orbitals(structure, basis, orbitals)
        batch = derive_density_matrix_from_orbitals(
            structure, basis, orbitals, level=DensityMatrixLevel.SCF,
        )
        density = batch.density_matrices[0]
        numpy.testing.assert_allclose(density.data.values, [[2.0]])
        self.assertIs(density.level, DensityMatrixLevel.SCF)
        self.assertIs(density.spin_role, DensityMatrixSpin.TOTAL)
        record = batch.provenance[0]
        self.assertEqual(record.operation, "derive_density_matrix_from_orbitals")
        self.assertEqual(dict(record.parameters)["density_source"], "orbital_occupations")
        self.assertEqual(record.source, "")
        self.assertEqual(record.parent_ids, (structure.id, basis.id, orbitals.id))
        project = QCProject(id=uuid4(), schema_version="0.1")
        project.commit(ImportBatch(structures=(structure,), basis_sets=(basis,), orbital_sets=(orbitals,)))
        project.commit(batch)

    def test_nto_source_is_rejected_without_false_positive_for_toronto(self):
        structure, basis, orbitals = orbital_entities()
        for source, operation, allowed in (
            ("Toronto/water.molden", "parse", True),
            ("water.nto.molden", "parse", False),
            ("water.molden", "natural_transition_orbitals", False),
        ):
            record = ProvenanceRecord(
                id=uuid4(), revision="p1", producer="test", producer_version="1",
                source=source, source_hash="a" * 64, parent_ids=(), operation=operation,
                parameters=(),
            )
            sourced = replace(orbitals, provenance_ids=(record.id,))
            with self.subTest(source=source, operation=operation):
                if allowed:
                    result = derive_density_matrix_from_orbitals(
                        structure, basis, sourced, level=DensityMatrixLevel.SCF,
                        source_provenance=(record,),
                    )
                    self.assertEqual(len(result.density_matrices), 1)
                else:
                    with self.assertRaisesRegex(ValueError, "NTO"):
                        derive_density_matrix_from_orbitals(
                            structure, basis, sourced, level=DensityMatrixLevel.SCF,
                            source_provenance=(record,),
                        )
        with self.assertRaisesRegex(ValueError, "source provenance"):
            derive_density_matrix_from_orbitals(
                structure, basis, sourced, level=DensityMatrixLevel.SCF,
            )

    @mock.patch("ChemBlender.core.wavefunction_observables._evaluate_stored_basis")
    def test_total_density_grid_preserves_semantics_and_provenance(self, evaluate):
        structure, basis = entities()
        matrix = density_matrix(
            structure.id,
            basis.id,
            data=ArrayData(
                values([2.0], (1, 1)),
                ("basis_function_row", "basis_function_column"),
                "dimensionless",
            ),
        )
        evaluate.return_value = numpy.asarray([[1.0, 2.0]])
        first = evaluate_density_matrix_grid(structure, basis, matrix, **GRID)
        second = evaluate_density_matrix_grid(structure, basis, matrix, **GRID)
        grid = first.datasets[0]
        provenance = first.provenance[0]
        self.assertEqual(grid.semantic_role, "electron_density")
        self.assertEqual(grid.structure_id, structure.id)
        self.assertEqual(grid.data.unit, "electron_per_cubic_bohr")
        numpy.testing.assert_allclose(grid.data.values[:, 0, 0], [2.0, 8.0])
        self.assertEqual(provenance.parent_ids, (structure.id, basis.id, matrix.id))
        self.assertEqual(first.datasets[0].revision, second.datasets[0].revision)

        project = QCProject(id=uuid4(), schema_version="0.1")
        project.commit(
            ImportBatch(
                structures=(structure,),
                basis_sets=(basis,),
                density_matrices=(matrix,),
            )
        )
        project.commit(first)

    @mock.patch("ChemBlender.core.wavefunction_observables._evaluate_stored_basis")
    def test_spin_density_retains_negative_values(self, evaluate):
        structure, basis = entities(width=3)
        matrix = density_matrix(
            structure.id,
            basis.id,
            width=3,
            spin_role=DensityMatrixSpin.SPIN,
            data=ArrayData(
                numpy.diag([1.0, -1.0, 0.0]),
                ("basis_function_row", "basis_function_column"),
                "dimensionless",
            ),
        )
        evaluate.return_value = numpy.asarray([[1.0, 0.0], [0.0, 2.0], [0.0, 0.0]])
        grid = evaluate_density_matrix_grid(structure, basis, matrix, **GRID).datasets[
            0
        ]
        self.assertEqual(grid.semantic_role, "spin_density")
        numpy.testing.assert_allclose(grid.data.values[:, 0, 0], [1.0, -4.0])

    @mock.patch("ChemBlender.core.wavefunction_observables._evaluate_esp")
    def test_esp_uses_total_rdm_and_explicit_nuclear_charge_dataset(self, evaluate):
        structure, basis = entities()
        matrix = density_matrix(structure.id, basis.id)
        charges = nuclear_charges(structure, (0.8,))
        evaluate.return_value = numpy.asarray([0.25, -0.5])
        batch = evaluate_electrostatic_potential_grid(
            structure,
            basis,
            matrix,
            charges,
            nuclear_exclusion_radius=0.01,
            **GRID,
        )
        grid = batch.datasets[0]
        self.assertEqual(grid.semantic_role, "electrostatic_potential")
        self.assertEqual(grid.structure_id, structure.id)
        self.assertEqual(grid.data.unit, "hartree_per_elementary_charge")
        numpy.testing.assert_allclose(grid.data.values[:, 0, 0], [0.25, -0.5])
        self.assertEqual(
            batch.provenance[0].parent_ids,
            (structure.id, basis.id, matrix.id, charges.id),
        )
        self.assertAlmostEqual(evaluate.call_args.args[3][0], 0.8)

    @mock.patch("ChemBlender.core.wavefunction_observables._evaluate_esp")
    def test_invalid_esp_roles_references_and_nuclear_singularities_fail(
        self, evaluate
    ):
        structure, basis = entities()
        total = density_matrix(structure.id, basis.id)
        spin = density_matrix(
            structure.id,
            basis.id,
            spin_role=DensityMatrixSpin.SPIN,
        )
        charges = nuclear_charges(structure)
        wrong_structure = nuclear_charges(structure, structure_id=uuid4())
        wrong_role = nuclear_charges(structure, semantic_role="mulliken_charge")
        invalid_values = nuclear_charges(structure, (float("nan"),))
        for matrix, charge_data in (
            (spin, charges),
            (total, wrong_structure),
            (total, wrong_role),
            (total, invalid_values),
        ):
            with self.subTest(matrix=matrix, charge_data=charge_data):
                with self.assertRaises(ValueError):
                    evaluate_electrostatic_potential_grid(
                        structure, basis, matrix, charge_data, **GRID
                    )
        with self.assertRaises(ValueError):
            evaluate_electrostatic_potential_grid(
                structure,
                basis,
                total,
                charges,
                origin=(0.0, 0.0, 0.0),
                step_vectors=GRID["step_vectors"],
                shape=(1, 1, 1),
                nuclear_exclusion_radius=1.0e-8,
            )
        self.assertEqual(evaluate.call_count, 0)

    @unittest.skipUnless(HAS_INTEGRATION, "GBasis/IOData integration unavailable")
    def test_real_rdm_density_spin_conservation_and_esp(self):
        from ChemBlender.core import (
            evaluate_electron_density_grid,
            parse_iodata_wavefunction,
        )

        water = parse_iodata_wavefunction(WATER_FCHK)
        water_structure = water.structures[0]
        water_basis = water.basis_sets[0]
        water_orbitals = water.orbital_sets[0]
        water_total = next(
            item
            for item in water.density_matrices
            if item.spin_role is DensityMatrixSpin.TOTAL
        )
        water_charges = water.datasets[0]

        spacing = 0.1
        coords = water_structure.coordinates.values
        lower = numpy.floor((coords.min(axis=0) - 6.0) / spacing) * spacing
        upper = numpy.ceil((coords.max(axis=0) + 6.0) / spacing) * spacing
        shape = tuple(
            int(round((high - low) / spacing)) + 1 for low, high in zip(lower, upper)
        )
        grid_args = {
            "origin": tuple(lower),
            "step_vectors": (
                (spacing, 0.0, 0.0),
                (0.0, spacing, 0.0),
                (0.0, 0.0, spacing),
            ),
            "shape": shape,
        }
        water_density = evaluate_density_matrix_grid(
            water_structure, water_basis, water_total, **grid_args
        ).datasets[0]
        self.assertAlmostEqual(
            float(water_density.data.values.sum() * spacing**3),
            10.00972518995233,
            places=6,
        )

        small_grid = {
            "origin": (3.0, 2.0, 1.0),
            "step_vectors": ((0.1, 0.0, 0.0), (0.0, 0.1, 0.0), (0.0, 0.0, 0.1)),
            "shape": (3, 1, 1),
        }
        rdm_small = evaluate_density_matrix_grid(
            water_structure, water_basis, water_total, **small_grid
        ).datasets[0]
        mo_small = evaluate_electron_density_grid(
            water_structure, water_basis, water_orbitals, **small_grid
        ).datasets[0]
        numpy.testing.assert_allclose(
            rdm_small.data.values, mo_small.data.values, rtol=0.0, atol=1.0e-7
        )
        esp = evaluate_electrostatic_potential_grid(
            water_structure,
            water_basis,
            water_total,
            water_charges,
            chunk_size=2,
            **small_grid,
        ).datasets[0]
        self.assertAlmostEqual(
            float(esp.data.values[0, 0, 0]), 0.0297531414634, places=10
        )

        ch3 = parse_iodata_wavefunction(CH3_FCHK)
        ch3_structure = ch3.structures[0]
        ch3_basis = ch3.basis_sets[0]
        ch3_spin = next(
            item
            for item in ch3.density_matrices
            if item.spin_role is DensityMatrixSpin.SPIN
        )
        coords = ch3_structure.coordinates.values
        lower = numpy.floor((coords.min(axis=0) - 6.0) / spacing) * spacing
        upper = numpy.ceil((coords.max(axis=0) + 6.0) / spacing) * spacing
        shape = tuple(
            int(round((high - low) / spacing)) + 1 for low, high in zip(lower, upper)
        )
        spin = evaluate_density_matrix_grid(
            ch3_structure,
            ch3_basis,
            ch3_spin,
            origin=tuple(lower),
            step_vectors=(
                (spacing, 0.0, 0.0),
                (0.0, spacing, 0.0),
                (0.0, 0.0, spacing),
            ),
            shape=shape,
        ).datasets[0]
        self.assertAlmostEqual(
            float(spin.data.values.sum() * spacing**3),
            0.9999988480353136,
            places=6,
        )
        self.assertLess(float(spin.data.values.min()), -0.03)


if __name__ == "__main__":
    unittest.main()
