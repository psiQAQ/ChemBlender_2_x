import sys
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from worker.external_program import (
    CRITIC2_ADAPTER,
    MULTIWFN_ADAPTER,
    ExternalInvocation,
    ExternalRunStatus,
    critic2_invocation,
    external_run_metadata,
    multiwfn_invocation,
    probe_program_version,
    run_external_program,
)


def script(root, body):
    path = root / "fake_program.py"
    path.write_text(body, encoding="utf-8")
    return path


class ExternalProgramTests(unittest.TestCase):
    def test_registered_descriptors_and_invocation_templates_are_explicit(self):
        self.assertEqual(CRITIC2_ADAPTER.program_id, "critic2")
        self.assertEqual(CRITIC2_ADAPTER.invocation_mode, "argv")
        self.assertEqual(MULTIWFN_ADAPTER.invocation_mode, "stdin_script")
        critic = critic2_invocation("input.cri", "output.cro")
        self.assertEqual(critic.arguments, ("-q", "-t", "-l", "input.cri", "output.cro"))
        self.assertEqual(critic.input_artifacts, ("input.cri",))
        multiwfn = multiwfn_invocation("wavefunction.fchk", "commands.txt")
        self.assertEqual(multiwfn.arguments, ("wavefunction.fchk",))
        self.assertEqual(multiwfn.stdin_artifact, "commands.txt")
        self.assertEqual(
            multiwfn.input_artifacts, ("wavefunction.fchk", "commands.txt")
        )

    def test_success_records_logs_hashes_version_and_outputs(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            program = script(
                root,
                "import pathlib,sys\n"
                "pathlib.Path(sys.argv[1]).write_text('ok', encoding='utf-8')\n"
                "print('stdout')\nprint('stderr', file=sys.stderr)\n",
            )
            invocation = ExternalInvocation(
                program_id="fake",
                adapter_version="1",
                executable=sys.executable,
                arguments=(program.name, "result.dat"),
                expected_artifacts=("result.dat",),
                timeout_seconds=5.0,
                program_version="fake 1.2",
            )
            record = run_external_program(invocation, root)
            self.assertEqual(record.status, ExternalRunStatus.SUCCESS)
            self.assertEqual(record.return_code, 0)
            self.assertEqual(record.program_version, "fake 1.2")
            self.assertEqual(len(record.stdout_hash), 64)
            self.assertEqual(len(record.stderr_hash), 64)
            self.assertEqual(record.expected_artifacts, ("result.dat",))
            metadata = external_run_metadata(record)
            self.assertEqual(metadata["status"], "success")
            self.assertEqual(metadata["argv"][0], sys.executable)

    def test_nonzero_exit_and_missing_output_never_succeed(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            failing = script(root, "raise SystemExit(7)\n")
            record = run_external_program(
                ExternalInvocation(
                    "fake", "1", sys.executable, (failing.name,), (), 5.0, "fake"
                ),
                root,
            )
            self.assertEqual(record.status, ExternalRunStatus.ERROR)
            self.assertEqual(record.return_code, 7)
            self.assertEqual(record.error_code, "nonzero_exit")

            missing = script(root, "print('done')\n")
            record = run_external_program(
                ExternalInvocation(
                    "fake", "1", sys.executable, (missing.name,), ("missing.dat",), 5.0, "fake"
                ),
                root,
            )
            self.assertEqual(record.status, ExternalRunStatus.INVALID_OUTPUT)
            self.assertEqual(record.error_code, "missing_output")

    def test_missing_program_is_a_diagnostic_error(self):
        with TemporaryDirectory() as directory:
            record = run_external_program(
                ExternalInvocation(
                    "missing",
                    "1",
                    "definitely-not-a-real-chemblender-program",
                    (),
                    (),
                    1.0,
                    "unavailable",
                ),
                directory,
            )
            self.assertEqual(record.status, ExternalRunStatus.ERROR)
            self.assertEqual(record.error_code, "program_not_found")
            self.assertIsNone(record.return_code)

    def test_timeout_and_cancel_terminate_process(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            slow = script(root, "import time\ntime.sleep(10)\n")
            invocation = ExternalInvocation(
                "fake", "1", sys.executable, (slow.name,), (), 0.1, "fake"
            )
            timed_out = run_external_program(invocation, root)
            self.assertEqual(timed_out.status, ExternalRunStatus.TIMEOUT)

            cancel = root / "cancel"
            timer = threading.Timer(0.1, cancel.touch)
            timer.start()
            try:
                cancelled = run_external_program(
                    ExternalInvocation(
                        "fake", "1", sys.executable, (slow.name,), (), 5.0, "fake"
                    ),
                    root,
                    cancel_path=cancel,
                )
            finally:
                timer.cancel()
            self.assertEqual(cancelled.status, ExternalRunStatus.CANCELLED)

    def test_paths_cannot_escape_job_root_or_reuse_stale_output(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            program = script(root, "print('ok')\n")
            with self.assertRaisesRegex(ValueError, "inside job root"):
                run_external_program(
                    ExternalInvocation(
                        "fake", "1", sys.executable, (program.name,), ("../escape",), 1.0, "fake"
                    ),
                    root,
                )
            (root / "stale.dat").write_text("old", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "already exists"):
                run_external_program(
                    ExternalInvocation(
                        "fake", "1", sys.executable, (program.name,), ("stale.dat",), 1.0, "fake"
                    ),
                    root,
                )

    def test_stdin_artifact_and_version_probe_use_no_shell(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            program = script(
                root,
                "import pathlib,sys\n"
                "data=sys.stdin.read()\npathlib.Path('result.dat').write_text(data, encoding='utf-8')\n",
            )
            (root / "commands.txt").write_text("commands", encoding="utf-8")
            record = run_external_program(
                ExternalInvocation(
                    "fake", "1", sys.executable, (program.name,), ("result.dat",), 5.0, "fake", "commands.txt"
                ),
                root,
            )
            self.assertEqual(record.status, ExternalRunStatus.SUCCESS)
            self.assertEqual((root / "result.dat").read_text(encoding="utf-8"), "commands")

            version = probe_program_version(
                sys.executable, ("-c", "print('fake 2.0')"), timeout_seconds=2.0
            )
            self.assertEqual(version, "fake 2.0")


if __name__ == "__main__":
    unittest.main()
