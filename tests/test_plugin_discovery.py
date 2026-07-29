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
