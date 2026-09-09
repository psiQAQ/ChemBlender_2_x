"""Reader runtime ownership after moving parsing out of the Viewer."""

import ast
import importlib
import subprocess
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

from chemblender_prepare.reader_api.discovery import ReaderPluginDiscovery
from chemblender_prepare.reader_api.registry import builtin_reader_plugin_registry
from tests.test_plugin_discovery import external_plugin

ROOT = Path(__file__).resolve().parents[1]


class ReaderAPIBridgeContractTests(unittest.TestCase):
    def test_cold_external_import_has_no_blender_or_science_dependency(self):
        code = """
import importlib.abc, sys
class RejectImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'bpy', 'ChemBlender', 'rdkit', 'gemmi', 'spglib', 'gbasis', 'iodata'}:
            raise AssertionError('unexpected import: ' + fullname)
sys.meta_path.insert(0, RejectImports())
from chemblender_prepare.reader_api.registry import builtin_reader_plugin_registry
from chemblender_prepare.reader_api.discovery import ReaderPluginDiscovery
snapshot = ReaderPluginDiscovery(builtin_reader_plugin_registry()).refresh()
assert len(snapshot.descriptors) == 22, len(snapshot.descriptors)
"""
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_discovery_snapshot_is_frozen_and_versioned_per_reader(self):
        discovery = ReaderPluginDiscovery(builtin_reader_plugin_registry())
        snapshot = discovery.refresh()
        self.assertIs(snapshot, discovery.refresh())
        with self.assertRaises(FrozenInstanceError):
            snapshot.generation = -1
        self.assertTrue(all(item.plugin_version and item.reader_version
                            for item in snapshot.descriptors))

    def test_registries_do_not_share_external_registration_or_failures(self):
        first = ReaderPluginDiscovery(builtin_reader_plugin_registry())
        second = ReaderPluginDiscovery(builtin_reader_plugin_registry())
        unchanged = second.refresh()
        plugin = external_plugin("org.example.isolation", "external.isolation")
        self.assertTrue(first.register(plugin).availability.available)
        self.assertFalse(first.register(plugin).availability.available)
        self.assertIs(second.refresh(), unchanged)
        self.assertNotIn(plugin.descriptor, unchanged.descriptors)
        self.assertTrue(first.unregister(plugin.manifest))
        self.assertTrue(all(item.availability.available for item in first.refresh().plugins))
        self.assertIs(second.refresh(), unchanged)

    def test_viewer_neither_owns_nor_imports_reader_api(self):
        self.assertFalse((ROOT / "ChemBlender/runtime/reader_api_bridge.py").exists())
        self.assertFalse(any((ROOT / "ChemBlender/reader_api").glob("*.py")))
        paths = tuple((ROOT / "ChemBlender/runtime").glob("*.py"))
        self.assertTrue(paths)
        for path in paths:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            self.assertNotIn("chemblender.reader_api.v1", source, path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [item.name for item in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                self.assertFalse(any("reader_api" in name or
                                     name.startswith("chemblender_prepare")
                                     for name in names), path)

    def test_root_lifecycle_lazy_delegates_to_registration_owner(self):
        package = importlib.import_module("ChemBlender")
        events = []
        registration = ModuleType("ChemBlender.runtime.registration")
        registration.register_extension = (
            lambda package_root: events.append(("register", package_root))
        )
        registration.unregister_extension = (
            lambda: events.append(("unregister",))
        )

        with patch.dict(
            sys.modules,
            {
                "ChemBlender.runtime.registration": registration,
            },
        ):
            for _ in range(2):
                package.register()
                package.unregister()

        self.assertEqual(
            events,
            [
                ("register", "ChemBlender"),
                ("unregister",),
                ("register", "ChemBlender"),
                ("unregister",),
            ],
        )

    def test_external_reader_and_model_identity_survive_viewer_lifecycle(self):
        from chemblender_prepare.reader_api import PublicImportBatch, ReaderPluginManifest
        registry = builtin_reader_plugin_registry()
        discovery = ReaderPluginDiscovery(registry)
        builtin_ids = tuple(id(item) for item in registry.descriptors)
        plugin = external_plugin("org.example.lifecycle", "external.lifecycle")
        self.assertTrue(discovery.register(plugin).availability.available)
        snapshot = discovery.refresh()
        self.test_root_lifecycle_lazy_delegates_to_registration_owner()
        self.assertIs(discovery.refresh(), snapshot)
        self.assertEqual(tuple(id(item) for item in registry.descriptors
                               if item.plugin_id == "chemblender.builtin"), builtin_ids)
        self.assertIs(next(item for item in registry.descriptors
                           if item.reader_id == plugin.descriptor.reader_id), plugin.descriptor)
        api = importlib.import_module("chemblender_prepare.reader_api")
        self.assertIs(api.PublicImportBatch, PublicImportBatch)
        self.assertIs(api.ReaderPluginManifest, ReaderPluginManifest)
        self.assertTrue(discovery.unregister(plugin.manifest))


if __name__ == "__main__":
    unittest.main()
