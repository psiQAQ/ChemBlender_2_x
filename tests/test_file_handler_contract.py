import importlib
import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


MODULE_NAME = "ChemBlender.ui.file_handlers"


class _FileHandler:
    is_registered = False


def _fake_bpy(*, file_handler=True):
    module = ModuleType("bpy")
    types = {"FileHandler": _FileHandler} if file_handler else {}
    module.types = SimpleNamespace(**types)
    module.registered = []
    module.register_failure = None
    module.partial_register_failure = None
    module.unregister_failure = None
    module.post_unregister_failure = None
    module.events = []

    def register_class(cls):
        module.events.append(("register", cls))
        if cls is module.partial_register_failure:
            module.registered.append(cls)
            cls.is_registered = True
            raise RuntimeError(f"{cls.__name__} partial registration failed")
        if cls is module.register_failure:
            raise RuntimeError(f"{cls.__name__} registration failed")
        if cls not in module.registered:
            module.registered.append(cls)
            cls.is_registered = True

    def unregister_class(cls):
        module.events.append(("unregister", cls))
        if cls is module.unregister_failure:
            raise OSError(f"{cls.__name__} cleanup failed")
        if cls in module.registered:
            module.registered.remove(cls)
            cls.is_registered = False
        if cls is module.post_unregister_failure:
            raise OSError(f"{cls.__name__} post-cleanup failed")

    module.utils = SimpleNamespace(
        register_class=register_class,
        unregister_class=unregister_class,
    )
    return module


def _context(area_type=None, region_type=None):
    area = None if area_type is None else SimpleNamespace(type=area_type)
    region = None if region_type is None else SimpleNamespace(type=region_type)
    return SimpleNamespace(area=area, region=region)


class FileHandlerContractTests(unittest.TestCase):
    def setUp(self):
        sys.modules.pop(MODULE_NAME, None)
        _FileHandler.is_registered = False
        self.bpy = _fake_bpy()
        self.modules = patch.dict(sys.modules, {"bpy": self.bpy})
        self.modules.start()

    def tearDown(self):
        module = sys.modules.get(MODULE_NAME)
        if module is not None:
            module.unregister()
        self.modules.stop()
        sys.modules.pop(MODULE_NAME, None)
        _FileHandler.is_registered = False

    def test_handlers_delegate_to_quick_import_with_available_builtin_extensions(self):
        module = importlib.import_module(MODULE_NAME)
        from ChemBlender.runtime.reader_api_bridge import (
            get_reader_plugin_registry,
        )

        expected = ";".join(
            sorted(
                {
                    extension.lower()
                    for descriptor in get_reader_plugin_registry().descriptors
                    if descriptor.plugin_id == "chemblender.builtin"
                    and descriptor.availability.available
                    for extension in descriptor.extensions
                }
            )
        )

        self.assertTrue(expected)
        self.assertNotIn("*", expected)
        self.assertEqual(
            tuple(cls.__name__ for cls in module.FILE_HANDLER_CLASSES),
            (
                "CHEMBLENDER_FH_view_3d_window",
                "CHEMBLENDER_FH_project_browser",
            ),
        )
        for cls in module.FILE_HANDLER_CLASSES:
            self.assertEqual(
                cls.bl_import_operator,
                "chemblender.quick_import",
            )
            self.assertEqual(cls.bl_file_extensions, expected)

    def test_extension_projection_filters_and_normalizes_controlled_descriptors(self):
        module = importlib.import_module(MODULE_NAME)
        available = SimpleNamespace(available=True)
        unavailable = SimpleNamespace(available=False)
        descriptors = (
            SimpleNamespace(
                plugin_id="chemblender.builtin",
                availability=available,
                extensions=("XYZ", ".cube", ".XYZ", "*.wild", "../bad"),
            ),
            SimpleNamespace(
                plugin_id="chemblender.builtin",
                availability=unavailable,
                extensions=(".cif",),
            ),
            SimpleNamespace(
                plugin_id="org.example.external",
                availability=available,
                extensions=(".external",),
            ),
        )

        self.assertEqual(
            module._builtin_extension_string(descriptors),
            ".cube;.xyz",
        )

    def test_handlers_accept_only_their_view3d_region_pair(self):
        module = importlib.import_module(MODULE_NAME)
        window = module.CHEMBLENDER_FH_view_3d_window
        sidebar = module.CHEMBLENDER_FH_project_browser

        self.assertIs(window.poll_drop(_context("VIEW_3D", "WINDOW")), True)
        self.assertIs(sidebar.poll_drop(_context("VIEW_3D", "UI")), True)
        for context in (
            None,
            SimpleNamespace(),
            _context(),
            _context("FILE_BROWSER", "WINDOW"),
            _context("OUTLINER", "WINDOW"),
            _context("VIEW_3D", "HEADER"),
        ):
            self.assertIs(window.poll_drop(context), False)
            self.assertIs(sidebar.poll_drop(context), False)
        self.assertIs(window.poll_drop(_context("VIEW_3D", "UI")), False)
        self.assertIs(
            sidebar.poll_drop(_context("VIEW_3D", "WINDOW")),
            False,
        )

    def test_poll_drop_does_not_inspect_filesystem_state(self):
        module = importlib.import_module(MODULE_NAME)

        class Bomb:
            area = SimpleNamespace(type="VIEW_3D")
            region = SimpleNamespace(type="WINDOW")

            def __getattr__(self, name):
                raise AssertionError(f"unexpected context access: {name}")

        result = module.CHEMBLENDER_FH_view_3d_window.poll_drop(Bomb())

        self.assertIs(type(result), bool)
        self.assertTrue(result)

    def test_register_and_unregister_own_each_handler_exactly_once(self):
        module = importlib.import_module(MODULE_NAME)

        module.register()
        module.register()
        self.assertEqual(self.bpy.registered, list(module.FILE_HANDLER_CLASSES))

        module.unregister()
        module.unregister()
        self.assertEqual(self.bpy.registered, [])

    def test_second_registration_failure_rolls_back_first(self):
        module = importlib.import_module(MODULE_NAME)
        first, second = module.FILE_HANDLER_CLASSES
        self.bpy.register_failure = second

        with self.assertRaisesRegex(RuntimeError, "registration failed"):
            module.register()

        self.assertEqual(self.bpy.registered, [])
        self.assertEqual(module._REGISTERED_CLASSES, ())
        self.assertEqual(
            self.bpy.events,
            [("register", first), ("register", second), ("unregister", first)],
        )

    def test_partial_second_registration_failure_rolls_back_both(self):
        module = importlib.import_module(MODULE_NAME)
        first, second = module.FILE_HANDLER_CLASSES
        self.bpy.partial_register_failure = second

        with self.assertRaisesRegex(RuntimeError, "partial registration failed"):
            module.register()

        self.assertEqual(self.bpy.registered, [])
        self.assertEqual(module._REGISTERED_CLASSES, ())
        self.assertEqual(
            self.bpy.events,
            [
                ("register", first),
                ("register", second),
                ("unregister", second),
                ("unregister", first),
            ],
        )

    def test_failed_registration_rollback_preserves_owner_for_retry(self):
        module = importlib.import_module(MODULE_NAME)
        first, second = module.FILE_HANDLER_CLASSES
        self.bpy.register_failure = second
        self.bpy.unregister_failure = first

        with self.assertRaisesRegex(RuntimeError, "registration failed") as caught:
            module.register()

        self.assertTrue(
            any("OSError" in note for note in caught.exception.__notes__)
        )
        self.assertEqual(module._REGISTERED_CLASSES, (first,))
        self.bpy.register_failure = None
        self.bpy.unregister_failure = None
        module.unregister()
        self.assertEqual(self.bpy.registered, [])

    def test_foreign_pre_registered_handler_is_not_unregistered(self):
        module = importlib.import_module(MODULE_NAME)
        foreign, owned = module.FILE_HANDLER_CLASSES
        foreign.is_registered = True

        module.register()
        module.unregister()

        self.assertTrue(foreign.is_registered)
        self.assertNotIn(("unregister", foreign), self.bpy.events)
        self.assertIn(("unregister", owned), self.bpy.events)
        foreign.is_registered = False

    def test_post_unregister_error_does_not_keep_false_residual_owner(self):
        module = importlib.import_module(MODULE_NAME)
        _, second = module.FILE_HANDLER_CLASSES
        module.register()
        self.bpy.post_unregister_failure = second

        with self.assertRaisesRegex(OSError, "post-cleanup failed"):
            module.unregister()

        self.assertEqual(self.bpy.registered, [])
        self.assertEqual(module._REGISTERED_CLASSES, ())

    def test_missing_file_handler_api_fails_closed(self):
        self.modules.stop()
        sys.modules.pop(MODULE_NAME, None)
        self.bpy = _fake_bpy(file_handler=False)
        self.modules = patch.dict(sys.modules, {"bpy": self.bpy})
        self.modules.start()

        from ChemBlender.runtime import reader_api_bridge

        with patch.object(
            reader_api_bridge,
            "get_reader_plugin_registry",
            side_effect=AssertionError("registry must not be accessed"),
        ):
            module = importlib.import_module(MODULE_NAME)
            module.register()

        self.assertEqual(module.FILE_HANDLER_CLASSES, ())
        self.assertEqual(self.bpy.registered, [])


if __name__ == "__main__":
    unittest.main()
