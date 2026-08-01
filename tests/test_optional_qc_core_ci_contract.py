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
LOCKS = {
    "cclib": ROOT / ".github" / "constraints" / "cclib-py313.txt",
    "iodata": ROOT / ".github" / "constraints" / "iodata-py313.txt",
    "gbasis": ROOT / ".github" / "constraints" / "gbasis-py312.txt",
}
FIXTURES = {
    "cclib": [
        (
            "submodules/cclib/data/Gaussian/basicGaussian16/water_hf_solvent_cpcm.log",
            "d3ade6a479a83ee3ae684c5ebc3cc0b0e30088b3e525063aeb217484f740acf5",
        ),
        (
            "submodules/cclib/data/ORCA/basicORCA4.1/water_mp2.out",
            "ed7bf74f17cc47bf378e35cda9035a98854e7609ac67510a7a55bebac952e8be",
        ),
        (
            "submodules/cclib/data/Gaussian/basicGaussian16/dvb_ir.out",
            "bc1a21de15ada135d5188b11d44226389022d92488ddfa8163ba7d4d713e5061",
        ),
        (
            "submodules/cclib/data/Gaussian/basicGaussian16/dvb_raman.out",
            "fc97b8c179dbad721262be6077be893b13b785b36f8ae3493a1dd4b3d4bf18b9",
        ),
        (
            "submodules/cclib/data/ORCA/basicORCA5.0/dvb_ir.out",
            "deb64567281a4673849812a63fc7b1147c33d1c4ad3b67f6b3bf7ec03ab1046c",
        ),
        (
            "submodules/cclib/data/ORCA/basicORCA5.0/dvb_raman.out",
            "956e9a7989c8fc917ef358f57423286d7228f59fff18f159e25c19e71e3181e8",
        ),
        (
            "submodules/cclib/data/Gaussian/basicGaussian16/dvb_td.out",
            "c9255c92b829a4d2072ffca262be4dd9212f35a9c75d84c1fe8eb5969c166eef",
        ),
        (
            "submodules/cclib/data/Gaussian/basicGaussian09/dvb_td.out",
            "01619fecb8ca4d80b1ddfddb6cb9dc1983e52e23616e20ac0e4f1a6bb55462e0",
        ),
        (
            "submodules/cclib/data/ORCA/basicORCA5.0/dvb_td.out",
            "b4262a21e11ea441551f465f4ae04aee0d4f9ddf35e6a94c0309400c924f17f6",
        ),
        (
            "submodules/cclib/data/ORCA/basicORCA5.0/dvb_adc2.log",
            "d6d371f25ae50c27a3046ec35217d2d528c4ba0fb28fd71738e69f5980ecbe35",
        ),
    ],
    "iodata": [
        (
            "submodules/iodata/iodata/test/data/water_sto3g_hf_g03.fchk",
            "aa8dec77849d4f9e1e9dc9357c80f5b4d6ba1efc3bbc17da6c59754bdaed0816",
        ),
        (
            "submodules/iodata/iodata/test/data/ch3_hf_sto3g.fchk",
            "b5b33475a6766447a287e6cf16ac6111eb489a5985743413b056ac2e7a4c384c",
        ),
        (
            "submodules/iodata/iodata/test/data/h2o.molden.input",
            "2bf025dc02fdb689e61c980ac55dc4bef35a31e4bfc819a668ac36d721f44f06",
        ),
    ],
    "gbasis": [
        (
            "submodules/iodata/iodata/test/data/water_sto3g_hf_g03.fchk",
            "aa8dec77849d4f9e1e9dc9357c80f5b4d6ba1efc3bbc17da6c59754bdaed0816",
        ),
        (
            "submodules/iodata/iodata/test/data/ch3_hf_sto3g.fchk",
            "b5b33475a6766447a287e6cf16ac6111eb489a5985743413b056ac2e7a4c384c",
        ),
        (
            "submodules/iodata/iodata/test/data/water_ccpvdz_pure_hf_g03.fchk",
            "c86f46db444f31613dbc2602b7b37b4ee4375d722b86e69eb04a163d3a1ec90a",
        ),
    ],
}


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
                "lock": ".github/constraints/cclib-py313.txt",
                "submodule": "07260dd0394cb1a2381d4d897746d727a12ad6ce",
                "module": "tests.test_cclib_adapter",
            },
            "iodata": {
                "python": 'python-version: "3.13"',
                "package": "qc-iodata==1.0.1",
                "lock": ".github/constraints/iodata-py313.txt",
                "submodule": "adab5813713ba64641565eb2a8c11803a4e9bba6",
                "module": "tests.test_iodata_adapter",
            },
            "gbasis": {
                "python": 'python-version: "3.12"',
                "package": "qc-gbasis==0.1.0",
                "lock": ".github/constraints/gbasis-py312.txt",
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
                self.assertIn(f"-c {requirement['lock']}", job)
                self.assertIn(
                    f"--require-version-file {requirement['lock']}", job
                )
                self.assertIn("timeout-minutes: 15", job)
                self.assertNotIn("unittest discover", job)
        gbasis = self._job("gbasis")
        self.assertIn("numpy==1.26.4", gbasis)
        self.assertIn("qc-iodata==1.0.1", gbasis)
        self.assertIn("tests.test_wavefunction_observables", gbasis)

    def test_each_backend_lock_is_full_exact_and_used_by_its_own_job(self):
        expected = {
            "cclib": {
                "cclib==1.8.1",
                "numpy==2.2.6",
                "packaging==26.2",
                "periodictable==2.1.0",
                "pyparsing==3.3.2",
                "scipy==1.16.3",
            },
            "iodata": {
                "attrs==26.1.0",
                "numpy==2.2.6",
                "qc-iodata==1.0.1",
                "scipy==1.16.3",
            },
            "gbasis": {
                "attrs==26.1.0",
                "importlib_resources==7.1.0",
                "mpmath==1.3.0",
                "numpy==1.26.4",
                "qc-gbasis==0.1.0",
                "qc-iodata==1.0.1",
                "scipy==1.16.3",
                "sympy==1.14.0",
            },
        }

        for backend, requirements in expected.items():
            with self.subTest(backend=backend):
                lock = LOCKS[backend]
                self.assertTrue(lock.is_file(), f"{backend} lock is missing")
                entries = {
                    line
                    for line in lock.read_text(encoding="utf-8").splitlines()
                    if line and not line.startswith("#")
                }
                self.assertEqual(entries, requirements)
                self.assertTrue(
                    all(
                        re.fullmatch(r"[A-Za-z0-9_.-]+==[^=\s]+", entry)
                        for entry in entries
                    )
                )
                self.assertIn(
                    f"-c {lock.relative_to(ROOT).as_posix()}", self._job(backend)
                )
                self.assertIn(
                    f"--require-version-file {lock.relative_to(ROOT).as_posix()}",
                    self._job(backend),
                )

    def test_fixture_hash_preflight_and_summary_artifact_are_required(self):
        workflow = self._workflow()
        for backend, expected_fixtures in FIXTURES.items():
            with self.subTest(backend=backend):
                job = self._job(backend)
                fixtures = re.findall(
                    r"--fixture ([^=\s]+)=([0-9a-f]{64})", job
                )
                self.assertEqual(fixtures, expected_fixtures)
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

    def test_each_fixture_checkout_disables_autocrlf_before_submodule_update(self):
        autocrlf = "git config --global core.autocrlf false"
        submodule_update = "git submodule update --init --depth 1"
        for backend in FIXTURES:
            with self.subTest(backend=backend):
                job = self._job(backend)
                self.assertEqual(job.count(autocrlf), 1)
                self.assertLess(job.index(autocrlf), job.index(submodule_update))

    def test_each_required_integration_imports_tests_from_checkout_root(self):
        expected = "PYTHONPATH: ${{ github.workspace }}"
        for backend in FIXTURES:
            with self.subTest(backend=backend):
                steps = [
                    step
                    for step in re.split(
                        r"(?m)(?=^      - (?:name:|uses:))",
                        self._job(backend),
                    )
                    if "python ChemBlender/scripts/run_required_integration.py" in step
                ]
                self.assertEqual(len(steps), 1)
                self.assertEqual(steps[0].count(expected), 1)

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
