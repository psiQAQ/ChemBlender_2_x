import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import UUID, uuid4

import numpy

from ChemBlender.core import (
    ArrayData, DensityMatrixSpin, ImportBatch, QCProject,
    close_project, open_project, save_project,
)
from ChemBlender.core.worker_protocol import (
    EntityReference, WorkerRequest, WorkerStatus, read_result, write_request,
)
from tests.test_density_matrix_model import density_matrix
from tests.test_wavefunction_grid import entities, GRID
from tests.test_wavefunction_observables import nuclear_charges
from worker.runner import default_registry, run_request


class WavefunctionWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.project_path = self.directory / "project.cbq"
        self.cancel_path = self.directory / "cancel"
        self.structure, self.basis, self.orbitals = entities()
        self.total = density_matrix(self.structure.id, self.basis.id)
        self.spin = replace(
            self.total, id=uuid4(), revision="spin-r1",
            spin_role=DensityMatrixSpin.SPIN,
            data=ArrayData(numpy.asarray([[-0.5]]),
                           ("basis_function_row", "basis_function_column"),
                           "dimensionless"),
        )
        self.charges = nuclear_charges(self.structure, (0.8,))
        project = QCProject(id=uuid4(), schema_version="0.1")
        project.commit(ImportBatch(
            structures=(self.structure,), basis_sets=(self.basis,),
            orbital_sets=(self.orbitals,), density_matrices=(self.total, self.spin),
            datasets=(self.charges,),
        ))
        self.project_id = project.id
        save_project(self.project_path, project)
        close_project(project)
        self.before = self.sidecar_bytes()

    def sidecar_bytes(self):
        return {
            str(path.relative_to(self.project_path)): path.read_bytes()
            for path in self.project_path.rglob("*") if path.is_file()
        }

    def run_operation(self, operation, *, inputs=None, parameters=None):
        if inputs is None:
            inputs = (self.structure, self.basis, self.orbitals)
        if parameters is None:
            parameters = {**GRID, "chunk_size": 1}
        request = WorkerRequest(
            request_id=uuid4(), project_locator=str(self.project_path),
            project_id=self.project_id, project_schema_version="0.1",
            operation_id=f"wavefunction.{operation}", operation_version="1",
            inputs=tuple(EntityReference(item.id, item.revision) for item in inputs),
            parameters=json.loads(json.dumps(parameters)),
        )
        request_path = self.directory / "request.json"
        result_path = self.directory / "result.json"
        write_request(request_path, request)
        result = run_request(request_path, result_path, default_registry(),
                             cancel_path=self.cancel_path)
        self.assertEqual(result, read_result(result_path))
        return result

    def published_grid(self, result):
        self.assertIs(result.status, WorkerStatus.SUCCESS, result.error)
        project = open_project(self.project_path)
        self.addCleanup(close_project, project)
        grid = project.datasets[UUID(result.metadata["dataset_id"])]
        self.assertIn(EntityReference(grid.id, grid.revision), result.outputs)
        return project, grid

    @patch("ChemBlender.core.wavefunction_grid._evaluate_channel")
    def test_mo_and_occupation_density_publish_grid_and_point_progress(self, evaluate):
        def values(_structure, _basis, coefficients, points):
            return coefficients[:, :1] * points[:, 0][None, :]

        evaluate.side_effect = values
        result = self.run_operation("mo_grid", parameters={
            **GRID, "chunk_size": 1, "channel": "restricted", "orbital_index": 0,
        })
        _, grid = self.published_grid(result)
        numpy.testing.assert_allclose(numpy.asarray(grid.data.values).ravel(), [1.0, 1.5])
        result = self.run_operation("electron_density_grid")
        _, density = self.published_grid(result)
        numpy.testing.assert_allclose(numpy.asarray(density.data.values).ravel(), [2.0, 4.5])
        self.assertTrue(all(len(call.args[3]) == 1 for call in evaluate.call_args_list))
        progress = json.loads((self.directory / "progress.json").read_text("utf-8"))
        self.assertEqual(progress, {"completed": 2, "total": 2})

    @patch("ChemBlender.core.wavefunction_observables._evaluate_stored_basis")
    def test_total_and_spin_rdm_keep_distinct_semantics(self, evaluate):
        evaluate.side_effect = lambda _s, _b, points: points[:, 0][None, :]
        for matrix, role, expected in (
            (self.total, "electron_density", [1.0, 2.25]),
            (self.spin, "spin_density", [-0.5, -1.125]),
        ):
            with self.subTest(role=role):
                result = self.run_operation(
                    "density_matrix_grid", inputs=(self.structure, self.basis, matrix),
                )
                _, grid = self.published_grid(result)
                self.assertEqual(grid.semantic_role, role)
                numpy.testing.assert_allclose(numpy.asarray(grid.data.values).ravel(), expected)

    @patch("ChemBlender.core.wavefunction_observables._evaluate_esp")
    def test_esp_uses_explicit_charge_and_total_rdm(self, evaluate):
        evaluate.side_effect = lambda _s, _b, _d, charges, points: (
            numpy.full(len(points), charges[0])
        )
        result = self.run_operation(
            "esp_grid", inputs=(self.structure, self.basis, self.total, self.charges),
        )
        project, grid = self.published_grid(result)
        numpy.testing.assert_allclose(numpy.asarray(grid.data.values).ravel(), [0.8, 0.8])
        self.assertEqual(grid.semantic_role, "electrostatic_potential")
        provenance = project.provenance[grid.provenance_ids[0]]
        self.assertIn(self.charges.id, provenance.parent_ids)

    @patch("ChemBlender.core.wavefunction_observables._evaluate_esp")
    def test_orbital_esp_publishes_derived_rdm_and_two_provenance_records(self, evaluate):
        evaluate.side_effect = lambda _s, _b, _d, _q, points: numpy.ones(len(points))
        result = self.run_operation(
            "esp_from_orbitals_grid",
            inputs=(self.structure, self.basis, self.orbitals, self.charges),
            parameters={**GRID, "chunk_size": 1, "density_level": "post_scf"},
        )
        project, grid = self.published_grid(result)
        derived = project.density_matrices[UUID(result.metadata["derived_density_matrix_id"])]
        self.assertEqual(derived.level.value, "post_scf")
        numpy.testing.assert_allclose(derived.data.values, [[2.0]])
        self.assertEqual(len(result.outputs), 4)
        rdm_source = project.provenance[derived.provenance_ids[0]]
        self.assertEqual(dict(rdm_source.parameters)["density_source"], "orbital_occupations")
        self.assertIn(derived.id, project.provenance[grid.provenance_ids[0]].parent_ids)

    @patch("ChemBlender.core.wavefunction_observables._evaluate_esp")
    def test_cancel_or_backend_error_never_publishes_partial_grid_or_derived_rdm(self, evaluate):
        for operation in ("esp_grid", "esp_from_orbitals_grid"):
            for cancel in (True, False):
                with self.subTest(operation=operation, cancel=cancel):
                    self.cancel_path.unlink(missing_ok=True)
                    calls = []

                    def incomplete(_s, _b, _d, _q, points):
                        calls.append(len(points))
                        if cancel:
                            self.cancel_path.touch()
                        elif len(calls) == 2:
                            raise RuntimeError("mock numerical failure")
                        return numpy.ones(len(points))

                    evaluate.side_effect = incomplete
                    derived = operation == "esp_from_orbitals_grid"
                    parameters = {**GRID, "chunk_size": 1}
                    if derived:
                        parameters["density_level"] = "scf"
                    result = self.run_operation(
                        operation, inputs=(self.structure, self.basis,
                                           self.orbitals if derived else self.total,
                                           self.charges), parameters=parameters,
                    )
                    self.assertIs(result.status, WorkerStatus.CANCELLED if cancel else WorkerStatus.ERROR)
                    self.assertEqual(len(calls), 1 if cancel else 2)
                    self.assertEqual(result.outputs, ())
                    self.assertEqual(self.sidecar_bytes(), self.before)

    def test_esp_rejects_missing_level_wrong_parent_and_spin_rdm(self):
        for operation, third, parameters in (
            ("esp_from_orbitals_grid", self.orbitals, GRID),
            ("esp_from_orbitals_grid", self.orbitals, {**GRID, "density_level": "unset"}),
            ("esp_grid", self.orbitals, GRID),
            ("esp_grid", self.spin, GRID),
            ("esp_grid", self.total, {**GRID, "unrecognized": 3}),
        ):
            with self.subTest(operation=operation, parameters=parameters):
                result = self.run_operation(
                    operation, inputs=(self.structure, self.basis, third, self.charges),
                    parameters=parameters,
                )
                self.assertIs(result.status, WorkerStatus.ERROR)
                self.assertEqual(self.sidecar_bytes(), self.before)


if __name__ == "__main__":
    unittest.main()
