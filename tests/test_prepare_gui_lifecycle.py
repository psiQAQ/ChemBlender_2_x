"""Ownership and failure recovery for the real external GUI task boundary."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from chemblender_prepare.gui import CliProcess, PrepareWindow


class PrepareGuiLifecycleTests(unittest.TestCase):
    def window(self, job):
        window = PrepareWindow.__new__(PrepareWindow)
        window.job, window.closing = job, False
        window.root, window.status, window.bar, window.report, window.run_button = (Mock() for _ in range(5))
        return window

    def test_cancel_deadline_terminates_only_owned_live_process_and_waits_for_exit(self):
        import chemblender_prepare.gui as gui
        process = Mock(poll=Mock(return_value=None))
        with patch.object(gui.subprocess, "Popen", return_value=process), patch.object(gui.time, "monotonic", return_value=10.0) as clock:
            job = CliProcess(["formats"])
            try:
                job.cancel()
                clock.return_value = 11.99
                job.cancel()  # Repeated clicks must not postpone the deadline.
                self.assertIsNone(job.poll())
                process.terminate.assert_not_called()
                clock.return_value = 12.0
                self.assertIsNone(job.poll())
                process.terminate.assert_called_once_with()
                self.assertIsNone(job.poll())
                process.terminate.assert_called_once_with()
                with self.assertRaisesRegex(RuntimeError, "wait for the owned process"):
                    job.close()
                self.assertTrue(job.root.exists())
                process.poll.return_value = 1
                with self.assertRaisesRegex(RuntimeError, "no final result"):
                    job.poll()
            finally:
                process.poll.return_value = 1
                job.close()
            self.assertFalse(job.root.exists())

    def test_real_unresponsive_cli_exits_without_stopping_another_process(self):
        import subprocess
        import sys
        import time
        import chemblender_prepare.gui as gui
        launch = subprocess.Popen
        sleeping = [sys.executable, "-c", "import time; time.sleep(30)"]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        other = launch(sleeping, creationflags=flags)
        job = None
        try:
            def unresponsive(argv, **kwargs):
                return launch(sleeping, **kwargs)
            with patch.object(gui.subprocess, "Popen", side_effect=unresponsive):
                job = CliProcess(["formats"])
            started = time.monotonic()
            job.cancel()
            deadline = started + 5.0
            while time.monotonic() < deadline:
                try:
                    job.poll()
                except RuntimeError as error:
                    self.assertIn("no final result", str(error))
                    break
                time.sleep(0.02)
            else:
                self.fail("Owned unresponsive process did not exit")
            self.assertGreaterEqual(time.monotonic() - started, 2.0)
            self.assertIsNotNone(job.process.poll())
            self.assertIsNone(other.poll())
            job.close()
            self.assertFalse(job.root.exists())
        finally:
            if job is not None and job.process.poll() is None:
                job.process.kill()
                job.process.wait(timeout=5)
            if job is not None:
                job.close()
            other.terminate()
            other.wait(timeout=5)

    def test_completed_result_wins_over_pending_cancellation(self):
        import chemblender_prepare.gui as gui
        process = Mock(poll=Mock(return_value=0))
        result = object()
        with patch.object(gui.subprocess, "Popen", return_value=process), patch.object(gui.time, "monotonic", side_effect=[10.0]), patch.object(gui, "read_result", return_value=result):
            job = CliProcess(["formats"])
            try:
                job.cancel()
                job.task.mkdir()
                (job.task / "result.json").touch()
                self.assertIs(job.poll(), result)
                process.terminate.assert_not_called()
            finally:
                job.close()

    def test_log_open_failure_closes_prior_stream_and_task(self):
        import chemblender_prepare.gui as gui
        with TemporaryDirectory() as parent:
            temporary = TemporaryDirectory(dir=parent)
            task_root = Path(temporary.name)
            actual_open = Path.open
            opened = []
            error = OSError("stderr unavailable")
            def open_log(path, *args, **kwargs):
                if path.name == "stderr.log":
                    raise error
                stream = actual_open(path, *args, **kwargs)
                opened.append(stream)
                return stream
            with patch.object(gui, "TemporaryDirectory", return_value=temporary), patch.object(Path, "open", open_log), patch.object(gui.subprocess, "Popen") as launch:
                with self.assertRaises(OSError) as caught:
                    CliProcess(["formats"])
            self.assertIs(caught.exception, error)
            launch.assert_not_called()
            self.assertTrue(all(stream.closed for stream in opened))
            self.assertFalse(task_root.exists())

    def test_process_start_failure_closes_owned_logs_and_task(self):
        import chemblender_prepare.gui as gui
        failures = (FileNotFoundError("processor missing"), KeyboardInterrupt(),
                    GeneratorExit(), MemoryError("launch exhausted memory"))
        for error in failures:
            with self.subTest(error=type(error).__name__), TemporaryDirectory() as parent:
                temporary = TemporaryDirectory(dir=parent)
                task_root = Path(temporary.name)
                streams = []
                def fail(argv, **kwargs):
                    self.assertTrue(task_root.is_dir())
                    streams.extend((kwargs["stdout"], kwargs["stderr"]))
                    self.assertTrue(all(not stream.closed for stream in streams))
                    self.assertEqual(argv[0], "processor with spaces.exe")
                    self.assertFalse(kwargs.get("shell", False))
                    raise error
                with patch.object(gui, "TemporaryDirectory", return_value=temporary), \
                     patch.object(gui.subprocess, "Popen", side_effect=fail) as launch:
                    with self.assertRaises(type(error)) as caught:
                        CliProcess(["formats"], python_executable="processor with spaces.exe")
                self.assertIs(caught.exception, error)
                launch.assert_called_once()
                self.assertTrue(all(stream.closed for stream in streams))
                self.assertFalse(task_root.exists())

    def test_fatal_result_cleanup_preserves_exception(self):
        error = GeneratorExit("result failed")
        job = SimpleNamespace(poll=Mock(side_effect=error), process=SimpleNamespace(poll=Mock(return_value=1)), close=Mock())
        window = self.window(job)
        with self.assertRaises(GeneratorExit) as caught:
            window.poll()
        self.assertIs(caught.exception, error)
        job.close.assert_called_once_with()
        self.assertIsNone(window.job)
        window.poll()  # A queued stale timer must not release a second time.
        job.close.assert_called_once_with()

    def test_report_widget_failure_does_not_retain_finished_task(self):
        job = SimpleNamespace(poll=Mock(side_effect=RuntimeError("no result")), process=SimpleNamespace(poll=Mock(return_value=1)), close=Mock())
        window = self.window(job)
        window.report.insert.side_effect = RuntimeError("widget unavailable")
        with self.assertRaisesRegex(RuntimeError, "widget unavailable"):
            window.poll()
        job.close.assert_called_once_with()
        self.assertIsNone(window.job)

    def test_cleanup_failure_keeps_ownership_and_retries_before_fatal(self):
        fatal = GeneratorExit("result fatal")
        job = SimpleNamespace(poll=Mock(side_effect=fatal), process=SimpleNamespace(poll=Mock(return_value=1)), close=Mock(side_effect=[OSError("cleanup unavailable"), None]))
        window = self.window(job)
        with self.assertRaises(GeneratorExit) as caught:
            window.poll()
        self.assertIs(caught.exception, fatal)
        self.assertIs(window.job, job)
        window.root.after.assert_called_once_with(100, window.poll)
        with self.assertRaises(GeneratorExit):
            window.poll()
        self.assertIsNone(window.job)

    def test_exit_after_poll_is_collected_by_next_poll_not_discarded(self):
        job = SimpleNamespace(poll=Mock(return_value=None), progress=Mock(return_value=None),
            process=SimpleNamespace(poll=Mock(return_value=0)), close=Mock())
        window = self.window(job)
        window.poll()
        job.close.assert_not_called()
        self.assertIs(window.job, job)
        job.poll.side_effect = RuntimeError("completed result diagnostic")
        window.poll()
        job.close.assert_called_once_with()
        self.assertIsNone(window.job)

    def test_live_progress_fatal_requests_cancel_and_retains_owner_until_exit(self):
        fatal = GeneratorExit("progress fatal")
        job = SimpleNamespace(poll=Mock(return_value=None), progress=Mock(side_effect=fatal),
            process=SimpleNamespace(poll=Mock(return_value=None)), close=Mock(), cancel=Mock())
        window = self.window(job)
        with self.assertRaises(GeneratorExit) as caught:
            window.poll()
        self.assertIs(caught.exception, fatal)
        job.cancel.assert_called_once_with()
        job.close.assert_not_called()
        self.assertIs(window.job, job)
        window.root.after.assert_called_once_with(100, window.poll)
        job.process.poll.return_value = 1
        job.poll.side_effect = RuntimeError("cancelled child exited")
        window.poll()
        job.close.assert_called_once_with()
        self.assertIsNone(window.job)

    def test_cancel_propagates_fatal_without_losing_task_ownership(self):
        fatal = GeneratorExit("cancel marker failure")
        job = SimpleNamespace(cancel=Mock(side_effect=fatal))
        window = self.window(job)
        with self.assertRaises(GeneratorExit) as caught:
            window.cancel()
        self.assertIs(caught.exception, fatal)
        self.assertIs(window.job, job)

    def test_start_ui_failure_does_not_launch_a_process(self):
        import chemblender_prepare.gui as gui
        window = self.window(None)
        window.values = {"command": Mock(get=Mock(return_value="formats")), "python": Mock(get=Mock(return_value="python"))}
        window.text_values = {}
        window.sources = Mock(get=Mock(return_value=""))
        window.preview = window.confirm_loss = window.infer_bonds = Mock(get=Mock(return_value=False))
        window.bar.start.side_effect = RuntimeError("progress setup failed")
        with patch.object(gui, "CliProcess") as launch, patch("tkinter.messagebox.showerror"):
            window.start()
        launch.assert_not_called()
        self.assertIsNone(window.job)
        window.bar.stop.assert_called_once_with()
        fatal = MemoryError("UI cleanup exhausted memory")
        window.bar.stop.side_effect = fatal
        with patch.object(gui, "CliProcess") as launch, patch("tkinter.messagebox.showerror") as dialog:
            with self.assertRaises(MemoryError) as caught:
                window.start()
        self.assertIs(caught.exception, fatal)
        launch.assert_not_called()
        dialog.assert_not_called()

    def test_fatal_cleanup_error_is_not_hidden_by_ordinary_result_error(self):
        fatal = MemoryError("cleanup exhausted memory")
        job = SimpleNamespace(poll=Mock(side_effect=ValueError("result failed")),
            process=SimpleNamespace(poll=Mock(return_value=1)),
            close=Mock(side_effect=[fatal, None]))
        window = self.window(job)
        with self.assertRaises(MemoryError) as raised:
            window.poll()
        self.assertIs(raised.exception, fatal)
        self.assertIs(window.job, job)
        window.root.after.assert_called_once_with(100, window.poll)
        window.poll()
        self.assertIsNone(window.job)
        self.assertEqual(job.close.call_count, 2)


if __name__ == "__main__":
    unittest.main()
