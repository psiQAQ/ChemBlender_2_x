import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import UUID, uuid4

import numpy

from cbq_core.model import QCProject
from cbq_core.sidecar import close_project
from cbq_core.sidecar import open_project
from cbq_core.sidecar import save_project
from cbq_core.worker_protocol import WorkerRequest
from cbq_core.worker_protocol import WorkerStatus
from cbq_core.worker_protocol import write_request
from chemblender_prepare.core import pyprocar_file as adapter
from tests.test_pyprocar_file import (
    FakeSurface, mocked_readers, mocked_surface, write_inputs,
)
from chemblender_prepare.worker.fermi_operation import register_fermi_surface_operation
from chemblender_prepare.worker.runner import OperationRegistry
from chemblender_prepare.worker.runner import run_request


class FermiWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        source = write_inputs(self.root / "inputs")
        self.artifacts = {path.name: {"path": path.relative_to(self.root).as_posix(),
                                     "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                          for path in source.iterdir()}
        self.project_path = self.root / "project.cbq"
        self.cancel_path = self.root / "cancel"
        project = QCProject(id=uuid4(), schema_version="0.1")
        self.project_id = project.id
        save_project(self.project_path, project)
        close_project(project)
        self.before = self.sidecar_bytes()

    def sidecar_bytes(self):
        return {path.relative_to(self.project_path).as_posix(): path.read_bytes()
                for path in self.project_path.rglob("*") if path.is_file()}

    def run_operation(self, artifacts=None, **parameters):
        request = WorkerRequest(
            request_id=uuid4(), project_locator=str(self.project_path),
            project_id=self.project_id, project_schema_version="0.1",
            operation_id="periodic.fermi_surface", operation_version="1", inputs=(),
            parameters={"source_artifacts": self.artifacts if artifacts is None else artifacts, **parameters},
        )
        request_path = self.root / "request.json"
        write_request(request_path, request)
        registry = OperationRegistry()
        register_fermi_surface_operation(registry)
        result = run_request(request_path, self.root / "result.json", registry, cancel_path=self.cancel_path)
        self.assertEqual(list(self.root.glob("fermi-text-*")), [])
        return result

    def test_success_publishes_linked_entities_and_source_hashes(self):
        # Adjacent third-party caches are never staged or opened.
        (self.root / "inputs/POTCAR").write_bytes(b"must not be opened")
        (self.root / "inputs/ebs.pkl").write_bytes(b"must not be unpickled")
        with mocked_readers(), mocked_surface():
            result = self.run_operation()
        self.assertIs(result.status, WorkerStatus.SUCCESS, result.error)
        reopened = open_project(self.project_path)
        self.addCleanup(close_project, reopened)
        self.assertEqual(len(reopened.datasets), 2)
        surface = reopened.datasets[UUID(result.metadata["fermi_surface_id"])]
        self.assertEqual(numpy.asarray(surface.band_indices.values).tolist(), [1, 3])
        self.assertEqual(surface.band_structure_id, UUID(result.metadata["band_structure_id"]))
        self.assertEqual(surface.structure_id, UUID(result.metadata["structure_id"]))
        self.assertEqual(len(result.outputs), 5)
        for provenance in reopened.provenance.values():
            self.assertEqual(provenance.source, "VASP text bundle")
            self.assertEqual(dict(provenance.parameters)["source_artifacts"], self.artifacts)

    def test_hash_mismatch_never_invokes_backend_or_mutates_project(self):
        artifacts = {**self.artifacts, "PROCAR": {**self.artifacts["PROCAR"], "sha256": "0" * 64}}
        with patch("chemblender_prepare.worker.fermi_operation.parse_vasp_fermi") as backend:
            result = self.run_operation(artifacts)
        backend.assert_not_called()
        self.assertIs(result.status, WorkerStatus.ERROR)
        self.assertEqual(result.error.code, "fermi_source_invalid")
        self.assertEqual(self.before, self.sidecar_bytes())

    def test_rejects_unlisted_file_path_escape_and_unrecognized_parameters(self):
        for artifacts, parameters in (
            ({**self.artifacts, "POTCAR": self.artifacts["PROCAR"]}, {}),
            ({**self.artifacts, "PROCAR": {**self.artifacts["PROCAR"], "path": "../PROCAR"}}, {}),
            (self.artifacts, {"fermi_shift": .5}),
        ):
            with self.subTest(parameters=parameters), patch("chemblender_prepare.worker.fermi_operation.parse_vasp_fermi") as backend:
                result = self.run_operation(artifacts, **parameters)
                self.assertIs(result.status, WorkerStatus.ERROR)
                backend.assert_not_called()
                self.assertEqual(self.before, self.sidecar_bytes())

    def test_numeric_failure_and_cancel_between_bands_publish_nothing(self):
        count = 0
        def failed(**kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise RuntimeError("second band failed")
            return FakeSurface(**kwargs)
        with mocked_readers(), patch.object(adapter, "_surface_backend", return_value=(failed, lambda *args: None)):
            result = self.run_operation()
        self.assertIs(result.status, WorkerStatus.ERROR)
        self.assertEqual(self.before, self.sidecar_bytes())
        def cancelled(**kwargs):
            self.cancel_path.touch()
            return FakeSurface(**kwargs)
        with mocked_readers(), patch.object(adapter, "_surface_backend", return_value=(cancelled, lambda *args: None)):
            result = self.run_operation()
        self.assertIs(result.status, WorkerStatus.CANCELLED)
        self.assertEqual(self.before, self.sidecar_bytes())


if __name__ == "__main__":
    unittest.main()
