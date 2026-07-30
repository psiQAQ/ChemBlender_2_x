"""Run the migration transaction against every hash-locked legacy fixture."""

import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "legacy-blend"
BLENDER_SCRIPT = ROOT / "tests" / "blender_legacy_migrate.py"
FIXTURE_HASHES = {
    "chemblender-2.1-molecule.blend": "36b05c3cacbcc067714615a49df35cf20973bc8122329194ddaecd249df6c3d4",
    "chemblender-2.2-crystal.blend": "f2995e826762a85bfb6854e314483175c3d39c2cceef109db3f395ab2e83c06a",
    "chemblender-2.2-edited-scaffold.blend": "a6af8e232fe7b934bf850f8e6b24d396596b79cc1fd38e8ff6eb071c50bf8740",
}


def blender_executable():
    configured = os.environ.get("BLENDER_EXECUTABLE")
    if configured:
        return Path(configured)
    default = Path("C:/Program Files/Blender Foundation/Blender 5.1/blender.exe")
    if default.is_file():
        return default
    found = shutil.which("blender")
    return Path(found) if found else None


class LegacyMigrationBlenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blender = blender_executable()
        if cls.blender is None:
            raise unittest.SkipTest("Blender 5.1 executable unavailable")

    def test_hash_locked_fixtures_migrate_and_reopen(self):
        self.assertEqual(
            tuple(sorted(path.name for path in FIXTURES.glob("*.blend"))),
            tuple(FIXTURE_HASHES),
        )
        for name, expected_hash in FIXTURE_HASHES.items():
            with self.subTest(fixture=name):
                fixture = FIXTURES / name
                self.assertEqual(
                    hashlib.sha256(fixture.read_bytes()).hexdigest(), expected_hash,
                )
                with tempfile.TemporaryDirectory(prefix="cb-legacy-migration-") as profile:
                    environment = os.environ.copy()
                    environment.update({
                        "BLENDER_USER_RESOURCES": profile,
                        "TEMP": profile,
                        "TMP": profile,
                    })
                    result = subprocess.run(
                        [
                            str(self.blender), "--background", "--python-exit-code", "1",
                            str(fixture), "--python", str(BLENDER_SCRIPT), "--", str(ROOT),
                        ],
                        cwd=ROOT, env=environment, check=False,
                        capture_output=True, text=True,
                    )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
