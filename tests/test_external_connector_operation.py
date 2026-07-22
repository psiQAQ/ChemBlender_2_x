import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from ChemBlender.core import (
    QCProject,
    external_record_request_document,
    ExternalRecordRequest,
    open_project,
    save_project,
)
from ChemBlender.core.worker_protocol import WorkerRequest, WorkerStatus, write_request
from worker.connector_operation import external_record_operation
from worker.operation import OperationContext, OperationError
from worker.runner import default_registry, run_request


FIXTURE = Path(__file__).parent / "fixtures" / "qcschema" / "atomic_result_v2.json"


def connector_request():
    return ExternalRecordRequest(
        provider="qcarchive",
        connector_version="1",
        locator=(("server_url", "https://archive.example.org"), ("record_id", "42")),
        envelope_type="qcschema",
        authentication_ref=None,
    )


class ExternalConnectorOperationTests(unittest.TestCase):
    def test_offline_fixture_replays_through_existing_qcschema_adapter(self):
        with TemporaryDirectory() as directory:
            project_path = Path(directory) / "project.cbq"
            project = QCProject(uuid4(), "0.1")
            save_project(project_path, project)
            source = project_path / "sources" / "record.json"
            source.parent.mkdir()
            source.write_bytes(FIXTURE.read_bytes())
            request = type("Request", (), {"parameters": {
                "connector_request": external_record_request_document(connector_request()),
                "transport": "offline_fixture",
                "offline_fixture": "sources/record.json",
            }})()
            output = external_record_operation(
                OperationContext(project_path, project, None), request
            )
            self.assertEqual(len(output.batch.calculations), 1)
            self.assertTrue(output.artifacts[0].startswith("cache/external-record/"))
            self.assertEqual(output.metadata["source_uri"], "qcarchive://record/42")
            self.assertNotIn("offline_fixture", output.metadata)
            for provenance in output.batch.provenance:
                self.assertEqual(provenance.source, "qcarchive://record/42")
                self.assertFalse(Path(provenance.source).is_absolute())

    def test_runner_commits_replay_and_uses_stable_provider_errors(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            project_path = root / "project.cbq"
            project = QCProject(uuid4(), "0.1")
            save_project(project_path, project)
            source = project_path / "sources" / "record.json"
            source.parent.mkdir()
            source.write_bytes(FIXTURE.read_bytes())
            parameters = {
                "connector_request": external_record_request_document(connector_request()),
                "transport": "offline_fixture",
                "offline_fixture": "sources/record.json",
            }
            request = WorkerRequest(
                request_id=uuid4(), project_locator="project.cbq", project_id=project.id,
                project_schema_version="0.1", operation_id="external_record.fetch",
                operation_version="1", inputs=(), parameters=parameters,
            )
            request_path = root / "request.json"
            write_request(request_path, request)
            result = run_request(request_path, root / "result.json", default_registry())
            self.assertEqual(result.status, WorkerStatus.SUCCESS)
            loaded = open_project(project_path)
            self.assertEqual(len(loaded.calculations), 1)
            self.assertTrue(all(not Path(item.source).is_absolute() for item in loaded.provenance.values()))

            provider_request = type("Request", (), {"parameters": {
                "connector_request": external_record_request_document(
                    ExternalRecordRequest(
                        provider="qcarchive", connector_version="1",
                        locator=(("server_url", "https://archive.example.org"), ("record_id", "42")),
                        envelope_type="qcschema", authentication_ref="env:CB_MISSING_TEST_TOKEN",
                    )
                ),
                "transport": "provider",
            }})()
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(OperationError, "authentication") as caught:
                    external_record_operation(
                        OperationContext(project_path, loaded, None), provider_request
                    )
            self.assertEqual(caught.exception.code, "authentication_missing")

            no_auth = dict(provider_request.parameters)
            no_auth["connector_request"] = external_record_request_document(connector_request())
            provider_request.parameters = no_auth
            with self.assertRaises(OperationError) as caught:
                external_record_operation(
                    OperationContext(project_path, loaded, None), provider_request
                )
            self.assertEqual(caught.exception.code, "dependency_missing")


if __name__ == "__main__":
    unittest.main()
