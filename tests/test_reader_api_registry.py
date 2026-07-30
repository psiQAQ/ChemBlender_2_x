import ast
import hashlib
import sys
import unittest
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from tempfile import TemporaryDirectory
from types import MappingProxyType
from uuid import uuid4

import numpy

from ChemBlender.core import (
    CapabilitySupport,
    SniffMatch,
    SniffResult,
    builtin_reader_registry,
)
from ChemBlender.reader_api import (
    ExecutionMode,
    ArrayData,
    DatasetStatus,
    Grid3D,
    IssueKind,
    ParseRequest,
    ParserIssue,
    ParserReport,
    ProgressEvent,
    PropertyDataset,
    ProvenanceRecord,
    PublicImportBatch,
    PublicReaderDescriptor,
    ReaderAvailability,
    ReaderManifestEntry,
    ReaderPlugin,
    ReaderPluginManifest,
    ReaderPluginRegistry,
    SniffRequest,
    builtin_reader_plugin_registry,
)


FIXTURES = Path(__file__).parent / "fixtures"


def available(mode="extension"):
    return ReaderAvailability(True, mode, "available", "")


def public_descriptor(
    reader_id,
    *,
    plugin_id="org.example.reader",
    extensions=(".dat",),
    availability=None,
):
    return PublicReaderDescriptor(
        plugin_id=plugin_id,
        plugin_version="1.0",
        reader_id=reader_id,
        reader_version="1",
        execution_mode=ExecutionMode.EXTENSION,
        extensions=extensions,
        capabilities={"structure": CapabilitySupport.SUPPORTED},
        availability=availability or available(),
    )


def manifest_for(descriptor, **changes):
    values = {
        "schema_version": "1",
        "plugin_id": descriptor.plugin_id,
        "plugin_version": descriptor.plugin_version,
        "chemblender_api": ">=1.0,<2.0",
        "execution_mode": descriptor.execution_mode,
        "license": ("SPDX:MIT",),
        "readers": (
            ReaderManifestEntry(
                descriptor.reader_id,
                descriptor.reader_version,
                descriptor.extensions,
                tuple(
                    name
                    for name, support in descriptor.capabilities.items()
                    if support is CapabilitySupport.SUPPORTED
                ),
            ),
        ),
    }
    values.update(changes)
    return ReaderPluginManifest(**values)


class FixedPlugin:
    def __init__(
        self,
        descriptor,
        *,
        match=SniffMatch.EXACT,
        priority=0,
        sniff_error=None,
        parse_error=None,
        result=None,
        manifest=None,
    ):
        self.descriptor = descriptor
        self.manifest = manifest or manifest_for(descriptor)
        self.priority = priority
        self._match = match
        self._sniff_error = sniff_error
        self._parse_error = parse_error
        self._result = result or PublicImportBatch()

    def sniff(self, request):
        if self._sniff_error is not None:
            raise self._sniff_error
        return SniffResult(self._match, self.descriptor.reader_id)

    def parse(self, request):
        if self._parse_error is not None:
            raise self._parse_error
        return self._result


class ReaderAPIRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "source.dat"
        self.source.write_bytes(b"fixture")

    def tearDown(self):
        self.temporary.cleanup()

    def sniff_request(self, source=None):
        source = source or self.source
        return SniffRequest(source, source.read_bytes())

    def parse_request(self, source=None, **changes):
        source = source or self.source
        values = {
            "source_path": source,
            "source_content_hash": hashlib.sha256(source.read_bytes()).hexdigest(),
            "validation_mode": "balanced",
            "canonical_parameters": {"encoding": "utf-8"},
            "staging_root": self.root,
            "progress": lambda event: None,
            "is_cancelled": lambda: False,
            "source_revision_id": uuid4(),
        }
        values.update(changes)
        return ParseRequest(**values)

    def test_request_and_progress_contracts_are_frozen_and_canonical(self):
        request = self.parse_request()
        event = ProgressEvent("parse", 1, 2, "reading")

        self.assertEqual(request.source_path, self.source.resolve())
        self.assertEqual(request.staging_root, self.root.resolve())
        self.assertEqual(request.validation_mode, "balanced")
        self.assertIs(type(request.source_revision_id), type(uuid4()))
        self.assertIs(type(request.canonical_parameters), MappingProxyType)
        self.assertEqual(dict(request.canonical_parameters), {"encoding": "utf-8"})
        self.assertEqual((event.stage, event.completed, event.total), ("parse", 1, 2))
        for value, field in (
            (request, "validation_mode"),
            (event, "stage"),
            (self.sniff_request(), "prefix"),
        ):
            with self.assertRaises(FrozenInstanceError):
                setattr(value, field, None)

    def test_parse_request_rejects_unsafe_or_noncanonical_fields(self):
        cases = (
            {"source_content_hash": "not-a-hash"},
            {"validation_mode": "guess"},
            {"canonical_parameters": {"bad key": "value"}},
            {"canonical_parameters": {"key": object()}},
            {"progress": None},
            {"is_cancelled": None},
            {"staging_root": self.source},
            {"source_revision_id": "not-a-uuid"},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                with self.assertRaises((TypeError, ValueError)):
                    self.parse_request(**changes)

    def test_protocol_is_structural_and_registry_rejects_duplicates(self):
        plugin = FixedPlugin(public_descriptor("example"))
        self.assertIsInstance(plugin, ReaderPlugin)

        registry = ReaderPluginRegistry((plugin,))
        with self.assertRaises(ValueError):
            registry.register(plugin)

    def test_registration_requires_exact_consistent_manifest(self):
        descriptor = public_descriptor("example")
        cases = []
        missing = FixedPlugin(descriptor)
        del missing.manifest
        cases.append(missing)
        wrong_type = FixedPlugin(descriptor)
        wrong_type.manifest = object()
        cases.append(wrong_type)
        cases.extend(
            (
                FixedPlugin(
                    descriptor,
                    manifest=manifest_for(
                        descriptor,
                        plugin_id="org.example.other",
                    ),
                ),
                FixedPlugin(
                    descriptor,
                    manifest=manifest_for(
                        descriptor,
                        plugin_version="2.0",
                    ),
                ),
                FixedPlugin(
                    descriptor,
                    manifest=manifest_for(
                        descriptor,
                        execution_mode=ExecutionMode.WORKER,
                    ),
                ),
                FixedPlugin(
                    descriptor,
                    manifest=manifest_for(
                        descriptor,
                        readers=(
                            ReaderManifestEntry(
                                "other",
                                "1",
                                (".dat",),
                                ("structure",),
                            ),
                        ),
                    ),
                ),
                FixedPlugin(
                    descriptor,
                    manifest=manifest_for(
                        descriptor,
                        readers=(
                            ReaderManifestEntry(
                                "example",
                                "2",
                                (".dat",),
                                ("structure",),
                            ),
                        ),
                    ),
                ),
                FixedPlugin(
                    descriptor,
                    manifest=manifest_for(
                        descriptor,
                        readers=(
                            ReaderManifestEntry(
                                "example",
                                "1",
                                (".other",),
                                ("structure",),
                            ),
                        ),
                    ),
                ),
                FixedPlugin(
                    descriptor,
                    manifest=manifest_for(
                        descriptor,
                        readers=(
                            ReaderManifestEntry(
                                "example",
                                "1",
                                (".dat",),
                                ("grid",),
                            ),
                        ),
                    ),
                ),
            )
        )

        for plugin in cases:
            with self.subTest(plugin=plugin):
                with self.assertRaises((TypeError, ValueError)):
                    ReaderPluginRegistry((plugin,))

    def test_manifest_lists_only_supported_runtime_capabilities(self):
        descriptor = PublicReaderDescriptor(
            plugin_id="org.example.reader",
            plugin_version="1.0",
            reader_id="example",
            reader_version="1",
            execution_mode=ExecutionMode.EXTENSION,
            extensions=(".dat",),
            capabilities={
                "structure": CapabilitySupport.SUPPORTED,
                "grid": CapabilitySupport.PARTIAL,
                "topology": CapabilitySupport.UNSUPPORTED,
            },
            availability=available(),
        )
        plugin = FixedPlugin(descriptor)

        ReaderPluginRegistry((plugin,))

        self.assertEqual(plugin.manifest.readers[0].capabilities, ("structure",))
        self.assertEqual(
            descriptor.capabilities["grid"],
            CapabilitySupport.PARTIAL,
        )
        self.assertEqual(
            descriptor.capabilities["topology"],
            CapabilitySupport.UNSUPPORTED,
        )

    def test_plugin_id_uses_one_complete_manifest(self):
        first = public_descriptor("first", extensions=(".first",))
        second = public_descriptor("second", extensions=(".second",))
        entries = (
            ReaderManifestEntry("first", "1", (".first",), ("structure",)),
            ReaderManifestEntry("second", "1", (".second",), ("structure",)),
        )
        shared = manifest_for(first, readers=entries)

        registry = ReaderPluginRegistry(
            (
                FixedPlugin(first, manifest=shared),
                FixedPlugin(second, manifest=shared),
            )
        )
        self.assertEqual(
            tuple(item.reader_id for item in registry.descriptors),
            ("first", "second"),
        )

        conflicting_license = manifest_for(
            second,
            readers=entries,
            license=("SPDX:Apache-2.0",),
        )
        conflicting_readers = manifest_for(
            second,
            readers=entries
            + (
                ReaderManifestEntry(
                    "unused",
                    "1",
                    (".unused",),
                    ("structure",),
                ),
            ),
        )
        for conflict in (conflicting_license, conflicting_readers):
            with self.subTest(manifest=conflict):
                registry = ReaderPluginRegistry(
                    (FixedPlugin(first, manifest=shared),)
                )
                with self.assertRaises(ValueError):
                    registry.register(FixedPlugin(second, manifest=conflict))

        other = public_descriptor(
            "other",
            plugin_id="org.example.other",
            extensions=(".other",),
        )
        registry = ReaderPluginRegistry(
            (
                FixedPlugin(first, manifest=shared),
                FixedPlugin(other),
            )
        )
        self.assertEqual(len(registry.descriptors), 2)

    def test_unregister_requires_exact_complete_manifest_and_is_atomic(self):
        first = public_descriptor("first", extensions=(".first",))
        second = public_descriptor("second", extensions=(".second",))
        entries = (
            ReaderManifestEntry("first", "1", (".first",), ("structure",)),
            ReaderManifestEntry("second", "1", (".second",), ("structure",)),
        )
        manifest = manifest_for(first, readers=entries)
        registry = ReaderPluginRegistry(
            (
                FixedPlugin(first, manifest=manifest),
                FixedPlugin(second, manifest=manifest),
            )
        )
        wrong = manifest_for(
            first,
            readers=entries,
            license=("SPDX:Apache-2.0",),
        )

        with self.assertRaises(ValueError):
            registry.unregister(wrong)
        self.assertEqual(
            tuple(item.reader_id for item in registry.descriptors),
            ("first", "second"),
        )

        registry.unregister(manifest)
        self.assertEqual(registry.descriptors, ())
        with self.assertRaises(KeyError):
            registry.unregister(manifest)

    def test_runtime_handle_callbacks_protect_builtin_plugin_identity(self):
        from ChemBlender.reader_api.registry import builtin_reader_plugins
        from ChemBlender.runtime.reader_api_bridge import (
            refresh_reader_plugin_discovery,
            register_reader_api_handle,
            remove_reader_api_handle,
        )

        namespace = {}
        handle = register_reader_api_handle(
            "synthetic_repository.chemblender",
            namespace=namespace,
        )
        external = FixedPlugin(public_descriptor("external"))
        builtin = builtin_reader_plugins()[0]
        try:
            self.assertIs(type(handle.register_callback), type(lambda: None))
            self.assertIs(type(handle.unregister_callback), type(lambda: None))
            handle.register_callback(external)
            handle.unregister_callback(external.manifest)
            before = refresh_reader_plugin_discovery().descriptors
            failed = handle.register_callback(builtin)
            self.assertFalse(failed.availability.available)
            self.assertEqual(
                failed.availability.reason_code,
                "plugin_registration_failed",
            )
            self.assertEqual(
                refresh_reader_plugin_discovery().descriptors,
                before,
            )
            self.assertTrue(handle.unregister_callback(builtin.manifest))
            self.assertNotIn(
                failed,
                refresh_reader_plugin_discovery().plugins,
            )
        finally:
            remove_reader_api_handle(handle, namespace=namespace)

    def test_selection_matches_existing_xyz_and_cube_registry(self):
        registry = builtin_reader_plugin_registry()
        old = builtin_reader_registry()
        for relative in ("xyz/water.xyz", "cube/sheared.cube"):
            source = FIXTURES / relative
            selected = registry.select(
                SniffRequest(source, source.read_bytes()[:65536])
            )
            self.assertEqual(
                selected.reader_id,
                old.select(source).reader_id,
            )

    def test_builtin_bridge_exposes_all_reader_metadata_without_optional_imports(self):
        from ChemBlender.reader_api.registry import builtin_reader_plugins

        before = set(sys.modules)
        plugins = builtin_reader_plugins()
        registry = ReaderPluginRegistry(plugins)

        self.assertEqual(len(registry.descriptors), 19)
        self.assertEqual({id(plugin.manifest) for plugin in plugins}, {id(plugins[0].manifest)})
        self.assertEqual(plugins[0].manifest.schema_version, "1")
        self.assertEqual(plugins[0].manifest.chemblender_api, ">=1.0,<2.0")
        self.assertEqual(
            plugins[0].manifest.license,
            ("SPDX:GPL-3.0-or-later",),
        )
        self.assertEqual(len(plugins[0].manifest.readers), 19)
        self.assertEqual(
            {item.plugin_id for item in registry.descriptors},
            {"chemblender.builtin"},
        )
        self.assertEqual(
            {item.execution_mode for item in registry.descriptors},
            {ExecutionMode.BUILT_IN},
        )
        self.assertFalse(
            {"cclib", "iodata", "gbasis", "ase", "pymatgen"} & (set(sys.modules) - before)
        )

    def test_unavailable_reader_remains_selectable_but_parse_returns_failed_batch(self):
        descriptor = public_descriptor(
            "unavailable",
            availability=ReaderAvailability(
                False,
                "extension",
                "dependency_missing",
                "example_dependency",
            ),
        )
        registry = ReaderPluginRegistry((FixedPlugin(descriptor),))

        self.assertIs(
            registry.select(self.sniff_request(), "unavailable"),
            descriptor,
        )
        result = registry.parse("unavailable", self.parse_request())

        self.assertIs(type(result), PublicImportBatch)
        self.assertEqual(result.structures, ())
        self.assertEqual(result.report.reader_id, "unavailable")
        self.assertEqual(result.report.issues[0].path, "reader.availability")

    def test_sniff_exception_records_diagnostic_and_continues(self):
        broken_descriptor = public_descriptor("broken")
        winner_descriptor = public_descriptor("winner")
        shared_manifest = manifest_for(
            broken_descriptor,
            readers=(
                ReaderManifestEntry(
                    "broken",
                    "1",
                    (".dat",),
                    ("structure",),
                ),
                ReaderManifestEntry(
                    "winner",
                    "1",
                    (".dat",),
                    ("structure",),
                ),
            ),
        )
        broken = FixedPlugin(
            broken_descriptor,
            priority=100,
            sniff_error=RuntimeError("broken"),
            manifest=shared_manifest,
        )
        winner = FixedPlugin(
            winner_descriptor,
            match=SniffMatch.PROBABLE,
            manifest=shared_manifest,
        )
        registry = ReaderPluginRegistry((broken, winner))

        selected = registry.select(self.sniff_request())

        self.assertEqual(selected.reader_id, "winner")
        self.assertEqual(len(registry.last_sniff_diagnostics), 1)
        diagnostic = registry.last_sniff_diagnostics[0]
        self.assertEqual(diagnostic.path, "reader.sniff")
        self.assertIn("broken", diagnostic.message)
        self.assertNotIn("RuntimeError('broken')", diagnostic.message)
        registry.select(self.sniff_request(), "winner")
        self.assertEqual(registry.last_sniff_diagnostics, ())

    def test_sniff_memory_error_propagates_unchanged(self):
        error = MemoryError("fatal")
        registry = ReaderPluginRegistry(
            (
                FixedPlugin(
                    public_descriptor("fatal"),
                    sniff_error=error,
                ),
            )
        )

        with self.assertRaises(MemoryError) as caught:
            registry.select(self.sniff_request())

        self.assertIs(caught.exception, error)

    def test_parse_exception_returns_inspectable_failed_batch(self):
        plugin = FixedPlugin(
            public_descriptor("broken"),
            parse_error=RuntimeError("reader implementation failed"),
        )
        registry = ReaderPluginRegistry((plugin,))

        result = registry.parse("broken", self.parse_request())

        self.assertIs(type(result), PublicImportBatch)
        self.assertEqual(result.report.reader_id, "broken")
        self.assertEqual(result.report.reader_version, "1")
        self.assertEqual(result.report.created_entity_ids, ())
        self.assertEqual(result.report.issues[0].path, "reader.parse")
        self.assertIn("RuntimeError", result.report.issues[0].message)

    def test_parse_memory_error_propagates_unchanged(self):
        error = MemoryError("fatal")
        registry = ReaderPluginRegistry(
            (
                FixedPlugin(
                    public_descriptor("fatal"),
                    parse_error=error,
                ),
            )
        )

        with self.assertRaises(MemoryError) as caught:
            registry.parse("fatal", self.parse_request())

        self.assertIs(caught.exception, error)

    def test_invalid_exact_public_batches_become_stable_parse_failures(self):
        incomplete_grid = object.__new__(Grid3D)
        dangling_grid = Grid3D(
            id=uuid4(),
            revision="grid-r1",
            semantic_role="electron_density",
            domain="grid",
            data=ArrayData(
                numpy.zeros((1, 1, 1)),
                ("x", "y", "z"),
                "electron_per_cubic_angstrom",
            ),
            status=DatasetStatus.COMPLETE,
            source_calculation=None,
            provenance_ids=(),
            origin=(0.0, 0.0, 0.0),
            step_vectors=(
                (1.0, 0.0, 0.0),
                (0.0, 1.0, 0.0),
                (0.0, 0.0, 1.0),
            ),
            coordinate_unit="angstrom",
            structure_id=uuid4(),
        )
        report_mismatch = ParserReport(
            "invalid",
            "1",
            (uuid4(),),
            (),
            (),
        )
        provenance_values = (
            [],
            lambda: None,
        )
        batches = [
            PublicImportBatch(datasets=(incomplete_grid,)),
            PublicImportBatch(datasets=(dangling_grid,)),
            PublicImportBatch(report=report_mismatch),
        ]
        for value in provenance_values:
            batches.append(
                PublicImportBatch(
                    provenance=(
                        ProvenanceRecord(
                            id=uuid4(),
                            revision="provenance-r1",
                            producer="test",
                            producer_version="1",
                            source="source.dat",
                            source_hash="",
                            parent_ids=(),
                            operation="parse",
                            parameters=(("unsafe", value),),
                        ),
                    )
                )
            )

        for batch in batches:
            with self.subTest(batch=batch):
                plugin = FixedPlugin(
                    public_descriptor("invalid"),
                    result=batch,
                )
                registry = ReaderPluginRegistry((plugin,))

                result = registry.parse("invalid", self.parse_request())

                self.assertIsNot(result, batch)
                self.assertEqual(result.report.issues[0].path, "reader.parse")
                self.assertEqual(
                    result.report.issues[0].message,
                    "reader parse failed: PublicBatchValidationError",
                )
                self.assertEqual(
                    registry._last_parse_exception_type,
                    "PublicBatchValidationError",
                )

    def test_private_parse_exception_evidence_is_exact_and_resets(self):
        plugin = FixedPlugin(
            public_descriptor("broken"), parse_error=RuntimeError("failed")
        )
        registry = ReaderPluginRegistry((plugin,))

        registry.parse("broken", self.parse_request())
        self.assertEqual(registry._last_parse_exception_type, "RuntimeError")

        fabricated = PublicImportBatch(
            report=ParserReport(
                "broken",
                "1",
                (),
                (),
                (
                    ParserIssue(
                        IssueKind.INVALID,
                        "reader.parse",
                        "reader parse failed: Fabricated",
                    ),
                ),
            )
        )
        plugin._parse_error = None
        plugin._result = fabricated
        self.assertIs(registry.parse("broken", self.parse_request()), fabricated)
        self.assertIsNone(registry._last_parse_exception_type)

    def test_successful_parse_returns_exact_public_batch_and_reports_progress(self):
        events = []
        expected = PublicImportBatch()
        registry = ReaderPluginRegistry(
            (FixedPlugin(public_descriptor("example"), result=expected),)
        )

        result = registry.parse(
            "example",
            self.parse_request(progress=events.append),
        )

        self.assertIs(result, expected)
        self.assertEqual(
            [
                (event.stage, event.completed, event.total)
                for event in events
            ],
            [
                ("source_hash", 0, 1),
                ("source_hash", 1, 1),
                ("parse", 0, 1),
                ("source_recheck", 0, 1),
                ("source_recheck", 1, 1),
                ("parse", 1, 1),
            ],
        )

    def test_success_validation_preserves_public_batch_and_array_identity(self):
        values = numpy.asarray([1.0, 2.0, 3.0])
        expected = PublicImportBatch(
            datasets=(
                PropertyDataset(
                    id=uuid4(),
                    revision="property-r1",
                    semantic_role="test_values",
                    domain="test",
                    data=ArrayData(values, ("entry",), "dimensionless"),
                    status=DatasetStatus.COMPLETE,
                    source_calculation=None,
                    provenance_ids=(),
                ),
            )
        )
        registry = ReaderPluginRegistry(
            (FixedPlugin(public_descriptor("example"), result=expected),)
        )

        result = registry.parse("example", self.parse_request())

        self.assertIs(result, expected)
        self.assertIs(result.datasets[0].data.values, values)

    def test_builtin_xyz_and_cube_parse_return_exact_public_batches(self):
        registry = builtin_reader_plugin_registry()
        for relative in ("xyz/water.xyz", "cube/sheared.cube"):
            source = FIXTURES / relative
            selected = registry.select(
                SniffRequest(source, source.read_bytes()[:65536])
            )

            result = registry.parse(
                selected.reader_id,
                self.parse_request(source),
            )

            with self.subTest(relative=relative):
                self.assertIs(type(result), PublicImportBatch)
                self.assertTrue(result.structures)

    def test_registry_rejects_nonpublic_parse_result(self):
        plugin = FixedPlugin(public_descriptor("invalid"))
        plugin._result = object()
        registry = ReaderPluginRegistry((plugin,))

        result = registry.parse("invalid", self.parse_request())

        self.assertIs(type(result), PublicImportBatch)
        self.assertEqual(result.report.issues[0].path, "reader.parse")
        self.assertIn("TypeError", result.report.issues[0].message)

    def test_cancellation_is_checked_before_and_after_plugin_parse(self):
        calls = []
        expected = PublicImportBatch()

        class CountingPlugin(FixedPlugin):
            def parse(self, request):
                calls.append("parse")
                return expected

        registry = ReaderPluginRegistry(
            (CountingPlugin(public_descriptor("example")),)
        )
        before = registry.parse(
            "example",
            self.parse_request(is_cancelled=lambda: True),
        )
        checks = iter((False, False, True))
        after = registry.parse(
            "example",
            self.parse_request(is_cancelled=lambda: next(checks)),
        )

        self.assertEqual(calls, ["parse"])
        for result in (before, after):
            self.assertIsNot(result, expected)
            self.assertEqual(result.report.issues[0].path, "reader.parse")
            self.assertIn("cancel", result.report.issues[0].message)

    def test_cancellation_callback_must_return_exact_bool(self):
        registry = ReaderPluginRegistry(
            (FixedPlugin(public_descriptor("example")),)
        )

        with self.assertRaises(TypeError):
            registry.parse(
                "example",
                self.parse_request(is_cancelled=lambda: 1),
            )

    def test_source_hash_mismatch_fails_before_calling_plugin(self):
        calls = []

        class CountingPlugin(FixedPlugin):
            def parse(self, request):
                calls.append("parse")
                return PublicImportBatch()

        registry = ReaderPluginRegistry(
            (CountingPlugin(public_descriptor("example")),)
        )

        result = registry.parse(
            "example",
            self.parse_request(source_content_hash="0" * 64),
        )

        self.assertEqual(calls, [])
        self.assertEqual(result.report.issues[0].path, "reader.source")
        self.assertIn("hash mismatch", result.report.issues[0].message)

    def test_source_change_during_parse_discards_success(self):
        expected = PublicImportBatch()

        class MutatingPlugin(FixedPlugin):
            def parse(self, request):
                request.source_path.write_bytes(b"changed")
                return expected

        registry = ReaderPluginRegistry(
            (MutatingPlugin(public_descriptor("example")),)
        )

        result = registry.parse("example", self.parse_request())

        self.assertIsNot(result, expected)
        self.assertEqual(result.report.issues[0].path, "reader.source")
        self.assertIn("changed", result.report.issues[0].message)

    def test_hashing_checks_cancellation_before_plugin_parse(self):
        self.source.write_bytes(b"x" * 131072)
        calls = []
        checks = iter((False, False, True))

        class CountingPlugin(FixedPlugin):
            def parse(self, request):
                calls.append("parse")
                return PublicImportBatch()

        registry = ReaderPluginRegistry(
            (CountingPlugin(public_descriptor("example")),)
        )

        result = registry.parse(
            "example",
            self.parse_request(is_cancelled=lambda: next(checks)),
        )

        self.assertEqual(calls, [])
        self.assertEqual(result.report.issues[0].path, "reader.parse")
        self.assertIn("cancel", result.report.issues[0].message)

    def test_host_callback_errors_are_not_misreported_as_source_failures(self):
        registry = ReaderPluginRegistry(
            (FixedPlugin(public_descriptor("example")),)
        )

        with self.assertRaises(OSError):
            registry.parse(
                "example",
                self.parse_request(
                    progress=lambda event: (_ for _ in ()).throw(
                        OSError("host callback failed")
                    )
                ),
            )

    def test_public_contract_exposes_no_project_blender_or_callable_path(self):
        forbidden = {
            "project",
            "qcproject",
            "bpy",
            "context",
            "datablock",
            "module",
            "callable",
            "argv",
            "shell",
        }
        for contract in (SniffRequest, ParseRequest, ProgressEvent, PublicReaderDescriptor):
            names = {field.name.lower() for field in fields(contract)}
            self.assertFalse(names & forbidden, (contract, names & forbidden))

        root = Path(__file__).parents[1] / "ChemBlender" / "reader_api"
        for name in ("protocol.py", "registry.py"):
            tree = ast.parse((root / name).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported = {alias.name for alias in node.names}
                    self.assertFalse(
                        any(item.startswith(("ChemBlender", "bl_ext")) for item in imported)
                    )
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    self.assertFalse(
                        (node.module or "").startswith(("ChemBlender", "bl_ext"))
                    )


if __name__ == "__main__":
    unittest.main()
