import hashlib
import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

import numpy

from ChemBlender.core import (
    ArrayData,
    CapabilitySupport,
    ImportBatch,
    QCProject,
    ReaderDescriptor,
    SourceRecord,
    SourceRevision,
    Structure,
    create_session,
    source_parse_identity,
)
from ChemBlender.core.import_pipeline import (
    ImportCancelled,
    ImportCommitDecisions,
    ImportRequest,
    ImportSource,
    ReaderOverride,
    StagedImportSession,
    ValidationMode,
    commit_import_preview,
)
from ChemBlender.reader_api import (
    ExecutionMode,
    PublicImportBatch,
    PublicReaderDescriptor,
    ReaderAvailability,
    ReaderManifestEntry,
    ReaderPluginManifest,
    ReaderPluginRegistry,
    ProgressEvent,
    SniffMatch,
    SniffRequest,
    SniffResult,
    builtin_reader_plugin_registry,
)
from ChemBlender.reader_api.import_pipeline_bridge import preflight_reader_plugins
from ChemBlender.reader_api.registry import _builtin_manifest, _builtin_plugin
from ChemBlender.runtime.reader_api_bridge import (
    get_reader_plugin_registry,
    register_reader_api_handle,
    remove_reader_api_handle,
)


FIXTURES = Path(__file__).parent / "fixtures"


def _identity_parameters(mode, extra=()):
    return tuple(sorted(
        (("source_content_state", "verified"), ("validation_mode", mode), *extra)
    ))


def _parameter_hash(parameters):
    return hashlib.sha256(
        json.dumps(
            parameters,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


class _Plugin:
    def __init__(self, descriptor, result):
        self.descriptor = descriptor
        self.priority = 100
        self._result = result
        entry = ReaderManifestEntry(
            descriptor.reader_id,
            descriptor.reader_version,
            descriptor.extensions,
            ("structure",),
        )
        self.manifest = ReaderPluginManifest(
            "1",
            descriptor.plugin_id,
            descriptor.plugin_version,
            ">=1.0,<2.0",
            descriptor.execution_mode,
            ("SPDX:MIT",),
            (entry,),
        )

    def sniff(self, request):
        self.sniff_prefix_size = len(request.prefix)
        return SniffResult(SniffMatch.EXACT, "fixture")

    def parse(self, request):
        return self._result(request) if callable(self._result) else self._result


def _descriptor(reader_id="external-reader", *, availability=None):
    return PublicReaderDescriptor(
        plugin_id="org.example.reader",
        plugin_version="1.0",
        reader_id=reader_id,
        reader_version="1",
        execution_mode=ExecutionMode.EXTENSION,
        extensions=(".ext",),
        capabilities={"structure": CapabilitySupport.SUPPORTED},
        availability=availability
        or ReaderAvailability(True, "extension", "available", ""),
    )


class ReaderAPIImportBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.staged = []

    def tearDown(self):
        for session in self.staged:
            if session.root.exists():
                session.discard()
        self.temporary.cleanup()

    def test_product_bridge_stages_inline_smiles_with_semantic_locator(self):
        session = StagedImportSession.create(temp_parent=self.root)
        self.staged.append(session)
        request = ImportRequest((ImportSource.smiles_text("CCO ethanol\n"),))

        preview = preflight_reader_plugins(
            request, builtin_reader_plugin_registry(), session
        )

        batch = session.result(preview.staged_batch_ids[0])
        revision, = batch.source_revisions
        self.assertEqual(revision.reader_id, "smiles")
        self.assertEqual(revision.locator, "inline:smiles")
        self.assertEqual(revision.locator_kind, "inline_text")
        self.assertNotIn(str(session.artifact_root), revision.locator)

    def test_product_bridge_repeated_inline_smiles_commits_distinct_entities(self):
        session = StagedImportSession.create(temp_parent=self.root)
        self.staged.append(session)
        first_preview = preflight_reader_plugins(
            ImportRequest((ImportSource.smiles_text("CCO ethanol\n"),)),
            builtin_reader_plugin_registry(), session,
        )
        second_preview = preflight_reader_plugins(
            ImportRequest((ImportSource.smiles_text("CCO ethanol\n"),)),
            builtin_reader_plugin_registry(), session,
        )
        first = session.result(first_preview.staged_batch_ids[0])
        second = session.result(second_preview.staged_batch_ids[0])
        self.assertNotEqual(first.structures[0].id, second.structures[0].id)
        self.assertNotEqual(first.molecular_records[0].id, second.molecular_records[0].id)
        self.assertEqual(first.provenance[0].source_hash, first.source_revisions[0].content_hash)
        self.assertEqual(second.provenance[0].source_hash, second.source_revisions[0].content_hash)
        project = QCProject(id=uuid4(), schema_version="1.0")
        project.commit(first)
        project.commit(second)

    def session(self):
        session = StagedImportSession.create(temp_parent=self.root)
        self.staged.append(session)
        return session

    def request(self, path, *, override=None):
        source = ImportSource(path)
        overrides = (
            ()
            if override is None
            else (ReaderOverride(source.id, override),)
        )
        return ImportRequest(
            (source,),
            ValidationMode.BALANCED,
            overrides,
        )

    def test_requires_exact_contracts_and_safe_canonical_parameters(self):
        source = self.root / "source.ext"
        source.write_bytes(b"fixture")
        request = self.request(source)
        registry = ReaderPluginRegistry()
        session = self.session()

        for arguments in (
            (object(), registry, session),
            (request, object(), session),
            (request, registry, object()),
        ):
            with self.subTest(arguments=arguments):
                with self.assertRaises(TypeError):
                    preflight_reader_plugins(*arguments)
        for parameters in (
            {request.sources[0].id: {"validation_mode": "strict"}},
            {request.sources[0].id: {"source_content_state": "changed"}},
            {request.sources[0].id: {"bad key": "value"}},
            {uuid4(): {"encoding": "utf-8"}},
        ):
            with self.subTest(parameters=parameters):
                with self.assertRaises((TypeError, ValueError)):
                    preflight_reader_plugins(
                        request,
                        registry,
                        session,
                        canonical_parameters_by_source=parameters,
                    )

    def test_local_reader_parameters_cannot_synthesize_pubchem_provenance(self):
        source = self.root / "local.ext"
        source.write_bytes(b"local reader fixture")
        request = self.request(source)
        content_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        session = self.session()

        preview = preflight_reader_plugins(
            request,
            ReaderPluginRegistry((
                _Plugin(_descriptor(), PublicImportBatch()),
            )),
            session,
            canonical_parameters_by_source={
                request.sources[0].id: {
                    "legacy_source_url": (
                        "https://pubchem.ncbi.nlm.nih.gov/rest/pug/"
                        "compound/cid/2244/SDF"
                    ),
                    "legacy_source_sha256": content_hash,
                }
            },
        )

        batch = session.result(preview.staged_batch_ids[0])
        self.assertFalse(
            any(item.operation == "pubchem_import" for item in batch.provenance)
        )

    def test_deferred_extxyz_with_canonical_parameters_keeps_its_identity(self):
        source = FIXTURES / "extxyz" / "multiframe-cell.extxyz"
        request = self.request(source)
        content_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        session = self.session()

        preview = preflight_reader_plugins(
            request,
            builtin_reader_plugin_registry(),
            session,
            canonical_parameters_by_source={
                request.sources[0].id: {
                    "legacy_source_url": (
                        "https://pubchem.ncbi.nlm.nih.gov/rest/pug/"
                        "compound/cid/2244/SDF"
                    ),
                    "legacy_source_sha256": content_hash,
                }
            },
        )
        result_id, = preview.staged_batch_ids
        preview_batch = session.result(result_id)

        self.assertTrue(session.has_pending_materializer(result_id))
        self.assertFalse(
            any(
                item.operation == "pubchem_import"
                for item in preview_batch.provenance
            )
        )
        materialized = session.materialize_result(result_id)
        self.assertEqual(
            tuple(item.id for item in materialized.provenance),
            tuple(item.id for item in preview_batch.provenance),
        )

    def test_external_identity_is_preserved_through_runtime_registration(self):
        source_path = self.root / "source.ext"
        source_path.write_bytes(b"external")
        request = self.request(source_path, override="external-reader")
        request_source_id = request.sources[0].id
        source_id = uuid4()
        self.assertNotEqual(source_id, request_source_id)
        content_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
        structure = Structure(
            id=uuid4(),
            revision="structure-r1",
            atomic_numbers=(1,),
            coordinates=ArrayData(
                numpy.asarray(((0.0, 0.0, 0.0),)),
                ("atom", "xyz"),
                "angstrom",
            ),
        )
        parameters = _identity_parameters(
            "balanced", (("encoding", "utf-8"),)
        )
        descriptor = _descriptor()
        source = SourceRecord(
            source_id,
            source_path.name,
            "local_file",
            "2026-07-25T00:00:00Z",
        )
        revision_template = SourceRevision(
            uuid4(),
            source_id,
            content_hash,
            len(source_path.read_bytes()),
            str(source_path.resolve()),
            "absolute_path",
            source_path.name,
            descriptor.plugin_id,
            descriptor.reader_id,
            descriptor.reader_version,
            "1.0-rc1",
            _parameter_hash(parameters),
            source_parse_identity(
                content_hash,
                descriptor.plugin_id,
                descriptor.reader_id,
                descriptor.reader_version,
                parameters,
            ),
            (structure.id,),
            (),
        )
        captured = {}

        def matching_result(parse_request):
            revision = replace(
                revision_template,
                id=parse_request.source_revision_id,
            )
            public = PublicImportBatch(
                sources=(source,),
                source_revisions=(revision,),
                structures=(structure,),
            )
            captured.update(revision=revision, public=public)
            return public

        plugin = _Plugin(descriptor, matching_result)
        namespace = {}
        handle = register_reader_api_handle(
            "synthetic.chemblender", namespace=namespace
        )
        handle.register_callback(plugin)
        try:
            registry = get_reader_plugin_registry()
            session = self.session()
            preview = preflight_reader_plugins(
                request,
                registry,
                session,
                canonical_parameters_by_source={
                    request_source_id: {"encoding": "utf-8"}
                },
            )
            staged = session.result(preview.staged_batch_ids[0])
            revision = captured["revision"]
            public = captured["public"]

            self.assertIs(staged.sources[0], source)
            self.assertIs(staged.source_revisions[0], revision)
            self.assertEqual(preview.source_previews[0].source_id, source_id)
            self.assertEqual(staged.structures, (structure,))
            project_session = create_session(temp_parent=self.root)
            try:
                committed = commit_import_preview(
                    project_session,
                    session,
                    preview,
                    ImportCommitDecisions(),
                )
                self.assertIn(source_id, committed.project.sources)
                self.assertNotIn(
                    request_source_id,
                    committed.project.sources,
                )
            finally:
                from ChemBlender.core import close_session

                close_session(project_session)

            for invalid_result in (
                lambda parse_request: replace(
                    public,
                    source_revisions=(),
                ),
                lambda parse_request: replace(
                    public,
                    source_revisions=(
                        replace(
                            revision,
                            id=parse_request.source_revision_id,
                            original_filename="wrong.ext",
                        ),
                    ),
                ),
            ):
                plugin._result = invalid_result
                invalid_session = self.session()
                invalid_preview = preflight_reader_plugins(
                    request,
                    registry,
                    invalid_session,
                    canonical_parameters_by_source={
                        request_source_id: {"encoding": "utf-8"}
                    },
                )
                invalid_batch = invalid_session.result(
                    invalid_preview.staged_batch_ids[0]
                )
                self.assertEqual(invalid_batch.structures, ())
                self.assertEqual(
                    invalid_batch.diagnostics[0].code,
                    "preflight.invalid_reader_result",
                )

            plugin._result = lambda parse_request: replace(
                captured["public"],
                source_revisions=(
                    replace(
                        captured["revision"],
                        id=uuid4(),
                    ),
                ),
            )
            mismatched_session = self.session()
            mismatched_preview = preflight_reader_plugins(
                request,
                registry,
                mismatched_session,
                canonical_parameters_by_source={
                    request_source_id: {"encoding": "utf-8"}
                },
            )
            mismatched = mismatched_session.result(
                mismatched_preview.staged_batch_ids[0]
            )
            self.assertEqual(mismatched.structures, ())
            self.assertEqual(
                mismatched.diagnostics[0].code,
                "external-reader.invalid",
            )
        finally:
            handle.unregister_callback(plugin.manifest)
            remove_reader_api_handle(handle, namespace=namespace)
        self.assertNotIn(
            descriptor.reader_id,
            tuple(item.reader_id for item in get_reader_plugin_registry().descriptors),
        )

    def test_external_scientific_result_without_identity_is_invalid(self):
        source = self.root / "source.ext"
        source.write_bytes(b"fixture")
        structure = Structure(
            id=uuid4(),
            revision="structure-r1",
            atomic_numbers=(1,),
            coordinates=ArrayData(
                numpy.asarray(((0.0, 0.0, 0.0),)),
                ("atom", "xyz"),
                "angstrom",
            ),
        )
        registry = ReaderPluginRegistry(
            (_Plugin(_descriptor(), PublicImportBatch(structures=(structure,))),)
        )
        session = self.session()

        preview = preflight_reader_plugins(
            self.request(source),
            registry,
            session,
        )
        staged = session.result(preview.staged_batch_ids[0])

        self.assertEqual(staged.structures, ())
        self.assertEqual(
            tuple(item.code for item in staged.diagnostics),
            ("preflight.invalid_reader_result",),
        )

    def test_invalid_reader_result_removes_its_staging_artifacts(self):
        source = self.root / "source.ext"
        source.write_bytes(b"fixture")
        structure = Structure(
            id=uuid4(),
            revision="structure-r1",
            atomic_numbers=(1,),
            coordinates=ArrayData(
                numpy.asarray(((0.0, 0.0, 0.0),)),
                ("atom", "xyz"),
                "angstrom",
            ),
        )

        def invalid_result(request):
            (request.staging_root / "orphan.bin").write_bytes(b"orphan")
            return PublicImportBatch(structures=(structure,))

        session = self.session()
        preview = preflight_reader_plugins(
            self.request(source),
            ReaderPluginRegistry((
                _Plugin(_descriptor(), invalid_result),
            )),
            session,
        )
        staged = session.result(preview.staged_batch_ids[0])

        self.assertEqual(staged.structures, ())
        self.assertEqual(
            tuple(item.code for item in staged.diagnostics),
            ("preflight.invalid_reader_result",),
        )
        self.assertEqual(tuple(session.artifact_root.iterdir()), ())

    def test_sniff_prefix_is_bounded_and_cancellation_is_typed(self):
        source = self.root / "source.ext"
        source.write_bytes(b"x" * 70000)
        plugin = _Plugin(_descriptor(), PublicImportBatch())
        registry = ReaderPluginRegistry((plugin,))
        session = self.session()
        progress = []

        preflight_reader_plugins(
            self.request(source),
            registry,
            session,
            progress=lambda stage, completed, total: progress.append(
                (stage, completed, total)
            ),
        )

        self.assertEqual(plugin.sniff_prefix_size, 65536)
        self.assertEqual(
            progress,
            (
                [
                    ("preflight", 0, 3),
                    ("hash", 1, 3),
                    ("reader", 2, 3),
                    ("reader.source_hash", 0, 1),
                    ("reader.source_hash", 1, 1),
                    ("reader.parse", 0, 1),
                    ("reader.source_recheck", 0, 1),
                    ("reader.source_recheck", 1, 1),
                    ("reader.parse", 1, 1),
                    ("parse", 3, 3),
                ]
            ),
        )
        cancelled_session = self.session()
        with self.assertRaises(ImportCancelled):
            preflight_reader_plugins(
                self.request(source),
                registry,
                cancelled_session,
                is_cancelled=lambda: True,
            )
        self.assertEqual(cancelled_session.result_ids, ())
        with self.assertRaises(TypeError):
            preflight_reader_plugins(
                self.request(source),
                registry,
                self.session(),
                is_cancelled=lambda: 1,
            )

    def test_snapshot_cancellation_callback_preserves_host_boundaries(self):
        source = self.root / "source.ext"
        source.write_bytes(b"fixture")
        cases = (
            (
                OSError("snapshot cancellation failed"),
                OSError,
                "snapshot cancellation failed",
            ),
            (
                RuntimeError("snapshot callback failed"),
                RuntimeError,
                "snapshot callback failed",
            ),
            (MemoryError("fatal snapshot failure"), MemoryError, "fatal"),
            (1, TypeError, "is_cancelled must return bool"),
            (True, ImportCancelled, "import preflight was cancelled"),
        )
        for callback_result, error_type, message in cases:
            with self.subTest(error_type=error_type):
                calls = 0
                session = self.session()

                def stateful_cancel():
                    nonlocal calls
                    calls += 1
                    if calls == 1:
                        return False
                    if isinstance(callback_result, Exception):
                        raise callback_result
                    return callback_result

                with self.assertRaisesRegex(error_type, message):
                    preflight_reader_plugins(
                        self.request(source),
                        ReaderPluginRegistry(),
                        session,
                        is_cancelled=stateful_cancel,
                    )
                self.assertEqual(session.result_ids, ())

    def test_selection_unavailability_and_parse_failures_are_staged(self):
        source = self.root / "source.ext"
        source.write_bytes(b"fixture")
        cases = (
            (
                ReaderPluginRegistry(),
                "preflight.reader_not_found",
            ),
            (
                ReaderPluginRegistry((
                    _Plugin(
                        _descriptor(
                            availability=ReaderAvailability(
                                False,
                                "extension",
                                "dependency_missing",
                                "optional package is missing",
                            )
                        ),
                        PublicImportBatch(),
                    ),
                )),
                "preflight.reader_unavailable",
            ),
        )
        for registry, code in cases:
            with self.subTest(code=code):
                session = self.session()
                preview = preflight_reader_plugins(
                    self.request(source), registry, session
                )
                batch = session.result(preview.staged_batch_ids[0])
                self.assertEqual(
                    tuple(item.code for item in batch.diagnostics),
                    (code,),
                )

        class BrokenPlugin(_Plugin):
            def parse(self, request):
                raise RuntimeError("broken")

        session = self.session()
        preview = preflight_reader_plugins(
            self.request(source),
            ReaderPluginRegistry((
                BrokenPlugin(_descriptor(), PublicImportBatch()),
            )),
            session,
        )
        batch = session.result(preview.staged_batch_ids[0])
        self.assertEqual(batch.diagnostics[0].field_path, "reader.parse")
        self.assertIn("RuntimeError", batch.diagnostics[0].message)

    def test_source_recheck_failure_discards_plugin_success(self):
        source = self.root / "source.ext"
        source.write_bytes(b"fixture")

        class MutatingPlugin(_Plugin):
            def parse(self, request):
                request.source_path.write_bytes(b"changed")
                return PublicImportBatch()

        session = self.session()
        preview = preflight_reader_plugins(
            self.request(source),
            ReaderPluginRegistry((
                MutatingPlugin(_descriptor(), PublicImportBatch()),
            )),
            session,
        )
        batch = session.result(preview.staged_batch_ids[0])

        self.assertEqual(len(preview.staged_batch_ids), 1)
        self.assertEqual(batch.structures, ())
        self.assertEqual(batch.diagnostics[0].field_path, "reader.source")
        self.assertIn("changed", batch.diagnostics[0].message)

    def test_hash_and_sniff_prefix_share_one_source_open(self):
        source = self.root / "source.ext"
        source.write_bytes(b"fixture")
        source = source.resolve()
        source_opens = 0
        opens_at_sniff = []
        original_open = Path.open

        class ObservingPlugin(_Plugin):
            def sniff(self, request):
                opens_at_sniff.append(source_opens)
                return super().sniff(request)

        def tracking_open(path, *args, **kwargs):
            nonlocal source_opens
            if path == source and args and args[0] == "rb":
                source_opens += 1
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", tracking_open):
            preflight_reader_plugins(
                self.request(source),
                ReaderPluginRegistry((
                    ObservingPlugin(_descriptor(), PublicImportBatch()),
                )),
                self.session(),
            )

        self.assertEqual(opens_at_sniff, [1])

    def test_source_deleted_after_sniff_is_staged_as_changed(self):
        source = self.root / "source.ext"
        source.write_bytes(b"fixture")

        class DeletingPlugin(_Plugin):
            def sniff(self, request):
                result = super().sniff(request)
                request.source_path.unlink()
                return result

        session = self.session()
        preview = preflight_reader_plugins(
            self.request(source),
            ReaderPluginRegistry((
                DeletingPlugin(_descriptor(), PublicImportBatch()),
            )),
            session,
        )
        batch = session.result(preview.staged_batch_ids[0])

        self.assertEqual(
            tuple(item.code for item in batch.diagnostics),
            ("preflight.source_changed",),
        )

    def test_source_replaced_by_directory_after_sniff_is_staged_as_changed(self):
        source = self.root / "source.ext"
        source.write_bytes(b"fixture")

        class ReplacingPlugin(_Plugin):
            def sniff(self, request):
                result = super().sniff(request)
                request.source_path.unlink()
                request.source_path.mkdir()
                return result

        session = self.session()
        preview = preflight_reader_plugins(
            self.request(source),
            ReaderPluginRegistry((
                ReplacingPlugin(_descriptor(), PublicImportBatch()),
            )),
            session,
        )
        batch = session.result(preview.staged_batch_ids[0])

        self.assertEqual(
            tuple(item.code for item in batch.diagnostics),
            ("preflight.source_changed",),
        )

    def test_one_shot_cancellation_inside_plugin_parse_is_typed(self):
        source = self.root / "source.ext"
        source.write_bytes(b"fixture")

        class CancellingPlugin(_Plugin):
            parsing = False

            def parse(self, request):
                self.parsing = True
                (request.staging_root / "orphan.bin").write_bytes(b"orphan")
                request.is_cancelled()
                return PublicImportBatch()

        plugin = CancellingPlugin(_descriptor(), PublicImportBatch())
        session = self.session()
        cancelled = False

        def one_shot_cancel():
            nonlocal cancelled
            if plugin.parsing and not cancelled:
                cancelled = True
                return True
            return False

        with self.assertRaises(ImportCancelled):
            preflight_reader_plugins(
                self.request(source),
                ReaderPluginRegistry((plugin,)),
                session,
                is_cancelled=one_shot_cancel,
            )
        self.assertEqual(session.result_ids, ())
        self.assertEqual(tuple(session.artifact_root.iterdir()), ())

    def test_terminal_cancellation_rolls_back_successful_reader_artifacts(self):
        source = FIXTURES / "extxyz" / "multiframe-cell.extxyz"
        session = self.session()
        checks_before_terminal = None

        def progress(stage, completed, total):
            nonlocal checks_before_terminal
            if stage == "reader.parse" and completed == total == 1:
                checks_before_terminal = 2

        def cancel_at_terminal_check():
            nonlocal checks_before_terminal
            if checks_before_terminal is None:
                return False
            if checks_before_terminal:
                checks_before_terminal -= 1
                return False
            return True

        with self.assertRaises(ImportCancelled):
            preflight_reader_plugins(
                self.request(source),
                builtin_reader_plugin_registry(),
                session,
                progress=progress,
                is_cancelled=cancel_at_terminal_check,
            )

        self.assertEqual(session.result_ids, ())
        self.assertEqual(tuple(session.artifact_root.iterdir()), ())

    @unittest.skipUnless(os.name == "nt", "Windows file ownership regression")
    def test_terminal_cancellation_releases_memmap_backed_memoryview(self):
        source = self.root / "memoryview.synthetic"
        source.write_bytes(b"memoryview")
        session = self.session()
        checks_before_terminal = None

        def parse(request):
            array_path = request.staging_root / "coordinates.npy"
            numpy.save(array_path, numpy.zeros((1, 3)))
            mapped = numpy.load(array_path, mmap_mode="r")
            structures = tuple(
                Structure(
                    id=uuid4(),
                    revision=f"structure-{index}-r1",
                    atomic_numbers=(1,),
                    coordinates=ArrayData(
                        values,
                        ("atom", "xyz"),
                        "angstrom",
                    ),
                )
                for index, values in enumerate((
                    memoryview(mapped),
                    memoryview(mapped.view(numpy.ndarray)),
                ))
            )
            return ImportBatch(structures=structures)

        descriptor = ReaderDescriptor(
            reader_id="memoryview",
            reader_version="1",
            extensions=(".synthetic",),
            capabilities={"structure": CapabilitySupport.SUPPORTED},
            priority=100,
            sniff=lambda path, prefix: SniffResult(
                SniffMatch.EXACT, "fixture"
            ),
            parse=lambda path: ImportBatch(),
            parse_request=parse,
        )
        registry = ReaderPluginRegistry((
            _builtin_plugin(
                descriptor,
                _builtin_manifest((descriptor,)),
            ),
        ))

        def progress(stage, completed, total):
            nonlocal checks_before_terminal
            if stage == "reader.parse" and completed == total == 1:
                checks_before_terminal = 2

        def cancel_at_terminal_check():
            nonlocal checks_before_terminal
            if checks_before_terminal is None:
                return False
            if checks_before_terminal:
                checks_before_terminal -= 1
                return False
            return True

        with self.assertRaises(ImportCancelled):
            preflight_reader_plugins(
                self.request(source),
                registry,
                session,
                progress=progress,
                is_cancelled=cancel_at_terminal_check,
            )

        self.assertEqual(session.result_ids, ())
        self.assertEqual(tuple(session.artifact_root.iterdir()), ())

    def test_host_callback_failures_escape_plugin_failure_staging(self):
        source = self.root / "source.ext"
        source.write_bytes(b"fixture")

        class ProgressPlugin(_Plugin):
            def parse(self, request):
                request.progress(ProgressEvent("decode", 1, 2))
                return PublicImportBatch()

        progress_registry = ReaderPluginRegistry((
            ProgressPlugin(_descriptor(), PublicImportBatch()),
        ))
        progress_session = self.session()

        def failing_progress(stage, completed, total):
            if stage == "reader.decode":
                raise OSError("host progress failed")

        with self.assertRaisesRegex(OSError, "host progress failed"):
            preflight_reader_plugins(
                self.request(source),
                progress_registry,
                progress_session,
                progress=failing_progress,
            )
        self.assertIsNone(progress_registry._last_parse_exception_type)
        self.assertEqual(progress_session.result_ids, ())

        class CancellationPlugin(_Plugin):
            parsing = False

            def parse(self, request):
                self.parsing = True
                request.is_cancelled()
                return PublicImportBatch()

        callback_cases = (
            (
                RuntimeError("host cancellation failed"),
                RuntimeError,
                "host cancellation failed",
            ),
            (1, TypeError, "is_cancelled must return bool"),
        )
        for callback_result, error_type, message in callback_cases:
            with self.subTest(error_type=error_type):
                plugin = CancellationPlugin(
                    _descriptor(), PublicImportBatch()
                )
                registry = ReaderPluginRegistry((plugin,))
                session = self.session()

                def stateful_cancel():
                    if not plugin.parsing:
                        return False
                    if isinstance(callback_result, Exception):
                        raise callback_result
                    return callback_result

                with self.assertRaisesRegex(error_type, message):
                    preflight_reader_plugins(
                        self.request(source),
                        registry,
                        session,
                        is_cancelled=stateful_cancel,
                    )
                self.assertIsNone(registry._last_parse_exception_type)
                self.assertEqual(session.result_ids, ())

    def test_host_attachment_value_error_propagates_once_without_reader_retry(self):
        source = self.root / "source.ext"
        source.write_bytes(b"fixture")
        session = self.session()
        sentinel = ValueError("host attachment sentinel")
        calls = []

        def attach(source, content_hash, batch):
            calls.append((source, content_hash, batch))
            raise sentinel

        with self.assertRaises(ValueError) as raised:
            preflight_reader_plugins(
                self.request(source),
                ReaderPluginRegistry((
                    _Plugin(_descriptor(), PublicImportBatch()),
                )),
                session,
                _batch_attachment=attach,
            )

        self.assertIs(raised.exception, sentinel)
        self.assertEqual(len(calls), 1)
        self.assertEqual(session.result_ids, ())
        self.assertEqual(tuple(session.artifact_root.iterdir()), ())

    def test_host_attachment_rejects_empty_or_replaced_science_batches(self):
        source = self.root / "source.ext"
        source.write_bytes(b"fixture")
        structure = Structure(
            id=uuid4(),
            revision="structure-r1",
            atomic_numbers=(1,),
            coordinates=ArrayData(
                numpy.asarray(((0.0, 0.0, 0.0),)),
                ("atom", "xyz"),
                "angstrom",
            ),
        )
        descriptor = ReaderDescriptor(
            reader_id="host-contract",
            reader_version="1",
            extensions=(".ext",),
            capabilities={"structure": CapabilitySupport.SUPPORTED},
            priority=100,
            sniff=lambda _path, _prefix: SniffResult(
                SniffMatch.EXACT,
                "fixture",
            ),
            parse=lambda _path: ImportBatch(),
            parse_request=lambda _request: ImportBatch(
                structures=(structure,),
            ),
        )
        registry = ReaderPluginRegistry((
            _builtin_plugin(descriptor, _builtin_manifest((descriptor,))),
        ))
        for name, mutate in (
            ("empty", lambda _batch: ImportBatch()),
            ("science", lambda batch: replace(batch, structures=())),
        ):
            with self.subTest(attachment=name):
                session = self.session()
                with self.assertRaises(ValueError) as raised:
                    preflight_reader_plugins(
                        self.request(source),
                        registry,
                        session,
                        _batch_attachment=lambda _source, _hash, batch: mutate(
                            batch
                        ),
                    )
                self.assertEqual(
                    getattr(raised.exception, "code", None),
                    "preflight.host_attachment_contract",
                )
                self.assertEqual(session.result_ids, ())
                self.assertEqual(tuple(session.artifact_root.iterdir()), ())

    def test_host_attachment_rejects_reader_report_replacement(self):
        session = self.session()

        with self.assertRaises(ValueError) as raised:
            preflight_reader_plugins(
                self.request(FIXTURES / "xyz" / "water.xyz"),
                builtin_reader_plugin_registry(),
                session,
                _batch_attachment=lambda _source, _hash, batch: replace(
                    batch,
                    report=None,
                ),
            )

        self.assertEqual(
            getattr(raised.exception, "code", None),
            "preflight.host_attachment_contract",
        )
        self.assertEqual(session.result_ids, ())
        self.assertEqual(tuple(session.artifact_root.iterdir()), ())

    def test_deferred_invalid_reader_candidate_does_not_call_host_attachment(self):
        source = self.root / "source.ext"
        source.write_bytes(b"fixture")
        preview_structure = Structure(
            id=uuid4(),
            revision="preview-r1",
            atomic_numbers=(1,),
            coordinates=ArrayData(
                numpy.asarray(((0.0, 0.0, 0.0),)),
                ("atom", "xyz"),
                "angstrom",
            ),
        )
        materialized_structure = replace(
            preview_structure,
            id=uuid4(),
            revision="materialized-r1",
        )

        def preview(request):
            (request.staging_root / "preview.marker").write_bytes(b"preview")
            return ImportBatch(structures=(preview_structure,))

        descriptor = ReaderDescriptor(
            reader_id="deferred-host-contract",
            reader_version="1",
            extensions=(".ext",),
            capabilities={"structure": CapabilitySupport.SUPPORTED},
            priority=100,
            sniff=lambda _path, _prefix: SniffResult(
                SniffMatch.EXACT,
                "fixture",
            ),
            parse=lambda _path: ImportBatch(),
            preview_request=preview,
            materialize_request=lambda _request: ImportBatch(
                structures=(materialized_structure,),
            ),
        )
        session = self.session()
        calls = []
        preview_result = preflight_reader_plugins(
            self.request(source),
            ReaderPluginRegistry((
                _builtin_plugin(descriptor, _builtin_manifest((descriptor,))),
            )),
            session,
            _batch_attachment=lambda _source, _hash, batch: calls.append(
                batch
            ) or batch,
        )
        result_id, = preview_result.staged_batch_ids

        with self.assertRaisesRegex(ValueError, "materialized reader result changed"):
            session.materialize_result(result_id)

        self.assertEqual(len(calls), 1)

    @unittest.skipUnless(os.name == "nt", "Windows file ownership regression")
    def test_host_attachment_exception_releases_memmap_artifacts_once(self):
        source = self.root / "memoryview.synthetic"
        source.write_bytes(b"memoryview")
        session = self.session()
        sentinel = ValueError("host attachment memmap sentinel")
        calls = []

        def parse(request):
            array_path = request.staging_root / "coordinates.npy"
            numpy.save(array_path, numpy.zeros((1, 3)))
            mapped = numpy.load(array_path, mmap_mode="r")
            return ImportBatch(
                structures=(
                    Structure(
                        id=uuid4(),
                        revision="structure-r1",
                        atomic_numbers=(1,),
                        coordinates=ArrayData(
                            memoryview(mapped),
                            ("atom", "xyz"),
                            "angstrom",
                        ),
                    ),
                ),
            )

        descriptor = ReaderDescriptor(
            reader_id="attachment-memoryview",
            reader_version="1",
            extensions=(".synthetic",),
            capabilities={"structure": CapabilitySupport.SUPPORTED},
            priority=100,
            sniff=lambda _path, _prefix: SniffResult(
                SniffMatch.EXACT,
                "fixture",
            ),
            parse=lambda _path: ImportBatch(),
            parse_request=parse,
        )

        def attach(source, content_hash, batch):
            calls.append((source, content_hash, batch))
            raise sentinel

        with self.assertRaises(ValueError) as raised:
            preflight_reader_plugins(
                self.request(source),
                ReaderPluginRegistry((
                    _builtin_plugin(descriptor, _builtin_manifest((descriptor,))),
                )),
                session,
                _batch_attachment=attach,
            )

        self.assertIs(raised.exception, sentinel)
        self.assertEqual(len(calls), 1)
        self.assertEqual(session.result_ids, ())
        self.assertEqual(tuple(session.artifact_root.iterdir()), ())

    def test_forged_builtin_metadata_cannot_bypass_external_identity(self):
        source = self.root / "source.ext"
        source.write_bytes(b"fixture")
        structure = Structure(
            id=uuid4(),
            revision="structure-r1",
            atomic_numbers=(1,),
            coordinates=ArrayData(
                numpy.asarray(((0.0, 0.0, 0.0),)),
                ("atom", "xyz"),
                "angstrom",
            ),
        )
        descriptor = PublicReaderDescriptor(
            plugin_id="chemblender.builtin",
            plugin_version="2.3.0",
            reader_id="forged",
            reader_version="1",
            execution_mode=ExecutionMode.BUILT_IN,
            extensions=(".ext",),
            capabilities={"structure": CapabilitySupport.SUPPORTED},
            availability=ReaderAvailability(
                True, "built_in", "available", ""
            ),
        )
        session = self.session()

        preview = preflight_reader_plugins(
            self.request(source),
            ReaderPluginRegistry((
                _Plugin(
                    descriptor,
                    PublicImportBatch(structures=(structure,)),
                ),
            )),
            session,
        )
        batch = session.result(preview.staged_batch_ids[0])

        self.assertEqual(batch.structures, ())
        self.assertEqual(
            batch.diagnostics[0].code,
            "preflight.invalid_reader_result",
        )

    def test_builtin_xyz_and_cube_stage_without_project_mutation(self):
        project = QCProject(uuid4(), "0.2")
        registry = builtin_reader_plugin_registry()
        for relative in ("xyz/water.xyz", "cube/sheared.cube"):
            with self.subTest(relative=relative):
                session = self.session()
                preview = preflight_reader_plugins(
                    self.request(FIXTURES / relative),
                    registry,
                    session,
                )
                batch = session.result(preview.staged_batch_ids[0])
                self.assertTrue(batch.structures)
                self.assertEqual(project.structures, {})
                self.assertEqual(len(batch.sources), 1)
                self.assertEqual(len(batch.source_revisions), 1)
                if relative.endswith(".cube"):
                    self.assertTrue(batch.datasets)
                    grid = batch.datasets[0]
                    self.assertEqual(grid.data.values.shape, (2, 2, 2))

    def test_builtin_cube_bridge_preserves_grid_and_array_identity(self):
        source = FIXTURES / "cube/sheared.cube"
        registry = builtin_reader_plugin_registry()
        selected = registry.select(
            SniffRequest(source, source.read_bytes()[:65536])
        )
        plugin = registry._plugin(selected.reader_id)
        internal = plugin.core_descriptor.parse(source)
        fixed_plugin = replace(
            plugin,
            core_descriptor=replace(
                plugin.core_descriptor,
                parse=lambda path: internal,
            ),
        )
        session = self.session()

        preview = preflight_reader_plugins(
            self.request(source),
            ReaderPluginRegistry((fixed_plugin,)),
            session,
        )
        staged = session.result(preview.staged_batch_ids[0])

        self.assertIs(staged.structures[0], internal.structures[0])
        self.assertIs(staged.datasets[0], internal.datasets[0])
        self.assertIs(
            staged.datasets[0].data.values,
            internal.datasets[0].data.values,
        )

    def test_builtin_preview_commits_only_after_confirmation(self):
        for relative in ("xyz/water.xyz", "cube/sheared.cube"):
            source = FIXTURES / relative
            session = self.session()
            preview = preflight_reader_plugins(
                self.request(source),
                builtin_reader_plugin_registry(),
                session,
            )
            project_session = create_session(temp_parent=self.root)
            try:
                self.assertEqual(project_session.project.structures, {})
                result = commit_import_preview(
                    project_session,
                    session,
                    preview,
                    ImportCommitDecisions(),
                )
                self.assertTrue(result.project.structures)
                if relative.endswith(".cube"):
                    self.assertTrue(result.project.datasets)
            finally:
                from ChemBlender.core import close_session

                close_session(project_session)


if __name__ == "__main__":
    unittest.main()
