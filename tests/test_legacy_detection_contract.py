import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "legacy-blend"
BLENDER_SCRIPT = ROOT / "tests" / "blender_legacy_extract.py"


def blender_executable():
    configured = os.environ.get("BLENDER_EXECUTABLE")
    if configured:
        return Path(configured)
    default = Path(
        "C:/Program Files/Blender Foundation/Blender 5.1/blender.exe"
    )
    if default.is_file():
        return default
    found = shutil.which("blender")
    return Path(found) if found else None


class LegacyDetectionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blender = blender_executable()
        if cls.blender is None:
            raise unittest.SkipTest("Blender 5.1 executable unavailable")

    def run_blender(self, fixture=None, synthetic=False):
        with tempfile.TemporaryDirectory(prefix="cb-legacy-") as profile:
            environment = os.environ.copy()
            environment.update(
                {
                    "BLENDER_USER_RESOURCES": profile,
                    "TEMP": profile,
                    "TMP": profile,
                }
            )
            command = [
                str(self.blender),
                "--background",
                "--factory-startup",
                "--python-exit-code",
                "1",
            ]
            if fixture is not None:
                command.append(str(fixture))
            command.extend(
                (
                    "--python",
                    str(BLENDER_SCRIPT),
                    "--",
                    str(ROOT),
                    "synthetic" if synthetic else "fixture",
                )
            )
            return subprocess.run(
                command,
                cwd=ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )

    def test_legacy_fixtures_detect_and_extract_without_datablock_mutation(self):
        for fixture in sorted(FIXTURES.glob("*.blend")):
            with self.subTest(fixture=fixture.name):
                result = self.run_blender(fixture)
                self.assertEqual(
                    result.returncode,
                    0,
                    result.stdout + result.stderr,
                )

    def test_current_factory_scene_is_not_legacy(self):
        result = self.run_blender()
        self.assertEqual(
            result.returncode,
            0,
            result.stdout + result.stderr,
        )

    def test_parent_induced_nonuniform_legacy_data_has_diagnostics_without_mutation(self):
        result = self.run_blender(synthetic=True)
        self.assertEqual(
            result.returncode,
            0,
            result.stdout + result.stderr,
        )


if __name__ == "__main__":
    unittest.main()
