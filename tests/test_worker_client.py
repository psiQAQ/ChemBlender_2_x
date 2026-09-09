import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from chemblender_prepare.worker_client import start_worker
from tests.test_worker_protocol import request


class WorkerInputStagingTests(unittest.TestCase):
    def test_inputs_exist_before_process_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "original.fchk"
            source.write_bytes(b"verified source bytes")
            executable = root / "python.exe"
            executable.touch()
            message = request()

            def launch(command, **kwargs):
                task = root / "jobs" / str(message.request_id)
                self.assertEqual((task / "input" / "source.fchk").read_bytes(), source.read_bytes())
                self.assertTrue((task / "request.json").is_file())
                self.assertEqual(command[0], str(executable))
                return Mock()

            with patch("chemblender_prepare.worker_client.subprocess.Popen", side_effect=launch):
                handle = start_worker(message, root / "jobs", python_executable=executable,
                                      staged_inputs={"input/source.fchk": source})
            handle._close_logs()

    def test_unsafe_reserved_or_missing_inputs_do_not_launch(self):
        for relative in ("../escape", "/absolute", "C:/escape", "a\\b", "a/../b", "a//b",
                         "request.json", "RESULT.JSON", "cancel/x", "stdout.log", "stderr.log",
                         "a./source", "input ", "x:stream"):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                executable = root / "python.exe"
                executable.touch()
                with patch("chemblender_prepare.worker_client.subprocess.Popen") as launch:
                    with self.assertRaises(ValueError):
                        start_worker(request(), root / "jobs", python_executable=executable,
                                     staged_inputs={relative: executable})
                    launch.assert_not_called()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "python.exe"
            executable.touch()
            with patch("chemblender_prepare.worker_client.subprocess.Popen") as launch:
                with self.assertRaises(FileNotFoundError):
                    start_worker(request(), root / "jobs", python_executable=executable,
                                 staged_inputs={"source.fchk": root / "missing"})
                launch.assert_not_called()

    def test_source_links_are_rejected_before_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "python.exe"
            executable.touch()
            with patch.object(Path, "is_symlink", return_value=True), patch(
                "chemblender_prepare.worker_client.subprocess.Popen"
            ) as launch:
                with self.assertRaisesRegex(ValueError, "links"):
                    start_worker(request(), root / "jobs", python_executable=executable,
                                 staged_inputs={"source.fchk": executable})
                launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
