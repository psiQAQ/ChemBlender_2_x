import ast
import hashlib
import importlib.util
import re
import sys
import tomllib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace

from ChemBlender import reader_api
from ChemBlender.core.import_pipeline import (
    ImportRequest,
    ImportSource,
    ReaderOverride,
    StagedImportSession,
)
from ChemBlender.reader_api.import_pipeline_bridge import (
    preflight_reader_plugins,
)


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "reader-extension"
READER = EXAMPLE / "reader.py"
BOOTSTRAP = EXAMPLE / "__init__.py"
FIXTURE = EXAMPLE / "fixtures" / "water.cbsimple"


def load_reader():
    name = "_chemblender_example_reader_test"
    spec = importlib.util.spec_from_file_location(name, READER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(name, None)


class ExampleReaderBoundaryTests(unittest.TestCase):
    def test_example_inventory_and_blender_manifest(self):
        expected = {
            "README.md",
            "LICENSE",
            "__init__.py",
            "reader.py",
            "blender_manifest.toml",
            "fixtures/water.cbsimple",
            "tests/test_reader.py",
        }
        actual = {
            path.relative_to(EXAMPLE).as_posix()
            for path in EXAMPLE.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        }
        self.assertTrue(expected <= actual)
        manifest = tomllib.loads(
            (EXAMPLE / "blender_manifest.toml").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["schema_version"], "1.0.0")
        self.assertEqual(manifest["id"], "chemblender_reader_example")
        self.assertEqual(manifest["type"], "add-on")
        self.assertEqual(manifest["blender_version_min"], "5.1.0")
        self.assertNotIn("wheels", manifest)
        self.assertFalse(EXAMPLE.is_relative_to(ROOT / "ChemBlender"))

    def test_business_reader_has_only_public_host_boundary(self):
        tree = ast.parse(READER.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = tuple(alias.name for alias in node.names)
                self.assertNotIn("bpy", names)
                self.assertFalse(
                    any(name.startswith("ChemBlender") for name in names)
                )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                self.assertNotEqual(module, "bpy")
                self.assertFalse(
                    module == "ChemBlender"
                    or module.startswith("ChemBlender.")
                )

    def test_bootstrap_only_resolves_the_published_api_handle(self):
        tree = ast.parse(BOOTSTRAP.read_text(encoding="utf-8"))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                prefix = "." * node.level + (node.module or "")
                imports.update(
                    prefix + alias.name
                    for alias in node.names
                )
        self.assertEqual(imports, {"importlib", "bpy", ".reader"})
        source = BOOTSTRAP.read_text(encoding="utf-8")
        self.assertIn('"chemblender.reader_api.v1"', source)
        self.assertNotIn("bl_ext.", source)
        self.assertNotIn("ChemBlender.reader_api", source)

    def test_manifest_sniff_parse_canonical_and_cancellation(self):
        module = load_reader()
        plugin = module.create_plugin(reader_api)

        self.assertIsInstance(plugin, reader_api.ReaderPlugin)
        self.assertEqual(
            plugin.manifest.plugin_id,
            "org.chemblender.example.simplecoords",
        )
        self.assertEqual(plugin.descriptor.reader_id, "simplecoords")
        self.assertEqual(plugin.descriptor.extensions, (".cbsimple",))
        self.assertIs(
            plugin.descriptor.capabilities["structure"],
            reader_api.CapabilitySupport.SUPPORTED,
        )
        self.assertEqual(
            reader_api.ReaderPluginManifest.from_toml(
                module.READER_MANIFEST_TOML
            ),
            plugin.manifest,
        )

        exact = plugin.sniff(
            reader_api.SniffRequest(FIXTURE, FIXTURE.read_bytes())
        )
        self.assertIs(exact.match, reader_api.SniffMatch.EXACT)
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            other = root / "other.cbsimple"
            other.write_bytes(b"not this format\n")
            none = plugin.sniff(
                reader_api.SniffRequest(other, other.read_bytes())
            )
            self.assertIs(none.match, reader_api.SniffMatch.NONE)

            events = []
            request = reader_api.ParseRequest(
                source_path=FIXTURE,
                source_content_hash=hashlib.sha256(
                    FIXTURE.read_bytes()
                ).hexdigest(),
                validation_mode="balanced",
                canonical_parameters={},
                staging_root=root,
                progress=events.append,
                is_cancelled=lambda: False,
            )
            batch = plugin.parse(request)
            self.assertEqual(batch.source_revisions[0].id, request.source_revision_id)
            self.assertEqual(batch.structures[0].atomic_numbers, (8, 1, 1))
            self.assertEqual(
                batch.structures[0].coordinates.dims,
                ("atom", "xyz"),
            )
            self.assertEqual(batch.report.parsed_capabilities, ("structure",))
            self.assertEqual(
                batch.report.created_entity_ids,
                (
                    batch.structures[0].id,
                    batch.provenance[0].id,
                ),
            )
            reader_api.internal_batch_from_public(batch)
            bundle = root / "bundle"
            reader_api.write_public_batch_bundle(bundle, batch)
            restored = reader_api.read_public_batch_bundle(bundle)
            self.assertEqual(
                restored.structures[0].atomic_numbers,
                batch.structures[0].atomic_numbers,
            )
            self.assertEqual(
                restored.structures[0].coordinates.shape,
                (3, 3),
            )
            self.assertTrue(events)

            cancelled = plugin.parse(
                reader_api.ParseRequest(
                    source_path=FIXTURE,
                    source_content_hash=request.source_content_hash,
                    validation_mode="balanced",
                    canonical_parameters={},
                    staging_root=root,
                    progress=lambda _event: None,
                    is_cancelled=lambda: True,
                )
            )
            self.assertEqual(cancelled.structures, ())
            self.assertEqual(cancelled.report.created_entity_ids, ())
            self.assertEqual(
                cancelled.report.issues[0].kind,
                reader_api.IssueKind.WARNING,
            )

    def test_malformed_sources_fail_without_partial_artifacts(self):
        plugin = load_reader().create_plugin(reader_api)
        cases = {
            "invalid-utf8": (
                b"\xff",
                "CBSIMPLE source must be UTF-8",
            ),
            "wrong-header": (
                b"CBSIMPLE 2\nunits angstrom\natoms 1\nH 0 0 0\n",
                "CBSIMPLE 1 header is required",
            ),
            "wrong-units": (
                b"CBSIMPLE 1\nunits bohr\natoms 1\nH 0 0 0\n",
                "CBSIMPLE 1 requires units angstrom",
            ),
            "count-mismatch": (
                b"CBSIMPLE 1\nunits angstrom\natoms 2\nH 0 0 0\n",
                "atom count must match the coordinate rows",
            ),
            "unknown-element": (
                b"CBSIMPLE 1\nunits angstrom\natoms 1\nX 0 0 0\n",
                "invalid atom row 1",
            ),
            "non-finite": (
                b"CBSIMPLE 1\nunits angstrom\natoms 1\nH nan 0 0\n",
                "invalid atom row 1",
            ),
            "trailing-row": (
                b"CBSIMPLE 1\nunits angstrom\natoms 1\n"
                b"H 0 0 0\nH 1 0 0\n",
                "atom count must match the coordinate rows",
            ),
        }
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, (source_bytes, message) in cases.items():
                with self.subTest(name=name):
                    source_path = root / f"{name}.cbsimple"
                    source_path.write_bytes(source_bytes)
                    staging_root = root / f"{name}-staging"
                    staging_root.mkdir()
                    request = reader_api.ParseRequest(
                        source_path=source_path,
                        source_content_hash=hashlib.sha256(
                            source_bytes
                        ).hexdigest(),
                        validation_mode="balanced",
                        canonical_parameters={},
                        staging_root=staging_root,
                        progress=lambda _event: None,
                        is_cancelled=lambda: False,
                    )
                    with self.assertRaisesRegex(
                        ValueError,
                        f"^{re.escape(message)}$",
                    ):
                        plugin.parse(request)
                    self.assertEqual(tuple(staging_root.iterdir()), ())

    def test_registration_lifecycle_is_idempotent_and_missing_host_is_safe(self):
        registrations = []
        removals = []
        handle = SimpleNamespace(
            module_name="ChemBlender.reader_api",
            register_callback=registrations.append,
            unregister_callback=removals.append,
        )
        bpy = ModuleType("bpy")
        bpy.app = SimpleNamespace(
            driver_namespace={"chemblender.reader_api.v1": handle}
        )
        package_name = "_chemblender_example_extension_test"
        spec = importlib.util.spec_from_file_location(
            package_name,
            BOOTSTRAP,
            submodule_search_locations=[str(EXAMPLE)],
        )
        package = importlib.util.module_from_spec(spec)
        previous = sys.modules.get("bpy")
        sys.modules["bpy"] = bpy
        sys.modules[package_name] = package
        try:
            spec.loader.exec_module(package)
            package.register()
            package.register()
            self.assertEqual(len(registrations), 1)
            self.assertEqual(
                registrations[0].manifest.plugin_id,
                "org.chemblender.example.simplecoords",
            )
            package.unregister()
            package.unregister()
            self.assertEqual(removals, [registrations[0].manifest])

            bpy.app.driver_namespace.clear()
            package.register()
            self.assertEqual(len(registrations), 1)
        finally:
            sys.modules.pop(package_name, None)
            sys.modules.pop(package_name + ".reader", None)
            if previous is None:
                sys.modules.pop("bpy", None)
            else:
                sys.modules["bpy"] = previous

    def test_product_preflight_preserves_external_source_identity(self):
        plugin = load_reader().create_plugin(reader_api)
        registry = reader_api.ReaderPluginRegistry((plugin,))
        source = ImportSource(FIXTURE)
        request = ImportRequest(
            sources=(source,),
            reader_overrides=(
                ReaderOverride(source.id, plugin.descriptor.reader_id),
            ),
        )
        with TemporaryDirectory() as temporary:
            session = StagedImportSession.create(temp_parent=Path(temporary))
            try:
                preview = preflight_reader_plugins(
                    request,
                    registry,
                    session,
                    canonical_parameters_by_source={
                        source.id: {"encoding": "utf-8"},
                    },
                )
                batch = session.result(preview.staged_batch_ids[0])
            finally:
                session.discard()

        self.assertEqual(batch.structures[0].atomic_numbers, (8, 1, 1))
        self.assertEqual(
            batch.source_revisions[0].reader_plugin_id,
            "org.chemblender.example.simplecoords",
        )
        self.assertEqual(
            batch.source_revisions[0].reader_id,
            "simplecoords",
        )


if __name__ == "__main__":
    unittest.main()
