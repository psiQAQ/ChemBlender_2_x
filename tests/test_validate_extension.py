import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "ChemBlender" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import validate_extension


class ValidateExtensionVersionTests(unittest.TestCase):
    def _run_preflight(self, version: str) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as temp_dir:
            extension_root = Path(temp_dir)
            (extension_root / "blender_manifest.toml").write_text(
                "\n".join(
                    (
                        'schema_version = "1.0.0"',
                        'id = "chemblender"',
                        f'version = "{version}"',
                        'name = "ChemBlender"',
                        'tagline = "Test extension"',
                        'maintainer = "ChemBlender"',
                        'type = "add-on"',
                        'blender_version_min = "5.1.0"',
                        'license = ["SPDX:GPL-3.0-or-later"]',
                    )
                )
                + "\n",
                encoding="utf-8",
            )
            output = io.StringIO()
            with (
                mock.patch.object(
                    sys,
                    "argv",
                    [
                        "validate_extension.py",
                        "--source-path",
                        str(extension_root),
                        "--skip-blender-validate",
                    ],
                ),
                contextlib.redirect_stdout(output),
            ):
                result = validate_extension.main()
        return result, output.getvalue()

    def test_local_preflight_accepts_proven_release_versions(self):
        for version in (
            "2.3.0",
            "2.3.0-alpha.1",
            "2.3.0-beta.2",
            "2.3.0-rc.1",
        ):
            with self.subTest(version=version):
                result, output = self._run_preflight(version)
                self.assertEqual(result, 0, output)
                self.assertNotIn("manifest version", output)

    def test_local_preflight_rejects_invalid_version_as_error(self):
        for version in (
            "2.3.0-alpha",
            "2.3.0-alpha.0",
            "2.3.0-preview.1",
            "02.3.0",
            "2\u0663.3.0",
            "2.3.0-alpha.1\u0661",
        ):
            with self.subTest(version=version):
                result, output = self._run_preflight(version)
                self.assertEqual(result, 1, output)
                self.assertIn("ERROR: manifest version", output)
                self.assertNotIn("WARN: manifest version", output)


if __name__ == "__main__":
    unittest.main()
