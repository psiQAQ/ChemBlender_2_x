import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from ChemBlender.core import (
    DiagnosticSeverity,
    DiagnosticValue,
    ImportBatch,
    ImportDiagnostic,
    IssueKind,
    ParserIssue,
    ProvenanceRecord,
    QCProject,
    QualityStatus,
    SourceRecord,
    SourceRevision,
    diagnostic_from_parser_issue,
)
from ChemBlender.core.sidecar import (
    SidecarIntegrityError,
    _manifest_hash,
    _open_project_with_manifest,
    close_project,
    open_project,
    save_project,
)


_HASH = "a" * 64


def source_pair(diagnostic_ids=()):
    source = SourceRecord(
        id=uuid4(),
        display_name="input.xyz",
        source_kind="file",
        created_at_utc="2026-07-24T00:00:00Z",
    )
    revision = SourceRevision(
        id=uuid4(),
        source_id=source.id,
        content_hash=_HASH,
        byte_size=1,
        locator="input.xyz",
        locator_kind="relative_path",
        original_filename="input.xyz",
        reader_plugin_id="chemblender",
        reader_id="xyz",
        reader_version="1",
        reader_api_version="0.1",
        import_parameters_hash=_HASH,
        parse_identity=_HASH,
        created_entity_ids=(),
        diagnostic_ids=diagnostic_ids,
    )
    return source, revision


def diagnostic(source_revision_id, **changes):
    values = {
        "id": uuid4(),
        "severity": DiagnosticSeverity.WARNING,
        "quality_status": QualityStatus.PARTIAL,
        "source_revision_id": source_revision_id,
        "record_key": None,
        "entity_id": None,
        "field_path": "atom.charge",
        "code": "xyz.missing_charge",
        "message": "charge is missing",
        "original_value": None,
        "normalized_value": None,
        "recovery_action": None,
        "scientific_consequence": "atomic charges are unavailable",
        "suggested_action": "choose a file containing charges",
    }
    values.update(changes)
    return ImportDiagnostic(**values)


class QualityAndDiagnosticTests(unittest.TestCase):
    def test_quality_and_severity_summary_orders_are_explicit(self):
        statuses = (
            QualityStatus.INVALID,
            QualityStatus.COMPLETE,
            QualityStatus.INCOMPLETE,
            QualityStatus.AMBIGUOUS,
            QualityStatus.PARTIAL,
        )
        self.assertEqual(
            tuple(sorted(statuses, key=lambda value: value.summary_order)),
            (
                QualityStatus.COMPLETE,
                QualityStatus.PARTIAL,
                QualityStatus.AMBIGUOUS,
                QualityStatus.INCOMPLETE,
                QualityStatus.INVALID,
            ),
        )
        severities = (
            DiagnosticSeverity.INFO,
            DiagnosticSeverity.ERROR,
            DiagnosticSeverity.WARNING,
        )
        self.assertEqual(
            tuple(sorted(severities, key=lambda value: value.summary_order)),
            (
                DiagnosticSeverity.ERROR,
                DiagnosticSeverity.WARNING,
                DiagnosticSeverity.INFO,
            ),
        )

    def test_quality_and_severity_enum_contracts_are_exact(self):
        self.assertEqual(
            tuple(
                (value.name, value.value, value.summary_order)
                for value in QualityStatus
            ),
            (
                ("COMPLETE", "complete", 0),
                ("PARTIAL", "partial", 1),
                ("AMBIGUOUS", "ambiguous", 2),
                ("INCOMPLETE", "incomplete", 3),
                ("INVALID", "invalid", 4),
            ),
        )
        self.assertEqual(
            tuple(
                (value.name, value.value, value.summary_order)
                for value in DiagnosticSeverity
            ),
            (
                ("INFO", "info", 2),
                ("WARNING", "warning", 1),
                ("ERROR", "error", 0),
            ),
        )

    def test_diagnostic_value_canonicalizes_recursive_json_safe_values(self):
        value = DiagnosticValue(
            {
                "z": [True, 2, -0.5],
                "a": {"text": "ok", "none": None},
            }
        )
        self.assertEqual(
            value.value,
            (
                "mapping",
                (
                    (
                        ("str", "a"),
                        (
                            "mapping",
                            (
                                (("str", "none"), ("none",)),
                                (("str", "text"), ("str", "ok")),
                            ),
                        ),
                    ),
                    (
                        ("str", "z"),
                        (
                            "sequence",
                            (
                                ("bool", True),
                                ("int", 2),
                                ("float", -0.5),
                            ),
                        ),
                    ),
                ),
            ),
        )
        unicode_keys = DiagnosticValue({"ä": 1, "Z": 2}).value[1]
        self.assertEqual(
            tuple(item[0][1] for item in unicode_keys),
            ("Z", "ä"),
        )

    def test_mapping_and_genuine_tuple_pairs_remain_distinct_after_sidecar(self):
        mapping_id = uuid4()
        sequence_id = uuid4()
        source, revision = source_pair((mapping_id, sequence_id))
        mapping = diagnostic(
            revision.id,
            id=mapping_id,
            original_value=DiagnosticValue({"a": 1}),
        )
        sequence = diagnostic(
            revision.id,
            id=sequence_id,
            original_value=DiagnosticValue((("a", 1),)),
        )
        self.assertNotEqual(mapping.original_value, sequence.original_value)
        project = QCProject(
            id=uuid4(),
            schema_version="0.2",
            sources={source.id: source},
            source_revisions={revision.id: revision},
            diagnostics={
                mapping.id: mapping,
                sequence.id: sequence,
            },
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "tagged-values.cbq"
            save_project(root, project)
            restored = open_project(root)
            try:
                restored_mapping = restored.diagnostics[mapping.id].original_value
                restored_sequence = restored.diagnostics[sequence.id].original_value
                self.assertEqual(restored_mapping, mapping.original_value)
                self.assertEqual(restored_sequence, sequence.original_value)
                self.assertNotEqual(restored_mapping, restored_sequence)
            finally:
                close_project(restored)

    def test_diagnostic_value_rejects_unsafe_or_noncanonical_values(self):
        class IntegerSubclass(int):
            pass

        class FloatSubclass(float):
            pass

        class StringSubclass(str):
            pass

        class ListSubclass(list):
            pass

        class TupleSubclass(tuple):
            pass

        class DictSubclass(dict):
            pass

        invalid = (
            b"bytes",
            {1: "non-string key"},
            {StringSubclass("key"): 1},
            math.nan,
            math.inf,
            -math.inf,
            IntegerSubclass(1),
            FloatSubclass(1.0),
            StringSubclass("value"),
            ListSubclass((1,)),
            TupleSubclass((1,)),
            DictSubclass(a=1),
            object(),
        )
        for value in invalid:
            with self.subTest(value=repr(value)):
                with self.assertRaises((TypeError, ValueError)):
                    DiagnosticValue(value)

    def test_import_diagnostic_requires_stable_code_and_consequence(self):
        revision_id = uuid4()
        with self.assertRaises(ValueError):
            diagnostic(
                revision_id,
                code="Invalid Code",
                scientific_consequence="",
            )

    def test_import_diagnostic_validates_identifiers_text_and_values(self):
        revision_id = uuid4()
        invalid_changes = (
            {"id": "not-a-uuid"},
            {"severity": "warning"},
            {"quality_status": "partial"},
            {"source_revision_id": None},
            {"record_key": ""},
            {"entity_id": "not-a-uuid"},
            {"field_path": ""},
            {"message": ""},
            {"original_value": "raw"},
            {"normalized_value": object()},
            {"recovery_action": ""},
            {"suggested_action": ""},
        )
        for changes in invalid_changes:
            with self.subTest(changes=changes):
                with self.assertRaises((TypeError, ValueError)):
                    diagnostic(revision_id, **changes)

    def test_legacy_parser_issue_conversion_uses_reader_not_message_for_code(self):
        revision_id = uuid4()
        entity_id = uuid4()
        issue = ParserIssue(
            IssueKind.AMBIGUOUS,
            "cube.values",
            "message text must not become a type tag",
        )
        converted = diagnostic_from_parser_issue(
            issue,
            revision_id,
            reader_id="cube",
            record_key="record-2",
            entity_id=entity_id,
        )
        self.assertEqual(converted.code, "cube.ambiguous")
        self.assertEqual(converted.message, issue.message)
        self.assertEqual(converted.field_path, issue.path)
        self.assertEqual(converted.source_revision_id, revision_id)
        self.assertEqual(converted.record_key, "record-2")
        self.assertEqual(converted.entity_id, entity_id)
        self.assertIs(converted.severity, DiagnosticSeverity.WARNING)
        self.assertIs(converted.quality_status, QualityStatus.AMBIGUOUS)

    def test_legacy_issue_mapping_is_explicit_for_every_kind(self):
        revision_id = uuid4()
        expected = {
            IssueKind.MISSING: (
                DiagnosticSeverity.WARNING,
                QualityStatus.INCOMPLETE,
            ),
            IssueKind.UNSUPPORTED: (
                DiagnosticSeverity.WARNING,
                QualityStatus.INCOMPLETE,
            ),
            IssueKind.AMBIGUOUS: (
                DiagnosticSeverity.WARNING,
                QualityStatus.AMBIGUOUS,
            ),
            IssueKind.INVALID: (
                DiagnosticSeverity.ERROR,
                QualityStatus.INVALID,
            ),
            IssueKind.WARNING: (
                DiagnosticSeverity.WARNING,
                QualityStatus.PARTIAL,
            ),
        }
        for kind, outcome in expected.items():
            with self.subTest(kind=kind):
                converted = diagnostic_from_parser_issue(
                    ParserIssue(kind, "field", "message"),
                    revision_id,
                    reader_id="legacy_reader",
                )
                self.assertEqual(
                    (converted.severity, converted.quality_status),
                    outcome,
                )
                self.assertEqual(converted.code, f"legacy_reader.{kind.value}")

    def test_legacy_conversion_requires_a_valid_reader_id(self):
        issue = ParserIssue(IssueKind.WARNING, "field", "message")
        for reader_id in ("", "Bad Reader"):
            with self.subTest(reader_id=reader_id):
                with self.assertRaises(ValueError):
                    diagnostic_from_parser_issue(
                        issue,
                        uuid4(),
                        reader_id=reader_id,
                    )


class ProjectDiagnosticRegistryTests(unittest.TestCase):
    def test_project_validates_diagnostic_keys_and_global_uuid_uniqueness(self):
        source, revision = source_pair()
        item = diagnostic(revision.id)
        with self.assertRaises(ValueError):
            QCProject(
                id=uuid4(),
                schema_version="0.2",
                sources={source.id: source},
                source_revisions={revision.id: revision},
                diagnostics={uuid4(): item},
            )
        with self.assertRaises(ValueError):
            QCProject(
                id=uuid4(),
                schema_version="0.2",
                sources={source.id: source},
                source_revisions={revision.id: revision},
                diagnostics={source.id: diagnostic(revision.id, id=source.id)},
            )

    def test_project_requires_bidirectional_revision_diagnostic_relationship(self):
        item_id = uuid4()
        source, revision = source_pair((item_id,))
        item = diagnostic(revision.id, id=item_id)
        project = QCProject(
            id=uuid4(),
            schema_version="0.2",
            sources={source.id: source},
            source_revisions={revision.id: revision},
            diagnostics={item.id: item},
        )
        self.assertIs(project.diagnostics[item.id], item)

        missing_source, missing_revision = source_pair((uuid4(),))
        with self.assertRaises(ValueError):
            QCProject(
                id=uuid4(),
                schema_version="0.2",
                sources={missing_source.id: missing_source},
                source_revisions={missing_revision.id: missing_revision},
            )

        other_source, other_revision = source_pair()
        with self.assertRaises(ValueError):
            QCProject(
                id=uuid4(),
                schema_version="0.2",
                sources={other_source.id: other_source},
                source_revisions={other_revision.id: other_revision},
                diagnostics={
                    item.id: diagnostic(revision.id, id=item.id),
                },
            )

    def test_import_batch_commits_diagnostics_atomically(self):
        item_id = uuid4()
        source, revision = source_pair((item_id,))
        item = diagnostic(revision.id, id=item_id)
        project = QCProject(id=uuid4(), schema_version="0.2")
        project.commit(
            ImportBatch(
                sources=(source,),
                source_revisions=(revision,),
                diagnostics=(item,),
            )
        )
        self.assertIs(project.diagnostics[item.id], item)

    def test_diagnostic_entity_reference_cannot_target_registry_metadata(self):
        item_id = uuid4()
        source, revision = source_pair((item_id,))
        with self.assertRaises(ValueError):
            QCProject(
                id=uuid4(),
                schema_version="0.2",
                sources={source.id: source},
                source_revisions={revision.id: revision},
                diagnostics={
                    item_id: diagnostic(
                        revision.id,
                        id=item_id,
                        entity_id=item_id,
                    ),
                },
            )

    def test_diagnostic_uuid_cannot_satisfy_created_entity_relationship(self):
        item_id = uuid4()
        source, revision = source_pair((item_id,))
        revision = SourceRevision(
            id=revision.id,
            source_id=revision.source_id,
            content_hash=revision.content_hash,
            byte_size=revision.byte_size,
            locator=revision.locator,
            locator_kind=revision.locator_kind,
            original_filename=revision.original_filename,
            reader_plugin_id=revision.reader_plugin_id,
            reader_id=revision.reader_id,
            reader_version=revision.reader_version,
            reader_api_version=revision.reader_api_version,
            import_parameters_hash=revision.import_parameters_hash,
            parse_identity=revision.parse_identity,
            created_entity_ids=(item_id,),
            diagnostic_ids=revision.diagnostic_ids,
        )
        with self.assertRaises(ValueError):
            QCProject(
                id=uuid4(),
                schema_version="0.2",
                sources={source.id: source},
                source_revisions={revision.id: revision},
                diagnostics={
                    item_id: diagnostic(revision.id, id=item_id),
                },
            )

    def test_diagnostic_uuid_cannot_satisfy_provenance_parent_relationship(self):
        item_id = uuid4()
        provenance_id = uuid4()
        source, revision = source_pair((item_id,))
        item = diagnostic(revision.id, id=item_id)
        provenance = ProvenanceRecord(
            id=provenance_id,
            revision="r1",
            producer="test",
            producer_version="1",
            source="input.xyz",
            source_hash=_HASH,
            parent_ids=(item_id,),
            operation="parse",
            parameters=(),
        )
        project = QCProject(id=uuid4(), schema_version="0.2")
        with self.assertRaises(ValueError):
            project.commit(
                ImportBatch(
                    sources=(source,),
                    source_revisions=(revision,),
                    diagnostics=(item,),
                    provenance=(provenance,),
                )
            )
        self.assertEqual(project.diagnostics, {})

    def test_sidecar_round_trips_diagnostics_and_legacy_fixture_stays_readable(self):
        item_id = uuid4()
        source, revision = source_pair((item_id,))
        item = diagnostic(
            revision.id,
            id=item_id,
            original_value=DiagnosticValue({"raw": [1, True]}),
            normalized_value=DiagnosticValue({"normalized": (1.0,)}),
        )
        project = QCProject(
            id=uuid4(),
            schema_version="0.2",
            sources={source.id: source},
            source_revisions={revision.id: revision},
            diagnostics={item.id: item},
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "diagnostics.cbq"
            save_project(root, project)
            restored = open_project(root)
            try:
                self.assertEqual(restored.diagnostics, project.diagnostics)
            finally:
                close_project(restored)

        fixture = (
            Path(__file__).resolve().parent
            / "fixtures"
            / "sidecar"
            / "model-v01"
        )
        restored = open_project(fixture)
        try:
            self.assertEqual(restored.diagnostics, {})
        finally:
            close_project(restored)

    def test_pre_diagnostic_v02_manifest_is_verified_before_defaulting(self):
        project = QCProject(id=uuid4(), schema_version="0.2")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "old-v02.cbq"
            save_project(root, project)
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertIn("diagnostics", manifest["project"])
            original_hash = manifest["manifest_sha256"]
            original_payload = {
                key: value
                for key, value in manifest.items()
                if key != "manifest_sha256"
            }
            self.assertEqual(
                original_hash,
                hashlib.sha256(
                    json.dumps(
                        original_payload,
                        ensure_ascii=False,
                        allow_nan=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest(),
            )
            del manifest["project"]["diagnostics"]
            payload = {
                key: value
                for key, value in manifest.items()
                if key != "manifest_sha256"
            }
            manifest["manifest_sha256"] = hashlib.sha256(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            manifest_path.write_text(
                json.dumps(
                    manifest,
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n",
                encoding="utf-8",
            )

            restored, metadata = _open_project_with_manifest(root)
            try:
                self.assertEqual(restored.diagnostics, {})
                self.assertEqual(metadata, manifest)
                self.assertEqual(
                    metadata["manifest_sha256"],
                    _manifest_hash(metadata),
                )
            finally:
                close_project(restored)

            manifest["project"]["schema_version"] = "tampered"
            manifest_path.write_text(
                json.dumps(
                    manifest,
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                SidecarIntegrityError,
                "manifest hash mismatch",
            ):
                open_project(root)


if __name__ == "__main__":
    unittest.main()
