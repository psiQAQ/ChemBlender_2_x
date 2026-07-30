from __future__ import annotations

from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "extension-package.yml"
CHECKOUT = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
SETUP_PYTHON = "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97"
UPLOAD_ARTIFACT = "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"


class NativeCoreCiContractTests(unittest.TestCase):
    def _job(self, name: str) -> str:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        marker = f"\n  {name}:\n"
        self.assertIn(marker, workflow)
        remainder = workflow.split(marker, 1)[1]
        next_job = re.search(r"(?m)^  [a-z][a-z0-9-]*:\n", remainder)
        return remainder[: next_job.start()] if next_job else remainder

    def _git(self, cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ("git", *args),
            cwd=cwd,
            check=True,
            capture_output=True,
            encoding="utf-8",
        )

    def _committed_range_result(self, contents: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = Path(temp_dir)
            self._git(repository, "init")
            self._git(repository, "config", "user.email", "ci@example.invalid")
            self._git(repository, "config", "user.name", "CI Contract")
            fixture = repository / "fixture.txt"
            fixture.write_text("base\n", encoding="utf-8", newline="\n")
            self._git(repository, "add", "fixture.txt")
            self._git(repository, "commit", "-m", "base")
            base = self._git(repository, "rev-parse", "HEAD").stdout.strip()
            fixture.write_text(contents, encoding="utf-8", newline="\n")
            self._git(repository, "add", "fixture.txt")
            self._git(repository, "commit", "-m", "head")
            return subprocess.run(
                ("git", "diff", "--check", base, "HEAD"),
                cwd=repository,
                check=False,
                capture_output=True,
                encoding="utf-8",
            )

    def test_native_core_is_a_stdlib_only_fast_gate(self):
        native = self._job("native-core")

        self.assertIn(CHECKOUT, native)
        self.assertIn(SETUP_PYTHON, native)
        self.assertEqual(native.count("uses:"), 2)
        self.assertIn("fetch-depth: 0", native)
        self.assertIn('python-version: "3.13"', native)
        self.assertIn("timeout-minutes: 10", native)
        for module in (
            "tests.test_dependency_inventory",
            "tests.test_legacy_fixture_inventory",
            "tests.test_quantum_visualization_docs",
            "tests.test_repository_contract",
            "tests.test_native_core_ci_contract",
        ):
            self.assertIn(module, native)
        self.assertIn("python -m compileall -q ChemBlender tests", native)
        self.assertIn("github.event.pull_request.base.sha", native)
        self.assertIn("github.event.before", native)
        self.assertIn("^[0-9a-fA-F]{40}$", native)
        self.assertIn("^0{40}$", native)
        self.assertIn("git rev-parse --verify HEAD^", native)
        self.assertIn("git rev-list --max-parents=0 HEAD", native)
        self.assertIn("git diff --check $base HEAD", native)
        self.assertIn('throw "Committed format check failed"', native)
        for forbidden in (
            "Download pinned extension wheels",
            "Download Blender",
            "Invoke-WebRequest",
            "Expand-Archive",
            "-m pip",
            "BLENDER_USER_RESOURCES",
        ):
            self.assertNotIn(forbidden, native)

    def test_committed_range_check_rejects_bad_head_and_accepts_clean_head(self):
        bad = self._committed_range_result("bad trailing whitespace  \n")
        clean = self._committed_range_result("clean\n")

        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("trailing whitespace", bad.stdout)
        self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)

    def test_package_waits_for_native_and_is_the_only_artifact_authority(self):
        native = self._job("native-core")
        package = self._job("package")

        self.assertIn("needs: native-core", package)
        self.assertIn("timeout-minutes: 30", package)
        self.assertIn("Download pinned extension wheels", package)
        self.assertIn("Download Blender 5.1.2", package)
        self.assertIn("-m pip install --disable-pip-version-check", package)
        self.assertIn("BLENDER_USER_RESOURCES", package)
        self.assertIn("build_extension.py --python $blenderPython --blender $blender", package)
        self.assertIn("tests/blender_smoke.py -- $package", package)
        self.assertIn(UPLOAD_ARTIFACT, package)
        self.assertNotIn(UPLOAD_ARTIFACT, native)
        self.assertEqual(
            WORKFLOW.read_text(encoding="utf-8").count(UPLOAD_ARTIFACT),
            1,
        )

    def test_package_workflow_keeps_read_only_permissions_and_full_action_pins(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertEqual(workflow.count("timeout-minutes:"), 2)
        actions = re.findall(r"uses:\s+([^\s]+)", workflow)
        self.assertTrue(actions)
        for action in actions:
            self.assertRegex(action, r"@[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main()
