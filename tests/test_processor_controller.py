"""Viewer-side unified processor lifecycle and trust-boundary contracts."""

from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from cbq_core.model import QCProject
from cbq_core.sidecar import save_project
from cbq_core.worker_protocol import (
    WorkerRequest,
    WorkerResult,
    WorkerStatus,
    write_result,
)
from ChemBlender.ui.processor import (
    ProcessorError,
    ProcessorState,
    create_task_directory,
    start_capability_test,
    start_worker,
)


ROOT = Path(__file__).resolve().parents[1]
PROCESSOR = ROOT / ".venv" / "Scripts" / "chemblender-prepare.exe"


def wait_for(task, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = task.poll()
        if snapshot.state in {
            ProcessorState.SUCCEEDED,
            ProcessorState.CANCELLED,
            ProcessorState.FAILED,
        }:
            return snapshot
        time.sleep(.02)
    raise AssertionError("processor task did not finish")


class ProcessorControllerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(prefix="processor-controller-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def worker_request(self, task_directory, request_id=None):
        project = QCProject(id=uuid4(), schema_version="1.1")
        sidecar = task_directory / "project.cbq"
        save_project(sidecar, project)
        return WorkerRequest(
            request_id=request_id or uuid4(),
            project_locator=str(sidecar),
            project_id=project.id,
            project_schema_version=project.schema_version,
            operation_id="project.verify",
            operation_version="1",
            inputs=(),
            parameters={},
        )

    @unittest.skipUnless(PROCESSOR.is_file(), "project processor launcher required")
    def test_real_capability_and_worker_use_one_executable_without_blocking(self):
        started = time.perf_counter()
        capability = start_capability_test(PROCESSOR, self.root)
        launch_elapsed = time.perf_counter() - started
        self.assertLess(launch_elapsed, .1)
        snapshot = wait_for(capability)
        self.assertIs(snapshot.state, ProcessorState.SUCCEEDED)
        self.assertEqual(snapshot.result["schema_name"],
                         "chemblender_prepare_capabilities")
        self.assertEqual(snapshot.result["worker_protocol_version"], "1")

        identity = uuid4()
        task_directory = create_task_directory(self.root, identity)
        request = self.worker_request(task_directory, identity)
        worker = start_worker(PROCESSOR, task_directory, request)
        snapshot = wait_for(worker)
        self.assertIs(snapshot.state, ProcessorState.SUCCEEDED)
        self.assertIs(snapshot.result.status, WorkerStatus.SUCCESS)
        self.assertEqual(snapshot.result.request_id, identity)

    def test_paths_are_absolute_and_frozen_project_stays_in_owned_task(self):
        with self.assertRaisesRegex(ProcessorError, "absolute"):
            start_capability_test(Path("processor.exe"), self.root)
        with self.assertRaisesRegex(ProcessorError, "does not exist"):
            start_capability_test(self.root / "missing.exe", self.root)

        executable = self.root / "processor.exe"
        executable.touch()
        identity = uuid4()
        task_directory = create_task_directory(self.root, identity)
        outside = self.root / "outside.cbq"
        save_project(outside, QCProject(id=uuid4(), schema_version="1.1"))
        request = WorkerRequest(
            identity, str(outside), uuid4(), "1.1", "project.verify", "1", (), {}
        )
        with patch("ChemBlender.ui.processor.subprocess.Popen") as launch:
            with self.assertRaisesRegex(ProcessorError, "inside the task"):
                start_worker(executable, task_directory, request)
            launch.assert_not_called()

    def test_cancel_marker_waits_two_seconds_then_terminates_owned_tree(self):
        executable = self.root / "processor.exe"
        executable.touch()
        identity = uuid4()
        task_directory = create_task_directory(self.root, identity)
        request = self.worker_request(task_directory, identity)
        process = Mock(pid=7341)
        process.poll.return_value = None
        with patch("ChemBlender.ui.processor.subprocess.Popen", return_value=process) as launch, \
                patch("ChemBlender.ui.processor.monotonic", side_effect=(2., 4.01)), \
                patch("ChemBlender.ui.processor._terminate_process_tree") as terminate:
            worker = start_worker(executable, task_directory, request)
            self.assertIs(worker.request_cancel().state, ProcessorState.CANCELLING)
            self.assertTrue((task_directory / "cancel").is_file())
            snapshot = worker.poll()
        self.assertIs(snapshot.state, ProcessorState.CANCELLED)
        terminate.assert_called_once_with(process)
        command = launch.call_args.args[0]
        self.assertEqual(command[:2], [str(executable.resolve()), "worker"])
        self.assertFalse(launch.call_args.kwargs["shell"])

    def test_wrong_result_identity_and_late_success_fail_closed(self):
        executable = self.root / "processor.exe"
        executable.touch()
        identity = uuid4()
        task_directory = create_task_directory(self.root, identity)
        request = self.worker_request(task_directory, identity)
        process = Mock(pid=7342)
        process.poll.return_value = 0
        with patch("ChemBlender.ui.processor.subprocess.Popen", return_value=process):
            worker = start_worker(executable, task_directory, request)
            write_result(task_directory / "result.json",
                         WorkerResult(uuid4(), WorkerStatus.SUCCESS))
            snapshot = worker.poll()
        self.assertIs(snapshot.state, ProcessorState.FAILED)
        self.assertIn("identity", snapshot.error)

        second_identity = uuid4()
        second = create_task_directory(self.root, second_identity)
        request = self.worker_request(second, second_identity)
        with patch("ChemBlender.ui.processor.subprocess.Popen", return_value=process):
            worker = start_worker(executable, second, request)
            worker.request_cancel()
            write_result(second / "result.json",
                         WorkerResult(request.request_id, WorkerStatus.SUCCESS))
            snapshot = worker.poll()
        self.assertIs(snapshot.state, ProcessorState.CANCELLED)
        self.assertIsNone(snapshot.result)

        third_identity = uuid4()
        third = create_task_directory(self.root, third_identity)
        request = self.worker_request(third, third_identity)
        failed_process = Mock(pid=7343)
        failed_process.poll.return_value = 7
        with patch("ChemBlender.ui.processor.subprocess.Popen",
                   return_value=failed_process):
            worker = start_worker(executable, third, request)
            write_result(third / "result.json",
                         WorkerResult(request.request_id, WorkerStatus.SUCCESS))
            snapshot = worker.poll()
        self.assertIs(snapshot.state, ProcessorState.FAILED)
        self.assertIn("code 7", snapshot.error)

if __name__ == "__main__":
    unittest.main()
