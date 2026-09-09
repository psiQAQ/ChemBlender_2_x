import sys
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import numpy

from cbq_core.model import ArrayData
from cbq_core.model import AtomicProperty
from cbq_core.model import CalculationRecord
from cbq_core.model import CalculationStatus
from cbq_core.model import DatasetStatus
from cbq_core.model import Grid3D
from cbq_core.model import ImportBatch
from cbq_core.model import OrbitalKind
from cbq_core.model import ProvenanceRecord
from cbq_core.model import QCProject
from cbq_core.sidecar import close_project
from cbq_core.session import close_session
from cbq_core.session import create_session
from cbq_core.sidecar import open_project
from cbq_core.sidecar import save_project
from cbq_core.worker_protocol import WorkerError
from cbq_core.worker_protocol import WorkerResult
from cbq_core.worker_protocol import WorkerStatus
from ChemBlender.ui import wavefunction
from ChemBlender.ui.tasks import TaskState
from tests.test_wavefunction_grid import entities


ROOT = Path(__file__).resolve().parents[1]
PARAMETERS = {
    "origin": [1., 1., 1.],
    "step_vectors": [[.5, 0., 0.], [0., .5, 0.], [0., 0., .5]],
    "shape": [3, 3, 3],
    "chunk_size": 8,
    "channel": "restricted",
    "orbital_index": 0,
}


class WavefunctionUITests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.structure, self.basis, self.orbitals = entities()
        project = QCProject(uuid4(), "0.2")
        project.commit(ImportBatch(structures=(self.structure,), basis_sets=(self.basis,),
                                   orbital_sets=(self.orbitals,)))
        self.session = create_session(temp_parent=self.temporary.name, project=project)

    def tearDown(self):
        try:
            wavefunction.clear_wavefunction_jobs(self.session)
        finally:
            try:
                close_session(self.session)
            finally:
                self.temporary.cleanup()

    def job(self, operation_id="wavefunction.mo_grid", *, parameters=None, inputs=None):
        return wavefunction.WavefunctionJob(
            self.session, operation_id, inputs or (self.structure, self.basis, self.orbitals),
            PARAMETERS if parameters is None else parameters,
            python_executable=sys.executable, working_directory=ROOT,
        )

    def execute_worker_in_snapshot(self, request, workspace, **_kwargs):
        from chemblender_prepare.worker.operation import OperationContext
        from chemblender_prepare.worker.wavefunction_operations import _mo_grid
        from chemblender_prepare.worker.wavefunction_operations import _esp_from_orbitals_grid

        locator = Path(request.project_locator)
        self.assertIn(self.session.temporary_root, locator.parents)
        self.assertNotEqual(locator, self.session.sidecar_path)
        task_directory = Path(workspace) / str(request.request_id)
        task_directory.mkdir()
        snapshot = open_project(locator)
        try:
            operation = (_mo_grid if request.operation_id == "wavefunction.mo_grid"
                         else _esp_from_orbitals_grid)
            output = operation(OperationContext(locator, snapshot, None, task_directory), request)
            snapshot.commit(output.batch)
            save_project(locator, snapshot)
            result = WorkerResult(request.request_id, WorkerStatus.SUCCESS,
                                  outputs=output.outputs, cache_key=output.cache_key,
                                  metadata=output.metadata)
        finally:
            close_project(snapshot)
        return SimpleNamespace(
            process=SimpleNamespace(poll=lambda: 0), poll=lambda: result,
            wait=lambda timeout=None: result, terminate=lambda: None,
            request_path=task_directory / "request.json",
        )

    @staticmethod
    def basis_values(_structure, _basis, coefficients, points):
        return numpy.ones((len(coefficients), len(points)))

    def test_snapshot_worker_cannot_modify_live_project_before_atomic_publish(self):
        job = self.job()
        with patch.object(wavefunction, "start_worker", side_effect=self.execute_worker_in_snapshot), patch(
            "chemblender_prepare.core.wavefunction_grid._evaluate_channel", side_effect=self.basis_values
        ):
            job.start()
            self.assertTrue(job.worker.join(5))
        job.worker.raise_if_failed()
        self.assertEqual(self.session.project.datasets, {})
        self.assertEqual(self.session.project.provenance, {})
        self.assertIsNot(job.snapshot.datasets, self.session.project.datasets)
        grid = job.publish(self.session)
        self.assertEqual(set(self.session.project.datasets), {grid.id})
        self.assertEqual(grid.structure_id, self.structure.id)
        self.assertEqual(self.session.active_entity_id, grid.id)
        self.assertEqual(self.session.dirty_reasons, frozenset({"wavefunction"}))
        job.close()
        self.assertFalse(job.root.exists())
        numpy.testing.assert_array_equal(grid.data.values, numpy.ones((3, 3, 3)))
        self.assertNotIn(self.session.id, wavefunction._JOBS)

    def test_frozen_inputs_survive_project_replacement_without_reading_unrelated_grid(self):
        unrelated = Grid3D(
            id=uuid4(), revision="unrelated", semantic_role="electron_density", domain="grid",
            data=ArrayData(numpy.zeros((2, 2, 2)), ("x", "y", "z"), "electron_per_cubic_bohr"),
            status=DatasetStatus.COMPLETE, source_calculation=None, provenance_ids=(),
            origin=(0., 0., 0.), step_vectors=((1., 0., 0.), (0., 1., 0.), (0., 0., 1.)),
            coordinate_unit="bohr", structure_id=self.structure.id,
        )
        self.session.project.commit(ImportBatch(datasets=(unrelated,)))
        source_path = Path(self.temporary.name) / "source.cbq"
        save_project(source_path, self.session.project)
        original = open_project(source_path)
        self.session.project = original
        original_coefficients = original.orbital_sets[self.orbitals.id].channels[0].coefficients.values
        original_grid = original.datasets[unrelated.id].data.values
        self.assertFalse(original_coefficients.loaded)
        with patch.object(original_grid, "_load", side_effect=AssertionError("unrelated grid read")):
            job = self.job()
        self.assertFalse(original_coefficients.loaded)
        self.assertEqual(job.snapshot.datasets, {})
        self.assertIsInstance(job.snapshot.orbital_sets[self.orbitals.id].channels[0].coefficients.values,
                              numpy.ndarray)
        self.session.project = QCProject(uuid4(), "0.2")
        close_project(original)
        with patch.object(original_coefficients, "_load", side_effect=AssertionError("closed input read")), patch.object(
            wavefunction, "start_worker", side_effect=self.execute_worker_in_snapshot
        ), patch("chemblender_prepare.core.wavefunction_grid._evaluate_channel", side_effect=self.basis_values):
            job.start()
            self.assertTrue(job.worker.join(5))
        job.worker.raise_if_failed()
        with self.assertRaisesRegex(ValueError, "active project changed"):
            job.publish(self.session)
        self.assertFalse(self.session.project.datasets)
        job.close()

    def test_snapshot_keeps_required_calculation_and_provenance_closure(self):
        from tests.test_density_matrix_model import density_matrix

        provenance = ProvenanceRecord(uuid4(), "p1", "test", "1", "fixture", "", (),
                                      "import", (("options", {"labels": ["original"]}),))
        calculation = CalculationRecord(uuid4(), "c1", CalculationStatus.SUCCESS,
                                        (self.structure.id,), (self.structure.id,), (), (provenance.id,))
        matrix = density_matrix(self.structure.id, self.basis.id,
                                source_calculation=calculation.id, provenance_ids=(provenance.id,))
        self.session.project.commit(ImportBatch(calculations=(calculation,), provenance=(provenance,),
                                               density_matrices=(matrix,)))
        job = self.job("wavefunction.density_matrix_grid", inputs=(self.structure, self.basis, matrix))
        self.assertEqual(set(job.snapshot.calculations), {calculation.id})
        self.assertEqual(set(job.snapshot.provenance), {provenance.id})
        self.assertEqual(job.snapshot.orbital_sets, {})
        provenance.parameters[0][1]["labels"].append("changed")
        self.assertEqual(job.snapshot.provenance[provenance.id].parameters[0][1]["labels"], ["original"])
        save_project(job.request.project_locator, job.snapshot)
        restored = open_project(job.request.project_locator)
        try:
            self.assertEqual(restored.density_matrices[matrix.id].source_calculation, calculation.id)
        finally:
            close_project(restored)
        job.close()

    def test_changed_inputs_and_late_cancel_both_discard_ready_result(self):
        for reason in ("changed", "cancelled"):
            with self.subTest(reason=reason):
                job = self.job()
                with patch.object(wavefunction, "start_worker", side_effect=self.execute_worker_in_snapshot), patch(
                    "chemblender_prepare.core.wavefunction_grid._evaluate_channel", side_effect=self.basis_values
                ):
                    job.start()
                    self.assertTrue(job.worker.join(5))
                job.worker.raise_if_failed()
                if reason == "changed":
                    self.session.project.structures[self.structure.id] = replace(self.structure, revision="changed")
                else:
                    job.cancel()
                with self.assertRaisesRegex((ValueError, RuntimeError), reason):
                    job.publish(self.session)
                self.assertFalse(self.session.project.datasets)
                self.assertFalse(self.session.dirty)
                job.close()
                self.session.project.structures[self.structure.id] = self.structure

    def test_worker_failure_preserves_live_project_and_closes_workspace(self):
        job = self.job()
        with patch.object(wavefunction, "start_worker", side_effect=OSError("worker unavailable")):
            job.start()
            self.assertTrue(job.worker.join(5))
        with self.assertRaisesRegex(OSError, "worker unavailable"):
            job.publish(self.session)
        job.close()
        self.assertFalse(self.session.project.datasets)
        self.assertFalse(self.session.project.provenance)
        self.assertFalse(job.root.exists())

    def test_session_cleanup_cancels_and_joins_owned_worker(self):
        running, cancelled, terminated = Event(), Event(), Event()

        def start(request, workspace, **_kwargs):
            running.set()
            result = WorkerResult(request.request_id, WorkerStatus.CANCELLED,
                                  error=WorkerError("cancelled", "cancelled"))
            return SimpleNamespace(
                process=SimpleNamespace(poll=lambda: 0 if terminated.is_set() else None),
                poll=lambda: result if cancelled.is_set() else None,
                request_cancel=cancelled.set, terminate=terminated.set,
                request_path=Path(workspace) / "request.json",
            )

        job = self.job()
        with patch.object(wavefunction, "start_worker", side_effect=start):
            job.start()
            self.assertTrue(running.wait(5))
            wavefunction.clear_wavefunction_jobs(self.session)
        self.assertTrue(cancelled.is_set())
        self.assertTrue(terminated.is_set())
        self.assertEqual(job.task.snapshot().state, TaskState.CANCELLED)
        self.assertFalse(job.root.exists())
        self.assertFalse(self.session.project.datasets)

    def test_output_semantics_are_validated_before_commit(self):
        job = self.job()
        original = wavefunction._detached_output

        def tampered(project, request, result):
            grid_id = UUID(result.metadata["dataset_id"])
            project.datasets[grid_id] = replace(project.datasets[grid_id], structure_id=None)
            return original(project, request, result)

        from uuid import UUID
        with patch.object(wavefunction, "start_worker", side_effect=self.execute_worker_in_snapshot), patch(
            "chemblender_prepare.core.wavefunction_grid._evaluate_channel", side_effect=self.basis_values
        ), patch.object(wavefunction, "_detached_output", side_effect=tampered):
            job.start()
            self.assertTrue(job.worker.join(5))
        with self.assertRaisesRegex(ValueError, "semantics or identity"):
            job.publish(self.session)
        job.close()
        self.assertFalse(self.session.project.datasets)

    def test_derived_rdm_and_esp_publish_together_only_with_explicit_charges_and_level(self):
        with self.assertRaisesRegex(ValueError, "effective nuclear-charge"):
            wavefunction.wavefunction_inputs(self.session.project,
                "wavefunction.esp_from_orbitals_grid", self.orbitals.id)
        charges = AtomicProperty(
            id=uuid4(), revision="charges-r1", semantic_role="nuclear_charge", domain="atom",
            data=ArrayData(numpy.ones(1), ("atom",), "elementary_charge"),
            status=DatasetStatus.COMPLETE, source_calculation=None, provenance_ids=(),
            structure_id=self.structure.id,
        )
        self.session.project.commit(ImportBatch(datasets=(charges,)))
        inputs = wavefunction.wavefunction_inputs(self.session.project,
            "wavefunction.esp_from_orbitals_grid", self.orbitals.id, nuclear_charge_id=charges.id)
        parameters = {key: value for key, value in PARAMETERS.items() if key not in {"channel", "orbital_index"}}
        parameters["density_level"] = "scf"
        job = self.job("wavefunction.esp_from_orbitals_grid", parameters=parameters, inputs=inputs)
        with patch.object(wavefunction, "start_worker", side_effect=self.execute_worker_in_snapshot), patch(
            "chemblender_prepare.core.wavefunction_observables._evaluate_esp",
            side_effect=lambda _s, _b, _d, _c, points: numpy.full(len(points), .25),
        ):
            job.start()
            self.assertTrue(job.worker.join(5))
        job.worker.raise_if_failed()
        self.assertFalse(self.session.project.density_matrices)
        self.assertEqual(set(self.session.project.datasets), {charges.id})
        grid = job.publish(self.session)
        self.assertEqual(grid.semantic_role, "electrostatic_potential")
        self.assertEqual(len(self.session.project.density_matrices), 1)
        self.assertEqual(len(job.worker.result.provenance), 2)
        job.close()

    def test_worker_configuration_progress_and_memory_use_bounded_explicit_inputs(self):
        settings = SimpleNamespace(worker_python=sys.executable, worker_repository=str(ROOT))
        self.assertEqual(wavefunction.worker_configuration(settings), (Path(sys.executable).resolve(), ROOT))
        settings.worker_python = ""
        with self.assertRaisesRegex(ValueError, "Set Worker"):
            wavefunction.worker_configuration(settings)
        path = Path(self.temporary.name) / "progress.json"
        for content, expected in ((b'{"completed":5,"total":10}', .475),
                                  (b'{"completed":true,"total":10}', None),
                                  (b'{"completed":11,"total":10}', None),
                                  (b"x" * 1025, None), (b"{partial", None)):
            path.write_bytes(content)
            self.assertEqual(wavefunction._worker_progress(path), expected)
        with patch.object(wavefunction, "estimate_grid_memory", return_value={}) as estimate:
            wavefunction.operation_memory(self.session.project, self.orbitals,
                                          "wavefunction.electron_density_grid", PARAMETERS)
        self.assertEqual(estimate.call_args.kwargs["orbital_count"], 2)



class PreparedOrbitalSelectionTests(unittest.TestCase):
    def setUp(self):
        WavefunctionUITests.setUp(self)

    def tearDown(self):
        try:
            close_session(self.session)
        finally:
            self.temporary.cleanup()

    def test_source_selection_survives_derived_grid_and_resets_source_bound_choices(self):
        structure, basis, orbitals = entities(OrbitalKind.UNRESTRICTED)
        self.session.project.commit(ImportBatch(structures=(structure,), basis_sets=(basis,),
                                               orbital_sets=(orbitals,)))
        settings = SimpleNamespace(orbital_source=str(self.orbitals.id),
            orbital_source_uuid=str(self.orbitals.id), channel="restricted", orbital_number=7)
        self.session.active_entity_id = orbitals.id
        self.assertIs(wavefunction._selected_orbitals(self.session, settings), orbitals)
        wavefunction.select_wavefunction_source(settings, orbitals)
        self.assertEqual(settings.orbital_source_uuid, str(orbitals.id))
        self.assertEqual(settings.channel, "alpha")
        self.assertEqual(settings.orbital_number, 1)
        self.session.active_entity_id = uuid4()  # Publication selects the new Grid, not the OrbitalSet.
        self.assertIs(wavefunction._selected_orbitals(self.session, settings), orbitals)
        settings.channel, settings.orbital_number = "beta", 2
        wavefunction.select_wavefunction_source(settings, orbitals)
        self.assertEqual((settings.channel, settings.orbital_number), ("beta", 2))
        # Selecting a prepared grid retains the chosen spin and orbital.
        settings.orbital_source_uuid = str(self.orbitals.id)
        wavefunction.select_wavefunction_source(settings, orbitals, reset=False)
        self.assertEqual(settings.orbital_source_uuid, str(orbitals.id))
        self.assertEqual((settings.channel, settings.orbital_number), ("beta", 2))

    def test_dynamic_entity_selection_uses_uuid_instead_of_old_list_position(self):
        first = (("NONE", "Select", ""), ("charge-a", "A", ""), ("charge-b", "B", ""))
        reordered = (("NONE", "Select", ""), ("charge-b", "B", ""), ("charge-a", "A", ""))
        replaced = (("NONE", "Select", ""), ("new-session-charge", "New", ""))
        self.assertEqual(wavefunction._enum_number(first, "charge-a"), 1)
        self.assertEqual(wavefunction._enum_number(reordered, "charge-a"), 2)
        self.assertEqual(wavefunction._enum_number(replaced, "charge-a"), 0)

    def test_stale_explicit_source_does_not_select_an_unrelated_set(self):
        settings = SimpleNamespace(orbital_source_uuid=str(uuid4()), channel="restricted")
        self.session.active_entity_id = uuid4()
        self.assertIsNone(wavefunction._selected_orbitals(self.session, settings))
        settings.orbital_source_uuid = "invalid-uuid"
        self.assertIsNone(wavefunction._selected_orbitals(self.session, settings))
        settings.orbital_source_uuid = ""
        self.assertIs(wavefunction._selected_orbitals(self.session, settings), self.orbitals)


if __name__ == "__main__":
    unittest.main()
