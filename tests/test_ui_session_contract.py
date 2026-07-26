import array
import gc
import importlib
import json
import sys
import unittest
import weakref
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
from uuid import UUID

import ChemBlender.core.project_service as project_service
from ChemBlender.core import (
    ArrayData,
    ImportBatch,
    ProjectServiceStatus,
    ProjectSession,
    QCProject,
    Structure,
    save_project,
)
from ChemBlender.project_link import (
    MANIFEST_HASH_KEY,
    PROJECT_ID_KEY,
    PROJECT_SCHEMA_KEY,
    SIDECAR_LOCATOR_KEY,
    write_project_link,
)


SESSION_MODULE = "ChemBlender.ui.session"
LINK_KEYS = (
    PROJECT_ID_KEY,
    PROJECT_SCHEMA_KEY,
    SIDECAR_LOCATOR_KEY,
    MANIFEST_HASH_KEY,
)


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

    def link_project(self, scene, name, project_id=UUID(int=1)):
        project = QCProject(id=project_id, schema_version="0.2")
        sidecar = Path(self.temporary.name) / f"{name}.cbq"
        save_project(sidecar, project)
        write_project_link(
            scene,
            project,
            sidecar,
            blend_path=self.fake_bpy.data.filepath,
        )
        return project, sidecar

    def storage_snapshot(self, sidecar):
        manifest_path = sidecar / "manifest.json"
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        return (
            manifest_bytes,
            manifest["generation_id"],
            manifest["manifest_sha256"],
            tuple(
                (
                    path.relative_to(sidecar).as_posix(),
                    path.read_bytes(),
                    path.stat().st_mtime_ns,
                )
                for path in sorted((sidecar / "arrays").glob("*.npy"))
            ),
        )

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

    def test_all_scenes_share_one_session_project_and_temporary_root(self):
        second_scene = Scene()
        self.fake_bpy.data.scenes = [self.scene, second_scene]

        first = self.ui.get_scene_session(self.scene)
        second = self.ui.get_scene_session(second_scene)
        coordinates = memoryview(array.array("d", (0.0, 0.0, 0.0)))
        coordinates = coordinates.cast("B").cast("d", shape=(1, 3))
        structure = Structure(
            id=UUID(int=3),
            revision="imported-through-first-scene",
            atomic_numbers=(1,),
            coordinates=ArrayData(
                coordinates,
                ("atom", "xyz"),
                "angstrom",
            ),
        )
        first.project.commit(ImportBatch(structures=(structure,)))
        first.mark_dirty("import")

        self.assertIs(second, first)
        self.assertIs(second.project, first.project)
        self.assertIs(second.project.structures[structure.id], structure)
        self.assertEqual(second.temporary_root, first.temporary_root)
        self.assertEqual(second.dirty_reasons, frozenset({"import"}))

    def test_new_and_replacement_sessions_notify_browser_once(self):
        notifications = []
        self.ui.register_session_mutation(
            lambda session: notifications.append(session.id)
        )

        first = self.ui.get_scene_session(self.scene)
        replacement = self.ui.new_scene_session(self.scene)

        self.assertEqual(notifications, [first.id, replacement.id])

    def test_load_notifies_browser_only_after_successful_project_adoption(self):
        notifications = []
        self.ui.register_session_mutation(
            lambda session: notifications.append(session.id)
        )
        second_scene = Scene()
        self.fake_bpy.data.filepath = str(
            Path(self.temporary.name) / "shared.blend"
        )
        project, sidecar = self.link_project(self.scene, "shared")
        write_project_link(
            second_scene,
            project,
            sidecar,
            blend_path=self.fake_bpy.data.filepath,
        )
        self.fake_bpy.data.scenes = [self.scene, second_scene]
        self.ui.get_scene_session(self.scene)
        notifications.clear()

        self.ui._load_post_handler(None)

        restored = self.ui.get_scene_session(self.scene)
        self.assertIs(self.ui.get_scene_session(second_scene), restored)
        self.assertEqual(notifications, [restored.id])

    def test_failed_or_invalid_load_does_not_advance_browser_revision(self):
        notifications = []
        self.ui.register_session_mutation(
            lambda session: notifications.append(session.id)
        )
        self.ui.get_scene_session(self.scene)
        notifications.clear()

        self.scene[PROJECT_ID_KEY] = "partial-link"
        self.ui._load_post_handler(None)
        self.assertEqual(notifications, [])

    def test_discarded_scene_does_not_close_file_session(self):
        transient = Scene()
        session = self.ui.get_scene_session(transient)
        reference = weakref.ref(transient)

        del transient
        gc.collect()

        self.assertIsNone(reference())
        self.assertIs(self.ui.get_scene_session(self.scene), session)
        self.assertTrue(session.temporary_root.exists())

    def test_registry_supports_blender_style_non_weakrefable_scene(self):
        scene = PointerScene(1234)

        session = self.ui.get_scene_session(scene)

        self.assertIs(self.ui.get_scene_session(scene), session)
        self.ui.close_scene_session(scene)
        self.assertFalse(session.temporary_root.exists())

    def test_pointer_reuse_still_returns_file_session(self):
        stale_scene = PointerScene(1234)
        stale = self.ui.get_scene_session(stale_scene)
        replacement_scene = PointerScene(1234)

        replacement = self.ui.get_scene_session(replacement_scene)

        self.assertIs(replacement, stale)
        self.assertTrue(stale.temporary_root.exists())

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
            "verify_project_session_for_scenes",
            side_effect=RuntimeError("verification failed"),
            create=True,
        ):
            self.ui._load_post_handler(None)

        replacement = self.ui.get_scene_session(self.scene)
        status, message = self.ui.get_scene_session_status(self.scene)
        self.assertIsNot(replacement, stale)
        self.assertEqual(status, "error")
        self.assertIn("verification failed", message)
        self.assertIn("marker failed", message)
        self.assertIn("close failed", message)

    def test_load_handler_replaces_stale_session_with_empty_file_session(self):
        stale = self.ui.get_scene_session(self.scene)

        self.ui._load_post_handler(None)

        current = self.ui.get_scene_session(self.scene)
        status, message = self.ui.get_scene_session_status(self.scene)
        self.assertIsNot(current, stale)
        self.assertFalse(stale.temporary_root.exists())
        self.assertEqual(status, "unlinked")
        self.assertEqual(message, "")

    def test_load_without_links_creates_one_empty_shared_session(self):
        second_scene = Scene()
        self.fake_bpy.data.scenes = [self.scene, second_scene]

        self.ui._load_post_handler(None)

        session = self.ui.get_scene_session(self.scene)
        self.assertIs(self.ui.get_scene_session(second_scene), session)
        self.assertEqual(session.project.structures, {})
        self.assertEqual(
            self.ui.get_scene_session_status(second_scene),
            ("unlinked", ""),
        )

    def test_load_valid_and_empty_links_adopts_and_projects_one_project(self):
        second_scene = Scene()
        self.fake_bpy.data.filepath = str(
            Path(self.temporary.name) / "partial.blend"
        )
        project, _sidecar = self.link_project(self.scene, "partial")
        self.fake_bpy.data.scenes = [self.scene, second_scene]

        self.ui._load_post_handler(None)

        session = self.ui.get_scene_session(self.scene)
        self.assertIs(self.ui.get_scene_session(second_scene), session)
        self.assertEqual(session.project.id, project.id)
        self.assertEqual(
            {key: second_scene[key] for key in LINK_KEYS},
            {key: self.scene[key] for key in LINK_KEYS},
        )
        self.assertEqual(
            self.ui.get_scene_session_status(second_scene),
            ("connected", ""),
        )

    def test_load_conflicting_valid_links_fails_closed(self):
        second_scene = Scene()
        self.fake_bpy.data.filepath = str(
            Path(self.temporary.name) / "conflict.blend"
        )
        first_project, _first_sidecar = self.link_project(
            self.scene,
            "first",
            UUID(int=1),
        )
        second_project, _second_sidecar = self.link_project(
            second_scene,
            "second",
            UUID(int=2),
        )
        self.fake_bpy.data.scenes = [self.scene, second_scene]

        self.ui._load_post_handler(None)

        session = self.ui.get_scene_session(self.scene)
        self.assertIs(self.ui.get_scene_session(second_scene), session)
        self.assertNotIn(
            session.project.id,
            {first_project.id, second_project.id},
        )
        self.assertEqual(
            self.ui.get_scene_session_status(self.scene),
            ("invalid", "conflicting scene project links"),
        )
        self.assertEqual(
            self.ui.get_scene_session_status(second_scene),
            ("invalid", "conflicting scene project links"),
        )

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

    def test_save_handler_publishes_once_after_scene_switch_and_links_all_scenes(self):
        second_scene = Scene()
        self.fake_bpy.data.scenes = [self.scene, second_scene]
        session = self.ui.get_scene_session(self.scene)
        session.mark_dirty("import")
        self.fake_bpy.context.scene = second_scene
        self.fake_bpy.data.filepath = str(
            Path(self.temporary.name) / "switched.blend"
        )

        with patch.object(
            project_service,
            "solidify_session",
            wraps=project_service.solidify_session,
        ) as publish:
            self.ui._save_pre_handler(None)

        publish.assert_called_once()
        self.assertFalse(session.dirty)
        self.assertEqual(
            {key: second_scene[key] for key in LINK_KEYS},
            {key: self.scene[key] for key in LINK_KEYS},
        )
        self.assertEqual(
            self.ui.get_scene_session_status(self.scene),
            ("connected", ""),
        )

    def test_save_handler_projects_clean_connected_session_to_new_scene(self):
        session = self.ui.get_scene_session(self.scene)
        session.mark_dirty("import")
        self.fake_bpy.data.filepath = str(
            Path(self.temporary.name) / "expanded.blend"
        )
        self.ui._save_pre_handler(None)
        self.assertFalse(session.dirty)
        sidecar = Path(self.temporary.name) / "expanded.cbq"
        before = self.storage_snapshot(sidecar)

        second_scene = Scene()
        self.fake_bpy.data.scenes.append(second_scene)

        with patch.object(
            project_service,
            "solidify_session",
            wraps=project_service.solidify_session,
        ) as publish:
            self.ui._save_pre_handler(None)

        publish.assert_not_called()
        self.assertEqual(
            {key: second_scene[key] for key in LINK_KEYS},
            {key: self.scene[key] for key in LINK_KEYS},
        )
        self.assertEqual(
            self.ui.get_scene_session_status(second_scene),
            ("connected", ""),
        )
        self.assertEqual(self.storage_snapshot(sidecar), before)

    def test_save_handler_clean_connected_identical_links_is_noop(self):
        session = self.ui.get_scene_session(self.scene)
        session.mark_dirty("import")
        self.fake_bpy.data.filepath = str(
            Path(self.temporary.name) / "noop.blend"
        )
        self.ui._save_pre_handler(None)
        sidecar = Path(self.temporary.name) / "noop.cbq"
        before = self.storage_snapshot(sidecar)

        with patch.object(
            project_service,
            "solidify_session",
            wraps=project_service.solidify_session,
        ) as publish:
            self.ui._save_pre_handler(None)

        publish.assert_not_called()
        self.assertEqual(self.storage_snapshot(sidecar), before)

    def test_save_handler_unknown_dirty_reason_still_republishes(self):
        session = self.ui.get_scene_session(self.scene)
        session.mark_dirty("import")
        self.fake_bpy.data.filepath = str(
            Path(self.temporary.name) / "scientific.blend"
        )
        self.ui._save_pre_handler(None)
        session.mark_dirty("future_scientific_reason")

        with patch.object(
            project_service,
            "solidify_session",
            wraps=project_service.solidify_session,
        ) as publish:
            self.ui._save_pre_handler(None)

        publish.assert_called_once()

    def test_save_handler_save_as_republishes_to_new_sibling(self):
        session = self.ui.get_scene_session(self.scene)
        session.mark_dirty("import")
        self.fake_bpy.data.filepath = str(
            Path(self.temporary.name) / "original.blend"
        )
        self.ui._save_pre_handler(None)
        self.fake_bpy.data.filepath = str(
            Path(self.temporary.name) / "copy.blend"
        )

        with patch.object(
            project_service,
            "solidify_session",
            wraps=project_service.solidify_session,
        ) as publish:
            self.ui._save_pre_handler(None)

        publish.assert_called_once()
        self.assertEqual(
            session.sidecar_path,
            (Path(self.temporary.name) / "copy.cbq").resolve(),
        )

    def test_save_handler_view_cache_only_does_not_republish(self):
        session = self.ui.get_scene_session(self.scene)
        session.mark_dirty("import")
        self.fake_bpy.data.filepath = str(
            Path(self.temporary.name) / "view-cache.blend"
        )
        self.ui._save_pre_handler(None)
        session.mark_dirty("view_cache")

        with patch.object(
            project_service,
            "solidify_session",
            wraps=project_service.solidify_session,
        ) as publish:
            self.ui._save_pre_handler(None)

        publish.assert_not_called()
        self.assertEqual(session.dirty_reasons, frozenset({"view_cache"}))

    def test_save_handler_does_not_publish_clean_missing_load(self):
        self.fake_bpy.data.filepath = str(
            Path(self.temporary.name) / "missing-state.blend"
        )
        self.link_project(self.scene, "source")
        self.scene[SIDECAR_LOCATOR_KEY] = "absent.cbq"
        original_link = dict(self.scene._properties)
        sibling = Path(self.temporary.name) / "missing-state.cbq"

        self.ui._load_post_handler(None)
        session = self.ui.get_scene_session(self.scene)
        self.assertFalse(session.dirty)
        self.assertIsNone(session.sidecar_path)
        self.assertEqual(
            self.ui.get_scene_session_status(self.scene)[0],
            "missing",
        )

        with patch.object(
            project_service,
            "solidify_session",
            wraps=project_service.solidify_session,
        ) as publish:
            self.ui._save_pre_handler(None)

        publish.assert_not_called()
        self.assertFalse(sibling.exists())
        self.assertEqual(self.scene._properties, original_link)
        self.assertEqual(
            self.ui.get_scene_session_status(self.scene)[0],
            "missing",
        )

    def test_save_handler_connected_sidecar_becoming_missing_stays_link_only(self):
        session = self.ui.get_scene_session(self.scene)
        session.mark_dirty("import")
        self.fake_bpy.data.filepath = str(
            Path(self.temporary.name) / "removed.blend"
        )
        self.ui._save_pre_handler(None)
        sidecar = Path(self.temporary.name) / "removed.cbq"
        sidecar.rename(Path(self.temporary.name) / "removed-away.cbq")

        with patch.object(
            project_service,
            "solidify_session",
            wraps=project_service.solidify_session,
        ) as publish:
            self.ui._save_pre_handler(None)
            self.ui._save_pre_handler(None)

        publish.assert_not_called()
        self.assertFalse(sidecar.exists())
        self.assertEqual(session.link_status, "missing")
        self.assertEqual(session.dirty_reasons, frozenset({"project_link"}))

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

    def test_clean_session_retries_failed_new_scene_link_on_next_save(self):
        self.fake_bpy.data.filepath = str(
            Path(self.temporary.name) / "retry-scene.blend"
        )
        session = self.ui.get_scene_session(self.scene)
        session.mark_dirty("import")
        self.ui._save_pre_handler(None)
        self.assertFalse(session.dirty)

        second_scene = FailingScene()
        second_scene.fail_next_link_write = True
        self.fake_bpy.data.scenes.append(second_scene)
        self.ui._save_pre_handler(None)

        self.assertEqual(session.dirty_reasons, frozenset({"project_link"}))
        self.assertEqual(session.link_status, "invalid")
        self.assertEqual(
            self.ui.get_scene_session_status(second_scene),
            ("error", "scene link write failed"),
        )

        sidecar = Path(self.temporary.name) / "retry-scene.cbq"
        before = self.storage_snapshot(sidecar)
        with patch.object(
            project_service,
            "solidify_session",
            wraps=project_service.solidify_session,
        ) as publish:
            self.ui._save_pre_handler(None)

        publish.assert_not_called()
        self.assertEqual(self.storage_snapshot(sidecar), before)
        self.assertFalse(session.dirty)
        self.assertEqual(session.link_status, "connected")
        self.assertEqual(
            {key: second_scene[key] for key in LINK_KEYS},
            {key: self.scene[key] for key in LINK_KEYS},
        )
        self.assertEqual(
            self.ui.get_scene_session_status(second_scene),
            ("connected", ""),
        )

    def test_close_dirty_session_writes_recovery_marker_and_retains_root(self):
        session = self.ui.get_scene_session(self.scene)
        session.mark_dirty("import")

        self.ui.close_scene_session(self.scene)

        marker = session.temporary_root / self.ui.RECOVERY_MARKER
        self.assertTrue(session.temporary_root.is_dir())
        self.assertEqual(marker.read_text(encoding="utf-8"), "import\n")

    def test_shared_session_closes_once_and_writes_one_recovery_marker(self):
        second_scene = Scene()
        session = self.ui.get_scene_session(self.scene)
        self.assertIs(self.ui.get_scene_session(second_scene), session)
        session.mark_dirty("import")

        with patch.object(
            self.ui,
            "close_session",
            wraps=self.ui.close_session,
        ) as close:
            self.ui.close_scene_session(self.scene)
            self.ui.close_scene_session(second_scene)

        close.assert_called_once_with(session, remove_temporary=False)
        markers = tuple(
            session.temporary_root.glob(self.ui.RECOVERY_MARKER)
        )
        self.assertEqual(len(markers), 1)

    def test_close_session_runs_registered_ui_cleanup_before_removal(self):
        session = self.ui.get_scene_session(self.scene)
        events = []

        def cleanup(value):
            events.append(("ui", value.id, value.temporary_root.exists()))

        self.ui.register_session_cleanup(cleanup)
        self.ui.close_scene_session(self.scene)

        self.assertEqual(events, [("ui", session.id, True)])
        self.assertFalse(session.temporary_root.exists())
        self.assertEqual(
            self.ui.get_scene_session_status(self.scene),
            ("unlinked", ""),
        )

    def test_new_session_clears_old_ui_state_before_replacement(self):
        old = self.ui.get_scene_session(self.scene)
        events = []
        self.ui.register_session_cleanup(
            lambda session: events.append(session.id)
        )

        new = self.ui.new_scene_session(self.scene)

        self.assertEqual(events, [old.id])
        self.assertIsNot(new, old)
        self.assertFalse(old.temporary_root.exists())

    def test_ui_cleanup_failure_preserves_retryable_session_ownership(self):
        session = self.ui.get_scene_session(self.scene)
        attempts = 0

        def cleanup(_session):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("staging still running")

        self.ui.register_session_cleanup(cleanup)

        with self.assertRaisesRegex(RuntimeError, "staging still running"):
            self.ui.close_scene_session(self.scene)

        self.assertIs(self.ui.get_scene_session(self.scene), session)
        self.assertTrue(session.temporary_root.exists())
        self.ui.close_scene_session(self.scene)
        self.assertEqual(attempts, 2)
        self.assertFalse(session.temporary_root.exists())

    def test_session_close_attempts_all_ui_cleanup_callbacks(self):
        session = self.ui.get_scene_session(self.scene)
        events = []
        attempts = 0

        def fail(_session):
            nonlocal attempts
            attempts += 1
            events.append("failed")
            if attempts == 1:
                raise RuntimeError("first cleanup failed")

        self.ui.register_session_cleanup(fail)
        self.ui.register_session_cleanup(
            lambda _session: events.append("completed")
        )

        with self.assertRaisesRegex(RuntimeError, "first cleanup failed"):
            self.ui.close_scene_session(self.scene)

        self.assertEqual(events, ["failed", "completed"])
        self.assertIs(self.ui.get_scene_session(self.scene), session)
        self.assertTrue(session.temporary_root.exists())

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
