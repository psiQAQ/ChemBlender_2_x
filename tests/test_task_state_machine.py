import builtins
import importlib.util
import math
import sys
from pathlib import Path
from threading import Event
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "ChemBlender" / "ui" / "tasks.py"


def load_tasks_without_bpy():
    name = "chemblender_task_state_without_bpy"
    spec = importlib.util.spec_from_file_location(name, TASKS)
    module = importlib.util.module_from_spec(spec)
    original_import = builtins.__import__

    def import_without_bpy(import_name, *args, **kwargs):
        if import_name == "bpy":
            raise AssertionError("ui.tasks must not import bpy")
        return original_import(import_name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=import_without_bpy):
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(name, None)
    return module


class TaskStateMachineTests(unittest.TestCase):
    def setUp(self):
        self.tasks = load_tasks_without_bpy()

    def test_running_task_reports_monotonic_stage_progress(self):
        task = self.tasks.Task()

        task.start("hash")
        task.progress("hash", 0.25)
        task.progress_event("sdf.index", 1, 2)

        snapshot = task.snapshot()
        self.assertIs(snapshot.state, self.tasks.TaskState.RUNNING)
        self.assertEqual(snapshot.stage, "sdf.index")
        self.assertEqual(snapshot.progress, 0.5)
        with self.assertRaisesRegex(ValueError, "monotonic"):
            task.progress("parse", 0.49)
        with self.assertRaisesRegex(ValueError, "finite"):
            task.progress("parse", math.nan)

    def test_invalid_transitions_are_rejected(self):
        task = self.tasks.Task()

        with self.assertRaisesRegex(RuntimeError, "pending"):
            task.succeed("complete")
        task.start("hash")
        task.succeed("complete")
        with self.assertRaisesRegex(RuntimeError, "succeeded"):
            task.request_cancel()

    def test_cancellation_wins_over_late_worker_success(self):
        task = self.tasks.Task()

        task.start("vdb.prepare")
        task.progress("vdb.prepare", 0.75)
        task.request_cancel()
        task.cancel()

        snapshot = task.snapshot()
        self.assertIs(snapshot.state, self.tasks.TaskState.CANCELLED)
        self.assertTrue(task.is_cancelled())
        self.assertEqual(snapshot.progress, 0.75)
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            task.succeed("complete")

    def test_event_adapter_keeps_nested_stage_events_monotonic(self):
        task = self.tasks.Task()
        adapter = self.tasks.TaskProgressAdapter(task)

        task.start("preflight")
        adapter("hash", 1, 3)
        first = task.snapshot().progress
        adapter("reader.parse", 0, 1)
        adapter("reader.parse", 1, 1)

        snapshot = task.snapshot()
        self.assertGreater(first, 0.0)
        self.assertGreaterEqual(snapshot.progress, first)
        self.assertLess(snapshot.progress, 1.0)
        self.assertEqual(snapshot.stage, "reader.parse")

    def test_worker_runs_pure_callback_and_finishes_cancelled(self):
        task = self.tasks.Task()
        reached_worker = Event()

        def prepare(cancelled, progress):
            progress("vdb.prepare", 0.25)
            reached_worker.set()
            while not cancelled():
                pass
            return "cancelled"

        worker = self.tasks.TaskWorker(task, prepare)
        worker.start("vdb.prepare")
        self.assertTrue(reached_worker.wait(1))
        task.request_cancel()
        self.assertTrue(worker.join(1))

        self.assertEqual(worker.result, "cancelled")
        self.assertIs(task.snapshot().state, self.tasks.TaskState.CANCELLED)

    def test_worker_cancel_request_is_safe_after_completion(self):
        task = self.tasks.Task()
        worker = self.tasks.TaskWorker(task, lambda _cancelled, _progress: None)

        worker.start("vdb.prepare")
        self.assertTrue(worker.join(1))

        snapshot = worker.request_cancel()
        self.assertIs(snapshot.state, self.tasks.TaskState.SUCCEEDED)


if __name__ == "__main__":
    unittest.main()
