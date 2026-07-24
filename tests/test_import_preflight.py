import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from ChemBlender.core import (
    DiagnosticSeverity,
    ImportBatch,
    IssueKind,
    ParserIssue,
    ParserReport,
    QCProject,
    source_parse_identity,
)
from ChemBlender.core.cube import CUBE_READER
from ChemBlender.core.import_pipeline import (
    ImportCancelled,
    ImportRequest,
    ImportSource,
    ReaderOverride,
    StagedImportSession,
    preflight_import,
)
from ChemBlender.core.readers import (
    ReaderAvailability,
    ReaderDescriptor,
    ReaderRegistry,
    ReaderRuntimeDescriptor,
    SniffMatch,
    SniffResult,
)
from ChemBlender.core.xyz import XYZ_READER


FIXTURES = Path(__file__).parent / "fixtures"


def fake_descriptor(reader_id, parse, *, sniff=None, priority=0):
    return ReaderDescriptor(
        reader_id=reader_id,
        reader_version="1",
        extensions=(".dat",),
        capabilities={},
        priority=priority,
        sniff=sniff
        or (lambda path, prefix: SniffResult(SniffMatch.EXACT, "fixture")),
        parse=parse,
    )


class ImportPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.sessions = []

    def tearDown(self):
        for session in reversed(self.sessions):
            if session.root.exists():
                session.discard()
        self.temporary.cleanup()

    def session(self):
        session = StagedImportSession.create(temp_parent=self.root)
        self.sessions.append(session)
        return session

    def copy_fixture(self, relative, name=None):
        source = FIXTURES / relative
        target = self.root / (name or source.name)
        target.write_bytes(source.read_bytes())
        return target

    def test_xyz_and_cube_preview_stage_sources_without_committing(self):
        xyz = self.copy_fixture(Path("xyz") / "water.xyz")
        cube = self.copy_fixture(Path("cube") / "sheared.cube")
        request = ImportRequest(
            sources=(ImportSource(xyz), ImportSource(cube)),
        )
        session = self.session()
        project = QCProject(id=uuid4(), schema_version="0.2")

        preview = preflight_import(
            request,
            ReaderRegistry((XYZ_READER, CUBE_READER)),
            session,
        )

        self.assertEqual(
            tuple(row.selected_reader_id for row in preview.source_previews),
            ("xyz", "cube"),
        )
        self.assertEqual(
            tuple(row.content_hash for row in preview.source_previews),
            (
                hashlib.sha256(xyz.read_bytes()).hexdigest(),
                hashlib.sha256(cube.read_bytes()).hexdigest(),
            ),
        )
        self.assertEqual(
            tuple(row.byte_size for row in preview.source_previews),
            (xyz.stat().st_size, cube.stat().st_size),
        )
        self.assertIn("structure", preview.source_previews[0].capabilities)
        self.assertIn("grid", preview.source_previews[1].capabilities)
        self.assertEqual(len(preview.staged_batch_ids), 2)
        self.assertEqual(project.sources, {})
        self.assertEqual(project.structures, {})

        for row in preview.source_previews:
            self.assertEqual(len(row.staged_batch_ids), 1)
            batch = session.result(row.staged_batch_ids[0])
            self.assertEqual(batch.sources[0].id, row.source_id)
            revision = batch.source_revisions[0]
            self.assertEqual(revision.source_id, row.source_id)
            self.assertEqual(revision.content_hash, row.content_hash)
            self.assertEqual(revision.byte_size, row.byte_size)
            self.assertEqual(revision.reader_id, row.selected_reader_id)
            self.assertEqual(
                revision.diagnostic_ids,
                tuple(item.id for item in batch.diagnostics),
            )
            self.assertEqual(revision.reader_plugin_id, "chemblender.builtin")
            self.assertEqual(revision.reader_api_version, "0.1")
            self.assertEqual(revision.locator, str(row.source_path))
            self.assertEqual(
                revision.parse_identity,
                source_parse_identity(
                    row.content_hash,
                    "chemblender.builtin",
                    row.selected_reader_id,
                    revision.reader_version,
                    (
                        ("execution_mode", "built_in"),
                        ("reader_override", None),
                        ("source_content_state", "verified"),
                        ("validation_mode", "balanced"),
                    ),
                ),
            )
            self.assertFalse(
                any(
                    item.severity is DiagnosticSeverity.ERROR
                    for item in batch.diagnostics
                )
            )
            project.commit(batch)

    def test_optional_unavailable_reader_is_reported_before_parse(self):
        source = self.root / "optional.dat"
        source.write_bytes(b"optional")
        calls = []
        descriptor = fake_descriptor(
            "optional",
            lambda path: calls.append(path) or ImportBatch(),
        )
        runtime = ReaderRuntimeDescriptor(
            descriptor=descriptor,
            plugin_id="example.optional",
            api_version="0.1",
            execution_mode="extension",
            availability=lambda: ReaderAvailability(
                available=False,
                execution_mode="extension",
                reason_code="dependency_unavailable",
                detail="example dependency is missing",
            ),
        )

        preview = preflight_import(
            ImportRequest(sources=(ImportSource(source),)),
            ReaderRegistry((runtime,)),
            self.session(),
        )

        batch = self.sessions[-1].result(preview.staged_batch_ids[0])
        self.assertEqual(calls, [])
        self.assertEqual(
            tuple(item.code for item in batch.diagnostics),
            ("preflight.reader_unavailable",),
        )
        self.assertEqual(
            batch.source_revisions[0].diagnostic_ids,
            (batch.diagnostics[0].id,),
        )

    def test_reader_override_selects_by_source_id(self):
        source = self.root / "override.dat"
        source.write_bytes(b"content")
        first = fake_descriptor("first", lambda path: ImportBatch())
        second = fake_descriptor("second", lambda path: ImportBatch())
        imported = ImportSource(source)
        request = ImportRequest(
            sources=(imported,),
            reader_overrides=(
                ReaderOverride(source_id=imported.id, reader_id="second"),
            ),
        )

        preview = preflight_import(
            request,
            ReaderRegistry((first, second)),
            self.session(),
        )

        row = preview.source_previews[0]
        batch = self.sessions[-1].result(row.staged_batch_ids[0])
        self.assertEqual(row.selected_reader_id, "second")
        self.assertEqual(batch.source_revisions[0].reader_id, "second")

    def test_wrong_extension_uses_content_selection(self):
        source = self.copy_fixture(Path("xyz") / "water.xyz", "water.cube")

        preview = preflight_import(
            ImportRequest(sources=(ImportSource(source),)),
            ReaderRegistry((XYZ_READER, CUBE_READER)),
            self.session(),
        )

        self.assertEqual(preview.source_previews[0].selected_reader_id, "xyz")

    def test_parser_issues_become_bidirectional_diagnostics(self):
        source = self.root / "issue.dat"
        source.write_bytes(b"issue")
        descriptor = fake_descriptor(
            "issues",
            lambda path: ImportBatch(
                report=ParserReport(
                    reader_id="issues",
                    reader_version="1",
                    created_entity_ids=(),
                    parsed_capabilities=(),
                    issues=(
                        ParserIssue(
                            IssueKind.WARNING,
                            "record.value",
                            "value was normalized",
                        ),
                    ),
                )
            ),
        )

        preview = preflight_import(
            ImportRequest(sources=(ImportSource(source),)),
            ReaderRegistry((descriptor,)),
            self.session(),
        )

        batch = self.sessions[-1].result(preview.staged_batch_ids[0])
        diagnostic = batch.diagnostics[0]
        revision = batch.source_revisions[0]
        self.assertEqual(diagnostic.code, "issues.warning")
        self.assertEqual(diagnostic.source_revision_id, revision.id)
        self.assertEqual(revision.diagnostic_ids, (diagnostic.id,))
        self.assertEqual(preview.diagnostic_ids, (diagnostic.id,))

    def test_selection_and_parse_failures_are_staged_with_stable_codes(self):
        sources = []
        cases = (
            ("unknown.dat", ReaderRegistry(), "preflight.reader_not_found"),
            (
                "parse.dat",
                ReaderRegistry(
                    (
                        fake_descriptor(
                            "broken",
                            lambda path: (_ for _ in ()).throw(
                                ValueError("invalid source")
                            ),
                        ),
                    )
                ),
                "preflight.parse_failed",
            ),
        )
        for name, registry, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                source = self.root / name
                source.write_bytes(b"content")
                sources.append(source)
                session = self.session()

                preview = preflight_import(
                    ImportRequest(sources=(ImportSource(source),)),
                    registry,
                    session,
                )

                batch = session.result(preview.staged_batch_ids[0])
                self.assertEqual(batch.diagnostics[0].code, expected_code)
                self.assertEqual(
                    batch.diagnostics[0].source_revision_id,
                    batch.source_revisions[0].id,
                )

    def test_ambiguous_selection_has_stable_code(self):
        ambiguous = self.root / "ambiguous.dat"
        ambiguous.write_bytes(b"ambiguous")
        session = self.session()

        preview = preflight_import(
            ImportRequest(sources=(ImportSource(ambiguous),)),
            ReaderRegistry(
                (
                    fake_descriptor("alpha", lambda path: ImportBatch()),
                    fake_descriptor("beta", lambda path: ImportBatch()),
                )
            ),
            session,
        )

        batch = session.result(preview.staged_batch_ids[0])
        self.assertEqual(
            batch.diagnostics[0].code,
            "preflight.reader_ambiguous",
        )

    def test_expected_availability_probe_failures_have_stable_code(self):
        for index, error in enumerate(
            (ImportError("dependency probe failed"), OSError("worker probe failed"))
        ):
            with self.subTest(error_type=type(error).__name__):
                source = self.root / f"availability-{index}.dat"
                source.write_bytes(b"availability")

                def fail_availability(error=error):
                    raise error

                registry = ReaderRegistry(
                    (
                        ReaderRuntimeDescriptor(
                            descriptor=fake_descriptor(
                                f"availability-{index}",
                                lambda path: ImportBatch(),
                            ),
                            execution_mode="extension",
                            availability=fail_availability,
                        ),
                    )
                )
                session = self.session()
                preview = preflight_import(
                    ImportRequest(sources=(ImportSource(source),)),
                    registry,
                    session,
                )
                batch = session.result(preview.staged_batch_ids[0])
                self.assertEqual(
                    batch.diagnostics[0].code,
                    "preflight.reader_availability_failed",
                )

    def test_availability_runtime_error_is_not_converted_to_diagnostic(self):
        source = self.root / "availability-runtime.dat"
        source.write_bytes(b"availability")

        def fail_availability():
            raise RuntimeError("availability implementation bug")

        session = self.session()
        with self.assertRaises(RuntimeError):
            preflight_import(
                ImportRequest(sources=(ImportSource(source),)),
                ReaderRegistry(
                    (
                        ReaderRuntimeDescriptor(
                            descriptor=fake_descriptor(
                                "availability-runtime",
                                lambda path: ImportBatch(),
                            ),
                            availability=fail_availability,
                        ),
                    )
                ),
                session,
            )
        self.assertEqual(session.result_ids, ())

    def test_source_removed_after_request_is_preserved_as_invalid_metadata(self):
        source = self.root / "removed.dat"
        source.write_bytes(b"content")
        request = ImportRequest(sources=(ImportSource(source),))
        source.unlink()
        session = self.session()

        preview = preflight_import(request, ReaderRegistry(), session)

        batch = session.result(preview.staged_batch_ids[0])
        self.assertEqual(batch.sources[0].id, request.sources[0].id)
        self.assertEqual(
            batch.diagnostics[0].code,
            "preflight.source_unavailable",
        )
        missing_revision = batch.source_revisions[0]
        empty = self.root / "empty.dat"
        empty.write_bytes(b"")
        empty_session = self.session()
        empty_preview = preflight_import(
            ImportRequest(sources=(ImportSource(empty),)),
            ReaderRegistry(),
            empty_session,
        )
        empty_revision = empty_session.result(
            empty_preview.staged_batch_ids[0]
        ).source_revisions[0]
        self.assertNotEqual(
            missing_revision.content_hash,
            empty_revision.content_hash,
        )
        self.assertNotEqual(
            missing_revision.parse_identity,
            empty_revision.parse_identity,
        )
        QCProject(id=uuid4(), schema_version="0.2").commit(batch)

    def test_hash_reads_are_bounded(self):
        source = self.root / "large.dat"
        source.write_bytes(b"x" * 200_000)
        descriptor = fake_descriptor("bounded", lambda path: ImportBatch())
        read_sizes = []
        original_open = Path.open

        class Monitored:
            def __init__(self, stream):
                self.stream = stream

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return self.stream.__exit__(*args)

            def read(self, size=-1):
                read_sizes.append(size)
                return self.stream.read(size)

        def monitored_open(path, *args, **kwargs):
            stream = original_open(path, *args, **kwargs)
            if Path(path) == source and "b" in (args[0] if args else kwargs.get("mode", "r")):
                return Monitored(stream)
            return stream

        with patch.object(Path, "open", monitored_open):
            preflight_import(
                ImportRequest(sources=(ImportSource(source),)),
                ReaderRegistry((descriptor,)),
                self.session(),
            )

        self.assertTrue(read_sizes)
        self.assertTrue(all(0 < size <= 65536 for size in read_sizes))

    def test_file_change_during_parse_becomes_invalid_staged_result(self):
        source = self.root / "changing.dat"
        source.write_bytes(b"before")

        def mutate(path):
            path.write_bytes(b"after")
            return ImportBatch()

        preview = preflight_import(
            ImportRequest(sources=(ImportSource(source),)),
            ReaderRegistry((fake_descriptor("changing", mutate),)),
            self.session(),
        )

        batch = self.sessions[-1].result(preview.staged_batch_ids[0])
        self.assertEqual(
            tuple(item.code for item in batch.diagnostics),
            ("preflight.source_changed",),
        )

    def test_multi_source_progress_is_monotonic_and_cancel_is_caller_atomic(self):
        paths = []
        for index in range(2):
            path = self.root / f"{index}.dat"
            path.write_bytes(str(index).encode("ascii"))
            paths.append(path)
        request = ImportRequest(
            sources=tuple(ImportSource(path) for path in paths),
        )
        registry = ReaderRegistry(
            (fake_descriptor("reader", lambda path: ImportBatch()),)
        )
        project = QCProject(id=uuid4(), schema_version="0.2")
        session = self.session()
        events = []

        with self.assertRaises(ImportCancelled):
            preflight_import(
                request,
                registry,
                session,
                progress=lambda stage, completed, total: events.append(
                    (stage, completed, total)
                ),
                is_cancelled=lambda: bool(events and events[-1][1] >= 3),
            )

        self.assertEqual(project.sources, {})
        self.assertEqual(len(session.result_ids), 1)
        self.assertEqual(
            [completed for _, completed, _ in events],
            sorted(completed for _, completed, _ in events),
        )
        self.assertEqual({total for _, _, total in events}, {6})
        root = session.root
        session.discard()
        self.assertFalse(root.exists())

    def test_terminal_progress_cancellation_never_returns_preview(self):
        cases = (
            (
                "success",
                ReaderRegistry(
                    (fake_descriptor("success", lambda path: ImportBatch()),)
                ),
                "parse",
            ),
            ("reader-error", ReaderRegistry(), "reader_error"),
        )
        for name, registry, terminal_stage in cases:
            with self.subTest(name=name):
                source = self.root / f"{name}.dat"
                source.write_bytes(b"content")
                session = self.session()
                cancelled = [False]
                events = []
                project = QCProject(id=uuid4(), schema_version="0.2")

                def progress(stage, completed, total):
                    events.append((stage, completed, total))
                    if completed == total:
                        cancelled[0] = True

                with self.assertRaises(ImportCancelled):
                    preflight_import(
                        ImportRequest(sources=(ImportSource(source),)),
                        registry,
                        session,
                        progress=progress,
                        is_cancelled=lambda: cancelled[0],
                    )

                self.assertEqual(events[-1][0], terminal_stage)
                self.assertEqual(len(session.result_ids), 1)
                self.assertEqual(project.sources, {})

    def test_fatal_exceptions_are_not_converted_to_diagnostics(self):
        source = self.root / "fatal.dat"
        source.write_bytes(b"fatal")
        descriptor = fake_descriptor(
            "fatal",
            lambda path: (_ for _ in ()).throw(MemoryError("fatal")),
        )
        session = self.session()

        with self.assertRaises(MemoryError):
            preflight_import(
                ImportRequest(sources=(ImportSource(source),)),
                ReaderRegistry((descriptor,)),
                session,
            )

        self.assertEqual(session.result_ids, ())

    def test_reader_programming_errors_are_not_converted_to_diagnostics(self):
        cases = (
            (
                "sniff",
                ReaderRegistry(
                    (
                        fake_descriptor(
                            "sniff-bug",
                            lambda path: ImportBatch(),
                            sniff=lambda path, prefix: (_ for _ in ()).throw(
                                AssertionError("sniff bug")
                            ),
                        ),
                    )
                ),
                AssertionError,
            ),
            (
                "availability",
                ReaderRegistry(
                    (
                        ReaderRuntimeDescriptor(
                            descriptor=fake_descriptor(
                                "availability-bug",
                                lambda path: ImportBatch(),
                            ),
                            availability=lambda: (_ for _ in ()).throw(
                                TypeError("availability bug")
                            ),
                        ),
                    )
                ),
                TypeError,
            ),
            (
                "parse",
                ReaderRegistry(
                    (
                        fake_descriptor(
                            "parse-bug",
                            lambda path: (_ for _ in ()).throw(
                                AssertionError("parse bug")
                            ),
                        ),
                    )
                ),
                AssertionError,
            ),
            (
                "parse-runtime",
                ReaderRegistry(
                    (
                        fake_descriptor(
                            "parse-runtime-bug",
                            lambda path: (_ for _ in ()).throw(
                                RuntimeError("parse implementation bug")
                            ),
                        ),
                    )
                ),
                RuntimeError,
            ),
        )
        for name, registry, error_type in cases:
            with self.subTest(name=name):
                source = self.root / f"{name}.dat"
                source.write_bytes(b"content")
                session = self.session()
                with self.assertRaises(error_type):
                    preflight_import(
                        ImportRequest(sources=(ImportSource(source),)),
                        registry,
                        session,
                    )
                self.assertEqual(session.result_ids, ())

    def test_requires_exact_contract_types(self):
        source = self.root / "source.dat"
        source.write_bytes(b"content")
        request = ImportRequest(sources=(ImportSource(source),))
        registry = ReaderRegistry(
            (fake_descriptor("reader", lambda path: ImportBatch()),)
        )
        session = self.session()

        for arguments in (
            (object(), registry, session),
            (request, object(), session),
            (request, registry, object()),
        ):
            with self.subTest(arguments=arguments):
                with self.assertRaises(TypeError):
                    preflight_import(*arguments)


if __name__ == "__main__":
    unittest.main()
