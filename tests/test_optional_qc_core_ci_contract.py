from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "optional-qc-core.yml"
DOCUMENTATION = ROOT / "docs" / "development" / "testing-and-ci.md"
CHECKOUT = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
SETUP_PYTHON = "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97"
UPLOAD_ARTIFACT = "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"


class OptionalQcCoreCiContractTests(unittest.TestCase):
    def _workflow(self) -> str:
        self.assertTrue(WORKFLOW.is_file(), "optional quantum-core workflow is missing")
        return WORKFLOW.read_text(encoding="utf-8")

    def _job(self, name: str) -> str:
        workflow = self._workflow()
        marker = f"\n  {name}:\n"
        self.assertIn(marker, workflow)
        remainder = workflow.split(marker, 1)[1]
        next_job = re.search(r"(?m)^  [a-z][a-z0-9-]*:\n", remainder)
        return remainder[: next_job.start()] if next_job else remainder

    def test_each_backend_uses_an_isolated_pinned_environment_and_submodule(self):
        expected = {
            "cclib": {
                "python": 'python-version: "3.13"',
                "package": "cclib==1.8.1",
                "submodule": "07260dd0394cb1a2381d4d897746d727a12ad6ce",
                "module": "tests.test_cclib_adapter",
            },
            "iodata": {
                "python": 'python-version: "3.13"',
                "package": "qc-iodata==1.0.1",
                "submodule": "adab5813713ba64641565eb2a8c11803a4e9bba6",
                "module": "tests.test_iodata_adapter",
            },
            "gbasis": {
                "python": 'python-version: "3.12"',
                "package": "qc-gbasis==0.1.0",
                "submodule": "6440c84f3fcf8d42cbd9b5de53ae8d70bed4cd4f",
                "module": "tests.test_wavefunction_grid",
            },
        }

        for backend, requirement in expected.items():
            with self.subTest(backend=backend):
                job = self._job(backend)
                self.assertIn(CHECKOUT, job)
                self.assertIn(SETUP_PYTHON, job)
                self.assertIn(requirement["python"], job)
                self.assertIn(requirement["package"], job)
                self.assertIn(requirement["submodule"], job)
                self.assertIn(requirement["module"], job)
                self.assertIn("git submodule update --init --depth 1", job)
                self.assertIn("run_required_integration.py", job)
                self.assertIn("timeout-minutes: 15", job)
                self.assertNotIn("unittest discover", job)
        gbasis = self._job("gbasis")
        self.assertIn("numpy==1.26.4", gbasis)
        self.assertIn("qc-iodata==1.0.1", gbasis)
        self.assertIn("tests.test_wavefunction_observables", gbasis)

    def test_fixture_hash_preflight_and_summary_artifact_are_required(self):
        workflow = self._workflow()
        for fixture_hash in (
            "02bc605f57477477f17d1f305f91cd9e4e62239456cb9a0ef288384c714d04d9",
            "18923bf60ff3c4bac650a0cd871a7417e2f779c5161dfa138ea677fad4f7eb42",
            "eae40334346cea9177ab5c75ca81cd53ed1fbcaf5d567a8818f067439e5c744f",
            "f208f87b45aaa9792cc5c032d7ad9d0e2e89f70df16d38a32916837c478248fe",
            "17aaa6f1ca3d4bdc9ce90d857c6b4ffbbeda2ceb660934cfc8caa211d9d34e29",
            "8389fcfb2014a4c320c800d1bb8e3003588ef845b4cee3f342ebe5c3d0398113",
            "d608b388b408a123447a637efeafd7e3c3436c645b01c4c48a446fb22648006b",
            "1b22bead2a4b13260f3ec870e8fe26a6c6400e52fd93f3fcbc1dff0301dfa9ff",
            "908be982bb2a50b88ded46e0df397c26e1d3399ea9fcac8f70940a4cb45c4be8",
            "fcb6c4b0bc8d35aa34a0e58a86c148622820f3234c5309c7719014a8d6fe556f",
            "2385f3da057bcc3a33327de7f36703bada5069ed3089fc581ece401473218415",
            "2b958cb5e03ca5d9e506b215aa424f9f1998b3ac4ce30b8fcb64795e8b895f3b",
            "9395e96ca9e464d883849e29d0f7ffb331f371512d2af6aa67f25061615bd3b7",
            "ef4b97f94cf701647f40042f2c44ea864f5ce9ac3cfeda7985acf31ac16fe7f3",
        ):
            self.assertIn(fixture_hash, workflow)
        self.assertEqual(workflow.count(UPLOAD_ARTIFACT), 3)
        self.assertIn("if: always()", workflow)
        self.assertIn("if-no-files-found: ignore", workflow)
        artifact_paths = re.findall(
            r"(?m)^          path: ([^\n]+)$", workflow
        )
        self.assertEqual(
            artifact_paths,
            ["summary-cclib.json", "summary-iodata.json", "summary-gbasis.json"],
        )
        self.assertNotIn("tar", workflow.lower())

    def test_workflow_is_read_only_pinned_and_documented_as_zero_skip_gate(self):
        workflow = self._workflow()
        documentation = DOCUMENTATION.read_text(encoding="utf-8")

        self.assertIn("permissions:\n  contents: read", workflow)
        actions = re.findall(r"uses:\s+([^\s]+)", workflow)
        self.assertEqual(len(actions), 9)
        for action in actions:
            self.assertRegex(action, r"@[0-9a-f]{40}$")
        self.assertIn("optional-qc-core", documentation)
        self.assertIn("run_required_integration.py", documentation)
        self.assertIn("skip", documentation.lower())


if __name__ == "__main__":
    unittest.main()
