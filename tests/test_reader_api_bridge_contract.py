import ast
import importlib
import sys
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from types import ModuleType
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class ReaderAPIBridgeContractTests(unittest.TestCase):
    def bridge(self):
        return importlib.import_module(
            "ChemBlender.runtime.reader_api_bridge"
        )

    def test_import_is_bpy_free_and_handle_is_versioned_frozen_metadata(self):
        sys.modules.pop("ChemBlender.runtime.reader_api_bridge", None)
        before = set(sys.modules)

        bridge = self.bridge()
        namespace = {}
        handle = bridge.register_reader_api_handle(
            "synthetic_repository.chemblender",
            namespace=namespace,
        )

        self.assertNotIn("bpy", set(sys.modules) - before)
        self.assertEqual(
            bridge.READER_API_HANDLE_KEY,
            "chemblender.reader_api.v0",
        )
        self.assertEqual(handle.api_version, "0.1")
        self.assertEqual(
            handle.module_name,
            "synthetic_repository.chemblender.reader_api",
        )
        self.assertIsNotNone(handle.owner_token)
        self.assertTrue(callable(handle.register_callback))
        self.assertTrue(callable(handle.unregister_callback))
        with self.assertRaises(FrozenInstanceError):
            handle.module_name = "changed"
        self.assertTrue(
            bridge.remove_reader_api_handle(handle, namespace=namespace)
        )

    def test_publication_is_idempotent_for_owner_and_rejects_conflicts(self):
        bridge = self.bridge()
        namespace = {}

        first = bridge.register_reader_api_handle(
            "synthetic_repository.chemblender",
            namespace=namespace,
        )
        second = bridge.register_reader_api_handle(
            "synthetic_repository.chemblender",
            namespace=namespace,
        )

        self.assertIs(second, first)
        forged = bridge.ReaderAPIHandle(
            "0.2",
            first.module_name,
            first.owner_token,
            lambda plugin: None,
            lambda manifest: None,
        )
        namespace[bridge.READER_API_HANDLE_KEY] = forged
        with self.assertRaises(bridge.ReaderAPIRegistrationError):
            bridge.register_reader_api_handle(
                "synthetic_repository.chemblender",
                namespace=namespace,
            )
        self.assertIs(namespace[bridge.READER_API_HANDLE_KEY], forged)
        with self.assertRaises(bridge.ReaderAPIRegistrationError):
            bridge.register_reader_api_handle(
                "different_repository.chemblender",
                namespace={},
            )
        namespace[bridge.READER_API_HANDLE_KEY] = first
        self.assertTrue(
            bridge.remove_reader_api_handle(first, namespace=namespace)
        )

    def test_removal_requires_exact_owned_handle(self):
        bridge = self.bridge()
        namespace = {}
        handle = bridge.register_reader_api_handle(
            "synthetic_repository.chemblender",
            namespace=namespace,
        )
        forged = bridge.ReaderAPIHandle(
            handle.api_version,
            handle.module_name,
            handle.owner_token,
            handle.register_callback,
            handle.unregister_callback,
        )

        self.assertFalse(
            bridge.remove_reader_api_handle(forged, namespace=namespace)
        )
        self.assertIs(
            namespace[bridge.READER_API_HANDLE_KEY],
            handle,
        )
        self.assertTrue(
            bridge.remove_reader_api_handle(handle, namespace=namespace)
        )
        self.assertNotIn(bridge.READER_API_HANDLE_KEY, namespace)
        self.assertFalse(
            bridge.remove_reader_api_handle(handle, namespace=namespace)
        )

    def test_bridge_uses_lazy_bpy_and_no_fixed_extension_namespace(self):
        bridge_path = ROOT / "ChemBlender/runtime/reader_api_bridge.py"
        paths = (
            ROOT / "ChemBlender/__init__.py",
            bridge_path,
            *(ROOT / "ChemBlender/reader_api").glob("*.py"),
        )
        for path in paths:
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("bl_ext.user_default", source)
        top_level_imports = ast.parse(
            bridge_path.read_text(encoding="utf-8")
        ).body
        self.assertFalse(
            any(
                (
                    isinstance(node, ast.Import)
                    and any(alias.name == "bpy" for alias in node.names)
                )
                or (
                    isinstance(node, ast.ImportFrom)
                    and node.module == "bpy"
                )
                for node in top_level_imports
            )
        )

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

    def test_registry_builtins_models_and_external_reader_survive_handle_cycle(self):
        bridge = self.bridge()
        registry = bridge.get_reader_plugin_registry()
        from ChemBlender.reader_api import (
            CapabilitySupport,
            PublicImportBatch,
            ReaderPluginManifest,
        )
        from ChemBlender.reader_api.registry import builtin_reader_plugins

        builtin = builtin_reader_plugins()[0]
        descriptor = replace(
            builtin.descriptor,
            plugin_id="org.example.lifecycle",
            reader_id="external.lifecycle",
        )
        entry = replace(
            builtin.manifest.readers[0],
            reader_id=descriptor.reader_id,
            reader_version=descriptor.reader_version,
            extensions=descriptor.extensions,
            capabilities=tuple(
                sorted(
                    name
                    for name, support in descriptor.capabilities.items()
                    if support is CapabilitySupport.SUPPORTED
                )
            ),
        )
        external = replace(
            builtin,
            descriptor=descriptor,
            manifest=replace(
                builtin.manifest,
                plugin_id=descriptor.plugin_id,
                readers=(entry,),
            ),
        )
        builtin_identities = tuple(
            id(item) for item in registry.descriptors
        )
        namespace = {}
        first = bridge.register_reader_api_handle(
            "synthetic_repository.chemblender",
            namespace=namespace,
        )
        try:
            first.register_callback(external)
            self.assertTrue(
                bridge.remove_reader_api_handle(first, namespace=namespace)
            )
            second = bridge.register_reader_api_handle(
                "synthetic_repository.chemblender",
                namespace=namespace,
            )
            self.assertIsNot(second, first)
            self.assertIs(bridge.get_reader_plugin_registry(), registry)
            self.assertEqual(
                tuple(
                    id(item)
                    for item in registry.descriptors
                    if item.plugin_id == "chemblender.builtin"
                ),
                builtin_identities,
            )
            external_descriptor = next(
                item
                for item in registry.descriptors
                if item.reader_id == "external.lifecycle"
            )
            self.assertIs(external_descriptor, descriptor)
            self.assertIs(
                importlib.import_module(
                    "ChemBlender.reader_api"
                ).PublicImportBatch,
                PublicImportBatch,
            )
            self.assertIs(
                importlib.import_module(
                    "ChemBlender.reader_api"
                ).ReaderPluginManifest,
                ReaderPluginManifest,
            )
            second.unregister_callback(external.manifest)
        finally:
            current = namespace.get(bridge.READER_API_HANDLE_KEY)
            if current is not None:
                bridge.remove_reader_api_handle(
                    current,
                    namespace=namespace,
                )


if __name__ == "__main__":
    unittest.main()
