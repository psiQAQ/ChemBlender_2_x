import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from ChemBlender.core import ProjectSession, close_session, create_session
from ChemBlender.core.model import QCProject


OWNER_MARKER = ".chemblender-session-owner"


class ProjectSessionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.temp_parent = Path(self.temporary.name)
        self.sessions = []

    def tearDown(self):
        for session in reversed(self.sessions):
            if session.temporary_root.exists():
                try:
                    close_session(session)
                except RuntimeError:
                    pass
        self.temporary.cleanup()

    def create_session(self, **kwargs):
        session = create_session(temp_parent=self.temp_parent, **kwargs)
        self.sessions.append(session)
        return session

    def test_create_session_uses_owned_uuid_root_and_current_project(self):
        session = self.create_session()

        self.assertIsInstance(session, ProjectSession)
        self.assertEqual(
            session.temporary_root.parent,
            self.temp_parent.resolve() / "chemblender",
        )
        self.assertEqual(session.temporary_root.name, str(session.id))
        self.assertEqual(
            (session.temporary_root / OWNER_MARKER).read_text(encoding="utf-8"),
            f"{session.id}\n",
        )
        self.assertEqual(session.project.schema_version, "0.2")
        self.assertIsNone(session.sidecar_path)
        self.assertIsNone(session.active_entity_id)
        self.assertIsNone(session.active_view_object_name)
        self.assertEqual(session.link_status, "unlinked")

    def test_close_session_removes_matching_owned_root(self):
        session = self.create_session()
        root = session.temporary_root

        close_session(session)

        self.assertFalse(root.exists())

    def test_close_session_refuses_missing_marker_and_preserves_files(self):
        session = self.create_session()
        root = session.temporary_root
        payload = root / "keep.txt"
        payload.write_text("keep", encoding="utf-8")
        (root / OWNER_MARKER).unlink()

        with self.assertRaises(RuntimeError):
            close_session(session)

        self.assertEqual(payload.read_text(encoding="utf-8"), "keep")

    def test_close_session_refuses_mismatched_marker_and_preserves_files(self):
        session = self.create_session()
        root = session.temporary_root
        payload = root / "keep.txt"
        payload.write_text("keep", encoding="utf-8")
        (root / OWNER_MARKER).write_text(f"{uuid4()}\n", encoding="utf-8")

        with self.assertRaises(RuntimeError):
            close_session(session)

        self.assertEqual(payload.read_text(encoding="utf-8"), "keep")

    def test_close_session_refuses_reassigned_external_root(self):
        session = self.create_session()
        owned_root = session.temporary_root
        external = self.temp_parent / "external"
        external.mkdir()
        (external / OWNER_MARKER).write_text(f"{session.id}\n", encoding="utf-8")
        payload = external / "keep.txt"
        payload.write_text("keep", encoding="utf-8")
        session.temporary_root = external

        with self.assertRaises(RuntimeError):
            close_session(session)

        self.assertEqual(payload.read_text(encoding="utf-8"), "keep")
        session.temporary_root = owned_root

    @unittest.skipUnless(
        os.name == "nt" and hasattr(Path, "is_junction"),
        "Windows junction support is required",
    )
    def test_create_session_refuses_junction_workspace(self):
        target = self.temp_parent / "junction-target"
        target.mkdir()
        workspace = self.temp_parent / "chemblender"
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(workspace), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(workspace.is_junction())
        try:
            with self.assertRaisesRegex(RuntimeError, "workspace"):
                create_session(temp_parent=self.temp_parent)
        finally:
            workspace.rmdir()

        self.assertEqual(list(target.iterdir()), [])

    @unittest.skipUnless(
        os.name == "nt" and hasattr(Path, "is_junction"),
        "Windows junction support is required",
    )
    def test_close_session_explicitly_refuses_junction_root(self):
        session = self.create_session()
        root = session.temporary_root
        (root / OWNER_MARKER).unlink()
        root.rmdir()
        target = self.temp_parent / "junction-root-target"
        target.mkdir()
        (target / OWNER_MARKER).write_text(f"{session.id}\n", encoding="utf-8")
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(root), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(root.is_junction())
        try:
            with self.assertRaisesRegex(RuntimeError, "unsafe session root"):
                close_session(session)
        finally:
            root.rmdir()

        self.assertTrue((target / OWNER_MARKER).is_file())

    def test_partial_marker_write_reraises_original_error_without_residue(self):
        original_open = Path.open
        sentinel = OSError("sentinel marker write failure")

        class PartialMarkerWriter:
            def __init__(self, stream):
                self.stream = stream

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.stream.close()

            def write(self, data):
                self.stream.write(data[:1])
                self.stream.flush()
                raise sentinel

        def injected_open(path, mode="r", *args, **kwargs):
            stream = original_open(path, mode, *args, **kwargs)
            if path.name == OWNER_MARKER and mode == "xb":
                return PartialMarkerWriter(stream)
            return stream

        with patch.object(Path, "open", new=injected_open):
            with self.assertRaises(OSError) as captured:
                create_session(temp_parent=self.temp_parent)

        self.assertIs(captured.exception, sentinel)
        workspace = self.temp_parent / "chemblender"
        self.assertEqual(list(workspace.iterdir()), [])

    def test_close_session_can_leave_temporary_root(self):
        session = self.create_session()
        root = session.temporary_root

        close_session(session, remove_temporary=False)

        self.assertTrue(root.is_dir())

    def test_dirty_reasons_are_marked_and_cleared_strictly(self):
        session = self.create_session()
        self.assertFalse(session.dirty)
        self.assertEqual(session.dirty_reasons, frozenset())

        session.mark_dirty("import")
        session.mark_dirty("view")
        self.assertTrue(session.dirty)
        self.assertEqual(session.dirty_reasons, frozenset({"import", "view"}))

        session.clear_dirty("import")
        self.assertEqual(session.dirty_reasons, frozenset({"view"}))
        session.clear_dirty("view")
        self.assertFalse(session.dirty)

        for invalid in ("", " ", " import", 1, None):
            with self.subTest(invalid=invalid):
                with self.assertRaises((TypeError, ValueError)):
                    session.mark_dirty(invalid)
        with self.assertRaises(KeyError):
            session.clear_dirty("unknown")

    def test_create_session_preserves_provided_project_identity(self):
        project = QCProject(id=uuid4(), schema_version="0.2")

        session = self.create_session(project=project)

        self.assertIs(session.project, project)


if __name__ == "__main__":
    unittest.main()
