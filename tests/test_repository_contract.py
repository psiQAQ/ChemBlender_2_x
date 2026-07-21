import re
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
        self.assertLessEqual(len(manifest["permissions"]["files"]), 64)
        self.assertIn("network", manifest["permissions"])
        self.assertLessEqual(len(manifest["permissions"]["network"]), 64)
        self.assertIn("scripts/", manifest["build"]["paths_exclude_pattern"])
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

    def test_package_workflow_pins_and_verifies_release_inputs(self):
        workflow = (ROOT / ".github" / "workflows" / "extension-package.yml").read_text(
            encoding="utf-8"
        )
        for action in (
            "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
            "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
            "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
        ):
            self.assertIn(action, workflow)
        self.assertIn("permissions:", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("timeout-minutes:", workflow)
        self.assertIn("BLENDER_USER_RESOURCES", workflow)
        self.assertIn("chemblender-2.2.0.sha256", workflow)
        self.assertIn("if: github.ref_type == 'tag'", workflow)
        self.assertIn("GITHUB_REF_NAME.TrimStart('v')", workflow)
        self.assertIn("Tag $tagVersion does not match manifest $manifestVersion", workflow)
        self.assertIn("blender-5.1.2.sha256", workflow)
        self.assertIn("f8bd59b24e128c9c70c975bfb1920cf610ba3096439a24ca2850eb861e767c48", workflow)

    def test_blender_smoke_covers_release_artifact(self):
        smoke = (ROOT / "tests" / "blender_smoke.py").read_text(encoding="utf-8")
        for expected in (
            "ZipFile",
            "Chem_Nodes.blend",
            "Chem_Nodes_En.blend",
            "EmbedMolecule",
            "--keep-enabled",
        ):
            self.assertIn(expected, smoke)

    def test_release_workflow_is_manual_and_deterministic(self):
        workflow = (ROOT / ".github" / "workflows" / "extension-release.yml").read_text(
            encoding="utf-8"
        )
        trigger = workflow.split("permissions:", 1)[0]
        self.assertIn("workflow_dispatch:", trigger)
        self.assertNotIn("pull_request:", trigger)
        self.assertNotIn("workflow_run:", trigger)
        self.assertNotRegex(trigger, r"(?m)^\s+push:")
        for expected in (
            "tag:",
            "publish:",
            "type: boolean",
            "default: false",
            "actions: read",
            "contents: read",
            "contents: write",
            "environment: release",
            "if: ${{ inputs.publish }}",
            "gh run list",
            "--workflow extension-package.yml",
            "--commit \"$tag_commit\"",
            "gh release create",
            "--draft",
            ".digest",
            "gh release edit",
            "--draft=false --latest",
        ):
            self.assertIn(expected, workflow)
        self.assertEqual(workflow.count("verify_release_artifact.py"), 2)
        self.assertEqual(workflow.count("path: tag-source"), 2)
        self.assertEqual(workflow.count("--extension-root tag-source/ChemBlender"), 2)
        self.assertIn("git -C tag-source", workflow)
        self.assertEqual(workflow.count("contents: write"), 1)
        actions = re.findall(r"uses:\s+([^\s]+)", workflow)
        self.assertTrue(actions)
        for action in actions:
            self.assertRegex(action, r"@[0-9a-f]{40}$")

if __name__ == "__main__":
    unittest.main()
