import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ChemBlender/scripts/generate_public_delivery_docs.py"


class PublicDeliveryDocsTests(unittest.TestCase):
    def module(self):
        spec = importlib.util.spec_from_file_location("public_delivery_docs", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_generated_public_surface_and_offline_guides_are_fresh(self):
        documents = self.module().render_documents()
        for relative, content in documents.items():
            self.assertEqual((ROOT / relative).read_bytes(), content, relative)
        surface = json.loads(documents["docs/prepare/public-surface.json"])
        self.assertEqual(len(surface["cli_commands"]), 10)
        self.assertEqual(len(surface["gui_commands"]), 9)
        self.assertEqual(len(surface["operations"]), 21)
        self.assertEqual(len(surface["readers"]), 22)
        self.assertEqual(len(surface["export_formats"]), 13)
        self.assertEqual(surface["reader_api_version"], "1.0-rc1")
        self.assertFalse(surface["python_sdk"])

    def test_offline_guides_have_no_remote_or_missing_resources(self):
        documents = self.module().render_documents()
        for language in ("en", "zh-CN"):
            manifest = json.loads(documents[f"docs/offline/{language}/manifest.json"])
            self.assertEqual(manifest["remote_resources"], 0)
            self.assertEqual(manifest["missing_resources"], 0)
            self.assertGreater(manifest["link_count"], 5)
            self.assertEqual(manifest["image_count"], 1)
            self.assertEqual(
                set(manifest["image_sha256"]),
                {"docs/user/assets/2.5.0/blender-viewer.png"},
            )


if __name__ == "__main__":
    unittest.main()
