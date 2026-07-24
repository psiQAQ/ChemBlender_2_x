import ast
import json
import sys
import subprocess
import tempfile
import unittest
from dataclasses import fields
from enum import Enum
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
        from ChemBlender.reader_api import (
            CapabilitySupport,
            ExecutionMode,
            PublicReaderDescriptor,
            ReaderAvailability,
        )

        descriptor = PublicReaderDescriptor(
            plugin_id="org.example.reader",
            plugin_version="1.0.0",
            reader_id="example-format",
            reader_version="1",
            execution_mode=ExecutionMode.EXTENSION,
            extensions=("EXAMPLE", ".other", ".EXAMPLE"),
            capabilities={
                "structure": CapabilitySupport.SUPPORTED,
                "atomic_property": CapabilitySupport.SUPPORTED,
            },
            availability=ReaderAvailability(True, "extension", "available", ""),
        )
        self.assertEqual(tuple(descriptor.capabilities), ("atomic_property", "structure"))
        with self.assertRaises(TypeError):
            descriptor.capabilities["grid"] = CapabilitySupport.SUPPORTED

    def test_descriptor_preserves_tri_state_capabilities(self):
        from ChemBlender.reader_api import (
            CapabilitySupport,
            ExecutionMode,
            PublicReaderDescriptor,
            ReaderAvailability,
        )

        descriptor = PublicReaderDescriptor(
            "org.example.reader",
            "1.0.0",
            "example-format",
            "1",
            ExecutionMode.EXTENSION,
            ("example",),
            {
                "unsupported": CapabilitySupport.UNSUPPORTED,
                "supported": CapabilitySupport.SUPPORTED,
                "partial": CapabilitySupport.PARTIAL,
            },
            ReaderAvailability(True, "extension", "available", ""),
        )

        self.assertEqual(
            tuple(descriptor.capabilities.items()),
            (
                ("partial", CapabilitySupport.PARTIAL),
                ("supported", CapabilitySupport.SUPPORTED),
                ("unsupported", CapabilitySupport.UNSUPPORTED),
            ),
        )

    def test_descriptor_rejects_non_exact_capability_support(self):
        from ChemBlender.reader_api import (
            ExecutionMode,
            PublicReaderDescriptor,
            ReaderAvailability,
        )

        class ForeignCapabilitySupport(str, Enum):
            SUPPORTED = "supported"

        class DuckCapabilitySupport:
            value = "supported"

        for value in (True, "supported", ForeignCapabilitySupport.SUPPORTED, DuckCapabilitySupport()):
            with self.subTest(value=value), self.assertRaises(TypeError):
                PublicReaderDescriptor(
                    "org.example.reader",
                    "1.0.0",
                    "example-format",
                    "1",
                    ExecutionMode.EXTENSION,
                    ("example",),
                    {"structure": value},
                    ReaderAvailability(True, "extension", "available", ""),
                )

    def test_descriptor_rejects_iterable_of_capability_pairs(self):
        from ChemBlender.reader_api import ExecutionMode, PublicReaderDescriptor, ReaderAvailability

        with self.assertRaises(TypeError):
            PublicReaderDescriptor(
                "org.example.reader", "1.0.0", "example-format", "1", ExecutionMode.EXTENSION,
                (".example",), [("structure", "supported")],
                ReaderAvailability(True, "extension", "available", ""),
            )

    def test_descriptor_rejects_execution_mode_enum_in_availability(self):
        from ChemBlender.reader_api import ExecutionMode, PublicReaderDescriptor, ReaderAvailability

        with self.assertRaises(TypeError):
            PublicReaderDescriptor(
                "org.example.reader", "1.0.0", "example-format", "1", ExecutionMode.EXTENSION,
                (".example",), {},
                ReaderAvailability(True, ExecutionMode.EXTENSION, "available", ""),
            )

    def test_descriptor_rejects_non_sequence_extensions(self):
        from ChemBlender.reader_api import (
            CapabilitySupport,
            ExecutionMode,
            PublicReaderDescriptor,
            ReaderAvailability,
        )

        for extensions in ("xyz", b".example", {".example"}):
            with self.subTest(extensions=extensions), self.assertRaises(ValueError):
                PublicReaderDescriptor(
                    "org.example.reader",
                    "1.0.0",
                    "example-format",
                    "1",
                    ExecutionMode.EXTENSION,
                    extensions,
                    {"structure": CapabilitySupport.SUPPORTED},
                    ReaderAvailability(True, "extension", "available", ""),
                )

    def test_public_descriptor_contains_no_callable(self):
        from ChemBlender.reader_api import (
            CapabilitySupport,
            ExecutionMode,
            PublicReaderDescriptor,
            ReaderAvailability,
        )

        descriptor = PublicReaderDescriptor(
            "org.example.reader", "1.0.0", "example-format", "1", ExecutionMode.EXTENSION,
            (".example",), {"structure": CapabilitySupport.SUPPORTED},
            ReaderAvailability(True, "extension", "available", ""),
        )
        self.assertFalse(any(callable(getattr(descriptor, field.name)) for field in fields(descriptor)))

    def test_reader_availability_is_exact_existing_class(self):
        from ChemBlender.core.readers import ReaderAvailability as ExistingReaderAvailability
        from ChemBlender.reader_api import ReaderAvailability

        self.assertIs(ReaderAvailability, ExistingReaderAvailability)

    def test_capability_support_is_exact_existing_class(self):
        from ChemBlender.core.readers import CapabilitySupport as ExistingCapabilitySupport
        from ChemBlender.reader_api import CapabilitySupport

        self.assertIs(CapabilitySupport, ExistingCapabilitySupport)

    def test_capability_matrix_snapshot_preserves_all_tri_state_values(self):
        from ChemBlender.reader_api import (
            CapabilitySupport,
            ExecutionMode,
            PublicReaderDescriptor,
            ReaderAvailability,
        )

        snapshot_path = Path(__file__).resolve().parents[1] / "docs" / "quantum-visualization" / "reader-capability-matrix.json"
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        support_by_status = {
            "supported": CapabilitySupport.SUPPORTED,
            "partial": CapabilitySupport.PARTIAL,
            "unsupported": CapabilitySupport.UNSUPPORTED,
        }
        descriptors = [
            PublicReaderDescriptor(
                "chemblender.builtin",
                "0.1",
                reader["reader_id"],
                reader["reader_version"],
                ExecutionMode.BUILT_IN,
                reader["extensions"],
                {name: support_by_status[status] for name, status in reader["capabilities"].items()},
                ReaderAvailability(True, "built_in", "available", ""),
            )
            for reader in snapshot["readers"]
        ]

        self.assertEqual(
            {support for descriptor in descriptors for support in descriptor.capabilities.values()},
            set(CapabilitySupport),
        )
        self.assertEqual(
            {
                descriptor.reader_id: {name: support.value for name, support in descriptor.capabilities.items()}
                for descriptor in descriptors
            },
            {reader["reader_id"]: reader["capabilities"] for reader in snapshot["readers"]},
        )

    def test_extensions_accept_compound_suffixes_and_normalize_deterministically(self):
        from ChemBlender.reader_api import ReaderManifestEntry

        entry = ReaderManifestEntry(
            "example-format",
            "1",
            ["XYZ", ".xyz", "TAR.GZ", ".tar.gz", ".molden.input"],
            ["structure"],
        )

        self.assertEqual(entry.extensions, (".molden.input", ".tar.gz", ".xyz"))
        self.assertEqual(
            ReaderManifestEntry("example-format", "1", ["tar.gz", ".TAR.GZ"], ["structure"]).extensions,
            (".tar.gz",),
        )

    def test_extensions_reject_unsafe_or_ambiguous_values(self):
        from ChemBlender.reader_api import ReaderManifestEntry

        for extension in (
            ".", "..", "..xyz", "...xyz", "..TAR.GZ", "../xyz",
            "folder/xyz", "x yz", "/", "\\", "*", "?", ";",
        ):
            with self.subTest(extension=extension), self.assertRaises(ValueError):
                ReaderManifestEntry("example-format", "1", [extension], ["structure"])

    def test_licenses_require_exact_trimmed_strings_and_normalize(self):
        from ChemBlender.reader_api import ReaderManifestEntry, ReaderPluginManifest

        entry = ReaderManifestEntry("example-format", "1", ["example"], ["structure"])
        licenses = ["MIT License", "Apache-2.0", "MIT License"]
        manifest = ReaderPluginManifest(
            "1", "org.example.reader", "1.0.0", ">=0.1,<1.0", "extension", licenses, [entry]
        )
        licenses.append("GPL-3.0-only")
        self.assertEqual(manifest.license, ("Apache-2.0", "MIT License"))

        class StringSubclass(str):
            pass

        for license_value in ("", "   ", " MIT", "MIT ", StringSubclass("MIT"), 1):
            with self.subTest(license_value=license_value), self.assertRaises(ValueError):
                ReaderPluginManifest(
                    "1", "org.example.reader", "1.0.0", ">=0.1,<1.0", "extension", [license_value], [entry]
                )

    def test_licenses_normalize_direct_helper_contract(self):
        from ChemBlender.reader_api.manifest import _licenses

        self.assertEqual(
            _licenses(["MIT OR Apache-2.0", "Apache-2.0", "Apache-2.0"]),
            ("Apache-2.0", "MIT OR Apache-2.0"),
        )

    def test_reader_api_modules_have_no_absolute_installed_namespace_imports(self):
        package_root = Path(__file__).resolve().parents[1] / "ChemBlender" / "reader_api"
        forbidden = ("ChemBlender", "bl_ext")

        for source_path in package_root.glob("*.py"):
            tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
            imported = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    imported.extend([node.module or "", *(alias.name for alias in node.names)])
            with self.subTest(source_path=source_path):
                self.assertFalse(
                    any(name == prefix or name.startswith(prefix + ".") for name in imported for prefix in forbidden),
                    imported,
                )

    def test_reader_api_reexports_descriptor_classes_from_descriptors_module(self):
        init_path = Path(__file__).resolve().parents[1] / "ChemBlender" / "reader_api" / "__init__.py"
        tree = ast.parse(init_path.read_text(encoding="utf-8"), filename=str(init_path))
        exports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module == "descriptors"
            for alias in node.names
        }

        self.assertTrue({"CapabilitySupport", "ReaderAvailability", "PublicReaderDescriptor"} <= exports)

    def test_reader_api_imports_from_a_synthetic_installed_namespace(self):
        repository_root = Path(__file__).resolve().parents[1]
        package_root = repository_root / "ChemBlender"
        script = f"""
import importlib.machinery
import importlib.util
import sys
import types
from pathlib import Path

repository_root = Path({str(repository_root)!r})
package_root = Path({str(package_root)!r})
sys.path[:] = [item for item in sys.path if item not in ('', str(repository_root))]
parent = types.ModuleType('synthetic_repository')
parent.__path__ = []
parent.__spec__ = importlib.machinery.ModuleSpec('synthetic_repository', loader=None, is_package=True)
sys.modules['synthetic_repository'] = parent
spec = importlib.util.spec_from_file_location(
    'synthetic_repository.chemblender',
    package_root / '__init__.py',
    submodule_search_locations=[str(package_root)],
)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
import synthetic_repository.chemblender.reader_api as reader_api
assert reader_api.CapabilitySupport.__name__ == 'CapabilitySupport'
assert not any(name in sys.modules for name in ('ChemBlender', 'bpy', 'cclib', 'iodata', 'gbasis', 'ase', 'pymatgen'))
"""

        subprocess.run([sys.executable, "-c", script], check=True, cwd=repository_root)

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
        self.assertIs(type(result.execution_mode), str)
        self.assertEqual(result.execution_mode, "extension")

    def test_availability_probe_returns_unavailable_for_missing_top_level_package(self):
        from ChemBlender.reader_api.descriptors import _probe_availability

        result = _probe_availability("reader_api_missing_sentinel", "extension")

        self.assertFalse(result.available)
        self.assertEqual(result.reason_code, "dependency_missing")
        self.assertIs(type(result.execution_mode), str)
        self.assertEqual(result.execution_mode, "extension")

    def test_availability_probe_reports_unexpected_probe_failure(self):
        from ChemBlender.reader_api.descriptors import _probe_availability

        with patch("ChemBlender.reader_api.descriptors.importlib.util.find_spec", side_effect=RuntimeError("broken finder")):
            result = _probe_availability("reader_api_probe_failure", "extension")

        self.assertFalse(result.available)
        self.assertEqual(result.reason_code, "dependency_probe_failed")
        self.assertIs(type(result.execution_mode), str)
        self.assertEqual(result.execution_mode, "extension")

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
                "CapabilitySupport",
                "ReaderAvailability",
                "ReaderManifestEntry",
                "ReaderPluginManifest",
                "PublicReaderDescriptor",
            ),
        )


if __name__ == "__main__":
    unittest.main()
