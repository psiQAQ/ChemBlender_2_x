from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "extension-package.yml"
ATTRIBUTES = ROOT / ".gitattributes"
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

    def test_windows_ci_does_not_inject_a_shared_dependency_site(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertNotIn("extensions/.local/lib/python3.13/site-packages", workflow)
        self.assertNotIn("PYTHONPATH", workflow)

    def test_raw_fixtures_and_reader_api_docs_are_checked_out_as_lf(self):
        attributes = ATTRIBUTES.read_text(encoding="utf-8")

        self.assertIn("tests/fixtures/mol2/*.mol2 text eol=lf", attributes)
        self.assertIn("docs/reader-api-v1/*.md text eol=lf", attributes)

    def test_blender_smoke_failure_stops_the_package_job(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        smoke = "--python tests/blender_cbq_viewer_smoke.py --"
        failure = 'if ($LASTEXITCODE -ne 0) { throw "Blender Viewer install smoke failed" }'

        self.assertLess(workflow.index(smoke), workflow.index(failure))
        self.assertEqual(workflow.count(smoke), 2)
        self.assertIn("tests/blender_cold_dependencies.py", workflow)


if __name__ == "__main__":
    unittest.main()
