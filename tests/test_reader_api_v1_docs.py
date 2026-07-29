import ast
import re
import tomllib
import unittest
from pathlib import Path

import ChemBlender.reader_api as reader_api


ROOT = Path(__file__).resolve().parents[1]
DOC_ROOT = ROOT / "docs" / "reader-api-v1"
DOC_NAMES = (
    "README.md",
    "manifest.md",
    "python-api.md",
    "worker-api.md",
    "diagnostics.md",
    "compatibility.md",
)


class ReaderApiV1DocumentationTests(unittest.TestCase):
    def read_doc(self, name):
        path = DOC_ROOT / name
        raw = path.read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), path)
        return raw.decode("utf-8")

    def test_document_set_is_linked_and_utf8_without_bom(self):
        documents = {name: self.read_doc(name) for name in DOC_NAMES}
        root_index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
        self.assertIn("reader-api-v1/README.md", root_index)
        for name in DOC_NAMES[1:]:
            self.assertIn(f"]({name})", documents["README.md"])

        for name, text in documents.items():
            for destination in re.findall(r"\[[^]]+\]\(([^)]+)\)", text):
                destination = destination.strip("<>").split("#", 1)[0]
                if not destination or destination.startswith(("http://", "https://")):
                    continue
                self.assertTrue(
                    (DOC_ROOT / destination).resolve().exists(),
                    f"{name}: {destination}",
                )

    def test_documented_public_symbols_are_the_exact_importable_surface(self):
        document = self.read_doc("python-api.md")
        match = re.search(
            r"```python\nPUBLIC_SYMBOLS = (\(.*?\))\n```",
            document,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        documented = ast.literal_eval(match.group(1))
        self.assertEqual(documented, reader_api.__all__)
        self.assertEqual(len(documented), len(set(documented)))
        namespace = {}
        exec(
            f"from ChemBlender.reader_api import {', '.join(documented)}",
            namespace,
        )
        self.assertTrue(all(name in namespace for name in documented))

    def test_installed_extension_bootstrap_uses_the_versioned_handle(self):
        document = self.read_doc("README.md")
        match = re.search(
            r"<!-- installed-extension-bootstrap -->\n```python\n(.*?)\n```",
            document,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        source = match.group(1)
        ast.parse(source)
        self.assertIn('"chemblender.reader_api.v1"', source)
        self.assertIn("bpy.app.driver_namespace", source)
        self.assertIn("import_module(handle.module_name)", source)
        self.assertIn("handle.register_callback", source)
        self.assertNotIn("bl_ext.user_default", source)
        self.assertNotIn("ChemBlender.core", source)

    def test_manifest_example_is_accepted_by_the_public_parser(self):
        document = self.read_doc("manifest.md")
        match = re.search(r"```toml\n(.*?)\n```", document, re.DOTALL)
        self.assertIsNotNone(match)
        source = match.group(1)
        parsed = tomllib.loads(source)
        self.assertEqual(parsed["chemblender_api"], ">=1.0,<2.0")
        manifest = reader_api.ReaderPluginManifest.from_toml(source)
        self.assertEqual(manifest.plugin_id, "org.example.reader")
        self.assertEqual(manifest.readers[0].reader_id, "example-format")

    def test_lifecycle_diagnostics_worker_and_compatibility_contracts_are_present(self):
        python_api = self.read_doc("python-api.md")
        worker_api = self.read_doc("worker-api.md")
        diagnostics = self.read_doc("diagnostics.md")
        compatibility = self.read_doc("compatibility.md")

        for term in (
            "discovery",
            "availability",
            "SniffRequest",
            "ParseRequest",
            "ProgressEvent",
            "is_cancelled",
            "PublicImportBatch",
            "canonical",
            "sidecar",
        ):
            self.assertIn(term, python_api)
        for term in (
            "reader.parse@0.1",
            "import-batch.json",
            "artifacts/<content-sha256>.npy",
            "SHA-256",
            "cancellation",
        ):
            self.assertIn(term, worker_api)
        for term in (
            "ParserReport",
            "ImportDiagnostic",
            "exception isolation",
            "plugin is missing",
            "reparse",
        ):
            self.assertIn(term, diagnostics)
        for term in (
            "same major",
            "optional fields",
            "two formal minor releases",
            "disabled",
            "diagnostic",
        ):
            self.assertIn(term, compatibility)

        combined = "\n".join(
            self.read_doc(name)
            for name in DOC_NAMES
        )
        self.assertNotIn("bl_ext.user_default", combined)
        self.assertNotIn("ChemBlender.core.model", combined)
        self.assertIn(reader_api.READER_API_VERSION, combined)


if __name__ == "__main__":
    unittest.main()
