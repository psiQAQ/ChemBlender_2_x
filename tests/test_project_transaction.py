import dataclasses
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import numpy

from ChemBlender.core import (
    ArrayData,
    CalculationRecord,
    CalculationStatus,
    DiagnosticSeverity,
    DiagnosticValue,
    ImportBatch,
    ImportDiagnostic,
    ParserReport,
    ProjectSession,
    ProvenanceRecord,
    QCProject,
    QualityStatus,
    SourceRecord,
    SourceRevision,
    Structure,
    close_project,
    close_session,
    create_session,
    open_project,
)
from ChemBlender.core.import_pipeline import (
    ConflictDecision,
    DuplicateAction,
    GroupingDecision,
    ImportCommitDecisions,
    ImportCommitResult,
    ImportPreview,
    SourcePreview,
    StagedImportSession,
    commit_import_preview,
    detect_import_conflicts,
    suggest_source_groups,
)
from ChemBlender.core.import_pipeline import transaction as transaction_module


class ProjectTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.project_sessions = []
        self.staged_sessions = []

    def tearDown(self):
        for session in reversed(self.staged_sessions):
            if session.root.exists():
                session.discard()
        for session in reversed(self.project_sessions):
            if session.temporary_root.exists():
                close_session(session)
        self.temporary.cleanup()

    def project_session(self, project=None):
        session = create_session(temp_parent=self.root, project=project)
        self.project_sessions.append(session)
        return session

    def staged_session(self):
        session = StagedImportSession.create(temp_parent=self.root)
        self.staged_sessions.append(session)
        return session

    @staticmethod
    def structure(coordinate=0.0):
        return Structure(
            id=uuid4(),
            revision="r1",
            atomic_numbers=(1,),
            coordinates=ArrayData(
                numpy.asarray(((coordinate, 0.0, 0.0),)),
                ("atom", "xyz"),
                "angstrom",
            ),
        )

    def stage(self, session, index, *, structure=None, calculation=None):
        source = SourceRecord(
            id=uuid4(),
            display_name=f"source-{index}.xyz",
            source_kind="local_file",
            created_at_utc="2026-07-24T00:00:00Z",
        )
        structure_values = () if structure is None else (structure,)
        calculation_values = () if calculation is None else (calculation,)
        created_ids = tuple(
            item.id for item in (*structure_values, *calculation_values)
        )
        revision_id = uuid4()
        diagnostic_id = uuid4()
        diagnostic = ImportDiagnostic(
            id=diagnostic_id,
            severity=DiagnosticSeverity.INFO,
            quality_status=QualityStatus.COMPLETE,
            source_revision_id=revision_id,
            record_key=None,
            entity_id=None,
            field_path="source",
            code="fixture.complete",
            message="fixture parsed",
            original_value=None,
            normalized_value=None,
            recovery_action=None,
            scientific_consequence="fixture is complete",
            suggested_action=None,
        )
        path = (self.root / f"source-{index}.xyz").resolve()
        revision = SourceRevision(
            id=revision_id,
            source_id=source.id,
            content_hash=f"{index + 1:064x}",
            byte_size=index + 1,
            locator=str(path),
            locator_kind="absolute_path",
            original_filename=path.name,
            reader_plugin_id="chemblender.builtin",
            reader_id="fixture",
            reader_version="1",
            reader_api_version="0.1",
            import_parameters_hash="a" * 64,
            parse_identity=f"{index + 101:064x}",
            created_entity_ids=created_ids,
            diagnostic_ids=(diagnostic_id,),
        )
        batch = ImportBatch(
            sources=(source,),
            source_revisions=(revision,),
            structures=structure_values,
            calculations=calculation_values,
            diagnostics=(diagnostic,),
        )
        batch_id = uuid4()
        session.register_result(batch_id, batch)
        row = SourcePreview(
            source_id=source.id,
            source_path=path,
            selected_reader_id=revision.reader_id,
            content_hash=revision.content_hash,
            byte_size=revision.byte_size,
            capabilities=("structure",),
            staged_batch_ids=(batch_id,),
            diagnostic_ids=(diagnostic_id,),
        )
        return row, batch_id, batch

    @staticmethod
    def preview(session, staged):
        rows = tuple(item[0] for item in staged)
        return ImportPreview(
            session_id=session.id,
            source_previews=rows,
            staged_batch_ids=tuple(item[1] for item in staged),
            diagnostic_ids=tuple(
                diagnostic_id
                for row in rows
                for diagnostic_id in row.diagnostic_ids
            ),
        )

    def test_invalid_second_batch_has_no_live_or_publication_side_effects(self):
        project_session = self.project_session()
        staged_session = self.staged_session()
        first = self.stage(staged_session, 0, structure=self.structure())
        dangling = CalculationRecord(
            id=uuid4(),
            revision="r1",
            status=CalculationStatus.SUCCESS,
            input_structure_ids=(uuid4(),),
            result_structure_ids=(),
            dataset_ids=(),
            provenance_ids=(),
        )
        second = self.stage(staged_session, 1, calculation=dangling)
        preview = self.preview(staged_session, (first, second))
        original_project = project_session.project
        original_dirty = project_session.dirty_reasons

        with self.assertRaises(ValueError):
            commit_import_preview(
                project_session,
                staged_session,
                preview,
                ImportCommitDecisions(),
            )

        self.assertIs(project_session.project, original_project)
        self.assertEqual(project_session.dirty_reasons, original_dirty)
        self.assertIsNone(project_session.sidecar_path)
        self.assertEqual(
            tuple(project_session.temporary_root.glob("*.cbq")),
            (),
        )

    def test_cross_batch_forward_references_commit_in_one_merged_batch(self):
        project_session = self.project_session()
        staged_session = self.staged_session()
        structure = self.structure()
        calculation = CalculationRecord(
            id=uuid4(),
            revision="r1",
            status=CalculationStatus.SUCCESS,
            input_structure_ids=(structure.id,),
            result_structure_ids=(),
            dataset_ids=(),
            provenance_ids=(),
        )
        first = self.stage(staged_session, 80, calculation=calculation)
        second = self.stage(staged_session, 81, structure=structure)
        for staged in (first, second):
            batch = staged[2]
            created_ids = tuple(
                entity.id
                for name in transaction_module._BATCH_ENTITY_FIELDS
                for entity in getattr(batch, name)
            )
            staged_session._results[staged[1]] = dataclasses.replace(
                batch,
                report=ParserReport(
                    reader_id="fixture",
                    reader_version="1",
                    created_entity_ids=created_ids,
                    parsed_capabilities=("structure",),
                    issues=(),
                ),
            )
        preview = self.preview(staged_session, (first, second))
        suggestions = suggest_source_groups(preview, staged_session)
        preview = dataclasses.replace(
            preview,
            grouping_suggestion_ids=tuple(
                suggestion.id for suggestion in suggestions
            ),
        )

        result = commit_import_preview(
            project_session,
            staged_session,
            preview,
            ImportCommitDecisions(),
        )

        self.assertIn(structure.id, result.project.structures)
        self.assertIn(calculation.id, result.project.calculations)

    def test_merged_batch_still_validates_each_parser_report_contract(self):
        project_session = self.project_session()
        staged_session = self.staged_session()
        staged = self.stage(staged_session, 82, structure=self.structure())
        staged_session._results[staged[1]] = dataclasses.replace(
            staged[2],
            report=ParserReport(
                reader_id="fixture",
                reader_version="1",
                created_entity_ids=(uuid4(),),
                parsed_capabilities=("structure",),
                issues=(),
            ),
        )
        preview = self.preview(staged_session, (staged,))

        with self.assertRaisesRegex(ValueError, "parser report"):
            commit_import_preview(
                project_session,
                staged_session,
                preview,
                ImportCommitDecisions(),
            )

        self.assertIsNone(project_session.sidecar_path)
        self.assertFalse(project_session.dirty)

    def test_commits_reopens_diagnostics_groups_and_view_plan_ids(self):
        project_session = self.project_session()
        staged_session = self.staged_session()
        first = self.stage(staged_session, 0, structure=self.structure())
        second = self.stage(staged_session, 1, structure=self.structure())
        base_preview = self.preview(staged_session, (first, second))
        suggestions = suggest_source_groups(base_preview, staged_session)
        self.assertEqual(len(suggestions), 1)
        view_plan_id = uuid4()
        preview = dataclasses.replace(
            base_preview,
            grouping_suggestion_ids=(suggestions[0].id,),
            default_view_plan_ids=(view_plan_id,),
        )

        result = commit_import_preview(
            project_session,
            staged_session,
            preview,
            ImportCommitDecisions(
                grouping_decisions=(
                    GroupingDecision(
                        suggestion=suggestions[0],
                        evidence_ids=suggestions[0].evidence_ids,
                    ),
                ),
            ),
        )

        self.assertIsInstance(project_session, ProjectSession)
        self.assertIs(result.project, project_session.project)
        self.assertTrue(project_session.dirty)
        self.assertIn("import", project_session.dirty_reasons)
        self.assertEqual(result.default_view_plan_ids, (view_plan_id,))
        self.assertEqual(len(project_session.project.sources), 2)
        self.assertEqual(len(project_session.project.source_revisions), 2)
        self.assertEqual(len(project_session.project.structures), 2)
        self.assertEqual(len(project_session.project.diagnostics), 2)
        self.assertEqual(len(project_session.project.calculation_groups), 1)
        self.assertEqual(result.sidecar_path, project_session.sidecar_path)
        reopened = open_project(result.sidecar_path)
        try:
            self.assertEqual(
                reopened.calculation_groups,
                project_session.project.calculation_groups,
            )
            self.assertEqual(set(reopened.structures), set(result.project.structures))
            self.assertEqual(set(reopened.diagnostics), set(result.project.diagnostics))
        finally:
            close_project(reopened)

    def test_adopts_exact_project_verified_by_publication(self):
        project_session = self.project_session()
        staged_session = self.staged_session()
        staged = self.stage(staged_session, 70, structure=self.structure())
        preview = self.preview(staged_session, (staged,))
        captured = {}
        real_solidify = transaction_module.solidify_session

        def capture_transfer(*args, **kwargs):
            published = real_solidify(*args, **kwargs)
            captured["project"] = published.project
            return published

        with patch.object(
            transaction_module,
            "solidify_session",
            side_effect=capture_transfer,
        ):
            result = commit_import_preview(
                project_session,
                staged_session,
                preview,
                ImportCommitDecisions(),
            )

        self.assertIsNotNone(captured["project"])
        self.assertIs(result.project, captured["project"])
        self.assertIs(project_session.project, captured["project"])

    def test_stale_grouping_snapshot_is_rejected_before_publication(self):
        project_session = self.project_session()
        staged_session = self.staged_session()
        first = self.stage(staged_session, 0, structure=self.structure())
        second = self.stage(staged_session, 1, structure=self.structure())
        preview = self.preview(staged_session, (first, second))
        suggestion = suggest_source_groups(preview, staged_session)[0]
        changed_structure = self.structure(0.2)
        changed_batch = dataclasses.replace(
            second[2],
            structures=(changed_structure,),
            source_revisions=(
                dataclasses.replace(
                    second[2].source_revisions[0],
                    created_entity_ids=(changed_structure.id,),
                ),
            ),
        )
        staged_session._results[second[1]] = changed_batch
        preview = dataclasses.replace(
            preview,
            grouping_suggestion_ids=(suggestion.id,),
        )

        with self.assertRaisesRegex(ValueError, "grouping"):
            commit_import_preview(
                project_session,
                staged_session,
                preview,
                ImportCommitDecisions(
                    grouping_decisions=(
                        GroupingDecision(
                            suggestion=suggestion,
                            evidence_ids=suggestion.evidence_ids,
                        ),
                    ),
                ),
            )

        self.assertIsNone(project_session.sidecar_path)
        self.assertFalse(project_session.dirty)

    def test_grouping_snapshot_is_validated_before_reuse_then_rederived(self):
        project_session = self.project_session()
        staged_session = self.staged_session()
        first = self.stage(staged_session, 83, structure=self.structure())
        second = self.stage(staged_session, 84, structure=self.structure())
        existing_structure = self.structure()
        existing_source = SourceRecord(
            id=uuid4(),
            display_name="existing.xyz",
            source_kind="local_file",
            created_at_utc="2026-07-24T00:00:00Z",
        )
        existing_revision = dataclasses.replace(
            first[2].source_revisions[0],
            id=uuid4(),
            source_id=existing_source.id,
            created_entity_ids=(existing_structure.id,),
            diagnostic_ids=(),
        )
        project_session.project.commit(
            ImportBatch(
                sources=(existing_source,),
                source_revisions=(existing_revision,),
                structures=(existing_structure,),
            )
        )
        preview = self.preview(staged_session, (first, second))
        conflicts = detect_import_conflicts(
            project_session.project,
            preview,
            staged_session,
        )
        suggestions = suggest_source_groups(preview, staged_session)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(len(suggestions), 1)
        preview = dataclasses.replace(
            preview,
            conflict_ids=(conflicts[0].id,),
            grouping_suggestion_ids=(suggestions[0].id,),
        )

        result = commit_import_preview(
            project_session,
            staged_session,
            preview,
            ImportCommitDecisions(
                conflicts=conflicts,
                conflict_decisions={
                    conflicts[0].id: ConflictDecision(
                        DuplicateAction.REUSE_EXISTING,
                        existing_revision_id=existing_revision.id,
                    )
                },
                grouping_decisions=(
                    GroupingDecision(
                        suggestion=suggestions[0],
                        evidence_ids=suggestions[0].evidence_ids,
                    ),
                ),
            ),
        )

        group = next(iter(result.project.calculation_groups.values()))
        self.assertEqual(
            set(group.source_revision_ids),
            {
                existing_revision.id,
                second[2].source_revisions[0].id,
            },
        )
        self.assertNotEqual(group.suggestion_id, suggestions[0].id)
        self.assertTrue(
            set(group.evidence_ids).isdisjoint(suggestions[0].evidence_ids)
        )

    def test_confirmed_group_involving_ignored_source_is_rejected(self):
        project_session = self.project_session()
        staged_session = self.staged_session()
        first = self.stage(staged_session, 85, structure=self.structure())
        second = self.stage(staged_session, 86, structure=self.structure())
        existing_source = SourceRecord(
            id=uuid4(),
            display_name="existing.xyz",
            source_kind="local_file",
            created_at_utc="2026-07-24T00:00:00Z",
        )
        existing_revision = dataclasses.replace(
            first[2].source_revisions[0],
            id=uuid4(),
            source_id=existing_source.id,
            content_hash="f" * 64,
            parse_identity="e" * 64,
            created_entity_ids=(),
            diagnostic_ids=(),
        )
        project_session.project.commit(
            ImportBatch(
                sources=(existing_source,),
                source_revisions=(existing_revision,),
            )
        )
        preview = self.preview(staged_session, (first, second))
        conflicts = detect_import_conflicts(
            project_session.project,
            preview,
            staged_session,
        )
        suggestions = suggest_source_groups(preview, staged_session)
        preview = dataclasses.replace(
            preview,
            conflict_ids=(conflicts[0].id,),
            grouping_suggestion_ids=(suggestions[0].id,),
        )

        with self.assertRaisesRegex(ValueError, "ignored source"):
            commit_import_preview(
                project_session,
                staged_session,
                preview,
                ImportCommitDecisions(
                    conflicts=conflicts,
                    conflict_decisions={
                        conflicts[0].id: DuplicateAction.IGNORE
                    },
                    grouping_decisions=(
                        GroupingDecision(
                            suggestion=suggestions[0],
                            evidence_ids=suggestions[0].evidence_ids,
                        ),
                    ),
                ),
            )

        self.assertIsNone(project_session.sidecar_path)
        self.assertFalse(project_session.dirty)

    def test_link_existing_does_not_zip_unrelated_created_entities(self):
        project_session = self.project_session()
        staged_session = self.staged_session()
        first = self.stage(staged_session, 90, structure=self.structure())
        second = self.stage(staged_session, 91, structure=self.structure())
        staged_revision = first[2].source_revisions[0]
        provenance = ProvenanceRecord(
            id=uuid4(),
            revision="r1",
            producer="fixture",
            producer_version="1",
            source="existing.xyz",
            source_hash=staged_revision.content_hash,
            parent_ids=(),
            operation="parse",
            parameters=(),
        )
        existing_source = SourceRecord(
            id=uuid4(),
            display_name="existing.xyz",
            source_kind="local_file",
            created_at_utc="2026-07-24T00:00:00Z",
        )
        existing_revision = dataclasses.replace(
            staged_revision,
            id=uuid4(),
            source_id=existing_source.id,
            locator=str((self.root / "relocated.xyz").resolve()),
            original_filename="relocated.xyz",
            parse_identity="e" * 64,
            created_entity_ids=(provenance.id,),
            diagnostic_ids=(),
        )
        project_session.project.commit(
            ImportBatch(
                sources=(existing_source,),
                source_revisions=(existing_revision,),
                provenance=(provenance,),
            )
        )
        preview = self.preview(staged_session, (first, second))
        conflicts = detect_import_conflicts(
            project_session.project,
            preview,
            staged_session,
        )
        suggestions = suggest_source_groups(preview, staged_session)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(len(suggestions), 1)
        preview = dataclasses.replace(
            preview,
            conflict_ids=(conflicts[0].id,),
            grouping_suggestion_ids=(suggestions[0].id,),
        )
        original_project = project_session.project

        with self.assertRaisesRegex(ValueError, "unavailable entity"):
            commit_import_preview(
                project_session,
                staged_session,
                preview,
                ImportCommitDecisions(
                    conflicts=conflicts,
                    conflict_decisions={
                        conflicts[0].id: ConflictDecision(
                            DuplicateAction.LINK_EXISTING,
                            existing_revision_id=existing_revision.id,
                        )
                    },
                    grouping_decisions=(
                        GroupingDecision(
                            suggestion=suggestions[0],
                            evidence_ids=suggestions[0].evidence_ids,
                        ),
                    ),
                ),
            )

        self.assertIs(project_session.project, original_project)
        self.assertIsNone(project_session.sidecar_path)
        self.assertFalse(project_session.dirty)
        self.assertEqual(
            tuple(project_session.temporary_root.glob("*.cbq")),
            (),
        )

    def test_conflict_preserves_default_view_intent_ids(self):
        project_session = self.project_session()
        staged_session = self.staged_session()
        staged = self.stage(
            staged_session,
            92,
            structure=self.structure(),
        )
        staged_revision = staged[2].source_revisions[0]
        existing_source = SourceRecord(
            id=uuid4(),
            display_name="existing.xyz",
            source_kind="local_file",
            created_at_utc="2026-07-24T00:00:00Z",
        )
        existing_revision = dataclasses.replace(
            staged_revision,
            id=uuid4(),
            source_id=existing_source.id,
            created_entity_ids=(),
            diagnostic_ids=(),
        )
        project_session.project.commit(
            ImportBatch(
                sources=(existing_source,),
                source_revisions=(existing_revision,),
            )
        )
        preview = self.preview(staged_session, (staged,))
        conflicts = detect_import_conflicts(
            project_session.project,
            preview,
            staged_session,
        )
        self.assertEqual(len(conflicts), 1)
        view_plan_id = uuid4()
        preview = dataclasses.replace(
            preview,
            conflict_ids=(conflicts[0].id,),
            default_view_plan_ids=(view_plan_id,),
        )

        result = commit_import_preview(
            project_session,
            staged_session,
            preview,
            ImportCommitDecisions(
                conflicts=conflicts,
                conflict_decisions={
                    conflicts[0].id: ConflictDecision(
                        DuplicateAction.REUSE_EXISTING,
                        existing_revision_id=existing_revision.id,
                    )
                },
            ),
        )

        self.assertEqual(result.default_view_plan_ids, (view_plan_id,))

    def test_independent_copy_rederives_grouping_snapshot_ids(self):
        project_session = self.project_session()
        staged_session = self.staged_session()
        first = self.stage(staged_session, 87, structure=self.structure())
        second = self.stage(staged_session, 88, structure=self.structure())
        existing_source = SourceRecord(
            id=uuid4(),
            display_name="existing.xyz",
            source_kind="local_file",
            created_at_utc="2026-07-24T00:00:00Z",
        )
        existing_revision = dataclasses.replace(
            first[2].source_revisions[0],
            id=uuid4(),
            source_id=existing_source.id,
            created_entity_ids=(),
            diagnostic_ids=(),
        )
        project_session.project.commit(
            ImportBatch(
                sources=(existing_source,),
                source_revisions=(existing_revision,),
            )
        )
        preview = self.preview(staged_session, (first, second))
        conflicts = detect_import_conflicts(
            project_session.project,
            preview,
            staged_session,
        )
        suggestions = suggest_source_groups(preview, staged_session)
        preview = dataclasses.replace(
            preview,
            conflict_ids=(conflicts[0].id,),
            grouping_suggestion_ids=(suggestions[0].id,),
        )

        result = commit_import_preview(
            project_session,
            staged_session,
            preview,
            ImportCommitDecisions(
                conflicts=conflicts,
                conflict_decisions={
                    conflicts[0].id: DuplicateAction.INDEPENDENT_COPY
                },
                grouping_decisions=(
                    GroupingDecision(
                        suggestion=suggestions[0],
                        evidence_ids=suggestions[0].evidence_ids,
                    ),
                ),
            ),
        )

        group = next(iter(result.project.calculation_groups.values()))
        self.assertNotEqual(group.suggestion_id, suggestions[0].id)
        self.assertTrue(
            set(group.evidence_ids).isdisjoint(suggestions[0].evidence_ids)
        )
        self.assertNotIn(
            first[2].source_revisions[0].id,
            group.source_revision_ids,
        )
        self.assertIn(
            second[2].source_revisions[0].id,
            group.source_revision_ids,
        )

    def test_new_revision_allocates_identity_and_targets_existing_source(self):
        existing_source = SourceRecord(
            id=uuid4(),
            display_name="existing.xyz",
            source_kind="local_file",
            created_at_utc="2026-07-24T00:00:00Z",
        )
        existing_revision = SourceRevision(
            id=uuid4(),
            source_id=existing_source.id,
            content_hash="1" * 64,
            byte_size=1,
            locator=str((self.root / "source-0.xyz").resolve()),
            locator_kind="absolute_path",
            original_filename="source-0.xyz",
            reader_plugin_id="chemblender.builtin",
            reader_id="fixture",
            reader_version="1",
            reader_api_version="0.1",
            import_parameters_hash="a" * 64,
            parse_identity="2" * 64,
            created_entity_ids=(),
            diagnostic_ids=(),
        )
        project = QCProject(id=uuid4(), schema_version="0.2")
        project.commit(
            ImportBatch(
                sources=(existing_source,),
                source_revisions=(existing_revision,),
            )
        )
        project_session = self.project_session(project)
        staged_session = self.staged_session()
        staged = self.stage(staged_session, 0, structure=self.structure())
        preview = self.preview(staged_session, (staged,))
        conflicts = detect_import_conflicts(project, preview, staged_session)
        self.assertEqual(len(conflicts), 1)
        preview = dataclasses.replace(
            preview,
            conflict_ids=(conflicts[0].id,),
        )
        staged_source = staged[2].sources[0]
        staged_revision = staged[2].source_revisions[0]
        staged_entity = staged[2].structures[0]

        result = commit_import_preview(
            project_session,
            staged_session,
            preview,
            ImportCommitDecisions(
                conflicts=conflicts,
                conflict_decisions={
                    conflicts[0].id: DuplicateAction.NEW_REVISION
                },
            ),
        )

        new_revision_ids = set(result.project.source_revisions) - {
            existing_revision.id
        }
        self.assertEqual(len(new_revision_ids), 1)
        new_revision = result.project.source_revisions[new_revision_ids.pop()]
        self.assertEqual(new_revision.source_id, existing_source.id)
        self.assertNotEqual(new_revision.id, staged_revision.id)
        self.assertNotIn(staged_source.id, result.project.sources)
        self.assertNotIn(staged_entity.id, result.project.structures)
        self.assertEqual(len(result.project.structures), 1)
        self.assertEqual(
            set(new_revision.created_entity_ids),
            set(result.project.structures) - set(project.structures),
        )

    def test_conflict_action_matrix_rewrites_or_skips_staging_atomically(self):
        cases = (
            (DuplicateAction.INDEPENDENT_COPY, "same_parse", True),
            (DuplicateAction.INDEPENDENT_SOURCE, "same_locator", True),
            (DuplicateAction.REUSE_EXISTING, "same_parse", False),
            (DuplicateAction.LOCATE_EXISTING, "same_parse", False),
            (DuplicateAction.LINK_EXISTING, "same_content", False),
            (DuplicateAction.IGNORE, "same_locator", False),
        )
        for case_index, (action, category, commits) in enumerate(cases):
            with self.subTest(action=action):
                project_session = self.project_session()
                staged_session = self.staged_session()
                staged = self.stage(
                    staged_session,
                    case_index + 20,
                    structure=self.structure(),
                )
                staged_revision = staged[2].source_revisions[0]
                existing_source = SourceRecord(
                    id=uuid4(),
                    display_name="existing.xyz",
                    source_kind="local_file",
                    created_at_utc="2026-07-24T00:00:00Z",
                )
                content_hash = (
                    staged_revision.content_hash
                    if category in ("same_parse", "same_content")
                    else "f" * 64
                )
                locator = (
                    staged_revision.locator
                    if category in ("same_parse", "same_locator")
                    else str((self.root / f"relocated-{case_index}.xyz").resolve())
                )
                parse_identity = (
                    staged_revision.parse_identity
                    if category == "same_parse"
                    else "e" * 64
                )
                existing_revision = dataclasses.replace(
                    staged_revision,
                    id=uuid4(),
                    source_id=existing_source.id,
                    content_hash=content_hash,
                    locator=locator,
                    original_filename=Path(locator).name,
                    parse_identity=parse_identity,
                    created_entity_ids=(),
                    diagnostic_ids=(),
                )
                project_session.project.commit(
                    ImportBatch(
                        sources=(existing_source,),
                        source_revisions=(existing_revision,),
                    )
                )
                preview = self.preview(staged_session, (staged,))
                conflicts = detect_import_conflicts(
                    project_session.project,
                    preview,
                    staged_session,
                )
                self.assertEqual(len(conflicts), 1)
                view_plan_id = uuid4()
                preview = dataclasses.replace(
                    preview,
                    conflict_ids=(conflicts[0].id,),
                    default_view_plan_ids=(view_plan_id,),
                )
                decision = action
                if action in {
                    DuplicateAction.REUSE_EXISTING,
                    DuplicateAction.LOCATE_EXISTING,
                    DuplicateAction.LINK_EXISTING,
                }:
                    decision = ConflictDecision(
                        action,
                        existing_revision_id=existing_revision.id,
                    )

                result = commit_import_preview(
                    project_session,
                    staged_session,
                    preview,
                    ImportCommitDecisions(
                        conflicts=conflicts,
                        conflict_decisions={conflicts[0].id: decision},
                    ),
                )

                staged_ids = set(
                    (
                        staged[2].sources[0].id,
                        staged_revision.id,
                        staged[2].structures[0].id,
                        staged[2].diagnostics[0].id,
                    )
                )
                project_ids = result.project._all_entity_ids()
                self.assertTrue(staged_ids.isdisjoint(project_ids))
                self.assertEqual(
                    result.default_view_plan_ids,
                    (view_plan_id,),
                )
                if not commits:
                    self.assertEqual(len(result.project.sources), 1)
                    self.assertEqual(len(result.project.source_revisions), 1)
                    self.assertEqual(result.project.structures, {})
                    self.assertEqual(result.project.diagnostics, {})
                    continue
                self.assertEqual(len(result.project.sources), 2)
                self.assertEqual(len(result.project.source_revisions), 2)
                self.assertEqual(len(result.project.structures), 1)
                self.assertEqual(len(result.project.diagnostics), 1)
                revision = next(
                    value
                    for value in result.project.source_revisions.values()
                    if value.id != existing_revision.id
                )
                diagnostic = next(iter(result.project.diagnostics.values()))
                self.assertIn(revision.source_id, result.project.sources)
                self.assertEqual(
                    set(revision.created_entity_ids),
                    set(result.project.structures),
                )
                self.assertEqual(revision.diagnostic_ids, (diagnostic.id,))
                self.assertEqual(diagnostic.source_revision_id, revision.id)

    def test_ambiguous_new_revision_target_fails_closed(self):
        project_session = self.project_session()
        staged_session = self.staged_session()
        staged = self.stage(
            staged_session,
            50,
            structure=self.structure(),
        )
        staged_revision = staged[2].source_revisions[0]
        existing = []
        for index in range(2):
            source = SourceRecord(
                id=uuid4(),
                display_name=f"existing-{index}.xyz",
                source_kind="local_file",
                created_at_utc="2026-07-24T00:00:00Z",
            )
            revision = dataclasses.replace(
                staged_revision,
                id=uuid4(),
                source_id=source.id,
                content_hash=f"{index + 900:064x}",
                parse_identity=f"{index + 950:064x}",
                created_entity_ids=(),
                diagnostic_ids=(),
            )
            existing.append((source, revision))
        project_session.project.commit(
            ImportBatch(
                sources=tuple(item[0] for item in existing),
                source_revisions=tuple(item[1] for item in existing),
            )
        )
        preview = self.preview(staged_session, (staged,))
        conflicts = detect_import_conflicts(
            project_session.project,
            preview,
            staged_session,
        )
        preview = dataclasses.replace(
            preview,
            conflict_ids=(conflicts[0].id,),
        )

        with self.assertRaisesRegex(ValueError, "unambiguous"):
            commit_import_preview(
                project_session,
                staged_session,
                preview,
                ImportCommitDecisions(
                    conflicts=conflicts,
                    conflict_decisions={
                        conflicts[0].id: DuplicateAction.NEW_REVISION
                    },
                ),
            )

        self.assertIsNone(project_session.sidecar_path)
        self.assertFalse(project_session.dirty)

    def test_rejects_wrong_session_and_mutable_decision_shapes(self):
        project_session = self.project_session()
        staged_session = self.staged_session()
        staged = self.stage(staged_session, 0, structure=self.structure())
        preview = self.preview(staged_session, (staged,))

        with self.assertRaises(TypeError):
            commit_import_preview(
                object(),
                staged_session,
                preview,
                ImportCommitDecisions(),
            )
        with self.assertRaises(TypeError):
            commit_import_preview(
                project_session,
                object(),
                preview,
                ImportCommitDecisions(),
            )
        with self.assertRaises(ValueError):
            commit_import_preview(
                project_session,
                self.staged_session(),
                preview,
                ImportCommitDecisions(),
            )
        with self.assertRaises(TypeError):
            ImportCommitDecisions(conflicts=[])
        with self.assertRaises(TypeError):
            GroupingDecision(
                suggestion=object(),
                evidence_ids=(UUID(int=0),),
            )

    def test_model_remap_treats_parameters_and_unknown_dataclasses_as_opaque(self):
        original_id, remapped_id = uuid4(), uuid4()
        provenance = ProvenanceRecord(
            id=original_id,
            revision="r1",
            producer="fixture",
            producer_version="1",
            source="fixture.xyz",
            source_hash="a" * 64,
            parent_ids=(original_id,),
            operation="parse",
            parameters=(("opaque_uuid", original_id),),
        )

        remapped = transaction_module._remap(
            provenance,
            {original_id: remapped_id},
        )

        self.assertEqual(remapped.id, remapped_id)
        self.assertEqual(remapped.parent_ids, (remapped_id,))
        self.assertEqual(
            remapped.parameters,
            (("opaque_uuid", original_id),),
        )
        array_data = ArrayData(
            values=numpy.array([original_id], dtype=object),
            dims=("item",),
            unit="dimensionless",
        )
        diagnostic_value = DiagnosticValue({"id": str(original_id)})
        self.assertIs(
            transaction_module._remap(
                array_data,
                {original_id: remapped_id},
            ),
            array_data,
        )
        self.assertIs(
            transaction_module._remap(
                diagnostic_value,
                {original_id: remapped_id},
            ),
            diagnostic_value,
        )

        @dataclass(frozen=True)
        class PluginPayload:
            value: UUID

        plugin_value = PluginPayload(original_id)
        self.assertIs(
            transaction_module._remap(
                plugin_value,
                {original_id: remapped_id},
            ),
            plugin_value,
        )

    def test_cleanup_failure_is_a_committed_result_warning(self):
        project_session = self.project_session()
        staged_session = self.staged_session()
        staged = self.stage(staged_session, 89, structure=self.structure())
        preview = self.preview(staged_session, (staged,))
        previous = project_session.project

        with patch.object(
            transaction_module,
            "close_project",
            side_effect=OSError("cleanup blocked"),
        ):
            result = commit_import_preview(
                project_session,
                staged_session,
                preview,
                ImportCommitDecisions(),
            )

        self.assertIsNot(project_session.project, previous)
        self.assertIs(result.project, project_session.project)
        self.assertTrue(project_session.dirty)
        self.assertEqual(
            result.cleanup_warnings,
            ("previous project cleanup failed: cleanup blocked",),
        )

    def test_import_commit_result_validates_exact_public_contract(self):
        project = QCProject(id=uuid4(), schema_version="0.2")
        path = (self.root / "project.cbq").resolve()
        valid = {
            "project": project,
            "sidecar_path": path,
            "committed_source_ids": (),
            "committed_source_revision_ids": (),
            "committed_entity_ids": (),
            "calculation_group_ids": (),
            "default_view_plan_ids": (),
            "cleanup_warnings": (),
        }
        self.assertEqual(
            ImportCommitResult(**valid).sidecar_path,
            path,
        )
        invalid = (
            ("project", object()),
            ("sidecar_path", str(path)),
            ("sidecar_path", Path("relative.cbq")),
            ("committed_source_ids", []),
            ("committed_source_revision_ids", ("not-a-uuid",)),
            ("committed_entity_ids", (UUID(int=0), UUID(int=0))),
            ("calculation_group_ids", [UUID(int=0)]),
            ("default_view_plan_ids", [UUID(int=0)]),
            ("cleanup_warnings", ["warning"]),
            ("cleanup_warnings", ("",)),
        )
        for name, value in invalid:
            with self.subTest(name=name, value=value):
                with self.assertRaises((TypeError, ValueError)):
                    ImportCommitResult(**{**valid, name: value})

    def test_multiple_batches_per_source_fail_closed_without_data_loss(self):
        project_session = self.project_session()
        staged_session = self.staged_session()
        staged = self.stage(staged_session, 60, structure=self.structure())
        second_batch_id = uuid4()
        staged_session.register_result(second_batch_id, ImportBatch())
        row = dataclasses.replace(
            staged[0],
            staged_batch_ids=(staged[1], second_batch_id),
        )
        preview = ImportPreview(
            session_id=staged_session.id,
            source_previews=(row,),
            staged_batch_ids=row.staged_batch_ids,
            diagnostic_ids=row.diagnostic_ids,
        )
        original_project = project_session.project

        with self.assertRaisesRegex(ValueError, "exactly one staged batch"):
            commit_import_preview(
                project_session,
                staged_session,
                preview,
                ImportCommitDecisions(),
            )

        self.assertIs(project_session.project, original_project)
        self.assertIsNone(project_session.sidecar_path)
        self.assertFalse(project_session.dirty)


if __name__ == "__main__":
    unittest.main()
