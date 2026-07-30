import importlib
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

from ChemBlender.core.readers import CapabilitySupport, ReaderAvailability
from ChemBlender.reader_api.manifest import (
    ExecutionMode,
    ReaderPluginManifest,
)
from ChemBlender.reader_api.registry import (
    ReaderPluginRegistry,
    builtin_reader_plugins,
)


def external_plugin(plugin_id, reader_id):
    builtin = builtin_reader_plugins()[0]
    descriptor = replace(
        builtin.descriptor,
        plugin_id=plugin_id,
        plugin_version="1.0.0",
        reader_id=reader_id,
        reader_version="1.0.0",
        execution_mode=ExecutionMode.EXTENSION,
        extensions=(f".{reader_id.rsplit('.', 1)[-1]}",),
        availability=ReaderAvailability(
            True,
            ExecutionMode.EXTENSION.value,
            "available",
            "",
        ),
    )
    entry = replace(
        next(
            item
            for item in builtin.manifest.readers
            if item.reader_id == builtin.descriptor.reader_id
        ),
        reader_id=reader_id,
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
    manifest = ReaderPluginManifest(
        schema_version="1",
        plugin_id=plugin_id,
        plugin_version=descriptor.plugin_version,
        chemblender_api=">=1.0,<2.0",
        execution_mode=ExecutionMode.EXTENSION,
        license=("SPDX:MIT",),
        readers=(entry,),
    )
    return replace(
        builtin,
        descriptor=descriptor,
        manifest=manifest,
    )


class _PoisonBoolean:
    def __bool__(self):
        raise OSError("poison bool")


class _MalformedManifest:
    plugin_id = "org.example.malformed_equality"
    plugin_version = "1.0.0"
    execution_mode = ExecutionMode.EXTENSION
    readers = ()

    def __init__(self, equality):
        self._equality = equality

    def __eq__(self, _other):
        if isinstance(self._equality, BaseException):
            raise self._equality
        return self._equality


class ReaderPluginDiscoveryTests(unittest.TestCase):
    def discovery(self):
        module = importlib.import_module("ChemBlender.reader_api.discovery")
        registry = ReaderPluginRegistry(builtin_reader_plugins())
        return module.ReaderPluginDiscovery(registry), registry

    def test_refresh_contains_only_builtins_until_explicit_registration(self):
        discovery, registry = self.discovery()

        first = discovery.refresh()
        second = discovery.refresh()

        self.assertIs(second, first)
        self.assertEqual(first.descriptors, registry.descriptors)
        self.assertEqual(
            {state.plugin_id for state in first.plugins},
            {"chemblender.builtin"},
        )

        plugin = external_plugin(
            "org.example.explicit",
            "external.explicit",
        )
        registered = discovery.register(plugin)
        refreshed = discovery.refresh()

        self.assertTrue(registered.availability.available)
        self.assertIsNot(refreshed, first)
        self.assertIs(discovery.refresh(), refreshed)
        self.assertIs(
            next(
                descriptor
                for descriptor in refreshed.descriptors
                if descriptor.reader_id == "external.explicit"
            ),
            plugin.descriptor,
        )

    def test_duplicate_plugin_and_reader_ids_fail_closed_and_clean_own_state(self):
        discovery, registry = self.discovery()
        good = external_plugin("org.example.good", "external.good")
        duplicate_plugin_id = external_plugin(
            "org.example.good",
            "external.other",
        )
        duplicate_reader_id = external_plugin(
            "org.example.other",
            "external.good",
        )

        discovery.register(good)
        plugin_failure = discovery.register(duplicate_plugin_id)
        reader_failure = discovery.register(duplicate_reader_id)

        self.assertFalse(plugin_failure.availability.available)
        self.assertEqual(
            plugin_failure.availability.reason_code,
            "plugin_registration_failed",
        )
        self.assertEqual(
            plugin_failure.availability.detail,
            "ValueError",
        )
        self.assertFalse(reader_failure.availability.available)
        self.assertEqual(
            tuple(
                descriptor.reader_id
                for descriptor in registry.descriptors
                if descriptor.plugin_id != "chemblender.builtin"
            ),
            ("external.good",),
        )
        self.assertEqual(
            {
                state.plugin_id
                for state in discovery.refresh().plugins
                if not state.availability.available
            },
            {"org.example.good", "org.example.other"},
        )

        self.assertTrue(discovery.unregister(duplicate_plugin_id.manifest))
        self.assertTrue(discovery.unregister(duplicate_reader_id.manifest))
        self.assertIn(
            "external.good",
            {item.reader_id for item in registry.descriptors},
        )
        self.assertTrue(discovery.unregister(good.manifest))
        self.assertEqual(
            {
                item.plugin_id
                for item in discovery.refresh().descriptors
            },
            {"chemblender.builtin"},
        )
        self.assertTrue(
            all(
                state.availability.available
                for state in discovery.refresh().plugins
            )
        )

    def test_duplicate_enable_is_reconciled_by_one_unregister(self):
        discovery, registry = self.discovery()
        plugin = external_plugin(
            "org.example.duplicate_enable",
            "external.duplicate_enable",
        )

        self.assertTrue(discovery.register(plugin).availability.available)
        failed = discovery.register(plugin)
        self.assertFalse(failed.availability.available)

        self.assertTrue(discovery.unregister(plugin.manifest))
        self.assertNotIn(
            plugin.descriptor.reader_id,
            {item.reader_id for item in registry.descriptors},
        )
        self.assertNotIn(
            plugin.descriptor.plugin_id,
            {item.plugin_id for item in discovery.refresh().plugins},
        )

    def test_recreated_equal_manifest_reconciles_unregister_failure(self):
        discovery, registry = self.discovery()
        first = external_plugin(
            "org.example.recreated",
            "external.recreated",
        )
        recreated = external_plugin(
            "org.example.recreated",
            "external.recreated",
        )
        self.assertEqual(recreated.manifest, first.manifest)
        self.assertIsNot(recreated.manifest, first.manifest)
        discovery.register(first)

        with patch.object(
            registry,
            "unregister",
            side_effect=OSError("registry unavailable"),
        ):
            failed_unregister = discovery.unregister(first.manifest)
        failed_register = discovery.register(recreated)
        self.assertFalse(failed_unregister.availability.available)
        self.assertFalse(failed_register.availability.available)

        self.assertTrue(discovery.unregister(recreated.manifest))
        self.assertNotIn(
            recreated.descriptor.reader_id,
            {item.reader_id for item in registry.descriptors},
        )
        self.assertNotIn(
            recreated.descriptor.plugin_id,
            {item.plugin_id for item in discovery.refresh().plugins},
        )

    def test_successful_retry_clears_equal_registration_and_unregistration_failures(self):
        discovery, registry = self.discovery()
        plugin = external_plugin(
            "org.example.transient",
            "external.transient",
        )
        failed_unregister = discovery.unregister(plugin.manifest)
        original_register = registry.register
        attempts = 0

        def transient_register(value):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise OSError("registry temporarily unavailable")
            return original_register(value)

        with patch.object(registry, "register", side_effect=transient_register):
            failed_register = discovery.register(plugin)
            available = discovery.register(plugin)

        self.assertFalse(failed_unregister.availability.available)
        self.assertFalse(failed_register.availability.available)
        self.assertTrue(available.availability.available)
        self.assertEqual(
            tuple(
                state
                for state in discovery.refresh().plugins
                if state.plugin_id == plugin.manifest.plugin_id
            ),
            (available,),
        )

    def test_repeated_equal_registration_failure_stays_one_snapshot_row(self):
        discovery, registry = self.discovery()
        plugin = external_plugin(
            "org.example.repeated_failure",
            "external.repeated_failure",
        )

        with patch.object(
            registry,
            "register",
            side_effect=OSError("registry unavailable"),
        ):
            first = discovery.register(plugin)
            second = discovery.register(plugin)

        self.assertEqual(first, second)
        self.assertEqual(
            tuple(
                state
                for state in discovery.refresh().plugins
                if state.plugin_id == plugin.manifest.plugin_id
            ),
            (second,),
        )

    def test_partial_multi_reader_registration_is_reconciled_once(self):
        discovery, registry = self.discovery()
        first = external_plugin(
            "org.example.multi",
            "external.multi.first",
        )
        second = external_plugin(
            "org.example.multi",
            "external.multi.second",
        )
        blocker = external_plugin(
            "org.example.blocker",
            second.descriptor.reader_id,
        )
        shared_manifest = replace(
            first.manifest,
            readers=(
                first.manifest.readers[0],
                second.manifest.readers[0],
            ),
        )
        first = replace(first, manifest=shared_manifest)
        second = replace(second, manifest=shared_manifest)
        discovery.register(blocker)
        self.assertTrue(discovery.register(first).availability.available)
        failed = discovery.register(second)
        self.assertFalse(failed.availability.available)

        self.assertTrue(discovery.unregister(shared_manifest))
        descriptors = registry.descriptors
        self.assertNotIn(
            first.descriptor.reader_id,
            {item.reader_id for item in descriptors},
        )
        self.assertIs(
            next(
                item
                for item in descriptors
                if item.reader_id == blocker.descriptor.reader_id
            ),
            blocker.descriptor,
        )
        self.assertNotIn(
            first.descriptor.plugin_id,
            {item.plugin_id for item in discovery.refresh().plugins},
        )

    def test_callback_failure_is_visible_without_hiding_good_reader(self):
        discovery, registry = self.discovery()
        good = external_plugin("org.example.good", "external.good")
        discovery.register(good)

        failed = discovery.register(object())

        self.assertEqual(failed.plugin_id, "unknown")
        self.assertFalse(failed.availability.available)
        self.assertEqual(
            failed.availability.reason_code,
            "plugin_registration_failed",
        )
        self.assertEqual(
            failed.availability.detail,
            "TypeError",
        )
        self.assertIs(
            next(
                descriptor
                for descriptor in registry.descriptors
                if descriptor.reader_id == "external.good"
            ),
            good.descriptor,
        )

    def test_fatal_callback_errors_pass_through_without_discovery_state(self):
        for fatal in (
            MemoryError("out of memory"),
            KeyboardInterrupt(),
            SystemExit(),
            GeneratorExit(),
        ):
            with self.subTest(error=type(fatal).__name__):
                discovery, registry = self.discovery()
                plugin = external_plugin(
                    "org.example.fatal",
                    "external.fatal",
                )
                before = discovery.refresh()

                with patch.object(
                    registry,
                    "register",
                    side_effect=fatal,
                ):
                    with self.assertRaises(type(fatal)):
                        discovery.register(plugin)

                self.assertIs(discovery.refresh(), before)

    def test_fatal_unregister_errors_pass_through_without_discovery_state(self):
        for fatal in (
            MemoryError("out of memory"),
            KeyboardInterrupt(),
            SystemExit(),
            GeneratorExit(),
        ):
            with self.subTest(error=type(fatal).__name__):
                discovery, registry = self.discovery()
                plugin = external_plugin(
                    "org.example.fatal_unregister",
                    "external.fatal_unregister",
                )
                discovery.register(plugin)
                before = discovery.refresh()

                with patch.object(
                    registry,
                    "unregister",
                    side_effect=fatal,
                ):
                    with self.assertRaises(type(fatal)):
                        discovery.unregister(plugin.manifest)

                self.assertIs(discovery.refresh(), before)
                self.assertTrue(discovery.unregister(plugin.manifest))

    def test_malformed_failure_metadata_cannot_escape_diagnostic_isolation(self):
        discovery, registry = self.discovery()
        plugin = SimpleNamespace(
            manifest=SimpleNamespace(
                plugin_id="org.example.malformed",
                plugin_version="1.0.0",
                execution_mode=ExecutionMode.EXTENSION,
                readers=1,
            ),
            descriptor=None,
            priority=0,
        )

        failed = discovery.register(plugin)

        self.assertFalse(failed.availability.available)
        self.assertEqual(failed.plugin_id, "org.example.malformed")
        self.assertEqual(failed.reader_ids, ())
        self.assertEqual(
            failed.availability.detail,
            "TypeError",
        )
        self.assertEqual(
            registry.descriptors,
            discovery.refresh().descriptors,
        )

    def test_malformed_equality_cannot_poison_unrelated_good_unregister(self):
        for equality in (
            OSError("poison equality"),
            _PoisonBoolean(),
        ):
            with self.subTest(equality=type(equality).__name__):
                discovery, registry = self.discovery()
                malformed = SimpleNamespace(
                    manifest=_MalformedManifest(equality),
                    descriptor=None,
                    priority=0,
                )
                failed = discovery.register(malformed)
                good = external_plugin(
                    "org.example.unrelated_good",
                    "external.unrelated_good",
                )
                discovery.register(good)

                self.assertTrue(discovery.unregister(good.manifest))

                self.assertNotIn(
                    good.descriptor.reader_id,
                    {item.reader_id for item in registry.descriptors},
                )
                self.assertIn(failed, discovery.refresh().plugins)

    def test_fatal_manifest_equality_preserves_state_and_propagates(self):
        for fatal in (
            MemoryError("out of memory"),
            KeyboardInterrupt(),
            SystemExit(),
            GeneratorExit(),
        ):
            with self.subTest(error=type(fatal).__name__):
                discovery, registry = self.discovery()
                malformed = SimpleNamespace(
                    manifest=_MalformedManifest(fatal),
                    descriptor=None,
                    priority=0,
                )
                discovery.register(malformed)
                good = external_plugin(
                    "org.example.equality_fatal_good",
                    "external.equality_fatal_good",
                )
                discovery.register(good)
                before = discovery.refresh()

                with self.assertRaises(type(fatal)):
                    discovery.unregister(good.manifest)

                self.assertIs(discovery.refresh(), before)
                self.assertIn(
                    good.descriptor.reader_id,
                    {item.reader_id for item in registry.descriptors},
                )

    def test_repeated_never_owned_unregister_stays_one_failure(self):
        discovery, registry = self.discovery()
        manifest = external_plugin(
            "org.example.never_owned",
            "external.never_owned",
        ).manifest
        before = registry.descriptors

        first = discovery.unregister(manifest)
        second = discovery.unregister(manifest)

        for failed in (first, second):
            self.assertFalse(failed.availability.available)
            self.assertEqual(
                failed.availability.reason_code,
                "plugin_unregistration_failed",
            )
        self.assertEqual(registry.descriptors, before)
        failures = tuple(
            state
            for state in discovery.refresh().plugins
            if state.plugin_id == manifest.plugin_id
            and not state.availability.available
        )
        self.assertEqual(failures, (second,))

    def test_unregister_failure_is_visible_and_retry_removes_registered_reader(self):
        discovery, registry = self.discovery()
        plugin = external_plugin("org.example.retry", "external.retry")
        discovery.register(plugin)

        with patch.object(
            registry,
            "unregister",
            side_effect=OSError("registry unavailable"),
        ):
            failed = discovery.unregister(plugin.manifest)

        self.assertFalse(failed.availability.available)
        self.assertEqual(
            failed.availability.reason_code,
            "plugin_unregistration_failed",
        )
        self.assertIn(
            "external.retry",
            {item.reader_id for item in registry.descriptors},
        )
        self.assertTrue(discovery.unregister(plugin.manifest))
        self.assertNotIn(
            "external.retry",
            {item.reader_id for item in registry.descriptors},
        )
        self.assertTrue(
            all(
                state.plugin_id != plugin.manifest.plugin_id
                or state.availability.available
                for state in discovery.refresh().plugins
            )
        )


class ReaderAPIDiscoveryBridgeTests(unittest.TestCase):
    def test_reserved_builtin_id_is_isolated_and_cleaned_by_discovery(self):
        bridge = importlib.import_module(
            "ChemBlender.runtime.reader_api_bridge"
        )
        registry = bridge.get_reader_plugin_registry()
        before = registry.descriptors
        reserved = external_plugin(
            "chemblender.builtin",
            "external.reserved",
        )
        namespace = {}
        handle = bridge.register_reader_api_handle(
            "synthetic_repository.chemblender",
            namespace=namespace,
        )
        registered_failure = False

        try:
            failed = handle.register_callback(reserved)
            registered_failure = True
            self.assertFalse(failed.availability.available)
            self.assertEqual(
                failed.availability.reason_code,
                "plugin_registration_failed",
            )
            self.assertEqual(failed.availability.detail, "ValueError")
            self.assertTrue(
                all(
                    actual is expected
                    for actual, expected in zip(
                        registry.descriptors,
                        before,
                        strict=True,
                    )
                )
            )
            self.assertIn(
                failed,
                bridge.refresh_reader_plugin_discovery().plugins,
            )
            self.assertTrue(
                handle.unregister_callback(reserved.manifest)
            )
            registered_failure = False
            self.assertTrue(
                all(
                    actual is expected
                    for actual, expected in zip(
                        registry.descriptors,
                        before,
                        strict=True,
                    )
                )
            )
            self.assertNotIn(
                failed,
                bridge.refresh_reader_plugin_discovery().plugins,
            )
        finally:
            if registered_failure:
                handle.unregister_callback(reserved.manifest)
            current = namespace.get(bridge.READER_API_HANDLE_KEY)
            if current is not None:
                bridge.remove_reader_api_handle(
                    current,
                    namespace=namespace,
                )

    def test_handle_callbacks_refresh_and_clean_explicit_plugin_state(self):
        bridge = importlib.import_module(
            "ChemBlender.runtime.reader_api_bridge"
        )
        plugin = external_plugin(
            "org.example.bridge_discovery",
            "external.bridge_discovery",
        )
        duplicate = external_plugin(
            "org.example.bridge_failure",
            plugin.descriptor.reader_id,
        )
        namespace = {}
        handle = bridge.register_reader_api_handle(
            "synthetic_repository.chemblender",
            namespace=namespace,
        )

        try:
            good_state = handle.register_callback(plugin)
            failed_state = handle.register_callback(duplicate)
            first = bridge.refresh_reader_plugin_discovery()
            second = bridge.refresh_reader_plugin_discovery()

            self.assertTrue(good_state.availability.available)
            self.assertFalse(failed_state.availability.available)
            self.assertIs(second, first)
            self.assertIn(
                plugin.descriptor.reader_id,
                {item.reader_id for item in first.descriptors},
            )
            self.assertIn(failed_state, first.plugins)

            self.assertTrue(
                handle.unregister_callback(duplicate.manifest)
            )
            self.assertIn(
                plugin.descriptor.reader_id,
                {
                    item.reader_id
                    for item in bridge.get_reader_plugin_registry().descriptors
                },
            )
            self.assertTrue(handle.unregister_callback(plugin.manifest))
        finally:
            current = namespace.get(bridge.READER_API_HANDLE_KEY)
            if current is not None:
                bridge.remove_reader_api_handle(
                    current,
                    namespace=namespace,
                )


if __name__ == "__main__":
    unittest.main()
