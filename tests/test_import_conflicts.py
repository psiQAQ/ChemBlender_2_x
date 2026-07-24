import dataclasses
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType
from uuid import UUID, uuid4

from ChemBlender.core.import_pipeline import conflicts as conflict_module
from ChemBlender.core.import_pipeline import (
    ConflictDecision,
    DuplicateAction,
    ImportConflict,
    ImportConflictCandidate,
    ImportConflictCategory,
    ImportPreview,
    SourcePreview,
    StagedImportSession,
    apply_conflict_decisions,
    detect_import_conflicts,
)
from ChemBlender.core.model import (
    DiagnosticSeverity,
    ImportBatch,
    ImportDiagnostic,
    ProvenanceRecord,
    QCProject,
    QualityStatus,
    SourceRecord,
    SourceRevision,
)


class ImportConflictTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.sessions = []

    def tearDown(self):
        for session in reversed(self.sessions):
            try:
                session.discard()
            except RuntimeError:
                pass
        self.temporary.cleanup()

    def session(self):
        session = StagedImportSession.create(temp_parent=self.root)
        self.sessions.append(session)
        return session

    @staticmethod
    def confirmed_preview(preview, conflicts):
        return dataclasses.replace(
            preview,
            conflict_ids=tuple(conflict.id for conflict in conflicts),
        )

    @staticmethod
    def source(source_id=None, name="source.xyz"):
        return SourceRecord(
            id=source_id or uuid4(),
            display_name=name,
            source_kind="local_file",
            created_at_utc="2026-07-24T00:00:00Z",
        )

    @staticmethod
    def revision(
        source_id,
        *,
        content="a",
        locator="C:/data/source.xyz",
        locator_kind="absolute_path",
        parse="b",
        created_entity_ids=(),
    ):
        return SourceRevision(
            id=uuid4(),
            source_id=source_id,
            content_hash=content * 64,
            byte_size=12,
            locator=locator,
            locator_kind=locator_kind,
            original_filename="source.xyz",
            reader_plugin_id="chemblender.builtin",
            reader_id="xyz",
            reader_version="2",
            reader_api_version="0.1",
            import_parameters_hash="c" * 64,
            parse_identity=parse * 64,
            created_entity_ids=created_entity_ids,
            diagnostic_ids=(),
        )

    @staticmethod
    def provenance(entity_id):
        return ProvenanceRecord(
            id=entity_id,
            revision="r1",
            producer="test",
            producer_version="1",
            source="source.xyz",
            source_hash="a" * 64,
            parent_ids=(),
            operation="parse",
            parameters=(),
        )

    def project(self, *revisions):
        sources = {
            revision.source_id: self.source(revision.source_id)
            for revision in revisions
        }
        entity_ids = {
            entity_id
            for revision in revisions
            for entity_id in revision.created_entity_ids
        }
        return QCProject(
            id=uuid4(),
            schema_version="0.2",
            sources=sources,
            source_revisions={
                revision.id: revision for revision in revisions
            },
            provenance={
                entity_id: self.provenance(entity_id)
                for entity_id in entity_ids
            },
        )

    def staged(
        self,
        *,
        content="a",
        locator="C:/incoming/source.xyz",
        locator_kind="absolute_path",
        parse="b",
        with_diagnostic=False,
        session=None,
    ):
        session = session or self.session()
        source = self.source()
        revision = self.revision(
            source.id,
            content=content,
            locator=locator,
            locator_kind=locator_kind,
            parse=parse,
        )
        diagnostics = ()
        if with_diagnostic:
            diagnostic = ImportDiagnostic(
                id=uuid4(),
                severity=DiagnosticSeverity.WARNING,
                quality_status=QualityStatus.PARTIAL,
                source_revision_id=revision.id,
                record_key=None,
                entity_id=None,
                field_path="source",
                code="test.warning",
                message="test warning",
                original_value=None,
                normalized_value=None,
                recovery_action=None,
                scientific_consequence="test data is partial",
                suggested_action=None,
            )
            diagnostics = (diagnostic,)
            revision = dataclasses.replace(
                revision, diagnostic_ids=(diagnostic.id,)
            )
        batch_id = uuid4()
        batch = ImportBatch(
            sources=(source,),
            source_revisions=(revision,),
            diagnostics=diagnostics,
        )
        session.register_result(batch_id, batch)
        source_preview = SourcePreview(
            source_id=source.id,
            source_path=(
                Path(locator)
                if Path(locator).is_absolute()
                else self.root / f"{source.id}.xyz"
            ),
            selected_reader_id="xyz",
            content_hash=revision.content_hash,
            byte_size=revision.byte_size,
            capabilities=("structure",),
            staged_batch_ids=(batch_id,),
            diagnostic_ids=tuple(item.id for item in diagnostics),
        )
        preview = ImportPreview(
            session_id=session.id,
            source_previews=(source_preview,),
            staged_batch_ids=(batch_id,),
            diagnostic_ids=tuple(item.id for item in diagnostics),
        )
        return session, preview, source_preview, revision

    def test_duplicate_action_machine_tags_are_exact(self):
        self.assertEqual(
            tuple((member.name, member.value) for member in DuplicateAction),
            (
                ("REUSE_EXISTING", "reuse_existing"),
                ("INDEPENDENT_COPY", "independent_copy"),
                ("LOCATE_EXISTING", "locate_existing"),
                ("NEW_REVISION", "new_revision"),
                ("INDEPENDENT_SOURCE", "independent_source"),
                ("IGNORE", "ignore"),
                ("LINK_EXISTING", "link_existing"),
            ),
        )
        self.assertEqual(
            tuple(
                (member.name, member.value)
                for member in ImportConflictCategory
            ),
            (
                ("SAME_PARSE_IDENTITY", "same_parse_identity"),
                (
                    "SAME_LOCATOR_CHANGED_CONTENT",
                    "same_locator_changed_content",
                ),
                ("SAME_CONTENT_RELOCATED", "same_content_relocated"),
            ),
        )

    def test_candidate_and_decision_are_frozen_exact_contracts(self):
        candidate = ImportConflictCandidate(
            source_id=uuid4(),
            revision_id=uuid4(),
            created_entity_ids=(uuid4(),),
        )
        decision = ConflictDecision(
            DuplicateAction.REUSE_EXISTING,
            existing_revision_id=candidate.revision_id,
        )

        self.assertEqual(decision.existing_revision_id, candidate.revision_id)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            candidate.revision_id = uuid4()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            decision.action = DuplicateAction.IGNORE
        with self.assertRaises(TypeError):
            ImportConflictCandidate("source", uuid4(), ())
        with self.assertRaises(ValueError):
            ConflictDecision(
                DuplicateAction.INDEPENDENT_COPY,
                existing_revision_id=candidate.revision_id,
            )
        with self.assertRaises(ValueError):
            ConflictDecision(DuplicateAction.LINK_EXISTING)
        with self.assertRaises(TypeError):
            ConflictDecision(
                DuplicateAction.REUSE_EXISTING,
                existing_revision_id="not-a-uuid",
            )

    def test_detects_three_categories_with_approved_defaults_and_actions(self):
        cases = (
            (
                "same-parse",
                self.revision(
                    uuid4(),
                    content="a",
                    locator="C:/old/source.xyz",
                    parse="b",
                ),
                {"content": "a", "locator": "C:/new/source.xyz", "parse": "b"},
                ImportConflictCategory.SAME_PARSE_IDENTITY,
                DuplicateAction.REUSE_EXISTING,
                (
                    DuplicateAction.REUSE_EXISTING,
                    DuplicateAction.INDEPENDENT_COPY,
                    DuplicateAction.LOCATE_EXISTING,
                ),
            ),
            (
                "same-locator",
                self.revision(
                    uuid4(),
                    content="a",
                    locator="C:/data/source.xyz",
                    parse="b",
                ),
                {"content": "d", "locator": "C:/data/source.xyz", "parse": "e"},
                ImportConflictCategory.SAME_LOCATOR_CHANGED_CONTENT,
                DuplicateAction.NEW_REVISION,
                (
                    DuplicateAction.NEW_REVISION,
                    DuplicateAction.INDEPENDENT_SOURCE,
                    DuplicateAction.IGNORE,
                ),
            ),
            (
                "relocated",
                self.revision(
                    uuid4(),
                    content="a",
                    locator="C:/old/source.xyz",
                    parse="b",
                ),
                {"content": "a", "locator": "D:/new/source.xyz", "parse": "e"},
                ImportConflictCategory.SAME_CONTENT_RELOCATED,
                DuplicateAction.LINK_EXISTING,
                (
                    DuplicateAction.LINK_EXISTING,
                    DuplicateAction.INDEPENDENT_COPY,
                ),
            ),
        )
        for name, existing, staged_values, category, default, allowed in cases:
            with self.subTest(name=name):
                session, preview, _, staged = self.staged(**staged_values)

                conflicts = detect_import_conflicts(
                    self.project(existing), preview, session
                )

                self.assertEqual(len(conflicts), 1)
                conflict = conflicts[0]
                self.assertEqual(conflict.staged_source_id, staged.source_id)
                self.assertEqual(conflict.staged_revision_id, staged.id)
                self.assertIs(conflict.category, category)
                self.assertIs(conflict.default_action, default)
                self.assertEqual(conflict.allowed_actions, allowed)
                self.assertEqual(
                    conflict.existing_source_ids, (existing.source_id,)
                )
                self.assertEqual(
                    conflict.existing_revision_ids, (existing.id,)
                )
                self.assertEqual(
                    conflict.candidates,
                    (
                        ImportConflictCandidate(
                            source_id=existing.source_id,
                            revision_id=existing.id,
                            created_entity_ids=existing.created_entity_ids,
                        ),
                    ),
                )

    def test_parse_identity_has_precedence_over_locator_and_content_matches(self):
        parse_match = self.revision(
            uuid4(),
            content="a",
            locator="D:/relocated/source.xyz",
            parse="b",
        )
        locator_match = self.revision(
            uuid4(),
            content="d",
            locator="C:/incoming/source.xyz",
            parse="e",
        )
        session, preview, _, _ = self.staged(
            content="a",
            locator="C:/incoming/source.xyz",
            parse="b",
        )

        conflict = detect_import_conflicts(
            self.project(parse_match, locator_match), preview, session
        )[0]

        self.assertIs(
            conflict.category, ImportConflictCategory.SAME_PARSE_IDENTITY
        )
        self.assertEqual(
            conflict.existing_revision_ids, (parse_match.id,)
        )

    def test_preserves_all_ambiguous_candidates_in_stable_order(self):
        first_entity, second_entity = uuid4(), uuid4()
        candidates = (
            self.revision(
                uuid4(),
                content="a",
                locator="C:/first/source.xyz",
                parse="b",
                created_entity_ids=(first_entity,),
            ),
            self.revision(
                uuid4(),
                content="a",
                locator="C:/second/source.xyz",
                parse="b",
                created_entity_ids=(second_entity, first_entity),
            ),
        )
        session, preview, _, _ = self.staged(
            content="a",
            locator="C:/third/source.xyz",
            parse="b",
        )

        first_run = detect_import_conflicts(
            self.project(*reversed(candidates)), preview, session
        )
        second_run = detect_import_conflicts(
            self.project(*candidates), preview, session
        )

        self.assertEqual(first_run, second_run)
        conflict = first_run[0]
        self.assertEqual(
            conflict.existing_source_ids,
            tuple(sorted((item.source_id for item in candidates), key=str)),
        )
        self.assertEqual(
            conflict.existing_revision_ids,
            tuple(sorted((item.id for item in candidates), key=str)),
        )
        self.assertEqual(
            conflict.existing_created_entity_ids,
            tuple(sorted((first_entity, second_entity), key=str)),
        )
        self.assertEqual(
            conflict.candidates,
            tuple(
                ImportConflictCandidate(
                    source_id=item.source_id,
                    revision_id=item.id,
                    created_entity_ids=item.created_entity_ids,
                )
                for item in sorted(candidates, key=lambda item: str(item.id))
            ),
        )
        self.assertIs(type(conflict.id), UUID)

    def test_conflict_id_binds_the_complete_candidate_snapshot(self):
        first = self.revision(uuid4(), parse="b")
        second = self.revision(uuid4(), parse="b")
        session, preview, _, _ = self.staged(parse="b")

        one = detect_import_conflicts(self.project(first), preview, session)[0]
        two = detect_import_conflicts(
            self.project(first, second), preview, session
        )[0]

        self.assertNotEqual(one.id, two.id)
        self.assertEqual(len(one.candidates), 1)
        self.assertEqual(len(two.candidates), 2)

    def test_no_match_produces_no_conflict(self):
        existing = self.revision(
            uuid4(),
            content="a",
            locator="C:/old/source.xyz",
            parse="b",
        )
        session, preview, _, _ = self.staged(
            content="d",
            locator="D:/new/source.xyz",
            parse="e",
        )

        self.assertEqual(
            detect_import_conflicts(self.project(existing), preview, session),
            (),
        )

    def test_locator_comparison_is_lexical_windows_stable_and_kind_aware(self):
        matching = self.revision(
            uuid4(),
            content="a",
            locator=r"c:\DATA\folder\..\source.xyz",
            parse="b",
        )
        other_kind = self.revision(
            uuid4(),
            content="a",
            locator="C:/data/source.xyz",
            locator_kind="uri",
            parse="b",
        )
        session, preview, _, _ = self.staged(
            content="d",
            locator="C:/data/./source.xyz",
            parse="e",
        )

        conflict = detect_import_conflicts(
            self.project(other_kind, matching), preview, session
        )[0]

        self.assertIs(
            conflict.category,
            ImportConflictCategory.SAME_LOCATOR_CHANGED_CONTENT,
        )
        self.assertEqual(conflict.existing_revision_ids, (matching.id,))

    def test_non_filesystem_locator_kinds_are_not_path_normalized(self):
        first = self.revision(
            uuid4(),
            locator="Class/../Entry",
            locator_kind="classpath",
        )
        second = self.revision(
            uuid4(),
            locator="Entry",
            locator_kind="classpath",
        )

        self.assertNotEqual(
            conflict_module._locator_key(first),
            conflict_module._locator_key(second),
        )

    def test_staged_revision_requires_matching_absolute_path_locator(self):
        for locator_kind in ("relative_path", "uri", "classpath"):
            with self.subTest(locator_kind=locator_kind):
                session, preview, _, _ = self.staged(
                    locator="source.xyz",
                    locator_kind=locator_kind,
                )
                with self.assertRaisesRegex(ValueError, "absolute_path"):
                    detect_import_conflicts(
                        self.project(), preview, session
                    )

    def test_detection_never_requires_a_live_locator_or_uses_mtime(self):
        missing = self.root / "missing" / "source.xyz"
        existing = self.revision(
            uuid4(),
            content="a",
            locator=str(missing),
            parse="b",
        )
        session, preview, _, _ = self.staged(
            content="d",
            locator=str(missing),
            parse="e",
        )
        before = dict(self.project(existing).source_revisions)
        project = self.project(existing)

        conflicts = detect_import_conflicts(project, preview, session)

        self.assertEqual(len(conflicts), 1)
        self.assertFalse(missing.exists())
        self.assertEqual(project.source_revisions, before)

    def test_detection_fails_closed_for_invalid_contracts_and_associations(self):
        session, preview, source_preview, revision = self.staged()
        project = self.project()
        with self.assertRaises(TypeError):
            detect_import_conflicts(object(), preview, session)
        with self.assertRaises(TypeError):
            detect_import_conflicts(project, object(), session)
        with self.assertRaises(TypeError):
            detect_import_conflicts(project, preview, object())
        with self.assertRaisesRegex(ValueError, "session"):
            detect_import_conflicts(
                project,
                dataclasses.replace(preview, session_id=uuid4()),
                session,
            )
        with self.assertRaisesRegex(ValueError, "exactly one"):
            detect_import_conflicts(
                project,
                dataclasses.replace(
                    preview,
                    source_previews=(
                        dataclasses.replace(
                            source_preview, staged_batch_ids=()
                        ),
                    ),
                ),
                session,
            )
        dangling = uuid4()
        with self.assertRaisesRegex(ValueError, "staged batch"):
            detect_import_conflicts(
                project,
                dataclasses.replace(
                    preview,
                    source_previews=(
                        dataclasses.replace(
                            source_preview, staged_batch_ids=(dangling,)
                        ),
                    ),
                    staged_batch_ids=(dangling,),
                ),
                session,
            )
        mismatched_source = self.source()
        bad_batch_id = uuid4()
        session.register_result(
            bad_batch_id,
            ImportBatch(
                sources=(mismatched_source,),
                source_revisions=(
                    dataclasses.replace(
                        revision, source_id=mismatched_source.id
                    ),
                ),
            ),
        )
        with self.assertRaisesRegex(ValueError, "source"):
            detect_import_conflicts(
                project,
                dataclasses.replace(
                    preview,
                    source_previews=(
                        dataclasses.replace(
                            source_preview, staged_batch_ids=(bad_batch_id,)
                        ),
                    ),
                    staged_batch_ids=(bad_batch_id,),
                ),
                session,
            )
        for name, changed_source in (
            (
                "reader",
                dataclasses.replace(
                    source_preview, selected_reader_id="cube"
                ),
            ),
            (
                "size",
                dataclasses.replace(
                    source_preview, byte_size=revision.byte_size + 1
                ),
            ),
            (
                "locator",
                dataclasses.replace(
                    source_preview, source_path=Path("D:/other.xyz")
                ),
            ),
        ):
            with self.subTest(name=name):
                with self.assertRaisesRegex(
                    ValueError, "reader|size|locator"
                ):
                    detect_import_conflicts(
                        project,
                        dataclasses.replace(
                            preview, source_previews=(changed_source,)
                        ),
                        session,
                    )

    def test_import_conflict_rejects_inconsistent_actions_and_ids(self):
        values = {
            "id": uuid4(),
            "staged_source_id": uuid4(),
            "staged_revision_id": uuid4(),
            "category": ImportConflictCategory.SAME_PARSE_IDENTITY,
            "default_action": DuplicateAction.REUSE_EXISTING,
            "allowed_actions": (
                DuplicateAction.REUSE_EXISTING,
                DuplicateAction.INDEPENDENT_COPY,
                DuplicateAction.LOCATE_EXISTING,
            ),
            "candidates": (
                ImportConflictCandidate(uuid4(), uuid4(), ()),
            ),
        }
        with self.assertRaises(TypeError):
            ImportConflict(**(values | {"id": "not-a-uuid"}))
        with self.assertRaises(TypeError):
            ImportConflict(
                **(values | {"default_action": "reuse_existing"})
            )
        with self.assertRaises(ValueError):
            ImportConflict(
                **(
                    values
                    | {
                        "allowed_actions": (
                            DuplicateAction.REUSE_EXISTING,
                        )
                    }
                )
            )
        with self.assertRaises(ValueError):
            ImportConflict(
                **(values | {"candidates": ()})
            )

    def test_apply_rejects_missing_unknown_and_disallowed_decisions_atomically(self):
        existing = self.revision(uuid4(), parse="b")
        project = self.project(existing)
        session, preview, _, _ = self.staged(parse="b")
        conflicts = detect_import_conflicts(
            project, preview, session
        )
        preview = self.confirmed_preview(preview, conflicts)
        project_before = dict(project.source_revisions)
        preview_before = preview
        session_ids = session.result_ids

        invalid = (
            {},
            {uuid4(): DuplicateAction.REUSE_EXISTING},
            {conflicts[0].id: DuplicateAction.NEW_REVISION},
            {conflicts[0].id: "reuse_existing"},
        )
        for decisions in invalid:
            with self.subTest(decisions=decisions):
                with self.assertRaises((TypeError, ValueError)):
                    apply_conflict_decisions(
                        preview,
                        conflicts,
                        decisions,
                        project=project,
                        session=session,
                    )
                self.assertIs(preview, preview_before)
                self.assertEqual(session.result_ids, session_ids)
                self.assertEqual(project.source_revisions, project_before)

    def test_ignore_and_reuse_filter_only_their_staged_inputs(self):
        session = self.session()
        _, first_preview, first_source, _ = self.staged(
            parse="b", with_diagnostic=True, session=session
        )
        _, second_preview, second_source, _ = self.staged(
            content="d",
            locator="D:/second.xyz",
            parse="e",
            with_diagnostic=True,
            session=session,
        )
        preview = ImportPreview(
            session_id=session.id,
            source_previews=(first_source, second_source),
            staged_batch_ids=(
                *first_preview.staged_batch_ids,
                *second_preview.staged_batch_ids,
            ),
            diagnostic_ids=(
                *first_preview.diagnostic_ids,
                *second_preview.diagnostic_ids,
            ),
        )
        existing = (
            self.revision(uuid4(), parse="b"),
            self.revision(
                uuid4(),
                content="a",
                locator="D:/second.xyz",
                parse="f",
            ),
        )
        project = self.project(*existing)
        conflicts = detect_import_conflicts(project, preview, session)
        preview = self.confirmed_preview(preview, conflicts)
        by_source = {conflict.staged_source_id: conflict for conflict in conflicts}
        project_before = dict(project.source_revisions)
        session_before = session.result_ids

        confirmed = apply_conflict_decisions(
            preview,
            conflicts,
            MappingProxyType(
                {
                    by_source[first_source.source_id].id:
                        ConflictDecision(
                            DuplicateAction.REUSE_EXISTING,
                            existing_revision_id=(
                                by_source[
                                    first_source.source_id
                                ].candidates[0].revision_id
                            ),
                        ),
                    by_source[second_source.source_id].id:
                        DuplicateAction.IGNORE,
                }
            ),
            project=project,
            session=session,
        )

        self.assertEqual(
            tuple(item.source_id for item in confirmed.source_previews),
            (first_source.source_id,),
        )
        self.assertEqual(
            confirmed.source_previews[0].staged_batch_ids, ()
        )
        self.assertEqual(confirmed.staged_batch_ids, ())
        self.assertEqual(confirmed.conflict_ids, ())
        self.assertEqual(confirmed.diagnostic_ids, ())
        self.assertEqual(confirmed.source_previews[0].diagnostic_ids, ())
        self.assertEqual(preview.source_previews, (first_source, second_source))
        self.assertEqual(session.result_ids, session_before)
        self.assertEqual(project.source_revisions, project_before)

    def test_independent_and_revision_decisions_preserve_staged_ids(self):
        cases = (
            (
                self.revision(uuid4(), parse="b"),
                {"parse": "b"},
                DuplicateAction.INDEPENDENT_COPY,
            ),
            (
                self.revision(
                    uuid4(), content="a", locator="C:/same.xyz", parse="b"
                ),
                {"content": "d", "locator": "C:/same.xyz", "parse": "e"},
                DuplicateAction.NEW_REVISION,
            ),
            (
                self.revision(
                    uuid4(), content="a", locator="C:/same.xyz", parse="b"
                ),
                {"content": "d", "locator": "C:/same.xyz", "parse": "e"},
                DuplicateAction.INDEPENDENT_SOURCE,
            ),
            (
                self.revision(
                    uuid4(), content="a", locator="C:/old.xyz", parse="b"
                ),
                {"content": "a", "locator": "D:/new.xyz", "parse": "e"},
                DuplicateAction.LINK_EXISTING,
            ),
        )
        for existing, staged_values, action in cases:
            with self.subTest(action=action):
                session, preview, _, _ = self.staged(**staged_values)
                project = self.project(existing)
                conflicts = detect_import_conflicts(
                    project, preview, session
                )
                preview = self.confirmed_preview(preview, conflicts)
                decision = action
                if action is DuplicateAction.LINK_EXISTING:
                    decision = ConflictDecision(
                        action,
                        existing_revision_id=existing.id,
                    )

                confirmed = apply_conflict_decisions(
                    preview,
                    conflicts,
                    {conflicts[0].id: decision},
                    project=project,
                    session=session,
                )

                self.assertEqual(
                    confirmed.staged_batch_ids, preview.staged_batch_ids
                )
                self.assertEqual(
                    confirmed.source_previews, preview.source_previews
                )
                self.assertEqual(confirmed.conflict_ids, ())

    def test_locate_existing_removes_only_the_staged_batch(self):
        existing = self.revision(uuid4(), parse="b")
        session, preview, source_preview, _ = self.staged(
            parse="b", with_diagnostic=True
        )
        project = self.project(existing)
        conflicts = detect_import_conflicts(
            project, preview, session
        )
        preview = self.confirmed_preview(preview, conflicts)

        confirmed = apply_conflict_decisions(
            preview,
            conflicts,
            {
                conflicts[0].id: ConflictDecision(
                    DuplicateAction.LOCATE_EXISTING,
                    existing_revision_id=existing.id,
                )
            },
            project=project,
            session=session,
        )

        self.assertEqual(
            confirmed.source_previews,
            (
                dataclasses.replace(
                    source_preview,
                    staged_batch_ids=(),
                    diagnostic_ids=(),
                ),
            ),
        )
        self.assertEqual(confirmed.staged_batch_ids, ())
        self.assertEqual(confirmed.diagnostic_ids, ())
        self.assertEqual(confirmed.source_previews[0].diagnostic_ids, ())

    def test_apply_requires_conflicts_to_be_attached_to_preview(self):
        existing = self.revision(uuid4(), parse="b")
        project = self.project(existing)
        session, preview, _, _ = self.staged(parse="b")
        conflicts = detect_import_conflicts(
            project, preview, session
        )

        with self.assertRaisesRegex(ValueError, "conflict"):
            apply_conflict_decisions(
                preview,
                conflicts,
                {conflicts[0].id: DuplicateAction.REUSE_EXISTING},
                project=project,
                session=session,
            )
        with self.assertRaisesRegex(ValueError, "conflict"):
            apply_conflict_decisions(
                dataclasses.replace(preview, conflict_ids=(uuid4(),)),
                conflicts,
                {conflicts[0].id: DuplicateAction.REUSE_EXISTING},
                project=project,
                session=session,
            )

    def test_target_actions_require_an_unambiguous_candidate_selection(self):
        first = self.revision(uuid4(), parse="b")
        second = self.revision(uuid4(), parse="b")
        project = self.project(first, second)
        session, preview, _, _ = self.staged(parse="b")
        conflicts = detect_import_conflicts(
            project, preview, session
        )
        preview = self.confirmed_preview(preview, conflicts)

        with self.assertRaisesRegex(ValueError, "candidate|target"):
            apply_conflict_decisions(
                preview,
                conflicts,
                {conflicts[0].id: DuplicateAction.REUSE_EXISTING},
                project=project,
                session=session,
            )
        with self.assertRaisesRegex(ValueError, "candidate"):
            apply_conflict_decisions(
                preview,
                conflicts,
                {
                    conflicts[0].id: ConflictDecision(
                        DuplicateAction.REUSE_EXISTING,
                        existing_revision_id=uuid4(),
                    )
                },
                project=project,
                session=session,
            )

        confirmed = apply_conflict_decisions(
            preview,
            conflicts,
            {
                conflicts[0].id: ConflictDecision(
                    DuplicateAction.REUSE_EXISTING,
                    existing_revision_id=first.id,
                )
            },
            project=project,
            session=session,
        )
        self.assertEqual(confirmed.staged_batch_ids, ())

    def test_target_action_rejects_bare_enum_for_a_unique_candidate(self):
        existing = self.revision(uuid4(), parse="b")
        project = self.project(existing)
        session, preview, _, _ = self.staged(parse="b")
        conflicts = detect_import_conflicts(project, preview, session)
        preview = self.confirmed_preview(preview, conflicts)

        with self.assertRaisesRegex(ValueError, "explicit"):
            apply_conflict_decisions(
                preview,
                conflicts,
                {conflicts[0].id: DuplicateAction.REUSE_EXISTING},
                project=project,
                session=session,
            )
        with self.assertRaises(TypeError):
            apply_conflict_decisions(
                preview,
                conflicts,
                {
                    conflicts[0].id: ConflictDecision(
                        DuplicateAction.REUSE_EXISTING,
                        existing_revision_id=existing.id,
                    )
                },
                project=object(),
                session=session,
            )

    def test_apply_rejects_conflicts_stale_against_live_project(self):
        first = self.revision(uuid4(), parse="b")
        second = self.revision(uuid4(), parse="b")
        initial_project = self.project(first)
        live_project = self.project(first, second)
        session, preview, _, _ = self.staged(parse="b")
        conflicts = detect_import_conflicts(
            initial_project, preview, session
        )
        preview = self.confirmed_preview(preview, conflicts)

        with self.assertRaisesRegex(ValueError, "live project"):
            apply_conflict_decisions(
                preview,
                conflicts,
                {
                    conflicts[0].id: ConflictDecision(
                        DuplicateAction.REUSE_EXISTING,
                        existing_revision_id=first.id,
                    )
                },
                project=live_project,
                session=session,
            )

    def test_apply_rejects_correctly_hashed_forged_candidate_snapshot(self):
        real = self.revision(uuid4(), parse="b")
        forged = self.revision(uuid4(), parse="b")
        live_project = self.project(real)
        session, preview, _, _ = self.staged(parse="b")
        conflicts = detect_import_conflicts(
            self.project(forged), preview, session
        )
        preview = self.confirmed_preview(preview, conflicts)

        with self.assertRaisesRegex(ValueError, "live project"):
            apply_conflict_decisions(
                preview,
                conflicts,
                {
                    conflicts[0].id: ConflictDecision(
                        DuplicateAction.REUSE_EXISTING,
                        existing_revision_id=forged.id,
                    )
                },
                project=live_project,
                session=session,
            )

    def test_apply_rejects_stale_or_forged_conflict_snapshots(self):
        existing = self.revision(uuid4(), parse="b")
        project = self.project(existing)
        session, preview, _, _ = self.staged(parse="b")
        conflict = detect_import_conflicts(
            project, preview, session
        )[0]
        cases = (
            dataclasses.replace(conflict, staged_revision_id=uuid4()),
            dataclasses.replace(
                conflict,
                candidates=(
                    ImportConflictCandidate(
                        source_id=uuid4(),
                        revision_id=uuid4(),
                        created_entity_ids=(),
                    ),
                ),
            ),
        )
        for forged in cases:
            with self.subTest(forged=forged):
                forged_preview = dataclasses.replace(
                    preview, conflict_ids=(forged.id,)
                )
                with self.assertRaisesRegex(
                    ValueError, "live project|staged revision|conflict id"
                ):
                    apply_conflict_decisions(
                        forged_preview,
                        (forged,),
                        {
                            forged.id: ConflictDecision(
                                DuplicateAction.REUSE_EXISTING,
                                existing_revision_id=(
                                    forged.candidates[0].revision_id
                                ),
                            )
                        },
                        project=project,
                        session=session,
                    )


if __name__ == "__main__":
    unittest.main()
