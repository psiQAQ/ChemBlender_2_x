import ast
import importlib
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch


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

    def test_root_lifecycle_publishes_after_registration_and_removes_first(self):
        package = importlib.import_module("ChemBlender")
        events = []
        handle = object()
        auto_load = ModuleType("ChemBlender.auto_load")
        auto_load.init = lambda: events.append("init")
        auto_load.register = lambda: events.append("auto_register")
        auto_load.unregister = lambda: events.append("auto_unregister")
        bridge = ModuleType("ChemBlender.runtime.reader_api_bridge")
        bridge.register_reader_api_handle = (
            lambda package_root: events.append(("publish", package_root))
            or handle
        )
        bridge.remove_reader_api_handle = (
            lambda value: events.append(("remove", value)) or True
        )

        with patch.dict(
            sys.modules,
            {
                "ChemBlender.auto_load": auto_load,
                "ChemBlender.runtime.reader_api_bridge": bridge,
            },
        ):
            with patch.object(package, "auto_load", auto_load, create=True):
                for _ in range(2):
                    package.register()
                    package.unregister()

        self.assertEqual(
            events,
            [
                "init",
                "auto_register",
                ("publish", "ChemBlender"),
                ("remove", handle),
                "auto_unregister",
                "init",
                "auto_register",
                ("publish", "ChemBlender"),
                ("remove", handle),
                "auto_unregister",
            ],
        )

    def test_root_registration_rolls_back_when_publication_fails(self):
        package = importlib.import_module("ChemBlender")
        events = []
        auto_load = ModuleType("ChemBlender.auto_load")
        auto_load.init = lambda: events.append("init")
        auto_load.register = lambda: events.append("auto_register")
        auto_load.unregister = lambda: events.append("rollback")
        bridge = ModuleType("ChemBlender.runtime.reader_api_bridge")

        def fail(package_root):
            events.append(("publish", package_root))
            raise RuntimeError("occupied")

        bridge.register_reader_api_handle = fail
        bridge.remove_reader_api_handle = Mock()

        with patch.dict(
            sys.modules,
            {
                "ChemBlender.auto_load": auto_load,
                "ChemBlender.runtime.reader_api_bridge": bridge,
            },
        ):
            with patch.object(package, "auto_load", auto_load, create=True):
                with self.assertRaises(RuntimeError):
                    package.register()

        self.assertEqual(
            events,
            ["init", "auto_register", ("publish", "ChemBlender"), "rollback"],
        )
        bridge.remove_reader_api_handle.assert_not_called()

    def test_root_rollback_preserves_publication_error_when_cleanup_fails(self):
        package = importlib.import_module("ChemBlender")
        publication_error = RuntimeError("occupied")
        auto_load = ModuleType("ChemBlender.auto_load")
        auto_load.init = Mock()
        auto_load.register = Mock()
        auto_load.unregister = Mock(side_effect=ValueError("cleanup failed"))
        bridge = ModuleType("ChemBlender.runtime.reader_api_bridge")
        bridge.register_reader_api_handle = Mock(
            side_effect=publication_error
        )
        bridge.remove_reader_api_handle = Mock()

        with patch.dict(
            sys.modules,
            {
                "ChemBlender.auto_load": auto_load,
                "ChemBlender.runtime.reader_api_bridge": bridge,
            },
        ):
            with patch.object(package, "auto_load", auto_load, create=True):
                with self.assertRaises(RuntimeError) as raised:
                    package.register()

        self.assertIs(raised.exception, publication_error)
        self.assertTrue(
            any("ValueError" in note for note in publication_error.__notes__)
        )
        self.assertIsNone(package._reader_api_handle)
        auto_load.unregister.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
