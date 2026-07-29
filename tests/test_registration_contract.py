import importlib
import json
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
REGISTRATION_MODULE = "ChemBlender.runtime.registration"
EXPECTED_ROOTS = (
    ".chem_utils",
    ".crys_utils",
    ".extension",
    ".output",
    ".panel",
    ".periodictable",
    ".read",
    ".scaffold",
    ".trajectory_view",
    ".ui.session",
    ".ui.properties",
    ".ui.quick_import",
    ".ui.import_preview",
    ".ui.topology",
    ".ui.biological",
    ".ui.scientific_edit",
    ".ui.export",
    ".ui.grid",
    ".ui.project_browser.panel",
    ".ui.file_handlers",
    ".ui.workspace",
)


def fresh_registration():
    sys.modules.pop(REGISTRATION_MODULE, None)
    return importlib.import_module(REGISTRATION_MODULE)


class RegistrationHarness:
    package_root = "synthetic_repository.synthetic_addon"

    class Alpha:
        pass

    class Beta:
        pass

    def __init__(self, registration):
        self.registration = registration
        self.events = []
        self.imports = []
        self.class_register_failure = None
        self.class_unregister_failure = None
        self.preexisting_classes = set()
        self.already_unregistered_classes = set()
        self.callback_register_failure = None
        self.callback_unregister_failure = None
        self.callback_state = set()
        self.publication_failure = None
        self.removal_failure = None
        self.handle = object()
        self.modules = {
            name: ModuleType(self.package_root + name)
            for name in registration.REGISTER_MODULE_NAMES
        }
        for name in (".extension", ".trajectory_view"):
            module = self.modules[name]
            module.register = self._module_register(name)
            module.unregister = self._module_unregister(name)

        self.auto_load = ModuleType(self.package_root + ".auto_load")
        self.auto_load.get_ordered_classes_to_register = (
            lambda modules: [self.Alpha, self.Beta, self.Alpha]
        )
        self.auto_load._safe_register_class = self._register_class
        self.auto_load._safe_unregister_class = self._unregister_class

        self.bridge = ModuleType(
            self.package_root + ".runtime.reader_api_bridge"
        )
        self.bridge.register_reader_api_handle = self._publish
        self.bridge.remove_reader_api_handle = self._remove
        self.bridge.refresh_reader_plugin_discovery = self._refresh_readers

    def _module_register(self, name):
        def register():
            self.events.append(("register_callback", name))
            self.callback_state.add(name)
            if self.callback_register_failure == name:
                raise LookupError(name)

        return register

    def _module_unregister(self, name):
        def unregister():
            self.events.append(("unregister_callback", name))
            if self.callback_unregister_failure == name:
                raise ArithmeticError(name)
            self.callback_state.discard(name)

        return unregister

    def _register_class(self, cls):
        self.events.append(("register_class", cls.__name__))
        if self.class_register_failure is cls:
            raise RuntimeError(cls.__name__)
        if cls in self.preexisting_classes:
            return False
        return True

    def _unregister_class(self, cls):
        self.events.append(("unregister_class", cls.__name__))
        if cls in self.already_unregistered_classes:
            return False
        if self.class_unregister_failure is cls:
            raise OSError(cls.__name__)
        return True

    def _publish(self, package_root):
        self.events.append(("publish_handle", package_root))
        if self.publication_failure is not None:
            raise self.publication_failure
        return self.handle

    def _remove(self, handle):
        self.events.append(("remove_handle", handle))
        if self.removal_failure is not None:
            raise self.removal_failure
        return True

    def _refresh_readers(self):
        self.events.append(("refresh_readers",))

    def import_module(self, name, package):
        self.imports.append((name, package))
        if name == ".auto_load":
            return self.auto_load
        if name == ".runtime.reader_api_bridge":
            return self.bridge
        return self.modules[name]

    def patch_imports(self):
        return patch.object(
            self.registration.importlib,
            "import_module",
            side_effect=self.import_module,
        )


class RegistrationContractTests(unittest.TestCase):
    def test_000_registration_module_exists(self):
        registration = fresh_registration()

        self.assertIsInstance(registration.REGISTER_MODULE_NAMES, tuple)

    def test_public_registration_interfaces_have_required_annotations(self):
        registration = fresh_registration()

        self.assertEqual(
            registration.__annotations__["REGISTER_MODULE_NAMES"],
            tuple[str, ...],
        )
        self.assertEqual(
            registration.register_extension.__annotations__,
            {"package_root": str, "return": None},
        )
        self.assertEqual(
            registration.unregister_extension.__annotations__,
            {"return": None},
        )

    def test_explicit_roots_cover_legacy_formal_inventory_only(self):
        registration = fresh_registration()
        inventory = json.loads(
            (
                ROOT
                / "tests/fixtures/registration/"
                "legacy-registration-inventory.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(registration.REGISTER_MODULE_NAMES, EXPECTED_ROOTS)
        self.assertEqual(inventory["schema_version"], 1)
        self.assertEqual(
            inventory["baseline_commit"],
            "7078356c85bd02fcb0db23b01490f87f16abfb94",
        )
        self.assertEqual(inventory["blender_version"], "5.1.2")
        covered_modules = set(registration.REGISTER_MODULE_NAMES)
        self.assertTrue(
            {
                entry["module"]
                for entry in inventory["registered_classes"]
            }.issubset(covered_modules)
        )
        self.assertTrue(
            {
                entry["module"]
                for entry in inventory["module_callbacks"]
            }.issubset(covered_modules)
        )
        for name in registration.REGISTER_MODULE_NAMES:
            self.assertTrue(name.startswith("."))
            self.assertFalse(
                name.startswith(
                    (".core", ".reader_api", ".runtime", ".legacy")
                )
            )
            self.assertTrue(
                (
                    ROOT
                    / "ChemBlender"
                    / f"{name[1:].replace('.', '/')}.py"
                ).is_file()
            )

    def test_import_is_bpy_free_and_runtime_package_has_no_side_effects(self):
        sys.modules.pop(REGISTRATION_MODULE, None)
        sys.modules.pop("ChemBlender.runtime", None)
        before = set(sys.modules)

        runtime = importlib.import_module("ChemBlender.runtime")

        self.assertIsNotNone(runtime.__doc__)
        self.assertNotIn(REGISTRATION_MODULE, sys.modules)
        self.assertNotIn("bpy", set(sys.modules) - before)
        registration = importlib.import_module(REGISTRATION_MODULE)
        self.assertNotIn("bpy", set(sys.modules) - before)
        self.assertFalse(hasattr(registration, "bpy"))

    def test_registration_is_relative_deterministic_and_exactly_reversible(self):
        registration = fresh_registration()
        harness = RegistrationHarness(registration)

        with harness.patch_imports():
            registration.register_extension(harness.package_root)
            registration.unregister_extension()

        root_imports = [
            item
            for item in harness.imports
            if item[0] in registration.REGISTER_MODULE_NAMES
        ]
        self.assertEqual(
            root_imports,
            [
                (name, harness.package_root)
                for name in registration.REGISTER_MODULE_NAMES
            ],
        )
        self.assertTrue(
            all(
                name.startswith(".") and package == harness.package_root
                for name, package in harness.imports
            )
        )
        self.assertEqual(
            harness.events,
            [
                ("register_class", "Alpha"),
                ("register_class", "Beta"),
                ("register_callback", ".extension"),
                ("register_callback", ".trajectory_view"),
                ("publish_handle", harness.package_root),
                ("remove_handle", harness.handle),
                ("unregister_callback", ".trajectory_view"),
                ("unregister_callback", ".extension"),
                ("unregister_class", "Beta"),
                ("unregister_class", "Alpha"),
            ],
        )

    def test_repeated_enable_disable_cycles_do_not_duplicate_work(self):
        registration = fresh_registration()
        harness = RegistrationHarness(registration)

        with harness.patch_imports():
            for _ in range(2):
                registration.register_extension(harness.package_root)
                registration.register_extension(harness.package_root)
                registration.unregister_extension()
                registration.unregister_extension()

        self.assertEqual(
            harness.events.count(("register_class", "Alpha")),
            2,
        )
        self.assertEqual(
            harness.events.count(("register_callback", ".extension")),
            2,
        )
        self.assertEqual(
            harness.events.count(("publish_handle", harness.package_root)),
            2,
        )
        self.assertEqual(
            harness.events.count(("remove_handle", harness.handle)),
            2,
        )

    def test_load_post_republishes_the_owned_reader_handle(self):
        registration = fresh_registration()
        harness = RegistrationHarness(registration)
        handlers = SimpleNamespace(
            load_post=[],
            persistent=lambda callback: callback,
        )
        fake_bpy = ModuleType("bpy")
        fake_bpy.app = SimpleNamespace(handlers=handlers)

        with patch.dict(sys.modules, {"bpy": fake_bpy}), harness.patch_imports():
            registration.register_extension(harness.package_root)
            self.assertEqual(len(handlers.load_post), 1)
            handlers.load_post[0](None)
            registration.unregister_extension()

        self.assertEqual(
            harness.events.count(("publish_handle", harness.package_root)),
            2,
        )
        self.assertEqual(
            harness.events.count(("refresh_readers",)),
            1,
        )
        self.assertEqual(handlers.load_post, [])

    def test_class_failure_rolls_back_only_registered_classes(self):
        registration = fresh_registration()
        harness = RegistrationHarness(registration)
        harness.class_register_failure = harness.Beta

        with harness.patch_imports():
            with self.assertRaisesRegex(RuntimeError, "Beta"):
                registration.register_extension(harness.package_root)

        self.assertEqual(
            harness.events,
            [
                ("register_class", "Alpha"),
                ("register_class", "Beta"),
                ("unregister_class", "Alpha"),
            ],
        )

    def test_owner_does_not_take_or_cleanup_preexisting_class(self):
        registration = fresh_registration()
        harness = RegistrationHarness(registration)
        harness.preexisting_classes.add(harness.Alpha)

        with harness.patch_imports():
            registration.register_extension(harness.package_root)
            self.assertEqual(
                registration._registered_classes,
                (harness.Beta,),
            )
            registration.unregister_extension()

        self.assertNotIn(
            ("unregister_class", "Alpha"),
            harness.events,
        )
        self.assertEqual(
            harness.events.count(("unregister_class", "Beta")),
            1,
        )

    def test_failing_callback_rolls_back_its_own_partial_state(self):
        registration = fresh_registration()
        harness = RegistrationHarness(registration)
        harness.callback_register_failure = ".trajectory_view"

        with harness.patch_imports():
            with self.assertRaisesRegex(LookupError, "trajectory_view"):
                registration.register_extension(harness.package_root)

        self.assertEqual(harness.callback_state, set())
        self.assertEqual(
            harness.events[-4:],
            [
                ("unregister_callback", ".trajectory_view"),
                ("unregister_callback", ".extension"),
                ("unregister_class", "Beta"),
                ("unregister_class", "Alpha"),
            ],
        )
        self.assertFalse(
            any(event[0] == "remove_handle" for event in harness.events)
        )

    def test_failing_callback_cleanup_error_is_noted_and_retryable(self):
        registration = fresh_registration()
        harness = RegistrationHarness(registration)
        harness.callback_register_failure = ".trajectory_view"
        harness.callback_unregister_failure = ".trajectory_view"

        with harness.patch_imports():
            with self.assertRaises(LookupError) as caught:
                registration.register_extension(harness.package_root)

            notes = getattr(caught.exception, "__notes__", ())
            self.assertTrue(
                any("ArithmeticError" in note for note in notes),
                notes,
            )
            self.assertEqual(
                registration._registered_callback_modules,
                (harness.modules[".trajectory_view"],),
            )

            harness.callback_unregister_failure = None
            registration.unregister_extension()

        self.assertEqual(harness.callback_state, set())
        self.assertEqual(
            harness.events.count(
                ("unregister_callback", ".trajectory_view")
            ),
            2,
        )

    def test_handle_publication_failure_preserves_incompatible_owner(self):
        registration = fresh_registration()
        harness = RegistrationHarness(registration)
        incompatible_owner = object()
        failure = RuntimeError("reader handle owned elsewhere")
        failure.incompatible_owner = incompatible_owner
        harness.publication_failure = failure

        with harness.patch_imports():
            with self.assertRaises(RuntimeError) as caught:
                registration.register_extension(harness.package_root)

        self.assertIs(caught.exception, failure)
        self.assertIs(caught.exception.incompatible_owner, incompatible_owner)
        self.assertFalse(
            any(event[0] == "remove_handle" for event in harness.events)
        )
        self.assertEqual(
            harness.events[-4:],
            [
                ("unregister_callback", ".trajectory_view"),
                ("unregister_callback", ".extension"),
                ("unregister_class", "Beta"),
                ("unregister_class", "Alpha"),
            ],
        )

    def test_cleanup_failures_are_notes_on_original_registration_error(self):
        registration = fresh_registration()
        harness = RegistrationHarness(registration)
        original = RuntimeError("publication failed")
        harness.publication_failure = original
        harness.callback_unregister_failure = ".trajectory_view"
        harness.class_unregister_failure = harness.Beta

        with harness.patch_imports():
            with self.assertRaises(RuntimeError) as caught:
                registration.register_extension(harness.package_root)

        self.assertIs(caught.exception, original)
        notes = getattr(caught.exception, "__notes__", ())
        self.assertTrue(
            any("ArithmeticError" in note for note in notes),
            notes,
        )
        self.assertTrue(any("OSError" in note for note in notes), notes)
        self.assertIn(
            ("unregister_callback", ".extension"),
            harness.events,
        )
        self.assertIn(("unregister_class", "Alpha"), harness.events)

    def test_unregistration_preserves_first_failure_and_finishes_cleanup(self):
        registration = fresh_registration()
        harness = RegistrationHarness(registration)

        with harness.patch_imports():
            registration.register_extension(harness.package_root)
            original = RuntimeError("handle removal failed")
            harness.removal_failure = original
            harness.callback_unregister_failure = ".trajectory_view"
            harness.class_unregister_failure = harness.Beta
            with self.assertRaises(RuntimeError) as caught:
                registration.unregister_extension()

        self.assertIs(caught.exception, original)
        notes = getattr(caught.exception, "__notes__", ())
        self.assertTrue(any("ArithmeticError" in note for note in notes))
        self.assertTrue(any("OSError" in note for note in notes))
        self.assertIn(
            ("unregister_callback", ".extension"),
            harness.events,
        )
        self.assertIn(("unregister_class", "Alpha"), harness.events)

    def test_unregistration_retries_only_residual_owned_state(self):
        registration = fresh_registration()
        harness = RegistrationHarness(registration)

        with harness.patch_imports():
            registration.register_extension(harness.package_root)
            harness.removal_failure = RuntimeError("handle removal failed")
            harness.callback_unregister_failure = ".trajectory_view"
            harness.class_unregister_failure = harness.Beta

            with self.assertRaisesRegex(RuntimeError, "handle removal failed"):
                registration.unregister_extension()

            self.assertEqual(registration._package_root, harness.package_root)
            self.assertIs(registration._reader_api_handle, harness.handle)
            self.assertEqual(
                registration._registered_callback_modules,
                (harness.modules[".trajectory_view"],),
            )
            self.assertEqual(
                registration._registered_classes,
                (harness.Beta,),
            )

            harness.removal_failure = None
            harness.callback_unregister_failure = None
            harness.class_unregister_failure = None
            registration.unregister_extension()

        self.assertIsNone(registration._package_root)
        self.assertIsNone(registration._reader_api_handle)
        self.assertEqual(registration._registered_callback_modules, ())
        self.assertEqual(registration._registered_classes, ())
        self.assertEqual(
            harness.events.count(("remove_handle", harness.handle)),
            2,
        )
        self.assertEqual(
            harness.events.count(
                ("unregister_callback", ".trajectory_view")
            ),
            2,
        )
        self.assertEqual(
            harness.events.count(("unregister_callback", ".extension")),
            1,
        )
        self.assertEqual(
            harness.events.count(("unregister_class", "Beta")),
            2,
        )
        self.assertEqual(
            harness.events.count(("unregister_class", "Alpha")),
            1,
        )

    def test_already_unregistered_owned_class_is_released_not_residual(self):
        registration = fresh_registration()
        harness = RegistrationHarness(registration)

        with harness.patch_imports():
            registration.register_extension(harness.package_root)
            harness.already_unregistered_classes.add(harness.Beta)
            registration.unregister_extension()

        self.assertIsNone(registration._package_root)
        self.assertEqual(registration._registered_classes, ())
        self.assertEqual(
            harness.events.count(("unregister_class", "Beta")),
            1,
        )

    def test_optional_stacks_are_not_registration_roots(self):
        registration = fresh_registration()
        forbidden = (
            "ase",
            "cclib",
            "gemmi",
            "iodata",
            "openvdb",
            "phonopy",
            "pymatgen",
            "pyprocar",
            "qcengine",
            "pyscf",
            "scipy",
        )

        self.assertFalse(
            any(
                name.startswith((".core", ".reader_api"))
                or any(stack in name for stack in forbidden)
                for name in registration.REGISTER_MODULE_NAMES
            )
        )

    def test_class_toposort_has_a_stable_tie_breaker(self):
        class Zulu:
            pass

        class Alpha:
            pass

        fake_bpy = ModuleType("bpy")
        fake_bpy.app = SimpleNamespace(version=(5, 1, 2))
        sys.modules.pop("ChemBlender.auto_load", None)
        with patch.dict(sys.modules, {"bpy": fake_bpy}):
            auto_load = importlib.import_module("ChemBlender.auto_load")
            ordered = auto_load.toposort(
                {
                    Zulu: set(),
                    Alpha: set(),
                }
            )
        sys.modules.pop("ChemBlender.auto_load", None)

        self.assertEqual(ordered, [Alpha, Zulu])

    def test_class_register_helper_propagates_unknown_blender_error(self):
        class Example:
            is_registered = False

        def fail(_cls):
            raise ValueError("unexpected registration failure")

        fake_bpy = ModuleType("bpy")
        fake_bpy.app = SimpleNamespace(version=(5, 1, 2))
        fake_bpy.utils = SimpleNamespace(register_class=fail)
        sys.modules.pop("ChemBlender.auto_load", None)
        with patch.dict(sys.modules, {"bpy": fake_bpy}):
            auto_load = importlib.import_module("ChemBlender.auto_load")
            with self.assertRaisesRegex(
                ValueError,
                "unexpected registration failure",
            ):
                auto_load._safe_register_class(Example)
        sys.modules.pop("ChemBlender.auto_load", None)

    def test_class_unregister_helper_propagates_unknown_blender_error(self):
        class Example:
            is_registered = True

        def fail(_cls):
            raise RuntimeError("unexpected unregistration failure")

        fake_bpy = ModuleType("bpy")
        fake_bpy.app = SimpleNamespace(version=(5, 1, 2))
        fake_bpy.utils = SimpleNamespace(unregister_class=fail)
        sys.modules.pop("ChemBlender.auto_load", None)
        with patch.dict(sys.modules, {"bpy": fake_bpy}):
            auto_load = importlib.import_module("ChemBlender.auto_load")
            with self.assertRaisesRegex(
                RuntimeError,
                "unexpected unregistration failure",
            ):
                auto_load._safe_unregister_class(Example)
        sys.modules.pop("ChemBlender.auto_load", None)

    def test_class_register_helper_skips_exact_registered_state(self):
        class Example:
            is_registered = True

        calls = []
        fake_bpy = ModuleType("bpy")
        fake_bpy.app = SimpleNamespace(version=(5, 1, 2))
        fake_bpy.utils = SimpleNamespace(
            register_class=lambda cls: calls.append(cls)
        )
        sys.modules.pop("ChemBlender.auto_load", None)
        with patch.dict(sys.modules, {"bpy": fake_bpy}):
            auto_load = importlib.import_module("ChemBlender.auto_load")
            self.assertFalse(auto_load._safe_register_class(Example))
        sys.modules.pop("ChemBlender.auto_load", None)

        self.assertEqual(calls, [])

    def test_class_unregister_helper_skips_exact_unregistered_state(self):
        class Example:
            is_registered = False

        calls = []
        fake_bpy = ModuleType("bpy")
        fake_bpy.app = SimpleNamespace(version=(5, 1, 2))
        fake_bpy.utils = SimpleNamespace(
            unregister_class=lambda cls: calls.append(cls)
        )
        sys.modules.pop("ChemBlender.auto_load", None)
        with patch.dict(sys.modules, {"bpy": fake_bpy}):
            auto_load = importlib.import_module("ChemBlender.auto_load")
            self.assertFalse(auto_load._safe_unregister_class(Example))
        sys.modules.pop("ChemBlender.auto_load", None)

        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
