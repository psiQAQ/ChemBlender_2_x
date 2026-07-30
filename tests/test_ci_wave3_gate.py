from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "extension-package.yml"
WAVE3_BRANCH = "feat/2.3.0-wave3-exchange-mol2-pdb-pqr"


class Wave3CiGateTests(unittest.TestCase):
    def test_package_workflow_runs_for_wave3_and_manual_dispatch(self):
        trigger = WORKFLOW.read_text(encoding="utf-8").split("permissions:", 1)[0]

        self.assertIn("pull_request:", trigger)
        self.assertIn("workflow_dispatch:", trigger)
        self.assertIn(f'      - "{WAVE3_BRANCH}"', trigger)

    def test_package_workflow_discovers_the_wave3_qualification_suite(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        required_modules = {
            "test_wave3_exchange_qualification.py",
            "test_exchange_models.py",
            "test_exchange_project_contract.py",
            "test_exchange_persistence.py",
            "test_mol2_reader.py",
            "test_pdb_reader.py",
            "test_pqr_reader.py",
            "test_reader_conformance_v1.py",
            "test_plugin_discovery.py",
        }

        self.assertIn(
            '& $blenderPython -m unittest discover -s tests -p "test_*.py" -v',
            workflow,
        )
        self.assertTrue(
            required_modules.issubset(
                {path.name for path in (ROOT / "tests").glob("test_*.py")}
            )
        )


if __name__ == "__main__":
    unittest.main()
