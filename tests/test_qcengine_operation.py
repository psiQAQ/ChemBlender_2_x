import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import UUID

from ChemBlender.core import QCProject, open_project, save_project
from ChemBlender.core.worker_protocol import WorkerRequest, WorkerStatus, write_request

from worker.qcengine_operation import (
    QCSchemaExecutionError,
    execute_qcschema,
    qcschema_compute_operation,
)
from worker.runner import default_registry, run_request


FIXTURES = Path(__file__).parent / "fixtures" / "qcschema"


def atomic_input_v2():
    result = json.loads((FIXTURES / "atomic_result_v2.json").read_text(encoding="utf-8"))
    return result["input_data"]


def atomic_result_v2():
    return json.loads((FIXTURES / "atomic_result_v2.json").read_text(encoding="utf-8"))


class QCSchemaExecutionTests(unittest.TestCase):
    def test_qcengine_success_uses_reviewed_compute_contract(self):
        calls = []

        def compute(input_data, program, **kwargs):
            calls.append((input_data, program, kwargs))
            return atomic_result_v2()

        result = execute_qcschema(
            {
                "backend": "qcengine",
                "input_data": atomic_input_v2(),
                "program": "psi4",
                "return_version": 2,
                "task_config": {"ncores": 2, "memory": 1.5, "retries": 0},
            },
            qcengine_compute=compute,
        )

        self.assertTrue(result["success"])
        self.assertEqual(calls[0][1], "psi4")
        self.assertEqual(
            calls[0][2],
            {
                "raise_error": False,
                "return_dict": True,
                "return_version": 2,
                "task_config": {"memory": 1.5, "ncores": 2, "retries": 0},
            },
        )

    def test_validation_rejects_uncontrolled_configuration_and_embedded_override(self):
        request = {
            "backend": "qcengine",
            "input_data": atomic_input_v2(),
            "program": "psi4",
            "return_version": 2,
            "task_config": {"mpiexec_command": "anything"},
        }
        with self.assertRaisesRegex(QCSchemaExecutionError, "task_config") as caught:
            execute_qcschema(request, qcengine_compute=lambda *args, **kwargs: {})
        self.assertEqual(caught.exception.code, "invalid_input")

        request["task_config"] = {}
        request["input_data"]["specification"]["extras"]["_qcengine_local_config"] = {
            "ncores": 99
        }
        with self.assertRaises(QCSchemaExecutionError) as caught:
            execute_qcschema(request, qcengine_compute=lambda *args, **kwargs: {})
        self.assertEqual(caught.exception.code, "invalid_input")

    def test_dependency_missing_and_failed_operation_have_stable_codes(self):
        request = {
            "backend": "qcengine",
            "input_data": atomic_input_v2(),
            "program": "missing-program",
            "return_version": 2,
            "task_config": {},
        }
        with patch("worker.qcengine_operation._load_qcengine_compute", side_effect=ImportError):
            with self.assertRaises(QCSchemaExecutionError) as caught:
                execute_qcschema(request)
        self.assertEqual(caught.exception.code, "dependency_missing")

        failed = {
            "schema_name": "qcschema_failed_operation",
            "schema_version": 2,
            "success": False,
            "error": {
                "error_type": "input_error",
                "error_message": "Program missing-program is not registered.",
            },
        }
        with self.assertRaises(QCSchemaExecutionError) as caught:
            execute_qcschema(request, qcengine_compute=lambda *args, **kwargs: failed)
        self.assertEqual(caught.exception.code, "calculation_failed")
        self.assertNotIn("Traceback", str(caught.exception))

    def test_pyscf_adapter_is_energy_only_and_returns_qcschema_v2(self):
        class FakeMolecule:
            nelec = (1, 1)

        class FakeSCF:
            converged = True

            def kernel(self):
                return -1.1

        calls = []

        class FakeGTO:
            @staticmethod
            def M(**kwargs):
                calls.append(kwargs)
                return FakeMolecule()

        class FakeSCFModule:
            @staticmethod
            def RHF(molecule):
                return FakeSCF()

            @staticmethod
            def UHF(molecule):
                raise AssertionError("closed-shell HF must use RHF")

        class FakePySCF:
            __version__ = "2.test"
            gto = FakeGTO
            scf = FakeSCFModule

        request = {
            "backend": "pyscf",
            "input_data": atomic_input_v2(),
            "program": "pyscf",
            "return_version": 2,
            "task_config": {"ncores": 1},
        }
        request["input_data"]["specification"]["driver"] = "energy"
        request["input_data"]["specification"]["model"] = {
            "method": "HF",
            "basis": "sto-3g",
        }
        request["input_data"]["specification"]["keywords"] = {}
        result = execute_qcschema(request, pyscf_module=FakePySCF)

        self.assertEqual(result["schema_name"], "qcschema_atomic_result")
        self.assertEqual(result["return_result"], -1.1)
        self.assertEqual(result["provenance"]["creator"], "PySCF")
        self.assertEqual(calls[0]["unit"], "Bohr")
        self.assertEqual(calls[0]["spin"], 0)

    def test_operation_writes_result_artifact_and_returns_normalized_batch(self):
        class Context:
            project_path = None

        with TemporaryDirectory() as directory:
            Context.project_path = Path(directory) / "project.cbq"
            Context.project_path.mkdir()
            request = type(
                "Request",
                (),
                {
                    "parameters": {
                        "backend": "qcengine",
                        "input_data": atomic_input_v2(),
                        "program": "psi4",
                        "return_version": 2,
                        "task_config": {},
                    }
                },
            )()
            with patch(
                "worker.qcengine_operation._load_qcengine_compute",
                return_value=lambda *args, **kwargs: atomic_result_v2(),
            ):
                output = qcschema_compute_operation(Context(), request)

            self.assertEqual(len(output.batch.calculations), 1)
            self.assertEqual(len(output.batch.qcschema_envelopes), 1)
            self.assertEqual(len(output.artifacts), 1)
            self.assertTrue((Context.project_path / output.artifacts[0]).is_file())
            self.assertEqual(output.metadata["backend"], "qcengine")

    def test_runner_commits_success_and_maps_failure_and_cancellation(self):
        project_id = UUID("10000000-0000-0000-0000-000000000010")
        request_id = UUID("30000000-0000-0000-0000-000000000030")
        parameters = {
            "backend": "qcengine",
            "input_data": atomic_input_v2(),
            "program": "psi4",
            "return_version": 2,
            "task_config": {},
        }
        with TemporaryDirectory() as directory:
            root = Path(directory)
            save_project(root / "project.cbq", QCProject(project_id, "0.1"))
            request = WorkerRequest(
                request_id=request_id,
                project_locator="project.cbq",
                project_id=project_id,
                project_schema_version="0.1",
                operation_id="qcschema.compute",
                operation_version="1",
                inputs=(),
                parameters=parameters,
            )
            request_path = root / "request.json"
            write_request(request_path, request)

            with patch(
                "worker.qcengine_operation._load_qcengine_compute",
                return_value=lambda *args, **kwargs: atomic_result_v2(),
            ):
                result = run_request(request_path, root / "success.json", default_registry())
            self.assertEqual(result.status, WorkerStatus.SUCCESS)
            self.assertEqual(len(open_project(root / "project.cbq").calculations), 1)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            save_project(root / "project.cbq", QCProject(project_id, "0.1"))
            request_path = root / "request.json"
            write_request(request_path, request)
            failed = {
                "schema_name": "qcschema_failed_operation",
                "schema_version": 2,
                "success": False,
                "error": {"error_type": "input_error", "error_message": "missing program"},
            }
            with patch(
                "worker.qcengine_operation._load_qcengine_compute",
                return_value=lambda *args, **kwargs: failed,
            ):
                result = run_request(request_path, root / "failed.json", default_registry())
            self.assertEqual(result.status, WorkerStatus.ERROR)
            self.assertEqual(result.error.code, "calculation_failed")
            self.assertEqual(len(open_project(root / "project.cbq").calculations), 0)

            cancel_path = root / "cancel"
            cancel_path.touch()
            with patch("worker.qcengine_operation._load_qcengine_compute") as load:
                result = run_request(
                    request_path,
                    root / "cancelled.json",
                    default_registry(),
                    cancel_path=cancel_path,
                )
            self.assertEqual(result.status, WorkerStatus.CANCELLED)
            load.assert_not_called()


if __name__ == "__main__":
    unittest.main()
