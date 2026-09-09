"""Unified processor entrypoints and environment routing."""

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from cbq_core.model import QCProject
from cbq_core.sidecar import save_project
from cbq_core.worker_protocol import (
    WorkerRequest,
    WorkerResult,
    WorkerStatus,
    read_result,
    write_request,
    write_result,
)
from chemblender_prepare.cli import main
from chemblender_prepare.runtime import (
    capability_document,
    doctor_document,
    load_configuration,
    request_environment,
    run_worker,
)


class PrepareRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix="prepare-runtime-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def configuration(self):
        path = self.root / "prepare.json"
        path.write_text(json.dumps({
            "schema_version": "1",
            "python": {
                "wavefunction": sys.executable,
                "scientific": sys.executable,
                "fermi": sys.executable,
            },
            "critic2": str(self.root / "critic2"),
        }), encoding="utf-8")
        return path

    def request(self, operation="project.verify", parameters=None):
        project = QCProject(id=uuid4(), schema_version="1.1")
        sidecar = self.root / "project.cbq"
        save_project(sidecar, project)
        request = WorkerRequest(
            request_id=uuid4(),
            project_locator=str(sidecar),
            project_id=project.id,
            project_schema_version=project.schema_version,
            operation_id=operation,
            operation_version="1",
            inputs=(),
            parameters=parameters or {},
        )
        path = self.root / "request.json"
        write_request(path, request)
        return path, request

    def test_strict_configuration_routes_only_declared_worker_families(self):
        configuration = load_configuration(self.configuration())
        self.assertEqual(request_environment(self.request("wavefunction.mo_grid")[1]), "wavefunction")
        self.assertEqual(request_environment(self.request("periodic.fermi_surface")[1]), "fermi")
        self.assertEqual(request_environment(self.request("periodic.phonon")[1]), "scientific")
        self.assertEqual(request_environment(self.request("topology.qtaim")[1]), "current")
        reader = self.request("reader.parse", {"reader_id": "pymatgen-vasp-grid"})[1]
        self.assertEqual(request_environment(reader), "scientific")
        builtin = self.request("reader.parse", {"reader_id": "cube"})[1]
        self.assertEqual(request_environment(builtin), "current")
        self.assertEqual(configuration["schema_version"], "1")
        invalid = self.root / "invalid.json"
        invalid.write_text('{"schema_version":"1","python":{},"extra":true}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "configuration fields"):
            load_configuration(invalid)

        request_path, request = self.request("wavefunction.mo_grid")
        result_path = self.root / "unconfigured-result.json"
        result = run_worker(request_path, result_path)
        self.assertEqual(result.request_id, request.request_id)
        self.assertEqual(result.error.code, "environment_unavailable")
        capabilities = capability_document()
        operations = {item["operation_id"]: item
                      for item in capabilities["operations"]}
        self.assertFalse(operations["wavefunction.mo_grid"]["available"])
        self.assertEqual(operations["wavefunction.mo_grid"]["reason"],
                         "not configured")

    def test_capabilities_are_versioned_and_use_live_backend_probes(self):
        probe = {
            "available": True,
            "python_version": "3.12.13",
            "executable": sys.executable,
            "versions": {"numpy": "1.26.4", "qc-gbasis": "0.1.0",
                         "qc-iodata": "1.0.1", "phonopy": "4.4.0"},
            "error": None,
        }
        critic = {"available": True, "version": "1.3.15", "error": None}
        with patch("chemblender_prepare.runtime._probe_python", return_value=probe), \
                patch("chemblender_prepare.runtime._probe_critic2", return_value=critic):
            document = capability_document(load_configuration(self.configuration()))
        self.assertEqual(document["schema_name"], "chemblender_prepare_capabilities")
        self.assertEqual(document["schema_version"], "1")
        self.assertEqual(document["worker_protocol_version"], "1")
        operations = {(item["operation_id"], item["operation_version"]): item
                      for item in document["operations"]}
        self.assertTrue(operations[("wavefunction.mo_grid", "1")]["available"])
        self.assertEqual(operations[("wavefunction.mo_grid", "1")]["backend_versions"],
                         {"qc-gbasis": "0.1.0"})
        self.assertTrue(operations[("project.verify", "1")]["available"])
        self.assertEqual(operations[("topology.qtaim", "1")]["backend_versions"],
                         {"critic2": "1.3.15"})
        self.assertEqual(operations[("periodic.phonon", "1")]["backend_versions"],
                         {"phonopy": "4.4.0"})
        readers = {item["reader_id"]: item for item in document["readers"]}
        self.assertEqual(len(readers), 22)
        self.assertEqual(readers["iodata_wavefunction"]["environment"], "wavefunction")
        self.assertEqual(readers["iodata_wavefunction"]["backend_versions"],
                         {"qc-iodata": "1.0.1"})

        stream = io.StringIO()
        with patch("chemblender_prepare.runtime._probe_python", return_value=probe), \
                patch.dict(os.environ, {"CHEMBLENDER_PREPARE_CONFIG": str(self.configuration())}), \
                redirect_stdout(stream):
            self.assertEqual(main(["capabilities", "--json"]), 0)
        self.assertEqual(json.loads(stream.getvalue())["schema_name"],
                         "chemblender_prepare_capabilities")

    def test_unified_worker_replays_existing_protocol_and_honours_cancel(self):
        request_path, request = self.request()
        result_path = self.root / "result.json"
        self.assertEqual(main(["worker", str(request_path), str(result_path)]), 0)
        result = read_result(result_path)
        self.assertEqual(result.request_id, request.request_id)
        self.assertIs(result.status, WorkerStatus.SUCCESS)

        cancelled_path, cancelled = self.request()
        cancelled_result = self.root / "cancelled.json"
        marker = self.root / "cancel"
        marker.touch()
        self.assertEqual(main(["worker", str(cancelled_path), str(cancelled_result),
                               "--cancel-file", str(marker)]), 1)
        result = read_result(cancelled_result)
        self.assertEqual(result.request_id, cancelled.request_id)
        self.assertIs(result.status, WorkerStatus.CANCELLED)

    def test_routed_worker_rejects_a_mismatched_result_identity(self):
        request_path, request = self.request("wavefunction.mo_grid")
        result_path = self.root / "routed-result.json"
        executable = self.root / "python.exe"
        executable.touch()
        configuration = {"schema_version": "1", "python": {
            "wavefunction": str(executable)}, "critic2": None}

        def routed(_command, **_kwargs):
            write_result(result_path, WorkerResult(uuid4(), WorkerStatus.SUCCESS))
            return SimpleNamespace(returncode=0)

        with patch("chemblender_prepare.runtime.subprocess.run", side_effect=routed):
            result = run_worker(request_path, result_path, configuration=configuration)
        self.assertEqual(result.request_id, request.request_id)
        self.assertIs(result.status, WorkerStatus.ERROR)
        self.assertEqual(result.error.code, "result_identity_mismatch")
        self.assertEqual(read_result(result_path), result)

    def test_doctor_checks_routes_task_directory_and_critic2_without_installing(self):
        probe = {"available": True, "python_version": "3.12.13",
                 "executable": sys.executable, "versions": {"numpy": "1.26.4"},
                 "error": None}
        critic = {"available": False, "version": None, "error": "not executable"}
        with patch("chemblender_prepare.runtime._probe_python", return_value=probe), \
                patch("chemblender_prepare.runtime._probe_critic2", return_value=critic):
            document = doctor_document(load_configuration(self.configuration()), self.root)
        self.assertEqual(document["schema_name"], "chemblender_prepare_doctor")
        checks = {item["id"]: item for item in document["checks"]}
        self.assertEqual(checks["task_directory"]["status"], "passed")
        self.assertEqual(checks["critic2"]["status"], "warning")
        self.assertIn("Configure", checks["critic2"]["fix"])


if __name__ == "__main__":
    unittest.main()
