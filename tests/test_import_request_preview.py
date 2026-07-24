import dataclasses
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from ChemBlender.core.import_pipeline import (
    ImportPreview,
    ImportRequest,
    ImportSource,
    ReaderOverride,
    SourcePreview,
    StagedImportSession,
    ValidationMode,
)
from ChemBlender.core.model import ImportBatch, QCProject


OWNER_MARKER = ".chemblender-import-owner"


class ImportRequestTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source_path = self.root / "source.xyz"
        self.source_path.write_text("1\nfixture\nH 0 0 0\n", encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def source(self, path=None):
        return ImportSource(path=path or self.source_path)

    def test_defaults_to_balanced_recovery(self):
        request = ImportRequest(sources=(self.source(),))

        self.assertIs(request.validation_mode, ValidationMode.BALANCED)

    def test_validation_mode_machine_contract_is_exact(self):
        self.assertEqual(
            tuple((member.name, member.value) for member in ValidationMode),
            (
                ("STRICT", "strict"),
                ("BALANCED", "balanced"),
                ("MAXIMUM", "maximum"),
            ),
        )

    def test_requires_non_empty_exact_tuple_of_sources(self):
        with self.assertRaises(ValueError):
            ImportRequest(sources=())
        with self.assertRaises(TypeError):
            ImportRequest(sources=[self.source()])

    def test_canonicalizes_source_paths_and_rejects_duplicates(self):
        nested = self.root / "nested"
        nested.mkdir()
        first = self.source()
        duplicate = self.source(nested / ".." / self.source_path.name)

        self.assertEqual(first.path, self.source_path.resolve(strict=True))
        self.assertEqual(duplicate.path, first.path)
        with self.assertRaisesRegex(ValueError, "unique"):
            ImportRequest(sources=(first, duplicate))

    def test_rejects_directory_and_missing_sources_without_scanning(self):
        with self.assertRaisesRegex(ValueError, "file"):
            self.source(self.root)
        with self.assertRaises(FileNotFoundError):
            self.source(self.root / "missing.xyz")

    def test_reader_override_must_target_an_included_source(self):
        source = self.source()
        outside = ReaderOverride(source_id=uuid4(), reader_id="xyz")

        with self.assertRaisesRegex(ValueError, "included source"):
            ImportRequest(sources=(source,), reader_overrides=(outside,))

        request = ImportRequest(
            sources=(source,),
            reader_overrides=(
                ReaderOverride(source_id=source.id, reader_id="xyz"),
            ),
        )
        self.assertEqual(request.reader_overrides[0].source_id, source.id)

    def test_rejects_implicit_coercion_and_duplicate_overrides(self):
        source = self.source()
        override = ReaderOverride(source_id=source.id, reader_id="xyz")

        with self.assertRaises(TypeError):
            ImportRequest(sources=(source,), validation_mode="balanced_recovery")
        with self.assertRaises(TypeError):
            ImportRequest(sources=(source,), reader_overrides=[override])
        with self.assertRaisesRegex(ValueError, "one override"):
            ImportRequest(
                sources=(source,),
                reader_overrides=(override, override),
            )
        with self.assertRaises(TypeError):
            ImportSource(path=str(self.source_path))

    def test_rejects_duplicate_source_ids(self):
        source_id = uuid4()
        second_path = self.root / "second.xyz"
        second_path.write_text("1\nfixture\nHe 0 0 0\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "source ids"):
            ImportRequest(
                sources=(
                    ImportSource(path=self.source_path, id=source_id),
                    ImportSource(path=second_path, id=source_id),
                ),
            )


class ImportPreviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name, "source.xyz")
        self.path.write_text("1\nfixture\nH 0 0 0\n", encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def source_preview(self):
        return SourcePreview(
            source_id=uuid4(),
            source_path=self.path.resolve(strict=True),
            selected_reader_id="xyz",
            content_hash="a" * 64,
            byte_size=self.path.stat().st_size,
            capabilities=("structure",),
            staged_batch_ids=(uuid4(),),
            diagnostic_ids=(uuid4(),),
        )

    def test_preview_contains_only_immutable_source_rows_and_ids(self):
        source_preview = self.source_preview()
        preview = ImportPreview(
            session_id=uuid4(),
            source_previews=(source_preview,),
            staged_batch_ids=source_preview.staged_batch_ids,
            conflict_ids=(uuid4(),),
            grouping_suggestion_ids=(uuid4(),),
            diagnostic_ids=source_preview.diagnostic_ids,
            default_view_plan_ids=(uuid4(),),
        )

        self.assertEqual(preview.source_previews, (source_preview,))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            preview.session_id = uuid4()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            source_preview.byte_size = 0

    def test_preview_rejects_mutable_project_and_blender_like_values(self):
        project = QCProject(id=uuid4(), schema_version="0.2")

        with self.assertRaises(TypeError):
            ImportPreview(
                session_id=uuid4(),
                source_previews=(project,),
            )
        with self.assertRaises(TypeError):
            ImportPreview(
                session_id=uuid4(),
                source_previews=(self.source_preview(),),
                conflict_ids=(object(),),
            )

    def test_source_preview_rejects_relative_or_mutable_values(self):
        relative = Path("source.xyz")
        with self.assertRaisesRegex(ValueError, "absolute"):
            SourcePreview(source_id=uuid4(), source_path=relative)
        with self.assertRaises(TypeError):
            SourcePreview(
                source_id=uuid4(),
                source_path=self.path.resolve(strict=True),
                capabilities=["structure"],
            )

    def test_source_preview_canonicalizes_without_requiring_a_live_file(self):
        source_path = self.path.parent / "nested" / ".." / "missing.xyz"

        preview = SourcePreview(
            source_id=uuid4(),
            source_path=source_path,
        )

        self.assertEqual(
            preview.source_path,
            source_path.resolve(strict=False),
        )


class StagedImportSessionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.parent = Path(self.temporary.name)
        self.sessions = []

    def tearDown(self):
        for session in reversed(self.sessions):
            try:
                session.discard()
            except RuntimeError:
                pass
        self.temporary.cleanup()

    def create_session(self):
        session = StagedImportSession.create(temp_parent=self.parent)
        self.sessions.append(session)
        return session

    def test_create_uses_exclusive_owned_root_marker_and_artifacts(self):
        session = self.create_session()

        self.assertEqual(session.root.name, str(session.id))
        self.assertEqual(
            (session.root / OWNER_MARKER).read_text(encoding="utf-8"),
            f"{session.id}\n",
        )
        self.assertEqual(session.artifact_root, session.root / "artifacts")
        self.assertTrue(session.artifact_root.is_dir())
        self.assertEqual(session.result_ids, ())

    def test_result_registry_has_minimal_typed_access(self):
        session = self.create_session()
        result_id = uuid4()
        batch = ImportBatch()

        session.register_result(result_id, batch)

        self.assertEqual(session.result_ids, (result_id,))
        self.assertIs(session.result(result_id), batch)
        with self.assertRaisesRegex(ValueError, "already registered"):
            session.register_result(result_id, batch)
        with self.assertRaises(TypeError):
            session.register_result("not-a-uuid", batch)
        with self.assertRaises(TypeError):
            session.register_result(uuid4(), object())

    def test_discard_removes_only_owned_root_and_is_idempotent(self):
        session = self.create_session()
        root = session.root
        outside = self.parent / "keep.txt"
        outside.write_text("keep", encoding="utf-8")

        session.discard()
        session.discard()

        self.assertFalse(root.exists())
        self.assertEqual(outside.read_text(encoding="utf-8"), "keep")

    def test_discard_refuses_tampered_marker_and_preserves_contents(self):
        session = self.create_session()
        payload = session.root / "keep.txt"
        payload.write_text("keep", encoding="utf-8")
        (session.root / OWNER_MARKER).write_text(
            f"{uuid4()}\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(RuntimeError, "marker"):
            session.discard()

        self.assertEqual(payload.read_text(encoding="utf-8"), "keep")

    def test_discard_refuses_same_content_marker_replacement(self):
        session = self.create_session()
        marker = session.root / OWNER_MARKER
        marker.unlink()
        marker.write_bytes(f"{session.id}\n".encode("utf-8"))
        payload = session.root / "keep.txt"
        payload.write_text("keep", encoding="utf-8")

        with self.assertRaisesRegex(RuntimeError, "marker"):
            session.discard()

        self.assertEqual(payload.read_text(encoding="utf-8"), "keep")

    def test_discard_refuses_same_path_root_replacement(self):
        session = self.create_session()
        original = self.parent / "original-root"
        session.root.rename(original)
        session.root.mkdir()
        (session.root / OWNER_MARKER).write_text(
            f"{session.id}\n",
            encoding="utf-8",
        )
        (session.root / "keep.txt").write_text("keep", encoding="utf-8")

        with self.assertRaisesRegex(RuntimeError, "unowned"):
            session.discard()

        self.assertEqual(
            (session.root / "keep.txt").read_text(encoding="utf-8"),
            "keep",
        )

    def test_discard_refuses_same_path_artifact_replacement(self):
        session = self.create_session()
        original = session.root / "original-artifacts"
        session.artifact_root.rename(original)
        session.artifact_root.mkdir()
        payload = session.artifact_root / "keep.txt"
        payload.write_text("keep", encoding="utf-8")

        with self.assertRaisesRegex(RuntimeError, "artifact"):
            session.discard()

        self.assertEqual(payload.read_text(encoding="utf-8"), "keep")

    def test_discard_refuses_reassigned_external_root(self):
        session = self.create_session()
        external = self.parent / "external"
        external.mkdir()
        (external / OWNER_MARKER).write_text(
            f"{session.id}\n",
            encoding="utf-8",
        )
        payload = external / "keep.txt"
        payload.write_text("keep", encoding="utf-8")
        session._root = external

        with self.assertRaisesRegex(RuntimeError, "unowned"):
            session.discard()

        self.assertEqual(payload.read_text(encoding="utf-8"), "keep")

    @unittest.skipUnless(
        os.name == "nt" and hasattr(Path, "is_junction"),
        "Windows junction support is required",
    )
    def test_discard_refuses_junction_root_without_touching_target(self):
        session = self.create_session()
        original = self.parent / "original-root"
        session.root.rename(original)
        target = self.parent / "junction-target"
        target.mkdir()
        (target / OWNER_MARKER).write_text(
            f"{session.id}\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                "cmd.exe",
                "/d",
                "/c",
                "mklink",
                "/J",
                str(session.root),
                str(target),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        try:
            with self.assertRaisesRegex(RuntimeError, "unsafe staging root"):
                session.discard()
        finally:
            session.root.rmdir()

        self.assertTrue((target / OWNER_MARKER).is_file())

    @unittest.skipUnless(
        os.name == "nt" and hasattr(Path, "is_junction"),
        "Windows junction support is required",
    )
    def test_discard_refuses_junction_artifact_without_touching_target(self):
        session = self.create_session()
        original = session.root / "original-artifacts"
        session.artifact_root.rename(original)
        target = self.parent / "artifact-target"
        target.mkdir()
        payload = target / "keep.txt"
        payload.write_text("keep", encoding="utf-8")
        result = subprocess.run(
            [
                "cmd.exe",
                "/d",
                "/c",
                "mklink",
                "/J",
                str(session.artifact_root),
                str(target),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        try:
            with self.assertRaisesRegex(RuntimeError, "artifact"):
                session.discard()
        finally:
            session.artifact_root.rmdir()

        self.assertEqual(payload.read_text(encoding="utf-8"), "keep")

    def test_result_access_rejects_discarded_session(self):
        session = self.create_session()
        result_id = uuid4()
        session.register_result(result_id, ImportBatch())
        session.discard()

        with self.assertRaisesRegex(RuntimeError, "discarded"):
            session.register_result(uuid4(), ImportBatch())
        with self.assertRaisesRegex(RuntimeError, "discarded"):
            session.result(result_id)


class ImportPipelineBoundaryTests(unittest.TestCase):
    def test_package_exports_current_preflight_contracts(self):
        from ChemBlender.core import import_pipeline

        self.assertEqual(
            set(import_pipeline.__all__),
            {
                "ConflictDecision",
                "CalculationGroup",
                "DuplicateAction",
                "GroupingEvidence",
                "GroupingDecision",
                "ImportCommitDecisions",
                "ImportCommitResult",
                "ImportConflict",
                "ImportConflictCandidate",
                "ImportConflictCategory",
                "ImportPreview",
                "ImportCancelled",
                "ImportRequest",
                "ImportSource",
                "ReaderOverride",
                "SourceGroupSuggestion",
                "SourcePreview",
                "StagedImportSession",
                "ValidationMode",
                "apply_conflict_decisions",
                "commit_import_preview",
                "detect_import_conflicts",
                "preflight_import",
                "suggest_source_groups",
            },
        )

    def test_fresh_import_does_not_load_blender_or_optional_stacks(self):
        code = """
import sys
import ChemBlender.core.import_pipeline
blocked = {'bpy', 'cclib', 'iodata', 'gbasis', 'ase', 'pymatgen'}
loaded = sorted(blocked.intersection(sys.modules))
assert loaded == [], loaded
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
