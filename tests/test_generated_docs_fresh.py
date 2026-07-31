import importlib.util
import json
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "ChemBlender" / "scripts" / "generate_format_docs.py"
FORMAT_CAPABILITIES = ROOT / "docs" / "user" / "format-capabilities.json"
DEPENDENCIES = ROOT / "docs" / "user" / "dependencies.json"
FORMATS = ROOT / "docs" / "user" / "formats.md"


def _canonical_json(document):
    return (
        json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


class GeneratedDocsFreshnessTests(unittest.TestCase):
    def _module(self):
        self.assertTrue(SCRIPT.is_file(), "format documentation generator is missing")
        spec = importlib.util.spec_from_file_location("generate_format_docs", SCRIPT)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_in_memory_generation_is_deterministic_canonical_and_fresh(self):
        module = self._module()

        first = module.render_documents(ROOT)
        second = module.render_documents(ROOT)

        self.assertEqual(first, second)
        self.assertEqual(
            set(first),
            {
                "docs/quantum-visualization/reader-capability-matrix.json",
                "docs/user/dependencies.json",
                "docs/user/format-capabilities.json",
                "docs/user/formats.md",
            },
        )
        for relative_path, generated in first.items():
            self.assertEqual(
                (ROOT / relative_path).read_bytes(),
                generated,
                relative_path,
            )
        for relative_path in (
            "docs/user/dependencies.json",
            "docs/user/format-capabilities.json",
            "docs/quantum-visualization/reader-capability-matrix.json",
        ):
            document = json.loads(first[relative_path])
            self.assertEqual(first[relative_path], _canonical_json(document))

    def test_format_capabilities_derive_runtime_contracts_and_export_maturity(self):
        document = json.loads(
            self._module().render_documents(ROOT)[
                "docs/user/format-capabilities.json"
            ]
        )

        self.assertEqual(document["reader_api_version"], "1.0-rc1")
        self.assertEqual(
            document["schema_name"],
            "chemblender_reader_capability_matrix",
        )
        self.assertEqual(document["schema_version"], 2)
        readers = document["readers"]
        self.assertEqual(
            [reader["reader_id"] for reader in readers],
            sorted(reader["reader_id"] for reader in readers),
        )
        self.assertEqual(len(readers), 19)
        required = {
            "availability_contract",
            "basenames",
            "execution_mode",
            "export",
            "extensions",
            "fixture_families",
            "capabilities",
            "plugin_id",
            "reader_api_version",
            "reader_id",
            "reader_version",
        }
        for reader in readers:
            self.assertEqual(set(reader), required)
            self.assertEqual(reader["plugin_id"], "chemblender.builtin")
            self.assertEqual(reader["execution_mode"], "built_in")
            self.assertEqual(reader["reader_api_version"], "1.0-rc1")
            self.assertNotIn("available", reader["availability_contract"])
            self.assertTrue(reader["fixture_families"])

        by_id = {reader["reader_id"]: reader for reader in readers}
        self.assertEqual(by_id["poscar"]["basenames"], ["CONTCAR", "POSCAR"])
        self.assertEqual(
            by_id["cif"]["availability_contract"],
            {"kind": "python_module", "module": "gemmi"},
        )
        self.assertEqual(
            by_id["xyz"]["availability_contract"],
            {"kind": "always"},
        )
        self.assertEqual(
            by_id["xyz"]["export"],
            {
                "execution_mode": "project_browser",
                "format_id": "xyz",
                "loss_policy": "lossless",
                "maturity": "F5",
            },
        )
        self.assertEqual(by_id["cube"]["export"]["maturity"], "F0")
        self.assertEqual(by_id["cube"]["export"]["execution_mode"], "none")
        self.assertEqual(by_id["cjson"]["export"]["execution_mode"], "core")

    def test_dependency_document_uses_the_pinned_inventory_without_runtime_claims(self):
        document = json.loads(
            self._module().render_documents(ROOT)["docs/user/dependencies.json"]
        )
        with (ROOT / "ChemBlender" / "dependencies.toml").open("rb") as handle:
            source = tomllib.load(handle)["dependency"]

        dependencies = document["dependencies"]
        self.assertEqual(
            [item["distribution"] for item in dependencies],
            sorted(item["distribution"] for item in dependencies),
        )
        self.assertEqual(
            {item["distribution"] for item in dependencies},
            {item["distribution"] for item in source},
        )
        source_by_name = {item["distribution"]: item for item in source}
        for item in dependencies:
            pinned = source_by_name[item["distribution"]]
            for source_key, output_key in (
                ("filename", "filename"),
                ("version", "version"),
                ("sha256", "sha256"),
                ("url", "source"),
            ):
                self.assertEqual(item[output_key], pinned[source_key])
            self.assertEqual(item["availability"]["kind"], "bundled_wheel")
            self.assertEqual(item["availability"]["required"], pinned["required"])
            self.assertNotIn("available", item["availability"])
            self.assertTrue(item["role"]["reader_ids"])

        self.assertEqual(
            next(
                item for item in dependencies if item["distribution"] == "rdkit"
            )["role"],
            {
                "kind": "reader_backend",
                "reader_ids": ["mol", "mol-v2000", "sdf", "smiles"],
            },
        )
        self.assertEqual(
            next(
                item for item in dependencies if item["distribution"] == "gemmi"
            )["role"],
            {"kind": "reader_backend", "reader_ids": ["cif"]},
        )

    def test_formats_marked_section_and_cli_check_are_current(self):
        formats = FORMATS.read_text(encoding="utf-8")
        self.assertEqual(
            formats.count("<!-- BEGIN GENERATED FORMAT CAPABILITIES -->"),
            1,
        )
        self.assertEqual(
            formats.count("<!-- END GENERATED FORMAT CAPABILITIES -->"),
            1,
        )
        self.assertIn("| Reader | Import | Export | Runtime | Fixtures |", formats)

        result = subprocess.run(
            (
                sys.executable,
                str(SCRIPT),
                "--repository-root",
                str(ROOT),
                "--check",
            ),
            cwd=ROOT,
            check=False,
            capture_output=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_formats_generation_preserves_the_tracked_crlf_contract(self):
        generated = self._module().render_documents(ROOT)[
            "docs/user/formats.md"
        ]

        self.assertGreater(generated.count(b"\r\n"), 0)
        self.assertEqual(generated.count(b"\n"), generated.count(b"\r\n"))


if __name__ == "__main__":
    unittest.main()
