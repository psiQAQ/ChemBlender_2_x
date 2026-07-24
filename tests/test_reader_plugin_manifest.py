import sys
import subprocess
import tempfile
import unittest
from dataclasses import fields
from pathlib import Path
from types import ModuleType
from unittest.mock import patch


VALID_MANIFEST = """
schema_version = "1"
plugin_id = "org.example.reader"
plugin_version = "1.0.0"
chemblender_api = ">=0.1,<1.0"
execution_mode = "extension"
license = ["SPDX:MIT"]

[[readers]]
reader_id = "example-format"
reader_version = "1"
extensions = [".example"]
capabilities = ["structure", "atomic_property"]
"""


class ReaderPluginManifestTests(unittest.TestCase):
    def manifest(self, text=VALID_MANIFEST):
        from ChemBlender.reader_api import ReaderPluginManifest

        return ReaderPluginManifest.from_toml(text)

    def test_reader_api_version_is_alpha_version(self):
        from ChemBlender.reader_api import READER_API_VERSION

        self.assertEqual(READER_API_VERSION, "0.1")

    def test_parses_valid_manifest_from_text_and_bytes(self):
        manifest = self.manifest()

        self.assertEqual(manifest.plugin_id, "org.example.reader")
        self.assertEqual(manifest.execution_mode.value, "extension")
        self.assertEqual(manifest.readers[0].capabilities, ("atomic_property", "structure"))
        self.assertEqual(self.manifest(VALID_MANIFEST.encode()), manifest)

    def test_rejects_invalid_plugin_id(self):
        with self.assertRaises(ValueError):
            self.manifest(VALID_MANIFEST.replace("org.example.reader", "Org Example"))

    def test_rejects_invalid_plugin_version(self):
        with self.assertRaises(ValueError):
            self.manifest(VALID_MANIFEST.replace('plugin_version = "1.0.0"', 'plugin_version = "v1"'))

    def test_rejects_invalid_api_ranges(self):
        for api_range in ("*", "latest", "^0.1", "~=0.1", ">=0.1", "", ">=0.1,<0.1", ">=1.0,<0.1"):
            with self.subTest(api_range=api_range), self.assertRaises(ValueError):
                self.manifest(VALID_MANIFEST.replace(">=0.1,<1.0", api_range))

    def test_rejects_incompatible_api_range(self):
        with self.assertRaises(ValueError):
            self.manifest(VALID_MANIFEST.replace(">=0.1,<1.0", ">=0.2,<1.0"))

    def test_rejects_duplicate_reader_id(self):
        with self.assertRaises(ValueError):
            self.manifest(VALID_MANIFEST + VALID_MANIFEST.split("[[readers]]", 1)[1].join(("\n[[readers]]", "")))

    def test_rejects_unknown_top_level_key(self):
        with self.assertRaises(ValueError):
            self.manifest(VALID_MANIFEST.replace('schema_version = "1"', 'schema_version = "1"\nunknown = true'))

    def test_rejects_missing_top_level_key(self):
        with self.assertRaises(ValueError):
            self.manifest(VALID_MANIFEST.replace('plugin_version = "1.0.0"\n', ""))

    def test_rejects_unknown_reader_key(self):
        with self.assertRaises(ValueError):
            self.manifest(VALID_MANIFEST.replace('reader_version = "1"', 'reader_version = "1"\nunknown = true'))

    def test_rejects_missing_reader_key(self):
        with self.assertRaises(ValueError):
            self.manifest(VALID_MANIFEST.replace('reader_version = "1"\n', ""))

    def test_rejects_unknown_execution_mode(self):
        with self.assertRaises(ValueError):
            self.manifest(VALID_MANIFEST.replace('execution_mode = "extension"', 'execution_mode = "thread"'))

    def test_rejects_empty_license(self):
        with self.assertRaises(ValueError):
            self.manifest(VALID_MANIFEST.replace('license = ["SPDX:MIT"]', 'license = []'))

    def test_normalizes_extensions_and_capabilities(self):
        manifest = self.manifest(
            VALID_MANIFEST.replace('[".example"]', '["EXAMPLE", ".other"]')
            .replace('["structure", "atomic_property"]', '["structure", "atomic_property", "structure"]')
        )

        self.assertEqual(manifest.readers[0].extensions, (".example", ".other"))
        self.assertEqual(manifest.readers[0].capabilities, ("atomic_property", "structure"))

    def test_deduplicates_duplicate_extension(self):
        manifest = self.manifest(VALID_MANIFEST.replace('[".example"]', '["example", ".EXAMPLE"]'))

        self.assertEqual(manifest.readers[0].extensions, (".example",))

    def test_rejects_invalid_capability_token(self):
        with self.assertRaises(ValueError):
            self.manifest(VALID_MANIFEST.replace('"atomic_property"', '"Atomic Property"'))

    def test_normalized_manifest_equality_is_deterministic(self):
        first = self.manifest(VALID_MANIFEST.replace('[".example"]', '["OTHER", "example"]'))
        second = self.manifest(VALID_MANIFEST.replace('[".example"]', '[".example", ".other"]'))

        self.assertEqual(first, second)

    def test_direct_manifest_construction_normalizes_and_freezes_mutable_inputs(self):
        from ChemBlender.reader_api import ExecutionMode, ReaderManifestEntry, ReaderPluginManifest

        extensions = ["EXAMPLE", ".EXAMPLE"]
        capabilities = ["structure", "atomic_property", "structure"]
        entry = ReaderManifestEntry("example-format", "1", extensions, capabilities)
        licenses = ["SPDX:MIT"]
        readers = [entry]
        manifest = ReaderPluginManifest(
            "1", "org.example.reader", "1.0.0", ">=0.1,<1.0", "extension", licenses, readers
        )
        extensions.append(".mutated")
        capabilities.append("grid")
        licenses.append("SPDX:Apache-2.0")
        readers.clear()

        self.assertEqual(entry.extensions, (".example",))
        self.assertEqual(entry.capabilities, ("atomic_property", "structure"))
        self.assertEqual(manifest.license, ("SPDX:MIT",))
        self.assertEqual(manifest.readers, (entry,))
        self.assertIs(manifest.execution_mode, ExecutionMode.EXTENSION)

    def test_direct_manifest_construction_rejects_invalid_values(self):
        from ChemBlender.reader_api import ReaderManifestEntry, ReaderPluginManifest

        with self.assertRaises(ValueError):
            ReaderManifestEntry("Example Format", "1", [".example"], ["structure"])
        with self.assertRaises(ValueError):
            ReaderPluginManifest("1", "org.example.reader", "1.0.0", "^0.1", "extension", ["SPDX:MIT"], [])

    def test_direct_manifest_rejects_non_string_schema_that_compares_equal(self):
        from ChemBlender.reader_api import ReaderManifestEntry, ReaderPluginManifest

        class EqualToOne:
            def __eq__(self, other):
                return True

        entry = ReaderManifestEntry("example-format", "1", [".example"], ["structure"])
        with self.assertRaises(ValueError):
            ReaderPluginManifest(EqualToOne(), "org.example.reader", "1.0.0", ">=0.1,<1.0", "extension", ["SPDX:MIT"], [entry])

    def test_descriptor_capabilities_are_immutable_and_ordered(self):
        from ChemBlender.reader_api import ExecutionMode, PublicReaderDescriptor, ReaderAvailability

        descriptor = PublicReaderDescriptor(
            plugin_id="org.example.reader",
            plugin_version="1.0.0",
            reader_id="example-format",
            reader_version="1",
            execution_mode=ExecutionMode.EXTENSION,
            extensions=("EXAMPLE", ".other", ".EXAMPLE"),
            capabilities={"structure": True, "atomic_property": True},
            availability=ReaderAvailability(True, "extension", "available", ""),
        )
        self.assertEqual(tuple(descriptor.capabilities), ("atomic_property", "structure"))
        with self.assertRaises(TypeError):
            descriptor.capabilities["grid"] = True

    def test_descriptor_rejects_iterable_of_capability_pairs(self):
        from ChemBlender.reader_api import ExecutionMode, PublicReaderDescriptor, ReaderAvailability

        with self.assertRaises(TypeError):
            PublicReaderDescriptor(
                "org.example.reader", "1.0.0", "example-format", "1", ExecutionMode.EXTENSION,
                (".example",), [("structure", True)],
                ReaderAvailability(True, "extension", "available", ""),
            )

    def test_public_descriptor_contains_no_callable(self):
        from ChemBlender.reader_api import ExecutionMode, PublicReaderDescriptor, ReaderAvailability

        descriptor = PublicReaderDescriptor(
            "org.example.reader", "1.0.0", "example-format", "1", ExecutionMode.EXTENSION,
            (".example",), {"structure": True},
            ReaderAvailability(True, "extension", "available", ""),
        )
        self.assertFalse(any(callable(getattr(descriptor, field.name)) for field in fields(descriptor)))

    def test_reader_availability_is_exact_existing_class(self):
        from ChemBlender.core.readers import ReaderAvailability as ExistingReaderAvailability
        from ChemBlender.reader_api import ReaderAvailability

        self.assertIs(ReaderAvailability, ExistingReaderAvailability)

    def test_availability_probe_does_not_import_present_optional_package(self):
        from ChemBlender.reader_api.descriptors import _probe_availability

        with tempfile.TemporaryDirectory() as directory:
            module_name = "reader_api_probe_sentinel"
            Path(directory, f"{module_name}.py").write_text("raise AssertionError('imported')\n", encoding="utf-8")
            sys.path.insert(0, directory)
            try:
                result = _probe_availability(module_name, "extension")
            finally:
                sys.path.remove(directory)
                sys.modules.pop(module_name, None)

        self.assertTrue(result.available)
        self.assertNotIn(module_name, sys.modules)

    def test_availability_probe_returns_unavailable_for_missing_top_level_package(self):
        from ChemBlender.reader_api.descriptors import _probe_availability

        result = _probe_availability("reader_api_missing_sentinel", "extension")

        self.assertFalse(result.available)
        self.assertEqual(result.reason_code, "dependency_missing")

    def test_availability_probe_reports_unexpected_probe_failure(self):
        from ChemBlender.reader_api.descriptors import _probe_availability

        with patch("ChemBlender.reader_api.descriptors.importlib.util.find_spec", side_effect=RuntimeError("broken finder")):
            result = _probe_availability("reader_api_probe_failure", "extension")

        self.assertFalse(result.available)
        self.assertEqual(result.reason_code, "dependency_probe_failed")

    def test_availability_probe_does_not_format_probe_exception(self):
        from ChemBlender.reader_api.descriptors import _probe_availability

        class ExplosiveError(Exception):
            def __str__(self):
                raise RuntimeError("formatted probe error")

        with patch("ChemBlender.reader_api.descriptors.importlib.util.find_spec", side_effect=ExplosiveError()):
            result = _probe_availability("reader_api_probe_failure", "extension")

        self.assertFalse(result.available)
        self.assertEqual(result.reason_code, "dependency_probe_failed")
        self.assertEqual(result.detail, "find_spec raised an exception")

    def test_availability_probe_treats_spec_less_loaded_module_as_unavailable(self):
        from ChemBlender.reader_api.descriptors import _probe_availability

        module_name = "reader_api_specless_sentinel"
        missing = object()
        previous = sys.modules.get(module_name, missing)
        sentinel = ModuleType(module_name)
        sentinel.__spec__ = None
        sys.modules[module_name] = sentinel
        try:
            result = _probe_availability(module_name, "extension")
        finally:
            if previous is missing:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = previous

        self.assertFalse(result.available)
        self.assertEqual(result.reason_code, "dependency_missing")

    def test_availability_probe_rejects_dotted_package_before_import(self):
        from ChemBlender.reader_api.descriptors import _probe_availability

        with tempfile.TemporaryDirectory() as directory:
            module_name = "reader_api_parent_sentinel"
            Path(directory, f"{module_name}.py").write_text("raise AssertionError('imported')\n", encoding="utf-8")
            sys.path.insert(0, directory)
            try:
                with self.assertRaises(ValueError):
                    _probe_availability(f"{module_name}.child", "extension")
            finally:
                sys.path.remove(directory)
                sys.modules.pop(module_name, None)

    def test_import_in_fresh_subprocess_does_not_load_blender_or_optional_stacks(self):
        subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; import ChemBlender.reader_api; "
                "assert all(name not in sys.modules for name in "
                "('bpy', 'cclib', 'iodata', 'gbasis', 'ase', 'pymatgen'))",
            ],
            check=True,
            cwd=Path(__file__).resolve().parents[1],
        )

    def test_public_all_is_exact(self):
        import ChemBlender.reader_api as reader_api

        self.assertEqual(
            reader_api.__all__,
            (
                "READER_API_VERSION",
                "ExecutionMode",
                "ReaderAvailability",
                "ReaderManifestEntry",
                "ReaderPluginManifest",
                "PublicReaderDescriptor",
            ),
        )


if __name__ == "__main__":
    unittest.main()
