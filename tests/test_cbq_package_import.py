import dataclasses
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import numpy

from cbq_core.model import ArrayData, ImportBatch, QCProject, Structure
from cbq_core.package_import import import_package, preview_package
from cbq_core.session import ProjectSession
from cbq_core.sidecar import close_project, open_project, save_project
from cbq_core.sidecar_migrations import CURRENT_PROJECT_SCHEMA_VERSION
from cbq_core.storage.publication import PublicationCancelled


class CBQPackageImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.session = ProjectSession(uuid4(), QCProject(uuid4(), CURRENT_PROJECT_SCHEMA_VERSION),
                                      self.root / 'owned')
        self.structure = Structure(uuid4(), '1', (1,),
            ArrayData(numpy.array([[1., 2., 3.]]), ('atom', 'xyz'), 'angstrom'))
        self.input = self.root / 'input.cbq'
        self.project = QCProject(uuid4(), CURRENT_PROJECT_SCHEMA_VERSION)
        self.project.commit(ImportBatch(structures=(self.structure,)))
        save_project(self.input, self.project)

    def tearDown(self):
        close_project(self.session.project)
        self.temp.cleanup()

    def test_add_reuse_and_reopen_without_input(self):
        original_project_id = self.session.project.id
        result = import_package(self.session, self.input)
        self.assertEqual(result.counts['new'], 1)
        self.assertEqual(self.session.project.id, original_project_id)
        owned = self.session.sidecar_path
        before = (owned / 'manifest.json').read_bytes()
        result = import_package(self.session, self.input)
        self.assertEqual(result.counts['new'], 0)
        self.assertEqual(result.counts['reused'], 1)
        self.assertEqual((owned / 'manifest.json').read_bytes(), before)
        shutil.rmtree(self.input)
        close_project(self.session.project)
        self.session.project = open_project(owned)
        numpy.testing.assert_array_equal(
            self.session.project.structures[self.structure.id].coordinates.values,
            self.structure.coordinates.values)

    def test_duplicate_sources_require_confirmation_once_then_reuse(self):
        from tests.test_import_conflicts import ImportConflictTests
        paths = []
        for index in range(3):
            source = ImportConflictTests.source(name=f"copy-{index}.xyz")
            structure = dataclasses.replace(self.structure, id=uuid4())
            revision = ImportConflictTests.revision(source.id,
                created_entity_ids=(structure.id,))
            project = QCProject(uuid4(), CURRENT_PROJECT_SCHEMA_VERSION)
            project.commit(ImportBatch(structures=(structure,), sources=(source,),
                                       source_revisions=(revision,)))
            paths.append(save_project(self.root / f"copy-{index}.cbq", project))
        import_package(self.session, paths[0])
        current = self.session.project
        before = (self.session.sidecar_path / "manifest.json").read_bytes()
        preview = preview_package(self.session, paths[1])
        self.assertEqual(len(preview.source_duplicates), 1)
        with self.assertRaisesRegex(ValueError, "explicit confirmation"):
            import_package(self.session, paths[1])
        self.assertIs(self.session.project, current)
        self.assertEqual((self.session.sidecar_path / "manifest.json").read_bytes(), before)
        import_package(self.session, paths[1], allow_duplicate_sources=True)
        self.assertEqual(len(self.session.project.structures), 2)
        self.assertEqual(len(self.session.project.sources), 2)
        before = (self.session.sidecar_path / "manifest.json").read_bytes()
        for path in paths[:2]:
            result = import_package(self.session, path)
            self.assertFalse(result.source_duplicates)
            self.assertEqual(result.counts["new"], 0)
            self.assertEqual(result.counts["reused"], 3)
        with self.assertRaisesRegex(ValueError, "explicit confirmation"):
            import_package(self.session, paths[2])
        self.assertEqual(len(self.session.project.sources), 2)
        self.assertEqual((self.session.sidecar_path / "manifest.json").read_bytes(), before)

    def test_same_uuid_different_array_rejects_entire_import(self):
        import_package(self.session, self.input)
        before = (self.session.sidecar_path / 'manifest.json').read_bytes()
        changed = dataclasses.replace(self.structure, coordinates=ArrayData(
            numpy.array([[8., 2., 3.]]), ('atom', 'xyz'), 'angstrom'))
        conflict = QCProject(uuid4(), CURRENT_PROJECT_SCHEMA_VERSION)
        conflict.commit(ImportBatch(structures=(changed, dataclasses.replace(self.structure, id=uuid4()))))
        path = self.root / 'conflict.cbq'
        save_project(path, conflict)
        self.assertEqual(len(preview_package(self.session, path).conflicts), 1)
        with self.assertRaisesRegex(ValueError, 'different content'):
            import_package(self.session, path)
        self.assertEqual(len(self.session.project.structures), 1)
        self.assertEqual((self.session.sidecar_path / 'manifest.json').read_bytes(), before)

    def test_cancel_and_failure_do_not_replace_live_project(self):
        previous = self.session.project
        with self.assertRaises(PublicationCancelled):
            import_package(self.session, self.input, is_cancelled=lambda: True)
        self.assertIs(self.session.project, previous)
        self.assertIsNone(self.session.sidecar_path)
        with patch('cbq_core.package_import.solidify_session', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError, 'disk full'):
                import_package(self.session, self.input)
        self.assertIs(self.session.project, previous)
        self.assertFalse(self.session.dirty)

    def test_existing_project_survives_each_publication_failure_and_retry(self):
        from cbq_core.storage import publication
        from cbq_core.sidecar import SidecarIntegrityError
        import_package(self.session, self.input)
        original = self.session.project
        destination = self.session.sidecar_path
        dirty = self.session.dirty_reasons
        before = {str(p.relative_to(destination)): p.read_bytes()
                  for p in destination.rglob("*") if p.is_file()}
        other = dataclasses.replace(self.structure, id=uuid4())
        incoming = QCProject(uuid4(), CURRENT_PROJECT_SCHEMA_VERSION)
        incoming.commit(ImportBatch(structures=(other,)))
        source = save_project(self.root / "second.cbq", incoming)
        for hook in ("_write_project_tree", "_verify_staged_project", "_verify_published_project"):
            with self.subTest(hook=hook):
                with patch.object(publication, hook, side_effect=SidecarIntegrityError("injected failure")):
                    with self.assertRaisesRegex(SidecarIntegrityError, "injected failure"):
                        import_package(self.session, source)
                self.assertIs(self.session.project, original)
                self.assertEqual(self.session.sidecar_path, destination)
                self.assertEqual(self.session.dirty_reasons, dirty)
                self.assertNotIn(other.id, original.structures)
                self.assertEqual(before, {str(p.relative_to(destination)): p.read_bytes()
                                          for p in destination.rglob("*") if p.is_file()})
                numpy.testing.assert_array_equal(original.structures[self.structure.id].coordinates.values,
                                                 self.structure.coordinates.values)
                # Failed candidates remain inspectable; they are not the active package.
                report = publication.inspect_publication_orphans(destination)
                self.assertTrue(report.temporary_paths)
                self.assertFalse(report.backup_paths)
                self.assertNotIn(destination, report.temporary_paths)
        result = import_package(self.session, source)
        self.assertEqual(result.counts['new'], 1)
        self.assertEqual(set(self.session.project.structures), {self.structure.id, other.id})
        reopened = open_project(destination, verify_arrays=True)
        try:
            self.assertEqual(set(reopened.structures), {self.structure.id, other.id})
        finally:
            close_project(reopened)

    def test_import_after_reopen_preserves_saved_package_until_explicit_save(self):
        saved = self.root / "saved.cbq"
        save_project(saved, self.session.project)
        close_project(self.session.project)
        self.session.project = open_project(saved, verify_arrays=True)
        self.session.sidecar_path = saved
        original = self.session.project
        before = {p.relative_to(saved): p.read_bytes() for p in saved.rglob("*") if p.is_file()}
        with patch('cbq_core.package_import.solidify_session', side_effect=OSError('disk full')):
            with self.assertRaisesRegex(OSError, 'disk full'):
                import_package(self.session, self.input)
        self.assertIs(self.session.project, original)
        self.assertEqual(self.session.sidecar_path, saved)
        self.assertFalse(self.session.dirty)
        import_package(self.session, self.input)
        self.assertEqual(before, {p.relative_to(saved): p.read_bytes()
                                  for p in saved.rglob("*") if p.is_file()})
        self.assertEqual(self.session.sidecar_path.parent, self.session.temporary_root)
        self.assertTrue(self.session.dirty)
        reopened = open_project(saved, verify_arrays=True)
        try:
            self.assertFalse(reopened.structures)
        finally:
            close_project(reopened)
        shutil.rmtree(self.input)
        reopened = open_project(self.session.sidecar_path, verify_arrays=True)
        try:
            numpy.testing.assert_array_equal(reopened.structures[self.structure.id].coordinates.values,
                                             self.structure.coordinates.values)
        finally:
            close_project(reopened)

    def test_post_commit_close_failure_is_warning_and_keeps_published_data(self):
        import cbq_core.package_import as importer
        original = self.session.project
        close = importer.close_project
        def fail_previous(project):
            if project is original:
                raise OSError("previous arrays locked")
            close(project)
        with patch.object(importer, 'close_project', side_effect=fail_previous):
            result = import_package(self.session, self.input)
        self.assertEqual(result.cleanup_warnings, ('Previous project cleanup: previous arrays locked',))
        self.assertIn(self.structure.id, self.session.project.structures)
        reopened = open_project(self.session.sidecar_path, verify_arrays=True)
        close_project(reopened)
        close_project(original)

    def test_preview_hash_prevents_changed_package_import(self):
        preview = preview_package(self.session, self.input)
        self.assertEqual(len(preview.manifest_sha256), 64)
        with self.assertRaisesRegex(ValueError, 'changed after preview'):
            import_package(self.session, self.input, expected_manifest_sha256='0' * 64)
        self.assertFalse(self.session.project.structures)


if __name__ == '__main__':
    unittest.main()
