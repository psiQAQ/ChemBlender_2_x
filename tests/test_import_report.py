import json
import tempfile
import unittest
from pathlib import Path
from uuid import UUID, uuid4

from ChemBlender.core.import_pipeline import (
    ImportPreview,
    SourcePreview,
    StagedImportSession,
    diagnostics_document,
    import_summary,
    render_diagnostics_markdown,
)
from ChemBlender.core.model import (
    DiagnosticSeverity,
    DiagnosticValue,
    ImportBatch,
    ImportDiagnostic,
    QualityStatus,
    SourceRecord,
    SourceRevision,
)


SOURCE_ID = UUID("20000000-0000-0000-0000-000000000001")
REVISION_ID = UUID("30000000-0000-0000-0000-000000000001")
BATCH_ID = UUID("40000000-0000-0000-0000-000000000001")
ENTITY_A = UUID("50000000-0000-0000-0000-000000000001")
ENTITY_B = UUID("50000000-0000-0000-0000-000000000002")


def diagnostic(
    suffix,
    severity,
    status,
    *,
    entity_id=None,
    source_revision_id=REVISION_ID,
    record_key=None,
    field_path="record.value",
    code="reader.issue",
    message="message",
    original_value=None,
    normalized_value=None,
):
    return ImportDiagnostic(
        id=UUID(f"60000000-0000-0000-0000-{suffix:012d}"),
        severity=severity,
        quality_status=status,
        source_revision_id=source_revision_id,
        record_key=record_key,
        entity_id=entity_id,
        field_path=field_path,
        code=code,
        message=message,
        original_value=original_value,
        normalized_value=normalized_value,
        recovery_action="recovered",
        scientific_consequence="review the result",
        suggested_action="inspect source",
    )


class ImportReportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source_path = (self.root / "source.xyz").resolve()
        self.source_path.write_text("1\nfixture\nH 0 0 0\n", encoding="utf-8")
        self.session = StagedImportSession.create(temp_parent=self.root)
        self.diagnostics = (
            diagnostic(
                5,
                DiagnosticSeverity.INFO,
                QualityStatus.COMPLETE,
                entity_id=None,
                record_key="z",
                field_path="line\nvalue",
                code="reader.info",
                message="safe | value",
                original_value=DiagnosticValue(
                    {"raw": [1, True, None], "label": "α"}
                ),
                normalized_value=DiagnosticValue({"value": 1.0}),
            ),
            diagnostic(
                4,
                DiagnosticSeverity.WARNING,
                QualityStatus.PARTIAL,
                entity_id=ENTITY_B,
                record_key="b",
                code="reader.partial",
            ),
            diagnostic(
                3,
                DiagnosticSeverity.WARNING,
                QualityStatus.AMBIGUOUS,
                entity_id=ENTITY_A,
                record_key="a",
                code="reader.ambiguous",
            ),
            diagnostic(
                2,
                DiagnosticSeverity.WARNING,
                QualityStatus.INCOMPLETE,
                entity_id=None,
                record_key=None,
                code="reader.incomplete",
            ),
            diagnostic(
                1,
                DiagnosticSeverity.ERROR,
                QualityStatus.INVALID,
                entity_id=ENTITY_A,
                record_key="invalid",
                code="reader.invalid",
            ),
        )
        self.register(self.diagnostics)

    def tearDown(self):
        self.session.discard()
        self.temporary.cleanup()

    def batch(self, diagnostics, *, revision_diagnostic_ids=None):
        diagnostic_ids = tuple(item.id for item in diagnostics)
        source = SourceRecord(
            id=SOURCE_ID,
            display_name="source.xyz",
            source_kind="file",
            created_at_utc="2026-07-24T00:00:00Z",
        )
        revision = SourceRevision(
            id=REVISION_ID,
            source_id=SOURCE_ID,
            content_hash="a" * 64,
            byte_size=self.source_path.stat().st_size,
            locator=str(self.source_path),
            locator_kind="absolute_path",
            original_filename=self.source_path.name,
            reader_plugin_id="builtin",
            reader_id="xyz",
            reader_version="1",
            reader_api_version="0.1",
            import_parameters_hash="b" * 64,
            parse_identity="c" * 64,
            created_entity_ids=(),
            diagnostic_ids=(
                diagnostic_ids
                if revision_diagnostic_ids is None
                else revision_diagnostic_ids
            ),
        )
        return ImportBatch(
            sources=(source,),
            source_revisions=(revision,),
            diagnostics=tuple(diagnostics),
        )

    def preview(self, diagnostic_ids=None, *, selected_reader_id="xyz"):
        ids = (
            tuple(item.id for item in self.diagnostics)
            if diagnostic_ids is None
            else diagnostic_ids
        )
        source_preview = SourcePreview(
            source_id=SOURCE_ID,
            source_path=self.source_path,
            selected_reader_id=selected_reader_id,
            content_hash="a" * 64,
            byte_size=self.source_path.stat().st_size,
            staged_batch_ids=(BATCH_ID,),
            diagnostic_ids=ids,
        )
        return ImportPreview(
            session_id=self.session.id,
            source_previews=(source_preview,),
            staged_batch_ids=(BATCH_ID,),
            diagnostic_ids=ids,
        )

    def register(self, diagnostics, *, revision_diagnostic_ids=None):
        self.session._results[BATCH_ID] = self.batch(
            diagnostics,
            revision_diagnostic_ids=revision_diagnostic_ids,
        )

    def test_summary_counts_diagnostics_by_quality_source_and_entity(self):
        summary = import_summary(self.preview(), self.session)

        expected_counts = {
            "complete": 1,
            "partial": 1,
            "ambiguous": 1,
            "incomplete": 1,
            "invalid": 1,
        }
        self.assertEqual(summary["overall"], expected_counts)
        self.assertEqual(
            summary["by_source"],
            [
                {
                    "source_id": str(SOURCE_ID),
                    "counts": expected_counts,
                }
            ],
        )
        self.assertEqual(
            summary["by_entity"],
            [
                {
                    "entity_id": str(ENTITY_A),
                    "counts": {
                        "complete": 0,
                        "partial": 0,
                        "ambiguous": 1,
                        "incomplete": 0,
                        "invalid": 1,
                    },
                },
                {
                    "entity_id": str(ENTITY_B),
                    "counts": {
                        "complete": 0,
                        "partial": 1,
                        "ambiguous": 0,
                        "incomplete": 0,
                        "invalid": 0,
                    },
                },
            ],
        )
        self.assertEqual(list(summary["overall"]), [
            "complete",
            "partial",
            "ambiguous",
            "incomplete",
            "invalid",
        ])

    def test_document_is_stable_and_restores_diagnostic_values(self):
        preview = self.preview()
        before = tuple(self.session._results.items())
        first = diagnostics_document(preview, self.session)
        self.assertEqual(tuple(self.session._results.items()), before)
        canonical = lambda value: json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )

        reversed_diagnostics = tuple(reversed(self.diagnostics))
        self.register(reversed_diagnostics)
        reversed_preview = self.preview(
            tuple(item.id for item in reversed_diagnostics)
        )
        second = diagnostics_document(reversed_preview, self.session)

        self.assertEqual(canonical(first), canonical(second))
        self.assertEqual(
            [item["severity"] for item in first["diagnostics"]],
            ["error", "warning", "warning", "warning", "info"],
        )
        info = first["diagnostics"][-1]
        self.assertEqual(
            info["original_value"],
            {"label": "α", "raw": [1, True, None]},
        )
        self.assertEqual(info["normalized_value"], {"value": 1.0})
        self.assertEqual(
            set(info),
            {
                "id",
                "severity",
                "quality_status",
                "source_revision_id",
                "source_id",
                "record_key",
                "entity_id",
                "field_path",
                "code",
                "message",
                "original_value",
                "normalized_value",
                "recovery_action",
                "scientific_consequence",
                "suggested_action",
            },
        )
        self.assertEqual(first["schema_name"], "chemblender_import_report")
        self.assertEqual(first["schema_version"], 1)
        self.assertEqual(
            render_diagnostics_markdown(first),
            render_diagnostics_markdown(second),
        )

    def test_markdown_consumes_document_and_escapes_cells(self):
        document = diagnostics_document(self.preview(), self.session)

        self.session.discard()
        markdown = render_diagnostics_markdown(document)

        self.assertIn("safe \\| value", markdown)
        self.assertIn("line value", markdown)
        self.assertNotIn("line\nvalue", markdown)
        self.assertTrue(markdown.endswith("\n"))

    def test_report_fails_closed_on_identity_and_association_mismatch(self):
        preview = self.preview()
        other = StagedImportSession.create(temp_parent=self.root)
        try:
            with self.assertRaisesRegex(ValueError, "session"):
                diagnostics_document(preview, other)
        finally:
            other.discard()

        wrong_source = SourcePreview(
            source_id=uuid4(),
            source_path=self.source_path,
            selected_reader_id="xyz",
            content_hash="a" * 64,
            byte_size=self.source_path.stat().st_size,
            staged_batch_ids=(BATCH_ID,),
            diagnostic_ids=preview.diagnostic_ids,
        )
        with self.assertRaisesRegex(ValueError, "source"):
            import_summary(
                ImportPreview(
                    session_id=self.session.id,
                    source_previews=(wrong_source,),
                    staged_batch_ids=(BATCH_ID,),
                    diagnostic_ids=preview.diagnostic_ids,
                ),
                self.session,
            )

        with self.assertRaisesRegex(ValueError, "diagnostic"):
            diagnostics_document(
                self.preview(tuple(reversed(preview.diagnostic_ids))),
                self.session,
            )

    def test_report_fails_closed_on_live_diagnostic_reference_mismatch(self):
        wrong_revision = diagnostic(
            1,
            DiagnosticSeverity.ERROR,
            QualityStatus.INVALID,
            source_revision_id=uuid4(),
        )
        self.register((wrong_revision,))
        with self.assertRaisesRegex(ValueError, "source revision"):
            import_summary(self.preview((wrong_revision.id,)), self.session)

        item = self.diagnostics[0]
        self.register((item,), revision_diagnostic_ids=())
        with self.assertRaisesRegex(ValueError, "revision diagnostic"):
            import_summary(self.preview((item.id,)), self.session)

    def test_report_keeps_diagnostics_when_reader_selection_failed(self):
        document = diagnostics_document(
            self.preview(selected_reader_id=None),
            self.session,
        )

        self.assertEqual(len(document["diagnostics"]), len(self.diagnostics))


if __name__ == "__main__":
    unittest.main()
