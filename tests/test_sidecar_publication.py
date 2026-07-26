import json
import os
import re
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import ChemBlender.core.storage.publication as publication
from ChemBlender.core.model import QCProject
from ChemBlender.core.session import close_session, create_session
from ChemBlender.core.sidecar import (
    SidecarIntegrityError,
    close_project,
    open_project,
    save_project,
)
from ChemBlender.core.storage.publication import (
    PublicationRecoveryReport,
    inspect_publication_orphans,
    solidify_session,
)
from tests.test_sidecar_storage import sample_project


ORPHAN_NAME = re.compile(
    r"\.project\.cbq\."
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}\.(?:tmp|backup)"
)


def tree_bytes(root):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class SidecarPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.sessions = []

    def tearDown(self):
        for session in reversed(self.sessions):
            if session.temporary_root.exists():
                close_session(session)
        self.temporary.cleanup()

    def create_session(self, project=None):
        session = create_session(
            temp_parent=self.root,
            project=project,
        )
        self.sessions.append(session)
        return session

    def test_success_returns_verified_identity_and_updates_session_path(self):
        session = self.create_session(sample_project())
        session.mark_dirty("import")
        destination = self.root / "project.cbq"

        published = solidify_session(session, destination)

        self.assertEqual(published.path, destination.resolve())
        self.assertEqual(published.project_id, session.project.id)
        self.assertEqual(published.schema_version, "0.2")
        self.assertRegex(published.manifest_sha256, r"^[0-9a-f]{64}$")
        self.assertIsInstance(published.generation_id, UUID)
        self.assertEqual(session.sidecar_path, destination.resolve())
        self.assertTrue(session.dirty)
        restored = open_project(
            destination,
            expected_project_id=session.project.id,
            expected_schema_version="0.2",
            verify_arrays=True,
        )
        close_project(restored)
        self.assertFalse(inspect_publication_orphans(destination).has_orphans)
        with self.assertRaises(FrozenInstanceError):
            published.schema_version = "changed"

    def test_opt_in_transfers_exact_verified_project_ownership(self):
        session = self.create_session(sample_project())
        destination = self.root / "project.cbq"

        published = solidify_session(
            session,
            destination,
            transfer_verified_project=True,
        )

        try:
            self.assertIsInstance(published.project, QCProject)
            self.assertIsNot(published.project, session.project)
            self.assertEqual(published.project.id, published.project_id)
            self.assertEqual(
                published.project.schema_version,
                published.schema_version,
            )
        finally:
            close_project(published.project)

    def test_default_publication_does_not_transfer_open_project(self):
        session = self.create_session(sample_project())

        published = solidify_session(session, self.root / "project.cbq")

        self.assertIsNone(published.project)

    def test_new_destination_final_verify_failure_leaves_only_stage_orphan(self):
        session = self.create_session(sample_project())
        destination = self.root / "project.cbq"

        with patch(
            "ChemBlender.core.storage.publication._verify_published_project",
            side_effect=SidecarIntegrityError("final verification failed"),
        ):
            with self.assertRaisesRegex(
                SidecarIntegrityError,
                "final verification failed",
            ):
                solidify_session(session, destination)

        self.assertFalse(destination.exists())
        self.assertIsNone(session.sidecar_path)
        report = inspect_publication_orphans(destination)
        self.assertEqual(len(report.temporary_paths), 1)
        self.assertEqual(report.backup_paths, ())
        self.assertEqual(report.temporary_paths[0].parent, destination.parent)
        self.assertRegex(report.temporary_paths[0].name, ORPHAN_NAME)

    def test_existing_destination_final_verify_failure_restores_exact_tree(self):
        destination = self.root / "project.cbq"
        old_session = self.create_session(sample_project())
        solidify_session(old_session, destination)
        old_tree = tree_bytes(destination)
        new_project = QCProject(id=uuid4(), schema_version="0.2")
        new_session = self.create_session(new_project)

        with patch(
            "ChemBlender.core.storage.publication._verify_published_project",
            side_effect=SidecarIntegrityError("final verification failed"),
        ):
            with self.assertRaises(SidecarIntegrityError):
                solidify_session(new_session, destination)

        self.assertEqual(tree_bytes(destination), old_tree)
        restored = open_project(destination, expected_project_id=old_session.project.id)
        close_project(restored)
        self.assertIsNone(new_session.sidecar_path)
        report = inspect_publication_orphans(destination)
        self.assertEqual(len(report.temporary_paths), 1)
        self.assertEqual(report.backup_paths, ())

    def test_existing_destination_is_unchanged_on_preverification_failure(self):
        destination = self.root / "project.cbq"
        old_session = self.create_session(sample_project())
        solidify_session(old_session, destination)
        old_tree = tree_bytes(destination)
        new_session = self.create_session(
            QCProject(id=uuid4(), schema_version="0.2")
        )

        with patch(
            "ChemBlender.core.storage.publication._verify_staged_project",
            side_effect=SidecarIntegrityError("staged verification failed"),
        ):
            with self.assertRaisesRegex(
                SidecarIntegrityError,
                "staged verification failed",
            ):
                solidify_session(new_session, destination)

        self.assertEqual(tree_bytes(destination), old_tree)
        self.assertIsNone(new_session.sidecar_path)
        report = inspect_publication_orphans(destination)
        self.assertEqual(len(report.temporary_paths), 1)
        self.assertEqual(report.backup_paths, ())

    def test_publish_rename_failure_restores_existing_destination(self):
        destination = self.root / "project.cbq"
        old_session = self.create_session(sample_project())
        solidify_session(old_session, destination)
        old_tree = tree_bytes(destination)
        new_session = self.create_session(
            QCProject(id=uuid4(), schema_version="0.2")
        )
        real_replace = os.replace

        def fail_candidate_publish(source, target):
            if Path(source).suffix == ".tmp" and Path(target) == destination:
                raise OSError("candidate publish failed")
            return real_replace(source, target)

        with patch(
            "ChemBlender.core.storage.publication.os.replace",
            side_effect=fail_candidate_publish,
        ):
            with self.assertRaisesRegex(OSError, "candidate publish failed"):
                solidify_session(new_session, destination)

        self.assertEqual(tree_bytes(destination), old_tree)
        self.assertIsNone(new_session.sidecar_path)
        report = inspect_publication_orphans(destination)
        self.assertEqual(len(report.temporary_paths), 1)
        self.assertEqual(report.backup_paths, ())

    def test_blocked_candidate_evacuation_preserves_candidate_and_old_backup(self):
        destination = self.root / "project.cbq"
        old_session = self.create_session(sample_project())
        solidify_session(old_session, destination)
        old_tree = tree_bytes(destination)
        new_session = self.create_session(
            QCProject(id=uuid4(), schema_version="0.2")
        )
        publication_error = SidecarIntegrityError("final verification failed")
        rollback_error = OSError("candidate evacuation blocked")
        real_replace = os.replace
        candidate_tree = {}

        def block_evacuation(source, target):
            if Path(source) == destination and Path(target).suffix == ".tmp":
                candidate_tree.update(tree_bytes(destination))
                raise rollback_error
            return real_replace(source, target)

        with (
            patch(
                "ChemBlender.core.storage.publication._verify_published_project",
                side_effect=publication_error,
            ),
            patch(
                "ChemBlender.core.storage.publication.os.replace",
                side_effect=block_evacuation,
            ),
            patch(
                "ChemBlender.core.storage.publication.shutil.rmtree"
            ) as recursive_delete,
        ):
            with self.assertRaises(Exception) as captured:
                solidify_session(new_session, destination)

        error = captured.exception
        self.assertIsInstance(error, publication.PublicationRecoveryError)
        self.assertIs(error.publication_error, publication_error)
        self.assertIs(error.rollback_error, rollback_error)
        self.assertIs(error.__cause__, publication_error)
        self.assertEqual(error.destination_path, destination)
        self.assertEqual(error.candidate_path, destination)
        self.assertEqual(tree_bytes(destination), candidate_tree)
        self.assertEqual(tree_bytes(error.backup_path), old_tree)
        self.assertEqual(error.report.backup_paths, (error.backup_path,))
        recursive_delete.assert_not_called()

    def test_blocked_new_candidate_evacuation_preserves_destination(self):
        destination = self.root / "project.cbq"
        session = self.create_session(sample_project())
        publication_error = SidecarIntegrityError("final verification failed")
        rollback_error = OSError("candidate evacuation blocked")
        real_replace = os.replace
        candidate_tree = {}

        def block_evacuation(source, target):
            if Path(source) == destination and Path(target).suffix == ".tmp":
                candidate_tree.update(tree_bytes(destination))
                raise rollback_error
            return real_replace(source, target)

        with (
            patch(
                "ChemBlender.core.storage.publication._verify_published_project",
                side_effect=publication_error,
            ),
            patch(
                "ChemBlender.core.storage.publication.os.replace",
                side_effect=block_evacuation,
            ),
            patch(
                "ChemBlender.core.storage.publication.shutil.rmtree"
            ) as recursive_delete,
        ):
            with self.assertRaises(Exception) as captured:
                solidify_session(session, destination)

        error = captured.exception
        self.assertIsInstance(error, publication.PublicationRecoveryError)
        self.assertIs(error.publication_error, publication_error)
        self.assertIs(error.rollback_error, rollback_error)
        self.assertEqual(error.candidate_path, destination)
        self.assertIsNone(error.backup_path)
        self.assertEqual(tree_bytes(destination), candidate_tree)
        recursive_delete.assert_not_called()

    def test_different_valid_generation_is_preserved_as_concurrent_replacement(self):
        destination = self.root / "project.cbq"
        old_session = self.create_session(sample_project())
        solidify_session(old_session, destination)
        old_tree = tree_bytes(destination)
        new_session = self.create_session(
            QCProject(id=uuid4(), schema_version="0.2")
        )
        candidate_orphan = self.root / f".project.cbq.{uuid4()}.tmp"

        def replace_final_generation(path, project_id):
            os.replace(path, candidate_orphan)
            publication._write_project_tree(path, new_session.project)
            return publication._verified_project(path, project_id)

        with patch(
            "ChemBlender.core.storage.publication._verify_published_project",
            side_effect=replace_final_generation,
        ):
            with self.assertRaises(Exception) as captured:
                solidify_session(new_session, destination)

        error = captured.exception
        self.assertIsInstance(error, publication.PublicationRecoveryError)
        self.assertEqual(error.candidate_path, destination)
        self.assertEqual(tree_bytes(error.backup_path), old_tree)
        replacement = open_project(destination, expected_project_id=new_session.project.id)
        close_project(replacement)
        self.assertTrue(candidate_orphan.is_dir())
        self.assertIn(candidate_orphan.resolve(), error.report.temporary_paths)
        self.assertIn(error.backup_path, error.report.backup_paths)

    def test_recovery_report_failure_does_not_mask_publication_errors(self):
        destination = self.root / "project.cbq"
        session = self.create_session(sample_project())
        publication_error = SidecarIntegrityError("final verification failed")
        rollback_error = OSError("candidate evacuation blocked")
        real_replace = os.replace

        def block_evacuation(source, target):
            if Path(source) == destination and Path(target).suffix == ".tmp":
                raise rollback_error
            return real_replace(source, target)

        with (
            patch(
                "ChemBlender.core.storage.publication._verify_published_project",
                side_effect=publication_error,
            ),
            patch(
                "ChemBlender.core.storage.publication.os.replace",
                side_effect=block_evacuation,
            ),
            patch(
                "ChemBlender.core.storage.publication._orphan_report",
                side_effect=OSError("cannot scan parent"),
            ),
        ):
            with self.assertRaises(Exception) as captured:
                solidify_session(session, destination)

        error = captured.exception
        self.assertIsInstance(error, publication.PublicationRecoveryError)
        self.assertIs(error.publication_error, publication_error)
        self.assertIs(error.rollback_error, rollback_error)
        self.assertEqual(error.candidate_path, destination)
        self.assertEqual(error.report.destination, destination)

    def test_backup_restore_failure_preserves_stage_and_original_error(self):
        for failure_phase in ("publish_rename", "final_verify"):
            with self.subTest(failure_phase=failure_phase):
                case_root = self.root / failure_phase
                case_root.mkdir()
                destination = case_root / "project.cbq"
                old_session = self.create_session(sample_project())
                solidify_session(old_session, destination)
                old_tree = tree_bytes(destination)
                new_session = self.create_session(
                    QCProject(id=uuid4(), schema_version="0.2")
                )
                publication_error = (
                    OSError("candidate publish failed")
                    if failure_phase == "publish_rename"
                    else SidecarIntegrityError("final verification failed")
                )
                rollback_error = OSError("backup restore failed")
                real_replace = os.replace

                def fail_publish_or_restore(source, target):
                    source = Path(source)
                    target = Path(target)
                    if (
                        failure_phase == "publish_rename"
                        and source.suffix == ".tmp"
                        and target == destination
                    ):
                        raise publication_error
                    if source.suffix == ".backup" and target == destination:
                        raise rollback_error
                    return real_replace(source, target)

                final_patch = (
                    patch(
                        "ChemBlender.core.storage.publication._verify_published_project",
                        side_effect=publication_error,
                    )
                    if failure_phase == "final_verify"
                    else patch(
                        "ChemBlender.core.storage.publication._verify_published_project",
                        wraps=publication._verify_published_project,
                    )
                )
                with (
                    final_patch,
                    patch(
                        "ChemBlender.core.storage.publication.os.replace",
                        side_effect=fail_publish_or_restore,
                    ),
                ):
                    with self.assertRaises(Exception) as captured:
                        solidify_session(new_session, destination)

                error = captured.exception
                self.assertIsInstance(error, publication.PublicationRecoveryError)
                self.assertIs(error.publication_error, publication_error)
                self.assertIs(error.rollback_error, rollback_error)
                self.assertFalse(destination.exists())
                self.assertTrue(error.candidate_path.is_dir())
                self.assertEqual(tree_bytes(error.backup_path), old_tree)
                self.assertIn(error.candidate_path, error.report.temporary_paths)
                self.assertIn(error.backup_path, error.report.backup_paths)

    def test_verified_metadata_comes_from_the_validated_manifest_read(self):
        root = self.root / "metadata.cbq"
        project = sample_project()
        save_project(root, project)
        manifest_path = root / "manifest.json"
        original_read_text = Path.read_text
        actual = json.loads(original_read_text(manifest_path, encoding="utf-8"))
        forged = dict(actual)
        forged["project_schema_version"] = "forged"
        forged["manifest_sha256"] = "f" * 64
        forged["generation_id"] = str(uuid4())
        reads = 0

        def swap_second_read(path, *args, **kwargs):
            nonlocal reads
            if Path(path) == manifest_path:
                reads += 1
                if reads == 2:
                    return json.dumps(forged)
            return original_read_text(path, *args, **kwargs)

        with patch.object(Path, "read_text", new=swap_second_read):
            verified = publication._verified_project(root, project.id)

        self.assertEqual(reads, 1)
        self.assertEqual(verified.schema_version, actual["project_schema_version"])
        self.assertEqual(verified.manifest_sha256, actual["manifest_sha256"])
        self.assertEqual(verified.generation_id, UUID(actual["generation_id"]))

    def test_backup_cleanup_failure_is_success_and_reports_orphan(self):
        destination = self.root / "project.cbq"
        first = self.create_session(sample_project())
        second = self.create_session(
            QCProject(id=uuid4(), schema_version="0.2")
        )
        solidify_session(first, destination)

        with patch(
            "ChemBlender.core.storage.publication.shutil.rmtree",
            side_effect=OSError("backup cleanup blocked"),
        ):
            published = solidify_session(second, destination)

        self.assertEqual(published.project_id, second.project.id)
        self.assertEqual(second.sidecar_path, destination)
        report = inspect_publication_orphans(destination)
        self.assertEqual(len(report.backup_paths), 1)
        architecture = (
            Path(__file__).resolve().parents[1]
            / "docs/quantum-visualization/2.3.0/architecture/cbq-sidecar-v0.2.md"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "backup 清理失败不使已复验的 publication 失败",
            architecture,
        )

    def test_repeated_success_replaces_destination_without_open_handles(self):
        destination = self.root / "project.cbq"
        first = self.create_session(sample_project())
        second = self.create_session(
            QCProject(id=uuid4(), schema_version="0.2")
        )

        solidify_session(first, destination)
        second_result = solidify_session(second, destination)

        restored = open_project(
            destination,
            expected_project_id=second.project.id,
            verify_arrays=True,
        )
        self.assertEqual(restored.id, second_result.project_id)
        close_project(restored)
        self.assertFalse(inspect_publication_orphans(destination).has_orphans)

    def test_destination_contract_rejects_bad_suffix_parent_and_link(self):
        session = self.create_session()
        with self.assertRaisesRegex(TypeError, "ProjectSession"):
            solidify_session(object(), self.root / "project.cbq")
        with self.assertRaisesRegex(ValueError, r"\.cbq"):
            save_project(self.root / "internal.tmp", session.project)
        with self.assertRaisesRegex(ValueError, r"\.cbq"):
            solidify_session(session, self.root / "project.data")
        with self.assertRaisesRegex(ValueError, "parent"):
            solidify_session(session, self.root / "missing" / "project.cbq")
        destination = self.root / "project.cbq"
        with patch(
            "ChemBlender.core.storage.publication._is_link_like",
            return_value=True,
        ):
            with self.assertRaisesRegex(ValueError, "link"):
                solidify_session(session, destination)

    def test_orphan_inspection_is_strict_sorted_and_non_destructive(self):
        destination = self.root / "project.cbq"
        first = self.root / f".project.cbq.{uuid4()}.tmp"
        second = self.root / f".project.cbq.{uuid4()}.backup"
        for path in (second, first):
            path.mkdir()
            (path / "keep.txt").write_text("keep", encoding="utf-8")
        ambiguous = (
            self.root / ".project.cbq.not-a-uuid.tmp",
            self.root / f".other.cbq.{uuid4()}.tmp",
            self.root / f".project.cbq.{uuid4()}.partial",
            self.root / f"project.cbq.{uuid4()}.backup",
        )
        for path in ambiguous:
            path.mkdir()

        report = inspect_publication_orphans(destination)

        self.assertIsInstance(report, PublicationRecoveryReport)
        self.assertEqual(report.destination, destination.resolve())
        self.assertEqual(report.temporary_paths, tuple(sorted((first.resolve(),))))
        self.assertEqual(report.backup_paths, tuple(sorted((second.resolve(),))))
        self.assertTrue(report.has_orphans)
        for path in (*report.temporary_paths, *report.backup_paths, *ambiguous):
            self.assertTrue(path.exists())
        with self.assertRaises(FrozenInstanceError):
            report.destination = self.root


if __name__ == "__main__":
    unittest.main()
