import json
import subprocess
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import UUID

import numpy

from ChemBlender.core import (
    ArrayData,
    DatasetStatus,
    ImportBatch,
    PropertyDataset,
    QCProject,
    Structure,
    open_project,
    save_project,
)
from ChemBlender.worker_client import WorkerProcessError, start_worker
from ChemBlender.core.worker_protocol import (
    EntityReference,
    ProtocolError,
    WorkerRequest,
    WorkerResult,
    WorkerStatus,
    read_request,
    read_result,
    write_request,
    write_result,
)
from worker.runner import OperationOutput, OperationRegistry, run_request


PROJECT_ID = UUID("10000000-0000-0000-0000-000000000001")
STRUCTURE_ID = UUID("20000000-0000-0000-0000-000000000002")
REQUEST_ID = UUID("30000000-0000-0000-0000-000000000003")


def project_with_structure():
    structure = Structure(
        id=STRUCTURE_ID,
        revision="structure-r1",
        atomic_numbers=(1,),
        coordinates=ArrayData(
            numpy.asarray([[0.0, 0.0, 0.0]]), ("atom", "xyz"), "angstrom"
        ),
    )
    project = QCProject(id=PROJECT_ID, schema_version="0.1")
    project.commit(ImportBatch(structures=(structure,)))
    return project


def request(project_locator="project.cbq", *, inputs=()):
    return WorkerRequest(
        request_id=REQUEST_ID,
        project_locator=project_locator,
        project_id=PROJECT_ID,
        project_schema_version="0.1",
        operation_id="test.operation",
        operation_version="1",
        inputs=inputs,
        parameters={"shape": [2, 3], "preview": True},
    )


class WorkerProtocolTests(unittest.TestCase):
    def test_request_round_trip_is_strict_and_canonical(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "request.json"
            original = request(
                inputs=(EntityReference(STRUCTURE_ID, "structure-r1"),)
            )
            write_request(path, original)
            first = path.read_bytes()
            self.assertEqual(read_request(path), original)
            write_request(path, original)
            self.assertEqual(path.read_bytes(), first)

            document = json.loads(path.read_text(encoding="utf-8"))
            document["unexpected"] = True
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(ProtocolError):
                read_request(path)

    def test_request_rejects_non_json_parameters_and_duplicate_inputs(self):
        with self.assertRaises(ProtocolError):
            replace(request(), parameters={"bad": float("nan")})
        reference = EntityReference(STRUCTURE_ID, "structure-r1")
        with self.assertRaises(ProtocolError):
            request(inputs=(reference, reference))

    def test_result_atomic_replace_preserves_previous_document(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            original = WorkerResult(REQUEST_ID, WorkerStatus.SUCCESS)
            write_result(path, original)
            previous = path.read_bytes()
            with patch(
                "ChemBlender.core.worker_protocol.os.replace",
                side_effect=OSError("disk full"),
            ):
                with self.assertRaises(OSError):
                    write_result(path, original)
            self.assertEqual(path.read_bytes(), previous)

    def test_runner_publishes_success_only_after_output_validation(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            save_project(root / "project.cbq", project_with_structure())
            request_path = root / "request.json"
            result_path = root / "result.json"
            write_request(
                request_path,
                request(inputs=(EntityReference(STRUCTURE_ID, "structure-r1"),)),
            )
            registry = OperationRegistry()
            registry.register(
                "test.operation",
                "1",
                lambda context, current: OperationOutput(
                    outputs=(EntityReference(STRUCTURE_ID, "structure-r1"),),
                    cache_key="a" * 64,
                ),
            )

            result = run_request(request_path, result_path, registry)
            self.assertEqual(result.status, WorkerStatus.SUCCESS)
            self.assertEqual(read_result(result_path), result)
            self.assertEqual(result.outputs[0].entity_id, STRUCTURE_ID)

    def test_runner_commits_operation_batch_before_success(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            save_project(root / "project.cbq", project_with_structure())
            request_path = root / "request.json"
            result_path = root / "result.json"
            write_request(request_path, request())
            dataset_id = UUID("40000000-0000-0000-0000-000000000004")
            dataset = PropertyDataset(
                id=dataset_id,
                revision="dataset-r1",
                semantic_role="test_value",
                domain="global",
                data=ArrayData(numpy.asarray([1.0]), ("value",), "dimensionless"),
                status=DatasetStatus.COMPLETE,
                source_calculation=None,
                provenance_ids=(),
            )
            batch = ImportBatch(datasets=(dataset,))
            registry = OperationRegistry()
            registry.register(
                "test.operation",
                "1",
                lambda context, current: OperationOutput(
                    outputs=(EntityReference(dataset_id, "dataset-r1"),),
                    cache_key="b" * 64,
                    batch=batch,
                ),
            )

            result = run_request(request_path, result_path, registry)
            self.assertEqual(result.status, WorkerStatus.SUCCESS)
            self.assertIn(dataset_id, open_project(root / "project.cbq").datasets)

    def test_failure_cancel_and_output_mismatch_never_publish_success(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            save_project(root / "project.cbq", project_with_structure())
            request_path = root / "request.json"
            write_request(request_path, request())

            failing = OperationRegistry()
            failing.register(
                "test.operation",
                "1",
                lambda context, current: (_ for _ in ()).throw(RuntimeError("boom")),
            )
            result_path = root / "failed.json"
            result = run_request(request_path, result_path, failing)
            self.assertEqual(result.status, WorkerStatus.ERROR)
            self.assertEqual(result.error.code, "operation_failed")
            self.assertNotIn("Traceback", result.error.message)

            called = []
            cancelled = OperationRegistry()
            cancelled.register(
                "test.operation",
                "1",
                lambda context, current: called.append(True),
            )
            cancel_path = root / "cancel"
            cancel_path.touch()
            result = run_request(
                request_path, root / "cancelled.json", cancelled, cancel_path=cancel_path
            )
            self.assertEqual(result.status, WorkerStatus.CANCELLED)
            self.assertEqual(called, [])

            mismatch = OperationRegistry()
            mismatch.register(
                "test.operation",
                "1",
                lambda context, current: OperationOutput(
                    outputs=(EntityReference(STRUCTURE_ID, "wrong-revision"),)
                ),
            )
            result = run_request(request_path, root / "mismatch.json", mismatch)
            self.assertEqual(result.status, WorkerStatus.ERROR)
            self.assertEqual(result.error.code, "output_validation_failed")

    def test_base_exception_crash_leaves_no_result(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            save_project(root / "project.cbq", project_with_structure())
            request_path = root / "request.json"
            result_path = root / "result.json"
            write_request(request_path, request())
            registry = OperationRegistry()
            registry.register(
                "test.operation",
                "1",
                lambda context, current: (_ for _ in ()).throw(SystemExit(9)),
            )
            with self.assertRaises(SystemExit):
                run_request(request_path, result_path, registry)
            self.assertFalse(result_path.exists())

    def test_cancellation_after_operation_does_not_commit_batch(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            save_project(root / "project.cbq", project_with_structure())
            request_path = root / "request.json"
            result_path = root / "result.json"
            cancel_path = root / "cancel"
            write_request(request_path, request())
            dataset_id = UUID("40000000-0000-0000-0000-000000000004")
            dataset = PropertyDataset(
                id=dataset_id,
                revision="dataset-r1",
                semantic_role="test_value",
                domain="global",
                data=ArrayData(numpy.asarray([1.0]), ("value",), "dimensionless"),
                status=DatasetStatus.COMPLETE,
                source_calculation=None,
                provenance_ids=(),
            )

            def cancel_during_operation(context, current):
                context.cancel_path.touch()
                return OperationOutput(
                    outputs=(EntityReference(dataset_id, "dataset-r1"),),
                    batch=ImportBatch(datasets=(dataset,)),
                )

            registry = OperationRegistry()
            registry.register("test.operation", "1", cancel_during_operation)
            result = run_request(
                request_path, result_path, registry, cancel_path=cancel_path
            )
            self.assertEqual(result.status, WorkerStatus.CANCELLED)
            self.assertNotIn(dataset_id, open_project(root / "project.cbq").datasets)

    def test_project_verify_runs_in_plain_python_subprocess(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            save_project(root / "project.cbq", project_with_structure())
            request_path = root / "request.json"
            result_path = root / "result.json"
            probe = request()
            probe = WorkerRequest(
                request_id=probe.request_id,
                project_locator=probe.project_locator,
                project_id=probe.project_id,
                project_schema_version=probe.project_schema_version,
                operation_id="project.verify",
                operation_version="1",
                inputs=(),
                parameters={},
            )
            write_request(request_path, probe)
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "worker.runner",
                    str(request_path),
                    str(result_path),
                ],
                check=True,
                cwd=Path(__file__).resolve().parents[1],
            )
            result = read_result(result_path)
            self.assertEqual(result.status, WorkerStatus.SUCCESS)
            self.assertEqual(result.request_id, REQUEST_ID)

    def test_default_registry_does_not_import_optional_backends(self):
        code = (
            "import sys; from worker.runner import default_registry; "
            "registry = default_registry(); "
            "registry.get('wavefunction.mo_grid', '1'); "
            "assert 'gbasis' not in sys.modules; assert 'pymatgen' not in sys.modules"
        )
        subprocess.run(
            [sys.executable, "-c", code],
            check=True,
            cwd=Path(__file__).resolve().parents[1],
        )

    def test_extension_client_launches_external_worker_without_blocking(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            sidecar = root / "project.cbq"
            save_project(sidecar, project_with_structure())
            original = request(str(sidecar))
            probe = WorkerRequest(
                request_id=original.request_id,
                project_locator=original.project_locator,
                project_id=original.project_id,
                project_schema_version=original.project_schema_version,
                operation_id="project.verify",
                operation_version="1",
                inputs=(),
                parameters={},
            )
            handle = start_worker(
                probe,
                root / "tasks",
                python_executable=sys.executable,
                working_directory=Path(__file__).resolve().parents[1],
            )
            result = handle.poll()
            if result is None:
                result = handle.wait(timeout=10)
            self.assertEqual(result.status, WorkerStatus.SUCCESS)
            self.assertTrue(handle.stdout_path.is_file())

            with self.assertRaises(WorkerProcessError):
                start_worker(
                    probe,
                    root / "tasks",
                    python_executable=sys.executable,
                    working_directory=Path(__file__).resolve().parents[1],
                )


if __name__ == "__main__":
    unittest.main()
