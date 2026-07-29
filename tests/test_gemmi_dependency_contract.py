import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "ChemBlender"
SCRIPTS = EXTENSION / "scripts"
GEMMI_WHEEL = "gemmi-0.7.5-cp313-cp313-win_amd64.whl"
GEMMI_URL = (
    "https://files.pythonhosted.org/packages/ee/ab/"
    "7d7463cda94f8b68b969ea97aaad679655a0e436efd6a643e528a8de114e/"
    f"{GEMMI_WHEEL}"
)
GEMMI_SHA256 = (
    "ad1f72ffa24adbfaf259e11471f6f071a668667f6ca846051f3bfea024fd337d"
)

sys.path.insert(0, str(SCRIPTS))

import validate_extension


class GemmiDependencyContractTests(unittest.TestCase):
    def test_manifest_and_workflow_lock_official_wheel(self):
        manifest = (EXTENSION / "blender_manifest.toml").read_text(
            encoding="utf-8"
        )
        workflow = (
            ROOT / ".github" / "workflows" / "extension-package.yml"
        ).read_text(encoding="utf-8")

        self.assertIn(f'\"./wheels/{GEMMI_WHEEL}\"', manifest)
        self.assertIn(GEMMI_WHEEL, workflow)
        self.assertIn(GEMMI_URL, workflow)
        self.assertIn(GEMMI_SHA256, workflow)
        self.assertIn('"GEMMI_WHEEL=$wheelPath`n"', workflow)
        self.assertIn(
            "$env:RDKIT_WHEEL $env:GEMMI_WHEEL",
            workflow,
        )

    def test_core_and_reader_api_import_without_loading_gemmi(self):
        code = (
            "import sys; "
            "import ChemBlender.core; "
            "import ChemBlender.reader_api; "
            "assert 'gemmi' not in sys.modules"
        )
        subprocess.run(
            [sys.executable, "-c", code],
            cwd=ROOT,
            check=True,
        )

    def test_preflight_rejects_undeclared_local_wheel(self):
        extension_root = self._minimal_extension(
            (
                "./wheels/rdkit-2026.3.3-cp313-cp313-win_amd64.whl",
                f"./wheels/{GEMMI_WHEEL}",
            ),
            extra_wheels=("unexpected.whl",),
        )

        result, output = self._run_preflight(extension_root)

        self.assertEqual(result, 1)
        self.assertIn("undeclared wheel file", output)

    def test_preflight_rejects_duplicate_manifest_wheel(self):
        extension_root = self._minimal_extension(
            (
                f"./wheels/{GEMMI_WHEEL}",
                f"./wheels/{GEMMI_WHEEL}",
            )
        )

        result, output = self._run_preflight(extension_root)

        self.assertEqual(result, 1)
        self.assertIn("duplicate wheel path", output)

    def test_preflight_rejects_duplicate_manifest_wheel_alias(self):
        extension_root = self._minimal_extension(
            (
                f"./wheels/{GEMMI_WHEEL}",
                f"./wheels/../wheels/{GEMMI_WHEEL}",
            )
        )

        result, output = self._run_preflight(extension_root)

        self.assertEqual(result, 1)
        self.assertIn("duplicate wheel path", output)

    def test_preflight_rejects_missing_manifest_wheel(self):
        extension_root = self._minimal_extension(
            (f"./wheels/{GEMMI_WHEEL}",)
        )
        (extension_root / "wheels" / GEMMI_WHEEL).unlink()

        result, output = self._run_preflight(extension_root)

        self.assertEqual(result, 1)
        self.assertIn("wheel path does not exist", output)

    def _minimal_extension(
        self,
        wheels: tuple[str, ...],
        *,
        extra_wheels: tuple[str, ...] = (),
    ) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        wheel_dir = root / "wheels"
        wheel_dir.mkdir()
        for wheel in set(wheels):
            (root / wheel.removeprefix("./")).write_bytes(b"wheel")
        for wheel in extra_wheels:
            (wheel_dir / wheel).write_bytes(b"wheel")
        wheel_lines = ",\n  ".join(f'"{wheel}"' for wheel in wheels)
        (root / "blender_manifest.toml").write_text(
            "\n".join(
                (
                    'schema_version = "1.0.0"',
                    'id = "chemblender"',
                    'version = "2.3.0-alpha.1"',
                    'name = "ChemBlender"',
                    'tagline = "Test extension"',
                    'maintainer = "ChemBlender"',
                    'type = "add-on"',
                    'blender_version_min = "5.1.0"',
                    'license = ["SPDX:GPL-3.0-or-later"]',
                    f"wheels = [\n  {wheel_lines}\n]",
                    "",
                )
            ),
            encoding="utf-8",
        )
        return root

    def _run_preflight(self, extension_root: Path) -> tuple[int, str]:
        stdout = io.StringIO()
        argv = [
            "validate_extension.py",
            "--source-path",
            str(extension_root),
            "--skip-blender-validate",
        ]
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(
            stdout
        ):
            result = validate_extension.main()
        return result, stdout.getvalue()


if __name__ == "__main__":
    unittest.main()
