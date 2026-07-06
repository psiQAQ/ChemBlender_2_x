import tomllib
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class ExtensionPackagingTests(unittest.TestCase):
    def test_manifest_declares_windows_5_1_extension_and_wheels(self):
        manifest_path = REPO_ROOT / "blender_manifest.toml"
        self.assertTrue(manifest_path.exists(), "缺少 blender_manifest.toml")

        manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["schema_version"], "1.0.0")
        self.assertEqual(manifest["type"], "add-on")
        self.assertEqual(manifest["blender_version_min"], "5.1.0")
        self.assertEqual(manifest["platforms"], ["windows-x64"])

        wheels = manifest.get("wheels")
        self.assertIsInstance(wheels, list)
        self.assertTrue(wheels, "manifest 必须声明至少一个 wheel")
        self.assertTrue(
            any("rdkit" in wheel.lower() for wheel in wheels),
            "manifest 必须声明 rdkit wheel",
        )
        for wheel in wheels:
            self.assertTrue(wheel.startswith("./wheels/"))
            self.assertTrue((REPO_ROOT / wheel[2:]).exists(), f"wheel 不存在: {wheel}")

    def test_auto_load_does_not_assume_directory_name_as_package(self):
        auto_load_text = (REPO_ROOT / "auto_load.py").read_text(encoding="utf-8")
        init_text = (REPO_ROOT / "__init__.py").read_text(encoding="utf-8")

        self.assertNotIn("directory.name", auto_load_text)
        self.assertIn("auto_load.init(__package__)", init_text)
    def test_runtime_install_ui_is_removed(self):
        panel_text = (REPO_ROOT / "panel.py").read_text(encoding="utf-8")
        ex_package_text = (REPO_ROOT / "ex_package.py").read_text(encoding="utf-8")

        self.assertNotIn("chem.install_rdkit", panel_text)
        self.assertNotIn("pypi_mirror", panel_text)
        self.assertNotIn("pip install", ex_package_text.lower())
        self.assertNotIn('"-m", "pip"', ex_package_text)


if __name__ == "__main__":
    unittest.main()
