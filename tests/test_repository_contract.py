import subprocess
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "ChemBlender"
WHEEL = "rdkit-2026.3.3-cp313-cp313-win_amd64.whl"


class RepositoryContractTests(unittest.TestCase):
    def test_extension_layout_and_manifest(self):
        manifest = tomllib.loads(
            (EXTENSION / "blender_manifest.toml").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["id"], "chemblender")
        self.assertEqual(manifest["version"], "2.2.0")
        self.assertEqual(manifest["blender_version_min"], "5.1.0")
        self.assertEqual(manifest["platforms"], ["windows-x64"])
        self.assertEqual(manifest["wheels"], [f"./wheels/{WHEEL}"])
        self.assertTrue((EXTENSION / "__init__.py").exists())
        self.assertTrue((EXTENSION / "scripts" / "build_extension.py").exists())

    def test_generated_and_local_dependencies_are_not_tracked(self):
        tracked = subprocess.run(
            ["git", "ls-files", "ChemBlender/wheels/*.whl", ".agents/cache/**"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.assertEqual(tracked, "")

    def test_runtime_source_has_no_package_install(self):
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in EXTENSION.rglob("*.py")
            if "scripts" not in path.parts
        ).lower()
        self.assertNotIn("pip install", source)
        self.assertNotIn('"-m", "pip"', source)

    def test_extension_uses_minimal_autoload_entrypoint(self):
        init_source = (EXTENSION / "__init__.py").read_text(encoding="utf-8")
        auto_load_source = (EXTENSION / "auto_load.py").read_text(encoding="utf-8")
        self.assertNotIn("bl_info", init_source)
        self.assertIn("auto_load.init()", init_source)
        self.assertIn("auto_load.register()", init_source)
        self.assertIn("auto_load.unregister()", init_source)
        self.assertIn('"wheels"', auto_load_source)
        self.assertIn("clear_submodule_cache", auto_load_source)

if __name__ == "__main__":
    unittest.main()
