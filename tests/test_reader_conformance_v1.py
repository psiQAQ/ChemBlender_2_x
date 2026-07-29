import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import ChemBlender.reader_api as reader_api
from ChemBlender.reader_api.conformance import (
    ReaderConformanceCase,
    run_reader_conformance_v1,
)
from ChemBlender.reader_api.protocol import ProgressEvent
from ChemBlender.reader_api.registry import ReaderPluginRegistry


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "reader-extension"
FIXTURE = EXAMPLE / "fixtures" / "water.cbsimple"
BUILTIN_FIXTURES = ROOT / "tests" / "fixtures"


def load_example_plugin():
    spec = importlib.util.spec_from_file_location(
        "_chemblender_test_simplecoords",
        EXAMPLE / "reader.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.create_plugin(reader_api)


def example_case(plugin=None):
    plugin = load_example_plugin() if plugin is None else plugin
    return ReaderConformanceCase(
        "simplecoords-water",
        ReaderPluginRegistry((plugin,)),
        "simplecoords",
        FIXTURE,
        ("structure",),
    )


class _RegressingProgressPlugin:
    def __init__(self, wrapped):
        self.wrapped = wrapped
        self.manifest = wrapped.manifest
        self.descriptor = wrapped.descriptor
        self.priority = wrapped.priority

    def sniff(self, request):
        return self.wrapped.sniff(request)

    def parse(self, request):
        request.progress(ProgressEvent("plugin", 2, 3))
        request.progress(ProgressEvent("plugin", 1, 3))
        return self.wrapped.parse(request)


class ReaderConformanceV1Tests(unittest.TestCase):
    def test_documented_cli_and_result_contract_are_present(self):
        document = (
            ROOT / "docs" / "reader-api-v1" / "conformance.md"
        ).read_text(encoding="utf-8")
        for term in (
            "ChemBlender.reader_api.conformance_cli",
            "--plugin-path",
            "--fixtures",
            "--output",
            "fixture basename/SHA-256",
            "pass`/`fail`/`skip",
            "required case 不允许 skip",
            "exception isolation",
        ):
            self.assertIn(term, document)

    def test_v1_document_contains_identity_status_hashes_and_environment(self):
        document = run_reader_conformance_v1((example_case(),))

        self.assertEqual(document["schema_version"], "1")
        self.assertEqual(
            document["reader_api_version"], reader_api.READER_API_VERSION
        )
        self.assertEqual(
            document["plugin"],
            {
                "id": "org.chemblender.example.simplecoords",
                "version": "1.0.0",
            },
        )
        self.assertEqual(document["summary"], {"fail": 0, "pass": 1, "skip": 0})
        self.assertTrue(document["passed"])
        case = document["cases"][0]
        self.assertEqual(case["case_id"], "simplecoords-water")
        self.assertEqual(case["status"], "pass")
        self.assertTrue(case["required"])
        self.assertIsNone(case["skip_reason"])
        self.assertEqual(case["reader"], {"id": "simplecoords", "version": "1.0"})
        self.assertEqual(case["fixture"]["path"], "water.cbsimple")
        self.assertRegex(case["fixture"]["sha256"], r"^[0-9a-f]{64}$")
        self.assertGreaterEqual(case["duration_seconds"], 0.0)
        self.assertEqual(case["diagnostics"], [])
        self.assertEqual(
            tuple(check["id"] for check in case["checks"])[-4:],
            (
                "quality_diagnostics",
                "progress_monotonicity",
                "artifact_security",
                "declared_capabilities",
            ),
        )
        self.assertTrue(all(check["status"] == "pass" for check in case["checks"]))
        self.assertEqual(document["environment"]["implementation"], "CPython")
        json.dumps(document, allow_nan=False, sort_keys=True)

    def test_optional_skip_requires_an_explicit_reason_and_required_cases_do_not_skip(self):
        case = example_case()
        with self.assertRaisesRegex(ValueError, "skip reason"):
            run_reader_conformance_v1(
                (case,),
                optional_skip_reasons={"simplecoords-water": ""},
            )

        document = run_reader_conformance_v1(
            (case,),
            optional_skip_reasons={
                "simplecoords-water": "optional dependency unavailable"
            },
        )
        result = document["cases"][0]
        self.assertEqual(result["status"], "skip")
        self.assertFalse(result["required"])
        self.assertEqual(
            result["skip_reason"], "optional dependency unavailable"
        )
        self.assertEqual(document["summary"], {"fail": 0, "pass": 0, "skip": 1})
        self.assertTrue(document["passed"])

    def test_progress_regression_is_a_required_failure(self):
        plugin = _RegressingProgressPlugin(load_example_plugin())
        document = run_reader_conformance_v1((example_case(plugin),))

        self.assertFalse(document["passed"])
        result = document["cases"][0]
        self.assertEqual(result["status"], "fail")
        progress = next(
            check
            for check in result["checks"]
            if check["id"] == "progress_monotonicity"
        )
        self.assertEqual(progress["status"], "fail")
        self.assertIn("monotonic", progress["detail"])

    def test_wave1_to_wave3_builtin_matrix_has_no_required_skip(self):
        registry = reader_api.builtin_reader_plugin_registry()
        specifications = (
            ("xyz", "xyz/water.xyz", ("structure",)),
            (
                "extxyz",
                "extxyz/multiframe-cell.extxyz",
                ("properties", "structure", "trajectory"),
            ),
            (
                "cube",
                "cube/sheared.cube",
                ("atomic_property", "grid", "structure"),
            ),
            (
                "cjson",
                "cjson/water-results.cjson",
                ("excited_state", "spectrum", "structure", "topology", "trajectory"),
            ),
            (
                "mol2",
                "mol2/small.mol2",
                (
                    "atomic_property",
                    "multi_record",
                    "structure",
                    "substructure",
                    "topology",
                ),
            ),
            (
                "pdb",
                "pdb/altloc.pdb",
                (
                    "atomic_identity",
                    "atomic_property",
                    "crystal",
                    "hierarchy",
                    "multi_model",
                    "structure",
                    "topology",
                    "trajectory",
                ),
            ),
            (
                "pqr",
                "pqr/no-chain.pqr",
                ("atomic_identity", "atomic_property", "hierarchy", "structure"),
            ),
            (
                "poscar",
                "poscar/cscl-selective.vasp",
                ("atomic_property", "crystal", "structure"),
            ),
        )
        cases = tuple(
            ReaderConformanceCase(
                f"builtin-{reader_id}",
                registry,
                reader_id,
                BUILTIN_FIXTURES / relative,
                capabilities,
            )
            for reader_id, relative, capabilities in specifications
        )
        document = run_reader_conformance_v1(cases)

        self.assertTrue(document["passed"], document)
        self.assertEqual(document["summary"], {"fail": 0, "pass": 8, "skip": 0})
        self.assertTrue(all(case["required"] for case in document["cases"]))

    def test_optional_dependency_cases_have_explicit_skip_reasons(self):
        registry = reader_api.builtin_reader_plugin_registry()
        cases = (
            ReaderConformanceCase(
                "builtin-cif-optional",
                registry,
                "cif",
                BUILTIN_FIXTURES / "cif" / "quartz.cif",
                ("cif_envelope", "crystal", "structure"),
            ),
            ReaderConformanceCase(
                "builtin-mol-optional",
                registry,
                "mol",
                BUILTIN_FIXTURES / "mol" / "water.mol",
                ("atomic_identity", "molecular_record", "structure", "topology"),
            ),
        )
        reasons = {
            case.name: (
                f"{case.reader_id} optional dependency unavailable in base runtime"
            )
            for case in cases
        }
        document = run_reader_conformance_v1(
            cases,
            optional_skip_reasons=reasons,
        )

        self.assertTrue(document["passed"])
        self.assertEqual(document["summary"], {"fail": 0, "pass": 0, "skip": 2})
        self.assertTrue(
            all(
                not case["required"] and case["skip_reason"]
                for case in document["cases"]
            )
        )

    def test_cli_runs_plugin_in_a_child_and_writes_canonical_utf8_json(self):
        with TemporaryDirectory() as temporary:
            output = Path(temporary) / "result.json"
            completed = subprocess.run(
                (
                    sys.executable,
                    "-m",
                    "ChemBlender.reader_api.conformance_cli",
                    "--plugin-path",
                    str(EXAMPLE),
                    "--fixtures",
                    str(EXAMPLE / "fixtures"),
                    "--output",
                    str(output),
                ),
                cwd=ROOT,
                capture_output=True,
                check=False,
            )

            self.assertEqual(
                completed.returncode,
                0,
                completed.stderr.decode("utf-8", errors="replace"),
            )
            raw = output.read_bytes()
            self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
            self.assertTrue(raw.endswith(b"\n"))
            document = json.loads(raw)
            self.assertTrue(document["passed"])
            self.assertEqual(
                raw,
                (
                    json.dumps(
                        document,
                        allow_nan=False,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                    + "\n"
                ).encode("utf-8"),
            )
            self.assertEqual(document["environment"]["process_isolation"], "subprocess")

    def test_cli_rejects_unsafe_plugin_or_fixture_paths(self):
        with TemporaryDirectory() as temporary:
            output = Path(temporary) / "result.json"
            completed = subprocess.run(
                (
                    sys.executable,
                    "-m",
                    "ChemBlender.reader_api.conformance_cli",
                    "--plugin-path",
                    str(EXAMPLE / "reader.py"),
                    "--fixtures",
                    str(EXAMPLE / "fixtures"),
                    "--output",
                    str(output),
                ),
                cwd=ROOT,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(completed.returncode, 0)
        self.assertFalse(output.exists())

    def test_cli_returns_one_and_keeps_machine_readable_required_failure(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixtures = root / "fixtures"
            fixtures.mkdir()
            (fixtures / "broken.cbsimple").write_bytes(b"not simplecoords\n")
            output = root / "result.json"
            completed = subprocess.run(
                (
                    sys.executable,
                    "-m",
                    "ChemBlender.reader_api.conformance_cli",
                    "--plugin-path",
                    str(EXAMPLE),
                    "--fixtures",
                    str(fixtures),
                    "--output",
                    str(output),
                ),
                cwd=ROOT,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 1)
            document = json.loads(output.read_bytes())
            self.assertFalse(document["passed"])
            self.assertEqual(document["cases"][0]["status"], "fail")
            self.assertTrue(document["cases"][0]["required"])


if __name__ == "__main__":
    unittest.main()
