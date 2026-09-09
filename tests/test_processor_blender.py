"""Run the processor lifecycle in Blender 5.1 with a private profile."""

import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
BLENDER = Path("C:/Program Files/Blender Foundation/Blender 5.1/blender.exe")
PROCESSOR = ROOT / ".venv" / "Scripts" / "chemblender-prepare.exe"
PACKAGE = ROOT / "ChemBlender" / "chemblender-2.5.0.zip"
PROCESSOR_CONFIG = (ROOT / ".blend-analysis" /
                    "2026-09-08-cbq-architecture-consolidation" /
                    "processor-config-01.json")
WAVEFUNCTION_SOURCE = (ROOT / "examples" / "scientific-visualization" /
                       "inputs" / "wavefunction" /
                       "water_sto3g_hf_g03.fchk")


class NativeProcessorControllerTests(unittest.TestCase):
    @unittest.skipUnless(BLENDER.is_file() and PROCESSOR.is_file()
                         and PROCESSOR_CONFIG.is_file()
                         and WAVEFUNCTION_SOURCE.is_file(),
                         "Blender, processor config, and wavefunction fixture are required")
    def test_real_reader_wavefunction_modal_and_reopen(self):
        with TemporaryDirectory(prefix="cb-processor-operations-") as profile:
            environment = dict(
                os.environ,
                BLENDER_USER_RESOURCES=profile,
                PYTHONNOUSERSITE="1",
                PYTHONDONTWRITEBYTECODE="1",
                CHEMBLENDER_PREPARE_CONFIG=str(PROCESSOR_CONFIG.resolve()),
            )
            environment.pop("PYTHONPATH", None)
            result = subprocess.run(
                [str(BLENDER), "--background", "--factory-startup", "--offline-mode",
                 "--python-exit-code", "1", "--python",
                 str(ROOT / "tests" / "blender_processor_operations.py"),
                 "--", str(ROOT), str(PROCESSOR), str(WAVEFUNCTION_SOURCE)],
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=180,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PROCESSOR_OPERATIONS_PASSED", result.stdout)
        print(next(line for line in result.stdout.splitlines()
                   if line.startswith("PROCESSOR_TIMINGS_JSON=")))

    @unittest.skipUnless(BLENDER.is_file() and PROCESSOR.is_file()
                         and PACKAGE.is_file() and PROCESSOR_CONFIG.is_file()
                         and WAVEFUNCTION_SOURCE.is_file(),
                         "built extension and real processor environment are required")
    def test_installed_reader_wavefunction_and_reopen(self):
        with TemporaryDirectory(prefix="cb-processor-operations-install-") as profile:
            environment = dict(
                os.environ,
                BLENDER_USER_RESOURCES=profile,
                PYTHONNOUSERSITE="1",
                PYTHONDONTWRITEBYTECODE="1",
                CHEMBLENDER_PREPARE_CONFIG=str(PROCESSOR_CONFIG.resolve()),
            )
            environment.pop("PYTHONPATH", None)
            result = subprocess.run(
                [str(BLENDER), "--background", "--factory-startup", "--offline-mode",
                 "--python-exit-code", "1", "--python",
                 str(ROOT / "tests" / "blender_processor_operations.py"),
                 "--", str(ROOT), str(PROCESSOR), str(WAVEFUNCTION_SOURCE),
                 str(PACKAGE)],
                cwd=profile,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=180,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PROCESSOR_OPERATIONS_PASSED", result.stdout)
        print(next(line for line in result.stdout.splitlines()
                   if line.startswith("PROCESSOR_TIMINGS_JSON=")))

    @unittest.skipUnless(BLENDER.is_file() and PROCESSOR.is_file(),
                         "Blender 5.1 and project processor are required")
    def test_registration_preview_capability_and_reload(self):
        with TemporaryDirectory(prefix="cb-processor-profile-") as profile:
            environment = dict(
                os.environ,
                BLENDER_USER_RESOURCES=profile,
                PYTHONNOUSERSITE="1",
                PYTHONDONTWRITEBYTECODE="1",
            )
            environment.pop("PYTHONPATH", None)
            result = subprocess.run(
                [str(BLENDER), "--background", "--factory-startup", "--offline-mode",
                 "--python-exit-code", "1", "--python",
                 str(ROOT / "tests" / "blender_processor_controller.py"),
                 "--", str(ROOT), str(PROCESSOR)],
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=90,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PROCESSOR_CONTROLLER_PASSED", result.stdout)

    @unittest.skipUnless(BLENDER.is_file() and PROCESSOR.is_file() and PACKAGE.is_file(),
                         "Blender 5.1, processor, and extension package are required")
    def test_installed_extension_uses_one_preference_and_keeps_local_editing(self):
        with TemporaryDirectory(prefix="cb-processor-install-") as profile:
            environment = dict(
                os.environ,
                BLENDER_USER_RESOURCES=profile,
                PYTHONNOUSERSITE="1",
                PYTHONDONTWRITEBYTECODE="1",
            )
            environment.pop("PYTHONPATH", None)
            result = subprocess.run(
                [str(BLENDER), "--background", "--factory-startup", "--offline-mode",
                 "--python-exit-code", "1", "--python",
                 str(ROOT / "tests" / "blender_processor_installed.py"),
                 "--", str(PACKAGE), str(PROCESSOR)],
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=90,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PROCESSOR_INSTALLED_PASSED", result.stdout)


if __name__ == "__main__":
    unittest.main()
