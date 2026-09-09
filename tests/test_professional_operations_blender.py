"""Real Blender cancellation gate for an owned external scientific task."""

import hashlib
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

import numpy

from cbq_core.model import ArrayData, ImportBatch, QCProject, Structure
from cbq_core.session import close_session, create_session
from cbq_core.storage.publication import solidify_session


ROOT = Path(__file__).resolve().parents[1]
BLENDER = Path("C:/Program Files/Blender Foundation/Blender 5.1/blender.exe")
PROCESSOR = ROOT / ".venv" / "Scripts" / "chemblender-prepare.exe"
CONFIG = (ROOT / ".blend-analysis" /
          "2026-09-08-cbq-architecture-consolidation" /
          "processor-config-01.json")
WFX = (ROOT / "examples" / "scientific-visualization" / "inputs" /
       "wavefunction" / "water_sto3g_hf.wfx")
PHONOPY = (ROOT / "examples" / "scientific-visualization" / "inputs" /
           "phonopy" / "NaCl")


@unittest.skipUnless(
    BLENDER.is_file() and PROCESSOR.is_file() and CONFIG.is_file()
    and WFX.is_file()
    and (PHONOPY / "phonopy_disp.yaml").is_file()
    and (PHONOPY / "FORCE_SETS").is_file() and (PHONOPY / "BORN").is_file(),
    "real Blender, processor environments, and professional fixtures required",
)
class ProfessionalOperationBlenderTests(unittest.TestCase):
    def test_modal_cancel_is_confirmed_without_project_mutation(self):
        probe = subprocess.run(
            ["wsl.exe", "--exec", "true"], capture_output=True, timeout=10,
        )
        detail = (probe.stdout + probe.stderr).decode("utf-16-le", errors="ignore")
        if probe.returncode and "Wsl/Service/CreateInstance/E_ACCESSDENIED" in detail:
            self.skipTest("WSL instance creation is denied by the test sandbox")
        with TemporaryDirectory(prefix="cb-professional-cancel-") as temporary:
            root = Path(temporary)
            text = WFX.read_text(encoding="utf-8")
            values = lambda name: text.split(f"<{name}>", 1)[1].split(
                f"</{name}>", 1)[0].split()
            numbers = tuple(map(int, values("Atomic Numbers")))
            coordinates = numpy.asarray(
                tuple(map(float, values("Nuclear Cartesian Coordinates")))
            ).reshape((len(numbers), 3))
            structure = Structure(
                uuid4(), hashlib.sha256(WFX.read_bytes()).hexdigest(), numbers,
                ArrayData(coordinates, ("atom", "xyz"), "bohr"),
            )
            project = QCProject(uuid4(), "1.1")
            project.commit(ImportBatch(structures=(structure,)))
            qtaim = root / "qtaim-input.cbq"
            session = create_session(temp_parent=root, project=project)
            try:
                solidify_session(session, qtaim)
            finally:
                close_session(session)
            profile = root / "profile"
            profile.mkdir()
            environment = dict(
                os.environ,
                BLENDER_USER_RESOURCES=str(profile),
                PYTHONNOUSERSITE="1",
                PYTHONDONTWRITEBYTECODE="1",
                CHEMBLENDER_PREPARE_CONFIG=str(CONFIG.resolve()),
            )
            environment.pop("PYTHONPATH", None)
            result = subprocess.run(
                [
                    str(BLENDER), "--background", "--factory-startup",
                    "--offline-mode", "--python-exit-code", "1", "--python",
                    str(ROOT / "tests" / "blender_professional_operations.py"),
                    "--", str(ROOT), str(PROCESSOR), str(qtaim), str(WFX),
                    str(PHONOPY / "phonopy_disp.yaml"),
                    str(PHONOPY / "FORCE_SETS"), str(PHONOPY / "BORN"),
                ],
                env=environment,
                capture_output=True,
                timeout=300,
            )
        stdout = result.stdout.decode("utf-8", errors="replace")
        stderr = result.stderr.decode("utf-8", errors="replace")
        self.assertEqual(result.returncode, 0, stdout + stderr)
        self.assertIn("BLENDER_PROFESSIONAL_OPERATIONS_PASSED", stdout)
        print(next(line for line in stdout.splitlines()
                   if line.startswith("PROCESSOR_CANCEL_TIMINGS_JSON=")))


if __name__ == "__main__":
    unittest.main()
