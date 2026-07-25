import gc
import importlib
import sys
import unittest
import weakref
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from ChemBlender.core import ProjectServiceStatus, ProjectSession
from ChemBlender.project_link import MANIFEST_HASH_KEY


SESSION_MODULE = "ChemBlender.ui.session"


class Scene:
    def __init__(self):
        self._properties = {}

    def __contains__(self, key):
        return key in self._properties

    def __getitem__(self, key):
        return self._properties[key]

    def __setitem__(self, key, value):
        self._properties[key] = value

    def __delitem__(self, key):
        del self._properties[key]


class FailingScene(Scene):
    def __init__(self):
        super().__init__()
        self.fail_next_link_write = False

    def __setitem__(self, key, value):
        if key == MANIFEST_HASH_KEY and self.fail_next_link_write:
            self.fail_next_link_write = False
            raise RuntimeError("scene link write failed")
        super().__setitem__(key, value)


class PointerScene:
    __slots__ = ("_properties", "_pointer")

    def __init__(self, pointer):
        self._properties = {}
        self._pointer = pointer

    def as_pointer(self):
        return self._pointer

    def __contains__(self, key):
        return key in self._properties

    def __getitem__(self, key):
        return self._properties[key]

    def __setitem__(self, key, value):
        self._properties[key] = value

    def __delitem__(self, key):
        del self._properties[key]


class UiSessionContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.scene = Scene()
        self.handlers = SimpleNamespace(
            load_post=[],
            save_pre=[],
            persistent=lambda callback: callback,
        )
        self.fake_bpy = ModuleType("bpy")
        self.fake_bpy.app = SimpleNamespace(
            tempdir=self.temporary.name,
            handlers=self.handlers,
        )
        self.fake_bpy.data = SimpleNamespace(filepath="", scenes=[self.scene])
        self.fake_bpy.context = SimpleNamespace(scene=self.scene)
        self.modules = patch.dict(sys.modules, {"bpy": self.fake_bpy})
        self.modules.start()
        sys.modules.pop(SESSION_MODULE, None)
        sys.modules.pop("ChemBlender.ui", None)
        self.ui = importlib.import_module(SESSION_MODULE)

    def tearDown(self):
        if hasattr(self, "ui"):
            self.ui.unregister()
        self.modules.stop()
        sys.modules.pop(SESSION_MODULE, None)
        sys.modules.pop("ChemBlender.ui", None)
        self.temporary.cleanup()

    def test_get_scene_session_creates_in_memory_current_schema_session(self):
        session = self.ui.get_scene_session(self.scene)

        self.assertIsInstance(session, ProjectSession)
        self.assertEqual(session.link_status, "unlinked")
        self.assertEqual(self.scene._properties, {})
        self.assertTrue(session.temporary_root.is_dir())

    def test_registry_does_not_retain_discarded_scene(self):
        transient = Scene()
        session = self.ui.get_scene_session(transient)
        reference = weakref.ref(transient)

        del transient
        gc.collect()

        self.assertIsNone(reference())
        self.assertEqual(len(self.ui._SCENE_SESSIONS), 0)
        self.assertFalse(session.temporary_root.exists())

    def test_registry_supports_blender_style_non_weakrefable_scene(self):
        scene = PointerScene(1234)

        session = self.ui.get_scene_session(scene)

        self.assertIs(self.ui.get_scene_session(scene), session)
        self.ui.close_scene_session(scene)
        self.assertFalse(session.temporary_root.exists())

    def test_pointer_reuse_replaces_and_closes_stale_session(self):
        stale_scene = PointerScene(1234)
        stale = self.ui.get_scene_session(stale_scene)
        replacement_scene = PointerScene(1234)

        replacement = self.ui.get_scene_session(replacement_scene)

        self.assertIsNot(replacement, stale)
        self.assertFalse(stale.temporary_root.exists())

    def test_load_handler_closes_sessions_for_scenes_absent_from_loaded_file(self):
        stale_scene = Scene()
        stale = self.ui.get_scene_session(stale_scene)
        self.fake_bpy.data.scenes = [self.scene]

        self.ui._load_post_handler(None)

        self.assertFalse(stale.temporary_root.exists())

    def test_load_cleanup_failure_keeps_live_replacement_and_error_status(self):
        stale = self.ui.get_scene_session(self.scene)
        stale.mark_dirty("import")

        with patch.object(
            self.ui,
            "_write_recovery_marker",
            side_effect=OSError("marker failed"),
        ), patch.object(
            self.ui,
            "close_session",
            side_effect=OSError("close failed"),
        ):
            self.ui._load_post_handler(None)

        replacement = self.ui.get_scene_session(self.scene)
        status, message = self.ui.get_scene_session_status(self.scene)
        self.assertIsNot(replacement, stale)
        self.assertEqual(status, "error")
        self.assertIn("marker failed", message)
        self.assertIn("close failed", message)

    def test_load_keeps_verification_and_stale_cleanup_failures(self):
        stale = self.ui.get_scene_session(self.scene)
        stale.mark_dirty("import")

        with patch.object(
            self.ui,
            "_write_recovery_marker",
            side_effect=OSError("marker failed"),
        ), patch.object(
            self.ui,
            "close_session",
            side_effect=OSError("close failed"),
        ), patch.object(
            self.ui,
            "verify_project_session",
            side_effect=RuntimeError("verification failed"),
        ):
            self.ui._load_post_handler(None)

        replacement = self.ui.get_scene_session(self.scene)
        status, message = self.ui.get_scene_session_status(self.scene)
        self.assertIsNot(replacement, stale)
        self.assertEqual(status, "error")
        self.assertIn("verification failed", message)
        self.assertIn("marker failed", message)
        self.assertIn("close failed", message)

    def test_load_handler_replaces_stale_session_and_exposes_service_result(self):
        stale = self.ui.get_scene_session(self.scene)

        self.ui._load_post_handler(None)

        current = self.ui.get_scene_session(self.scene)
        status, message = self.ui.get_scene_session_status(self.scene)
        self.assertIsNot(current, stale)
        self.assertFalse(stale.temporary_root.exists())
        self.assertEqual(status, ProjectServiceStatus.INVALID.value)
        self.assertEqual(message, "invalid scene project link")

    def test_save_handler_publishes_dirty_saved_session_and_marks_it_clean(self):
        session = self.ui.get_scene_session(self.scene)
        session.mark_dirty("import")
        self.fake_bpy.data.filepath = str(Path(self.temporary.name) / "scene.blend")

        self.ui._save_pre_handler(None)

        status, message = self.ui.get_scene_session_status(self.scene)
        self.assertFalse(session.dirty)
        self.assertEqual(status, ProjectServiceStatus.CONNECTED.value)
        self.assertEqual(message, "")
        self.assertTrue((Path(self.temporary.name) / "scene.cbq").is_dir())

    def test_save_handler_ignores_non_blend_path(self):
        session = self.ui.get_scene_session(self.scene)
        session.mark_dirty("import")
        self.fake_bpy.data.filepath = str(Path(self.temporary.name) / "scene.tmp")

        self.ui._save_pre_handler(None)

        self.assertTrue(session.dirty)
        self.assertEqual(self.ui.get_scene_session_status(self.scene), ("unlinked", ""))
        self.assertFalse((Path(self.temporary.name) / "scene.cbq").exists())

    def test_save_handler_preserves_dirty_session_and_verified_link_on_failure(self):
        scene = FailingScene()
        self.fake_bpy.context.scene = scene
        self.fake_bpy.data.scenes = [scene]
        self.fake_bpy.data.filepath = str(Path(self.temporary.name) / "scene.blend")
        session = self.ui.get_scene_session(scene)
        session.mark_dirty("import")
        self.ui._save_pre_handler(None)
        verified_link = dict(scene._properties)
        session.mark_dirty("edit")
        scene.fail_next_link_write = True

        self.ui._save_pre_handler(None)

        status, message = self.ui.get_scene_session_status(scene)
        self.assertTrue(session.dirty)
        self.assertEqual(session.dirty_reasons, frozenset({"edit"}))
        self.assertEqual(scene._properties, verified_link)
        self.assertEqual(status, "error")
        self.assertEqual(message, "scene link write failed")

    def test_close_dirty_session_writes_recovery_marker_and_retains_root(self):
        session = self.ui.get_scene_session(self.scene)
        session.mark_dirty("import")

        self.ui.close_scene_session(self.scene)

        marker = session.temporary_root / self.ui.RECOVERY_MARKER
        self.assertTrue(session.temporary_root.is_dir())
        self.assertEqual(marker.read_text(encoding="utf-8"), "import\n")

    def test_close_retries_after_marker_failure_when_resource_close_succeeds(self):
        session = self.ui.get_scene_session(self.scene)
        session.mark_dirty("import")
        with patch.object(
            self.ui,
            "_write_recovery_marker",
            side_effect=OSError("marker failed"),
        ):
            with self.assertRaisesRegex(OSError, "marker failed"):
                self.ui.close_scene_session(self.scene)

        self.assertIs(self.ui.get_scene_session(self.scene), session)
        self.assertEqual(self.ui.get_scene_session_status(self.scene)[0], "error")

        self.ui.close_scene_session(self.scene)

        self.assertFalse(self.ui._SCENE_SESSIONS)
        self.assertFalse(self.ui._RECOVERY_SESSIONS)
        self.assertTrue(session.temporary_root.is_dir())

    def test_unregister_retries_retained_recovery_after_total_cleanup_failure(self):
        stale = self.ui.get_scene_session(self.scene)
        stale.mark_dirty("import")
        with patch.object(
            self.ui,
            "_write_recovery_marker",
            side_effect=OSError("marker failed"),
        ), patch.object(
            self.ui,
            "close_session",
            side_effect=OSError("close failed"),
        ):
            self.ui._load_post_handler(None)

        self.assertIn(stale.id, self.ui._RECOVERY_SESSIONS)
        self.assertIsNot(self.ui.get_scene_session(self.scene), stale)

        self.ui.unregister()

        self.assertFalse(self.ui._SCENE_SESSIONS)
        self.assertFalse(self.ui._RECOVERY_SESSIONS)
        self.assertTrue(stale.temporary_root.is_dir())

    def test_registration_is_idempotent_and_removes_only_owned_handler_pair(self):
        def foreign_handler(_dummy):
            return None

        self.handlers.load_post.append(foreign_handler)
        self.handlers.save_pre.append(foreign_handler)

        self.ui.register()
        self.ui.register()
        self.assertEqual(self.handlers.load_post.count(self.ui._load_post_handler), 1)
        self.assertEqual(self.handlers.save_pre.count(self.ui._save_pre_handler), 1)

        self.ui.unregister()

        self.assertEqual(self.handlers.load_post, [foreign_handler])
        self.assertEqual(self.handlers.save_pre, [foreign_handler])


if __name__ == "__main__":
    unittest.main()
