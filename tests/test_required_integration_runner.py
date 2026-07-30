from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "ChemBlender" / "scripts" / "run_required_integration.py"


class RequiredIntegrationRunnerTests(unittest.TestCase):
    def _write_module(self, root: Path, name: str, body: str) -> str:
        package = root / "required_runner_sample"
        package.mkdir(exist_ok=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / f"{name}.py").write_text(
            textwrap.dedent(body), encoding="utf-8"
        )
        return f"required_runner_sample.{name}"

    def _run(self, root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(root) + os.pathsep + environment.get(
            "PYTHONPATH", ""
        )
        return subprocess.run(
            [sys.executable, str(RUNNER), *arguments],
            cwd=root,
            check=False,
            capture_output=True,
            encoding="utf-8",
            env=environment,
        )

    def _summary_for(self, root: Path, module: str, *arguments: str):
        summary = root / "required-summary.json"
        result = self._run(
            root,
            "--summary",
            str(summary),
            "--module",
            module,
            *arguments,
        )
        self.assertTrue(summary.is_file(), result.stderr)
        return result, json.loads(summary.read_text(encoding="utf-8")), summary

    def test_passing_module_writes_canonical_summary_with_versions_and_fixture_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            module = self._write_module(
                root,
                "passing",
                """
                import unittest

                class Passing(unittest.TestCase):
                    def test_passes(self):
                        self.assertEqual(2 + 2, 4)
                """,
            )
            fixture = root / "fixture.bin"
            fixture.write_bytes(b"fixture contents\n")
            digest = hashlib.sha256(fixture.read_bytes()).hexdigest()
            numpy_version = importlib.metadata.version("numpy")

            result, summary, summary_path = self._summary_for(
                root,
                module,
                "--fixture",
                f"fixture.bin={digest}",
                "--require-version",
                f"numpy=={numpy_version}",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(summary["counts"], {
                "error": 0,
                "failed": 0,
                "load_error": 0,
                "passed": 1,
                "skipped": 0,
                "total": 1,
            })
            self.assertEqual(summary["fixture_hashes"], {"fixture.bin": digest})
            self.assertEqual(summary["test_ids"]["passed"], [
                "required_runner_sample.passing.Passing.test_passes"
            ])
            self.assertEqual(summary["versions"]["numpy"], numpy_version)
            self.assertEqual(summary["version_errors"], [])
            self.assertEqual(
                summary_path.read_text(encoding="utf-8"),
                json.dumps(summary, sort_keys=True, separators=(",", ":")) + "\n",
            )

    def test_skipped_required_test_is_recorded_and_fails_the_runner(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            module = self._write_module(
                root,
                "skipped",
                """
                import unittest

                class Skipped(unittest.TestCase):
                    @unittest.skip("required backend unavailable")
                    def test_is_skipped(self):
                        pass
                """,
            )

            result, summary, _ = self._summary_for(root, module)

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(summary["counts"]["skipped"], 1)
            self.assertEqual(summary["test_ids"]["skipped"], [
                "required_runner_sample.skipped.Skipped.test_is_skipped"
            ])

    def test_failed_required_test_is_recorded_and_fails_the_runner(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            module = self._write_module(
                root,
                "failed",
                """
                import unittest

                class Failed(unittest.TestCase):
                    def test_fails(self):
                        self.fail("expected failure")
                """,
            )

            result, summary, _ = self._summary_for(root, module)

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(summary["counts"]["failed"], 1)
            self.assertEqual(summary["test_ids"]["failed"], [
                "required_runner_sample.failed.Failed.test_fails"
            ])

    def test_errored_required_test_is_recorded_and_fails_the_runner(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            module = self._write_module(
                root,
                "errored",
                """
                import unittest

                class Errored(unittest.TestCase):
                    def test_errors(self):
                        raise RuntimeError("expected error")
                """,
            )

            result, summary, _ = self._summary_for(root, module)

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(summary["counts"]["error"], 1)
            self.assertEqual(summary["test_ids"]["error"], [
                "required_runner_sample.errored.Errored.test_errors"
            ])

    def test_empty_required_module_is_recorded_and_fails_the_runner(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            module = self._write_module(root, "empty", "VALUE = 1\n")

            result, summary, _ = self._summary_for(root, module)

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(summary["counts"]["total"], 0)
            self.assertEqual(summary["zero_discovered"], [module])

    def test_unloadable_required_module_is_recorded_and_fails_the_runner(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_module(root, "present", "VALUE = 1\n")

            result, summary, _ = self._summary_for(
                root, "required_runner_sample.missing"
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(summary["counts"]["load_error"], 1)
            self.assertEqual(summary["test_ids"]["load_error"], [
                "required_runner_sample.missing"
            ])

    def test_missing_required_fixture_is_recorded_and_fails_the_runner(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            module = self._write_module(
                root,
                "passing",
                """
                import unittest

                class Passing(unittest.TestCase):
                    def test_passes(self):
                        self.assertTrue(True)
                """,
            )

            result, summary, _ = self._summary_for(
                root,
                module,
                "--fixture",
                "missing.fixture=" + "0" * 64,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(summary["fixture_errors"], ["missing.fixture: missing"])
            self.assertEqual(summary["counts"]["total"], 0)


if __name__ == "__main__":
    unittest.main()
