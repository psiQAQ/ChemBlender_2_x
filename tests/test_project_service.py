import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import UUID

import ChemBlender.core as core
import ChemBlender.core.project_service as project_service
from ChemBlender.core import (
    ProjectServiceStatus,
    QCProject,
    clear_derived_cache,
    close_session,
    create_session,
    relink_project_session,
    save_project,
    save_project_session,
    verify_project_session,
)
from ChemBlender.core.sidecar import open_project
from ChemBlender.project_link import (
    MANIFEST_HASH_KEY,
    PROJECT_ID_KEY,
    PROJECT_SCHEMA_KEY,
    SIDECAR_LOCATOR_KEY,
    write_project_link,
)
from tests.test_sidecar_storage import FRAMES_ID, sample_project


PROJECT_ID = UUID("10000000-0000-0000-0000-000000000001")
LINK_KEYS = (
    PROJECT_ID_KEY,
    PROJECT_SCHEMA_KEY,
    SIDECAR_LOCATOR_KEY,
    MANIFEST_HASH_KEY,
)


class FatalLinkWriteScene(dict):
    def __init__(self, *args, error, rollback_failure_key=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.error = error
        self.rollback_failure_key = rollback_failure_key
        self.write_failed = False

    def __setitem__(self, key, value):
        if key == PROJECT_SCHEMA_KEY and not self.write_failed:
            self.write_failed = True
            raise self.error
        super().__setitem__(key, value)

    def __delitem__(self, key):
        if self.write_failed and key == self.rollback_failure_key:
            raise RuntimeError("Scene rollback failed")
        super().__delitem__(key)


class ProjectServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
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
            project=project or QCProject(id=PROJECT_ID, schema_version="0.2"),
        )
        self.sessions.append(session)
        return session

    def linked_scene(self, sidecar, project):
        scene = {"view-marker": "preserve"}
        write_project_link(scene, project, sidecar)
        return scene

    def save_for_scenes(self, *, session, scenes, blend_path):
        operation = getattr(
            project_service,
            "save_project_session_for_scenes",
            None,
        )
        self.assertIsNotNone(operation)
        return operation(
            session=session,
            scenes=scenes,
            blend_path=blend_path,
        )

    def verify_for_scenes(self, *, session, scenes, blend_path=None):
        operation = getattr(
            project_service,
            "verify_project_session_for_scenes",
            None,
        )
        self.assertIsNotNone(operation)
        return operation(
            session=session,
            scenes=scenes,
            blend_path=blend_path,
        )

    @staticmethod
    def loaded_candidate_recorder(open_candidate):
        opened_projects = []
        lazy_values = []

        def record(*args, **kwargs):
            project, manifest = open_candidate(*args, **kwargs)
            values = project.datasets[FRAMES_ID].data.values
            values[0]
            opened_projects.append(project)
            lazy_values.append(values)
            return project, manifest

        return record, opened_projects, lazy_values

    def storage_snapshot(self, sidecar):
        manifest_path = sidecar / "manifest.json"
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        arrays = tuple(
            (
                path.relative_to(sidecar).as_posix(),
                path.read_bytes(),
                path.stat().st_mtime_ns,
            )
            for path in sorted((sidecar / "arrays").glob("*.npy"))
        )
        return (
            manifest_bytes,
            manifest["generation_id"],
            manifest["manifest_sha256"],
            arrays,
        )

    def test_unsaved_blend_returns_unsaved_without_mutation(self):
        session = self.create_session()
        scene = {"view-marker": "preserve"}
        before = (session.project, session.sidecar_path, session.link_status, dict(scene))

        result = save_project_session(session=session, scene=scene, blend_path="")

        self.assertEqual(result.status, ProjectServiceStatus.UNSAVED)
        self.assertEqual(
            (session.project, session.sidecar_path, session.link_status, scene),
            before,
        )
        self.assertEqual(list(self.root.glob("*.cbq")), [])

    def test_save_publishes_same_name_sidecar_and_connected_scene_hash(self):
        session = self.create_session()
        session.mark_dirty("import")
        blend = self.root / "sample.blend"
        scene = {}

        result = save_project_session(
            session=session,
            scene=scene,
            blend_path=blend,
        )

        destination = self.root / "sample.cbq"
        manifest = json.loads(
            (destination / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(result.status, ProjectServiceStatus.CONNECTED)
        self.assertEqual(result.path, destination.resolve())
        self.assertEqual(result.manifest_sha256, manifest["manifest_sha256"])
        self.assertEqual(scene[PROJECT_ID_KEY], str(PROJECT_ID))
        self.assertEqual(scene[PROJECT_SCHEMA_KEY], "0.2")
        self.assertEqual(scene[MANIFEST_HASH_KEY], result.manifest_sha256)
        self.assertEqual(session.sidecar_path, destination.resolve())
        self.assertEqual(session.link_status, "connected")
        self.assertFalse(session.dirty)

    def test_save_projects_one_verified_link_to_every_scene(self):
        session = self.create_session()
        session.mark_dirty("import")
        blend = self.root / "shared.blend"
        scenes = (
            {"scene-marker": "first"},
            {"scene-marker": "second"},
        )

        result = self.save_for_scenes(
            session=session,
            scenes=scenes,
            blend_path=blend,
        )

        expected = {
            key: scenes[0][key]
            for key in LINK_KEYS
        }
        self.assertEqual(result.status, ProjectServiceStatus.CONNECTED)
        self.assertEqual(
            tuple({key: scene[key] for key in LINK_KEYS} for scene in scenes),
            (expected, expected),
        )
        self.assertEqual(
            (scenes[0]["scene-marker"], scenes[1]["scene-marker"]),
            ("first", "second"),
        )
        self.assertFalse(session.dirty)

    def test_later_scene_write_failure_restores_every_link_and_keeps_dirty(self):
        class FailingScene(dict):
            failed = False

            def __setitem__(self, key, value):
                if key == MANIFEST_HASH_KEY and not self.failed:
                    self.failed = True
                    raise RuntimeError("later scene write failed")
                super().__setitem__(key, value)

        session = self.create_session()
        session.mark_dirty("import")
        first = {
            "scene-marker": "first",
            PROJECT_ID_KEY: "old-first",
            PROJECT_SCHEMA_KEY: "old-schema-first",
            SIDECAR_LOCATOR_KEY: "old-first.cbq",
            MANIFEST_HASH_KEY: "1" * 64,
        }
        second = FailingScene(
            {
                "scene-marker": "second",
                PROJECT_ID_KEY: "old-second",
                PROJECT_SCHEMA_KEY: "old-schema-second",
                SIDECAR_LOCATOR_KEY: "old-second.cbq",
                MANIFEST_HASH_KEY: "2" * 64,
            }
        )
        originals = (dict(first), dict(second))

        with self.assertRaisesRegex(RuntimeError, "later scene write failed"):
            self.save_for_scenes(
                session=session,
                scenes=(first, second),
                blend_path=self.root / "rollback.blend",
            )

        self.assertEqual((first, second), originals)
        self.assertEqual(session.dirty_reasons, frozenset({"import"}))
        self.assertEqual(session.link_status, ProjectServiceStatus.INVALID.value)

    def test_clean_session_link_failure_marks_project_link_for_retry(self):
        class FailingScene(dict):
            failed = False

            def __setitem__(self, key, value):
                if key == MANIFEST_HASH_KEY and not self.failed:
                    self.failed = True
                    raise RuntimeError("new scene link write failed")
                super().__setitem__(key, value)

        session = self.create_session()
        session.mark_dirty("import")
        blend = self.root / "retry.blend"
        linked = {}
        self.save_for_scenes(
            session=session,
            scenes=(linked,),
            blend_path=blend,
        )
        self.assertFalse(session.dirty)

        with self.assertRaisesRegex(RuntimeError, "new scene link write failed"):
            self.save_for_scenes(
                session=session,
                scenes=(linked, FailingScene()),
                blend_path=blend,
            )

        self.assertEqual(session.dirty_reasons, frozenset({"project_link"}))
        self.assertEqual(session.link_status, ProjectServiceStatus.INVALID.value)

    def test_fatal_partial_scene_link_writes_restore_snapshot_and_identity(self):
        links = project_service._project_links()
        values = {
            PROJECT_ID_KEY: str(PROJECT_ID),
            PROJECT_SCHEMA_KEY: "0.2",
            SIDECAR_LOCATOR_KEY: "candidate.cbq",
            MANIFEST_HASH_KEY: "a" * 64,
        }

        for fatal in (
            KeyboardInterrupt("link write interrupted"),
            MemoryError("link write exhausted memory"),
        ):
            with self.subTest(error=type(fatal).__name__):
                scene = FatalLinkWriteScene(
                    {"scene-marker": "preserve"},
                    error=fatal,
                )

                with self.assertRaises(type(fatal)) as raised:
                    project_service._write_scene_links(
                        (scene,),
                        values,
                        links,
                    )

                self.assertIs(raised.exception, fatal)
                self.assertEqual(scene, {"scene-marker": "preserve"})

    def test_fatal_incomplete_link_rollback_preserves_identity_and_structure(self):
        links = project_service._project_links()
        fatal = KeyboardInterrupt("link write interrupted")
        scene = FatalLinkWriteScene(
            {"scene-marker": "preserve"},
            error=fatal,
            rollback_failure_key=PROJECT_ID_KEY,
        )
        values = {
            PROJECT_ID_KEY: str(PROJECT_ID),
            PROJECT_SCHEMA_KEY: "0.2",
            SIDECAR_LOCATOR_KEY: "candidate.cbq",
            MANIFEST_HASH_KEY: "b" * 64,
        }

        with self.assertRaises(KeyboardInterrupt) as raised:
            project_service._write_scene_links((scene,), values, links)

        self.assertIs(raised.exception, fatal)
        recovery = fatal.__cause__
        self.assertIsInstance(
            recovery,
            project_service.SceneLinkWriteRecoveryError,
        )
        self.assertIs(recovery.write_error, fatal)
        self.assertEqual(
            tuple(
                (failure.scene_index, failure.key, str(failure.error))
                for failure in recovery.rollback_failures
            ),
            ((0, PROJECT_ID_KEY, "Scene rollback failed"),),
        )
        self.assertEqual(recovery.residual_keys, ((0, PROJECT_ID_KEY),))
        self.assertIn(
            "Scene project link write failed and rollback was incomplete",
            fatal.__notes__[0],
        )
        self.assertIn("rollback_failures=", fatal.__notes__[0])
        self.assertIn("residual_keys=", fatal.__notes__[0])

    def test_link_sync_identical_scene_is_noop_and_preserves_storage(self):
        class NoWriteScene(dict):
            def __setitem__(self, key, value):
                raise AssertionError(f"unexpected Scene write: {key}")

        session = self.create_session(project=sample_project())
        blend = self.root / "noop.blend"
        scene = {}
        session.mark_dirty("import")
        self.save_for_scenes(
            session=session,
            scenes=(scene,),
            blend_path=blend,
        )
        sidecar = blend.with_suffix(".cbq")
        before = self.storage_snapshot(sidecar)
        scene = NoWriteScene(scene)

        result = project_service.sync_project_session_links_for_scenes(
            session=session,
            scenes=(scene,),
            blend_path=blend,
        )

        self.assertEqual(result.status, ProjectServiceStatus.CONNECTED)
        self.assertEqual(self.storage_snapshot(sidecar), before)
        self.assertFalse(session.dirty)

    def test_link_sync_adds_empty_scene_without_republishing(self):
        session = self.create_session(project=sample_project())
        blend = self.root / "expanded.blend"
        linked = {}
        session.mark_dirty("import")
        self.save_for_scenes(
            session=session,
            scenes=(linked,),
            blend_path=blend,
        )
        sidecar = blend.with_suffix(".cbq")
        before = self.storage_snapshot(sidecar)
        empty = {"scene-marker": "preserve"}

        result = project_service.sync_project_session_links_for_scenes(
            session=session,
            scenes=(linked, empty),
            blend_path=blend,
        )

        self.assertEqual(result.status, ProjectServiceStatus.CONNECTED)
        self.assertEqual(
            {key: empty[key] for key in LINK_KEYS},
            {key: linked[key] for key in LINK_KEYS},
        )
        self.assertEqual(empty["scene-marker"], "preserve")
        self.assertEqual(self.storage_snapshot(sidecar), before)

    def test_link_sync_rejects_partial_and_conflicting_links(self):
        session = self.create_session()
        blend = self.root / "conflicting.blend"
        linked = {}
        session.mark_dirty("import")
        self.save_for_scenes(
            session=session,
            scenes=(linked,),
            blend_path=blend,
        )
        cases = (
            {PROJECT_ID_KEY: linked[PROJECT_ID_KEY]},
            {
                **linked,
                MANIFEST_HASH_KEY: "f" * 64,
            },
        )

        for invalid in cases:
            with self.subTest(invalid=invalid):
                before = dict(invalid)
                result = project_service.sync_project_session_links_for_scenes(
                    session=session,
                    scenes=(linked, invalid),
                    blend_path=blend,
                )
                self.assertEqual(result.status, ProjectServiceStatus.INVALID)
                self.assertEqual(invalid, before)
                self.assertIn("project_link", session.dirty_reasons)

    def test_link_sync_updates_only_locator_and_clears_only_project_link(self):
        session = self.create_session()
        old_blend = self.root / "old" / "project.blend"
        old_blend.parent.mkdir()
        linked = {}
        session.mark_dirty("import")
        self.save_for_scenes(
            session=session,
            scenes=(linked,),
            blend_path=old_blend,
        )
        new_blend = self.root / "moved" / "project.blend"
        new_blend.parent.mkdir()
        expected_locator = os.path.relpath(
            session.sidecar_path,
            new_blend.parent,
        )
        session.mark_dirty("project_link")
        session.mark_dirty("view_cache")

        result = project_service.sync_project_session_links_for_scenes(
            session=session,
            scenes=(linked,),
            blend_path=new_blend,
        )

        self.assertEqual(result.status, ProjectServiceStatus.CONNECTED)
        self.assertEqual(linked[SIDECAR_LOCATOR_KEY], expected_locator)
        self.assertEqual(session.dirty_reasons, frozenset({"view_cache"}))

    def test_link_sync_rejects_divergent_complete_locators_without_mutation(self):
        session = self.create_session()
        blend = self.root / "locator-conflict.blend"
        first = {}
        second = {}
        session.mark_dirty("import")
        self.save_for_scenes(
            session=session,
            scenes=(first, second),
            blend_path=blend,
        )
        second[SIDECAR_LOCATOR_KEY] = "unrelated-location.cbq"
        session.mark_dirty("project_link")
        session.mark_dirty("view_cache")
        original_project = session.project
        original_sidecar = session.sidecar_path
        original_scenes = (dict(first), dict(second))
        before = self.storage_snapshot(original_sidecar)

        result = project_service.sync_project_session_links_for_scenes(
            session=session,
            scenes=(first, second),
            blend_path=blend,
        )

        self.assertEqual(result.status, ProjectServiceStatus.INVALID)
        self.assertEqual((dict(first), dict(second)), original_scenes)
        self.assertIs(session.project, original_project)
        self.assertEqual(session.sidecar_path, original_sidecar)
        self.assertEqual(session.link_status, ProjectServiceStatus.INVALID.value)
        self.assertEqual(
            session.dirty_reasons,
            frozenset({"project_link", "view_cache"}),
        )
        self.assertEqual(self.storage_snapshot(original_sidecar), before)

    def test_link_sync_updates_coherent_moved_locators_and_empty_scene(self):
        session = self.create_session()
        old_blend = self.root / "old-multi" / "project.blend"
        old_blend.parent.mkdir()
        first = {}
        second = {}
        session.mark_dirty("import")
        self.save_for_scenes(
            session=session,
            scenes=(first, second),
            blend_path=old_blend,
        )
        empty = {"scene-marker": "preserve"}
        new_blend = self.root / "moved-multi" / "project.blend"
        new_blend.parent.mkdir()
        expected_locator = os.path.relpath(
            session.sidecar_path,
            new_blend.parent,
        )
        session.mark_dirty("project_link")
        session.mark_dirty("view_cache")
        before = self.storage_snapshot(session.sidecar_path)

        result = project_service.sync_project_session_links_for_scenes(
            session=session,
            scenes=(first, empty, second),
            blend_path=new_blend,
        )

        self.assertEqual(result.status, ProjectServiceStatus.CONNECTED)
        self.assertEqual(
            {scene[SIDECAR_LOCATOR_KEY] for scene in (first, empty, second)},
            {expected_locator},
        )
        self.assertEqual(empty["scene-marker"], "preserve")
        self.assertEqual(session.dirty_reasons, frozenset({"view_cache"}))
        self.assertEqual(self.storage_snapshot(session.sidecar_path), before)

    def test_fatal_link_sync_restores_all_scenes_and_marks_retry(self):
        session = self.create_session(project=sample_project())
        old_blend = self.root / "fatal-sync-old" / "project.blend"
        old_blend.parent.mkdir()
        linked = {}
        session.mark_dirty("import")
        self.save_for_scenes(
            session=session,
            scenes=(linked,),
            blend_path=old_blend,
        )
        new_blend = self.root / "fatal-sync-new" / "project.blend"
        new_blend.parent.mkdir()
        fatal = KeyboardInterrupt("link sync interrupted")
        failing = FatalLinkWriteScene(
            {"scene-marker": "preserve"},
            error=fatal,
        )
        scenes = (linked, failing)
        originals = tuple(dict(scene) for scene in scenes)
        project = session.project
        sidecar = session.sidecar_path
        storage = self.storage_snapshot(sidecar)
        session.mark_dirty("view_cache")

        with self.assertRaises(KeyboardInterrupt) as raised:
            project_service.sync_project_session_links_for_scenes(
                session=session,
                scenes=scenes,
                blend_path=new_blend,
            )

        self.assertIs(raised.exception, fatal)
        self.assertEqual(tuple(dict(scene) for scene in scenes), originals)
        self.assertIs(session.project, project)
        self.assertEqual(session.sidecar_path, sidecar)
        self.assertEqual(session.link_status, ProjectServiceStatus.INVALID.value)
        self.assertEqual(
            session.dirty_reasons,
            frozenset({"project_link", "view_cache"}),
        )
        self.assertEqual(self.storage_snapshot(sidecar), storage)

    def test_verify_identical_scene_links_adopts_project_once(self):
        sidecar = self.root / "identical.cbq"
        stored = sample_project()
        save_project(sidecar, stored)
        first = self.linked_scene(sidecar, stored)
        second = dict(first)
        session = self.create_session()
        previous = session.project
        links = project_service._project_links()
        record_open, opened_projects, lazy_values = (
            self.loaded_candidate_recorder(links._open_project_with_manifest)
        )

        with patch.object(
            links,
            "_open_project_with_manifest",
            side_effect=record_open,
        ), patch.object(
            project_service,
            "close_project",
            wraps=project_service.close_project,
        ) as close:
            result = self.verify_for_scenes(
                session=session,
                scenes=(first, second),
            )

        self.assertEqual(result.status, ProjectServiceStatus.CONNECTED)
        self.assertIs(session.project, opened_projects[0])
        self.assertIs(result.project, session.project)
        self.assertTrue(lazy_values[0].loaded)
        self.assertEqual(
            lazy_values[0][0][1].tolist(),
            [0.0, 0.0, 0.74],
        )
        close.assert_called_once_with(previous)

    def test_verify_valid_and_empty_scene_projects_link_then_adopts_once(self):
        sidecar = self.root / "partial.cbq"
        stored = QCProject(id=PROJECT_ID, schema_version="0.2")
        save_project(sidecar, stored)
        linked = self.linked_scene(sidecar, stored)
        empty = {"scene-marker": "empty"}
        session = self.create_session()

        with patch.object(
            project_service,
            "_adopt_project",
            wraps=project_service._adopt_project,
        ) as adopt:
            result = self.verify_for_scenes(
                session=session,
                scenes=(linked, empty),
            )

        self.assertEqual(result.status, ProjectServiceStatus.CONNECTED)
        self.assertEqual(
            {key: empty[key] for key in LINK_KEYS},
            {key: linked[key] for key in LINK_KEYS},
        )
        self.assertEqual(empty["scene-marker"], "empty")
        adopt.assert_called_once()

    def test_fatal_multi_scene_verify_rolls_back_and_closes_candidate(self):
        sidecar = self.root / "fatal-verify.cbq"
        stored = sample_project()
        save_project(sidecar, stored)
        linked = self.linked_scene(sidecar, stored)
        fatal = KeyboardInterrupt("verify link write interrupted")
        failing = FatalLinkWriteScene(
            {"scene-marker": "preserve"},
            error=fatal,
        )
        scenes = (linked, failing)
        originals = tuple(dict(scene) for scene in scenes)
        session = self.create_session()
        session.mark_dirty("import")
        before = (
            session.project,
            session.sidecar_path,
            session.dirty_reasons,
        )
        links = project_service._project_links()
        record_open, opened_projects, lazy_values = (
            self.loaded_candidate_recorder(links._open_project_with_manifest)
        )

        with patch.object(
            links,
            "_open_project_with_manifest",
            side_effect=record_open,
        ), patch.object(
            project_service,
            "close_project",
            wraps=project_service.close_project,
        ) as close:
            with self.assertRaises(KeyboardInterrupt) as raised:
                self.verify_for_scenes(session=session, scenes=scenes)

        self.assertIs(raised.exception, fatal)
        self.assertEqual(tuple(dict(scene) for scene in scenes), originals)
        self.assertEqual(
            (
                session.project,
                session.sidecar_path,
                session.dirty_reasons,
            ),
            before,
        )
        self.assertEqual(session.link_status, ProjectServiceStatus.INVALID.value)
        close.assert_called_once_with(opened_projects[0])
        self.assertFalse(lazy_values[0].loaded)

    def test_multi_scene_verify_adoption_failure_restores_links_and_candidate(self):
        sidecar = self.root / "verify-adoption-failure.cbq"
        stored = sample_project()
        save_project(sidecar, stored)
        linked = self.linked_scene(sidecar, stored)
        empty = {"scene-marker": "empty"}
        scenes = (linked, empty)
        originals = tuple(dict(scene) for scene in scenes)
        session = self.create_session()
        session.mark_dirty("import")
        previous = session.project
        before = (
            session.project,
            session.sidecar_path,
            session.link_status,
            session.dirty_reasons,
        )
        opened_projects = []
        lazy_values = []
        closed = []
        links = project_service._project_links()
        real_open = links._open_project_with_manifest
        real_close = project_service.close_project

        def record_open(*args, **kwargs):
            project, manifest = real_open(*args, **kwargs)
            values = project.datasets[FRAMES_ID].data.values
            values[0]
            opened_projects.append(project)
            lazy_values.append(values)
            return project, manifest

        def fail_previous(project):
            if project is previous:
                raise OSError("old project close failed")
            closed.append(project)
            return real_close(project)

        try:
            with patch.object(
                links,
                "_open_project_with_manifest",
                side_effect=record_open,
            ), patch.object(
                project_service,
                "close_project",
                side_effect=fail_previous,
            ):
                with self.assertRaisesRegex(OSError, "^old project close failed$"):
                    self.verify_for_scenes(session=session, scenes=scenes)
            actual_scenes = tuple(dict(scene) for scene in scenes)
            candidate_loaded = lazy_values[0].loaded
        finally:
            for project in opened_projects:
                real_close(project)

        self.assertEqual(actual_scenes, originals)
        self.assertEqual(
            (
                session.project,
                session.sidecar_path,
                session.link_status,
                session.dirty_reasons,
            ),
            before,
        )
        self.assertEqual(closed, opened_projects)
        self.assertFalse(candidate_loaded)

    def test_adoption_fatal_baseexceptions_restore_links_and_close_candidate(self):
        sidecar = self.root / "fatal-adoption.cbq"
        save_project(sidecar, sample_project())
        real_close = project_service.close_project

        for fatal in (KeyboardInterrupt(), SystemExit(), GeneratorExit()):
            with self.subTest(error=type(fatal).__name__):
                session = self.create_session()
                previous = session.project
                before = (
                    session.project,
                    session.sidecar_path,
                    session.link_status,
                    session.dirty_reasons,
                )
                candidate = open_project(sidecar)
                lazy_values = candidate.datasets[FRAMES_ID].data.values
                lazy_values[0]
                scenes = (
                    {"scene-marker": "linked"},
                    {"scene-marker": "empty"},
                )
                originals = tuple(dict(scene) for scene in scenes)
                snapshots = tuple(
                    (
                        scene,
                        {
                            key: project_service._MISSING_LINK_VALUE
                            for key in LINK_KEYS
                        },
                    )
                    for scene in scenes
                )
                for scene in scenes:
                    scene.update({key: "candidate" for key in LINK_KEYS})
                closed = []

                def fail_previous(project):
                    if project is previous:
                        raise fatal
                    closed.append(project)
                    real_close(project)

                try:
                    with patch.object(
                        project_service,
                        "close_project",
                        side_effect=fail_previous,
                    ):
                        with self.assertRaises(type(fatal)) as raised:
                            project_service._adopt_verified_project(
                                session,
                                candidate,
                                sidecar,
                                scene_snapshots=snapshots,
                            )
                    actual_scenes = tuple(dict(scene) for scene in scenes)
                    candidate_loaded = lazy_values.loaded
                finally:
                    real_close(candidate)

                self.assertIs(raised.exception, fatal)
                self.assertEqual(actual_scenes, originals)
                self.assertEqual(closed, [candidate])
                self.assertFalse(candidate_loaded)
                self.assertEqual(
                    (
                        session.project,
                        session.sidecar_path,
                        session.link_status,
                        session.dirty_reasons,
                    ),
                    before,
                )

    def test_memory_error_survives_incomplete_rollback_and_cleanup_failure(self):
        class RollbackFailingScene(dict):
            fail_restore = False

            def __delitem__(self, key):
                if key == MANIFEST_HASH_KEY and self.fail_restore:
                    raise RuntimeError("Scene rollback failed")
                super().__delitem__(key)

        sidecar = self.root / "fatal-structured.cbq"
        save_project(sidecar, sample_project())
        session = self.create_session()
        previous = session.project
        before = (
            session.project,
            session.sidecar_path,
            session.link_status,
            session.dirty_reasons,
        )
        candidate = open_project(sidecar)
        lazy_values = candidate.datasets[FRAMES_ID].data.values
        lazy_values[0]
        scene = RollbackFailingScene({"scene-marker": "preserve"})
        original = dict(scene)
        snapshot = {
            key: project_service._MISSING_LINK_VALUE
            for key in LINK_KEYS
        }
        scene.update({key: "candidate" for key in LINK_KEYS})
        scene.fail_restore = True
        fatal = MemoryError("adoption exhausted memory")
        real_close = project_service.close_project
        closed = []

        def fail_cleanup(project):
            if project is previous:
                raise fatal
            closed.append(project)
            real_close(project)
            raise OSError("candidate cleanup failed")

        try:
            with patch.object(
                project_service,
                "close_project",
                side_effect=fail_cleanup,
            ):
                with self.assertRaises(MemoryError) as raised:
                    project_service._adopt_verified_project(
                        session,
                        candidate,
                        sidecar,
                        scene_snapshots=((scene, snapshot),),
                    )
            candidate_loaded = lazy_values.loaded
        finally:
            real_close(candidate)

        self.assertIs(raised.exception, fatal)
        self.assertEqual(closed, [candidate])
        self.assertFalse(candidate_loaded)
        self.assertEqual(
            (
                session.project,
                session.sidecar_path,
                session.link_status,
                session.dirty_reasons,
            ),
            before,
        )
        self.assertEqual(
            scene,
            {
                **original,
                MANIFEST_HASH_KEY: "candidate",
            },
        )
        notes = fatal.__notes__
        self.assertEqual(len(notes), 2)
        self.assertIn(
            "Scene project link write failed and rollback was incomplete",
            notes[0],
        )
        self.assertIn("rollback_failures=", notes[0])
        self.assertIn(MANIFEST_HASH_KEY, notes[0])
        self.assertIn("residual_keys=", notes[0])
        self.assertEqual(
            notes[1],
            "candidate project cleanup failed: candidate cleanup failed",
        )

    def test_multi_scene_verify_incomplete_adoption_rollback_is_structured(self):
        class RollbackFailingScene(dict):
            fail_restore = False

            def __delitem__(self, key):
                if key == MANIFEST_HASH_KEY and self.fail_restore:
                    raise RuntimeError("Scene rollback failed")
                super().__delitem__(key)

        sidecar = self.root / "verify-structured.cbq"
        stored = sample_project()
        save_project(sidecar, stored)
        linked = self.linked_scene(sidecar, stored)
        failing = RollbackFailingScene({"scene-marker": "preserve"})
        scenes = (linked, failing)
        session = self.create_session()
        session.mark_dirty("import")
        previous = session.project
        before = (
            session.project,
            session.sidecar_path,
            session.link_status,
            session.dirty_reasons,
        )
        closed = []
        links = project_service._project_links()
        record_open, opened_projects, lazy_values = (
            self.loaded_candidate_recorder(links._open_project_with_manifest)
        )
        real_close = project_service.close_project

        def fail_cleanup(project):
            if project is previous:
                failing.fail_restore = True
                raise OSError("old project close failed")
            closed.append(project)
            real_close(project)
            raise OSError("candidate cleanup failed")

        try:
            with patch.object(
                links,
                "_open_project_with_manifest",
                side_effect=record_open,
            ), patch.object(
                project_service,
                "close_project",
                side_effect=fail_cleanup,
            ):
                with self.assertRaises(
                    project_service.SceneLinkWriteRecoveryError
                ) as caught:
                    self.verify_for_scenes(session=session, scenes=scenes)
            candidate_loaded = lazy_values[0].loaded
        finally:
            for project in opened_projects:
                real_close(project)

        error = caught.exception
        self.assertEqual(str(error.write_error), "old project close failed")
        self.assertEqual(
            tuple(
                (failure.scene_index, failure.key, str(failure.error))
                for failure in error.rollback_failures
            ),
            ((1, MANIFEST_HASH_KEY, "Scene rollback failed"),),
        )
        self.assertEqual(error.residual_keys, ((1, MANIFEST_HASH_KEY),))
        self.assertEqual(
            error.__notes__,
            ["candidate project cleanup failed: candidate cleanup failed"],
        )
        self.assertEqual(closed, opened_projects)
        self.assertFalse(candidate_loaded)
        self.assertEqual(dict(linked), self.linked_scene(sidecar, stored))
        self.assertEqual(
            failing,
            {
                "scene-marker": "preserve",
                MANIFEST_HASH_KEY: linked[MANIFEST_HASH_KEY],
            },
        )
        self.assertEqual(
            (
                session.project,
                session.sidecar_path,
                session.link_status,
                session.dirty_reasons,
            ),
            before,
        )

    def test_verify_conflicting_valid_scene_links_fails_closed(self):
        first_project = QCProject(id=PROJECT_ID, schema_version="0.2")
        second_project = QCProject(id=UUID(int=2), schema_version="0.2")
        first_sidecar = self.root / "first.cbq"
        second_sidecar = self.root / "second.cbq"
        save_project(first_sidecar, first_project)
        save_project(second_sidecar, second_project)
        scenes = (
            self.linked_scene(first_sidecar, first_project),
            self.linked_scene(second_sidecar, second_project),
        )
        originals = tuple(dict(scene) for scene in scenes)
        session = self.create_session()
        original_project = session.project

        result = self.verify_for_scenes(session=session, scenes=scenes)

        self.assertEqual(result.status, ProjectServiceStatus.INVALID)
        self.assertEqual(result.message, "conflicting scene project links")
        self.assertIs(session.project, original_project)
        self.assertEqual(tuple(dict(scene) for scene in scenes), originals)
        self.assertNotEqual(session.link_status, "connected")

    def test_save_scene_write_failure_is_unexpected_and_marks_session_invalid(self):
        class FailingScene(dict):
            failed = False

            def __setitem__(self, key, value):
                if key == MANIFEST_HASH_KEY and not self.failed:
                    self.failed = True
                    raise RuntimeError("scene write failed")
                super().__setitem__(key, value)

        session = self.create_session()
        session.mark_dirty("import")
        scene = FailingScene({"view-marker": "preserve"})

        with self.assertRaisesRegex(RuntimeError, "scene write failed"):
            save_project_session(
                session=session,
                scene=scene,
                blend_path=self.root / "sample.blend",
            )

        self.assertEqual(session.sidecar_path, (self.root / "sample.cbq").resolve())
        self.assertEqual(session.link_status, "invalid")
        self.assertEqual(session.dirty_reasons, frozenset({"import"}))
        self.assertEqual(scene, {"view-marker": "preserve"})
        self.assertTrue((self.root / "sample.cbq" / "manifest.json").is_file())

    def test_fatal_save_link_write_rolls_back_and_marks_session_invalid(self):
        session = self.create_session()
        session.mark_dirty("import")
        fatal = KeyboardInterrupt("save link write interrupted")
        first = {"scene-marker": "first"}
        failing = FatalLinkWriteScene(
            {"scene-marker": "second"},
            error=fatal,
        )
        scenes = (first, failing)
        originals = tuple(dict(scene) for scene in scenes)
        project = session.project
        blend = self.root / "fatal-save.blend"

        with self.assertRaises(KeyboardInterrupt) as raised:
            self.save_for_scenes(
                session=session,
                scenes=scenes,
                blend_path=blend,
            )

        self.assertIs(raised.exception, fatal)
        self.assertEqual(tuple(dict(scene) for scene in scenes), originals)
        self.assertIs(session.project, project)
        self.assertEqual(session.sidecar_path, blend.with_suffix(".cbq").resolve())
        self.assertEqual(session.link_status, ProjectServiceStatus.INVALID.value)
        self.assertEqual(session.dirty_reasons, frozenset({"import"}))

    def test_save_new_generation_scene_failure_never_leaves_connected_status(self):
        session = self.create_session()
        blend = self.root / "existing.blend"
        scene = {}
        save_project_session(session=session, scene=scene, blend_path=blend)
        session.mark_dirty("edit")
        old_scene = dict(scene)

        class FailingScene(dict):
            failed = False

            def __setitem__(self, key, value):
                if key == MANIFEST_HASH_KEY and not self.failed:
                    self.failed = True
                    raise RuntimeError("scene write failed")
                super().__setitem__(key, value)

        failing_scene = FailingScene(scene)
        with self.assertRaisesRegex(RuntimeError, "scene write failed"):
            save_project_session(
                session=session,
                scene=failing_scene,
                blend_path=blend,
            )

        manifest = json.loads(
            (self.root / "existing.cbq" / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(failing_scene, old_scene)
        self.assertNotEqual(
            failing_scene[MANIFEST_HASH_KEY],
            manifest["manifest_sha256"],
        )
        self.assertEqual(session.sidecar_path, (self.root / "existing.cbq").resolve())
        self.assertEqual(session.link_status, "invalid")
        self.assertEqual(session.dirty_reasons, frozenset({"edit"}))

    def test_verify_connected_replaces_session_project_and_transfers_ownership(self):
        sidecar = self.root / "stored.cbq"
        stored = QCProject(id=PROJECT_ID, schema_version="0.2")
        save_project(sidecar, stored)
        scene = self.linked_scene(sidecar, stored)
        session = self.create_session()
        session.mark_dirty("import")
        previous = session.project

        with patch.object(
            project_service,
            "close_project",
            wraps=project_service.close_project,
        ) as close:
            result = verify_project_session(session=session, scene=scene)

        self.assertEqual(result.status, ProjectServiceStatus.CONNECTED)
        self.assertIs(result.project, session.project)
        self.assertIsNot(session.project, previous)
        self.assertEqual(session.sidecar_path, sidecar.resolve())
        self.assertEqual(session.link_status, "connected")
        self.assertFalse(session.dirty)
        close.assert_called_once_with(previous)

    def test_verify_connected_closes_replaced_lazy_array_resources(self):
        previous_sidecar = self.root / "previous.cbq"
        save_project(previous_sidecar, sample_project())
        previous = open_project(previous_sidecar)
        lazy_values = previous.datasets[FRAMES_ID].data.values
        lazy_values[0]
        self.assertTrue(lazy_values.loaded)
        candidate = self.root / "candidate-lazy.cbq"
        stored = QCProject(id=previous.id, schema_version="0.2")
        save_project(candidate, stored)
        scene = self.linked_scene(candidate, stored)
        session = self.create_session(project=previous)

        result = verify_project_session(session=session, scene=scene)

        self.assertEqual(result.status, ProjectServiceStatus.CONNECTED)
        self.assertFalse(lazy_values.loaded)

    def test_single_scene_verify_adoption_failure_closes_candidate(self):
        sidecar = self.root / "single-verify-adoption-failure.cbq"
        stored = sample_project()
        save_project(sidecar, stored)
        scene = self.linked_scene(sidecar, stored)
        original_scene = dict(scene)
        session = self.create_session()
        session.mark_dirty("import")
        previous = session.project
        before = (
            session.project,
            session.sidecar_path,
            session.link_status,
            session.dirty_reasons,
        )
        opened_projects = []
        lazy_values = []
        closed = []
        links = project_service._project_links()
        real_open = links._open_project_with_manifest
        real_close = project_service.close_project

        def record_open(*args, **kwargs):
            project, manifest = real_open(*args, **kwargs)
            values = project.datasets[FRAMES_ID].data.values
            values[0]
            opened_projects.append(project)
            lazy_values.append(values)
            return project, manifest

        def fail_previous(project):
            if project is previous:
                raise OSError("old project close failed")
            closed.append(project)
            return real_close(project)

        try:
            with patch.object(
                links,
                "_open_project_with_manifest",
                side_effect=record_open,
            ), patch.object(
                project_service,
                "close_project",
                side_effect=fail_previous,
            ):
                with self.assertRaisesRegex(OSError, "^old project close failed$"):
                    verify_project_session(session=session, scene=scene)
            candidate_loaded = lazy_values[0].loaded
        finally:
            for project in opened_projects:
                real_close(project)

        self.assertEqual(scene, original_scene)
        self.assertEqual(
            (
                session.project,
                session.sidecar_path,
                session.link_status,
                session.dirty_reasons,
            ),
            before,
        )
        self.assertEqual(closed, opened_projects)
        self.assertFalse(candidate_loaded)

    def test_verify_missing_does_not_mutate_scene_or_session(self):
        sidecar = self.root / "missing.cbq"
        stored = QCProject(id=PROJECT_ID, schema_version="0.2")
        save_project(sidecar, stored)
        scene = self.linked_scene(sidecar, stored)
        for path in sorted(sidecar.rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
        sidecar.rmdir()
        session = self.create_session()
        session.mark_dirty("import")
        before = (session.project, session.sidecar_path, session.link_status, dict(scene))

        result = verify_project_session(session=session, scene=scene)

        self.assertEqual(result.status, ProjectServiceStatus.MISSING)
        self.assertEqual(
            (session.project, session.sidecar_path, session.link_status, scene),
            before,
        )
        self.assertEqual(session.dirty_reasons, frozenset({"import"}))

    def test_verify_mismatch_does_not_mutate_scene_or_session(self):
        sidecar = self.root / "changed.cbq"
        stored = QCProject(id=PROJECT_ID, schema_version="0.2")
        save_project(sidecar, stored)
        scene = self.linked_scene(sidecar, stored)
        save_project(sidecar, stored)
        session = self.create_session()
        session.mark_dirty("import")
        before = (session.project, session.sidecar_path, session.link_status, dict(scene))

        result = verify_project_session(session=session, scene=scene)

        self.assertEqual(result.status, ProjectServiceStatus.MISMATCH)
        self.assertEqual(
            (session.project, session.sidecar_path, session.link_status, scene),
            before,
        )
        self.assertEqual(session.dirty_reasons, frozenset({"import"}))

    def test_verify_invalid_does_not_mutate_scene_or_session(self):
        sidecar = self.root / "invalid.cbq"
        stored = QCProject(id=PROJECT_ID, schema_version="0.2")
        save_project(sidecar, stored)
        scene = self.linked_scene(sidecar, stored)
        (sidecar / "manifest.json").write_text("{", encoding="utf-8")
        session = self.create_session()
        session.mark_dirty("import")
        before = (session.project, session.sidecar_path, session.link_status, dict(scene))

        result = verify_project_session(session=session, scene=scene)

        self.assertEqual(result.status, ProjectServiceStatus.INVALID)
        self.assertEqual(
            (session.project, session.sidecar_path, session.link_status, scene),
            before,
        )
        self.assertEqual(session.dirty_reasons, frozenset({"import"}))

    def test_verify_incompatible_does_not_mutate_scene_or_session(self):
        sidecar = self.root / "incompatible.cbq"
        stored = QCProject(id=PROJECT_ID, schema_version="0.2")
        save_project(sidecar, stored)
        scene = self.linked_scene(sidecar, stored)
        scene[PROJECT_SCHEMA_KEY] = "9.9"
        session = self.create_session()
        session.mark_dirty("import")
        before = (session.project, session.sidecar_path, session.link_status, dict(scene))

        result = verify_project_session(session=session, scene=scene)

        self.assertEqual(result.status, ProjectServiceStatus.INCOMPATIBLE)
        self.assertEqual(
            (session.project, session.sidecar_path, session.link_status, scene),
            before,
        )
        self.assertEqual(session.dirty_reasons, frozenset({"import"}))

    def test_relink_uuid_mismatch_has_zero_mutation(self):
        sidecar = self.root / "other.cbq"
        save_project(sidecar, QCProject(id=UUID(int=2), schema_version="0.2"))
        session = self.create_session()
        session.mark_dirty("import")
        scene = {"view-marker": "preserve"}
        before = (session.project, session.sidecar_path, session.link_status, dict(scene))

        result = relink_project_session(
            session=session,
            scene=scene,
            sidecar_path=sidecar,
        )

        self.assertEqual(result.status, ProjectServiceStatus.MISMATCH)
        self.assertEqual(
            (session.project, session.sidecar_path, session.link_status, scene),
            before,
        )
        self.assertEqual(session.dirty_reasons, frozenset({"import"}))

    def test_relink_missing_and_invalid_have_zero_mutation(self):
        for case in ("missing", "invalid"):
            with self.subTest(case=case):
                sidecar = self.root / f"{case}.cbq"
                if case == "invalid":
                    sidecar.mkdir()
                    (sidecar / "manifest.json").write_text("{", encoding="utf-8")
                session = self.create_session()
                session.mark_dirty("import")
                scene = {"view-marker": "preserve"}
                before = (
                    session.project,
                    session.sidecar_path,
                    session.link_status,
                    dict(scene),
                )

                result = relink_project_session(
                    session=session,
                    scene=scene,
                    sidecar_path=sidecar,
                )

                self.assertEqual(
                    result.status,
                    (
                        ProjectServiceStatus.MISSING
                        if case == "missing"
                        else ProjectServiceStatus.INVALID
                    ),
                )
                self.assertEqual(
                    (session.project, session.sidecar_path, session.link_status, scene),
                    before,
                )
                self.assertEqual(session.dirty_reasons, frozenset({"import"}))

    def test_relink_incompatible_has_zero_mutation(self):
        sidecar = self.root / "future.cbq"
        save_project(sidecar, QCProject(id=PROJECT_ID, schema_version="0.2"))
        manifest_path = sidecar / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["manifest_version"] = "9.9"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        session = self.create_session()
        session.mark_dirty("import")
        scene = {"view-marker": "preserve"}
        before = (session.project, session.sidecar_path, session.link_status, dict(scene))

        result = relink_project_session(
            session=session,
            scene=scene,
            sidecar_path=sidecar,
        )

        self.assertEqual(result.status, ProjectServiceStatus.INCOMPATIBLE)
        self.assertEqual(
            (session.project, session.sidecar_path, session.link_status, scene),
            before,
        )
        self.assertEqual(session.dirty_reasons, frozenset({"import"}))

    def test_relink_verified_sidecar_updates_scene_and_session_consistently(self):
        sidecar = self.root / "candidate.cbq"
        stored = QCProject(id=PROJECT_ID, schema_version="0.2")
        save_project(sidecar, stored)
        session = self.create_session()
        session.mark_dirty("import")
        scene = {"view-marker": "preserve"}

        result = relink_project_session(
            session=session,
            scene=scene,
            sidecar_path=sidecar,
        )

        self.assertEqual(result.status, ProjectServiceStatus.CONNECTED)
        self.assertIs(result.project, session.project)
        self.assertEqual(session.sidecar_path, sidecar.resolve())
        self.assertEqual(session.link_status, "connected")
        self.assertFalse(session.dirty)
        self.assertEqual(scene[MANIFEST_HASH_KEY], result.manifest_sha256)
        self.assertEqual(scene[SIDECAR_LOCATOR_KEY], str(sidecar.resolve()))
        self.assertEqual(scene["view-marker"], "preserve")

    def test_relink_scene_write_failure_closes_candidate_and_has_zero_mutation(self):
        class FailingScene(dict):
            failed = False

            def __setitem__(self, key, value):
                if key == MANIFEST_HASH_KEY and not self.failed:
                    self.failed = True
                    raise RuntimeError("scene write failed")
                super().__setitem__(key, value)

        sidecar = self.root / "candidate-failure.cbq"
        stored = QCProject(id=PROJECT_ID, schema_version="0.2")
        save_project(sidecar, stored)
        session = self.create_session()
        session.mark_dirty("import")
        scene = FailingScene({"view-marker": "preserve"})
        before = (session.project, session.sidecar_path, session.link_status, dict(scene))

        with self.assertRaisesRegex(RuntimeError, "scene write failed"):
            relink_project_session(
                session=session,
                scene=scene,
                sidecar_path=sidecar,
            )

        self.assertEqual(
            (session.project, session.sidecar_path, session.link_status, scene),
            before,
        )
        self.assertEqual(session.dirty_reasons, frozenset({"import"}))

    def test_fatal_multi_scene_relink_rolls_back_and_closes_candidate(self):
        session = self.create_session()
        session.mark_dirty("import")
        candidate = self.root / "fatal-relink.cbq"
        save_project(candidate, sample_project())
        fatal = KeyboardInterrupt("relink write interrupted")
        first = {"scene-marker": "first"}
        failing = FatalLinkWriteScene(
            {"scene-marker": "second"},
            error=fatal,
        )
        scenes = (first, failing)
        originals = tuple(dict(scene) for scene in scenes)
        before = (
            session.project,
            session.sidecar_path,
            session.link_status,
            session.dirty_reasons,
        )
        record_open, opened_projects, lazy_values = (
            self.loaded_candidate_recorder(
                project_service._open_project_with_manifest
            )
        )

        with patch.object(
            project_service,
            "_open_project_with_manifest",
            side_effect=record_open,
        ), patch.object(
            project_service,
            "close_project",
            wraps=project_service.close_project,
        ) as close:
            with self.assertRaises(KeyboardInterrupt) as raised:
                project_service.relink_project_session_for_scenes(
                    session=session,
                    scenes=scenes,
                    sidecar_path=candidate,
                )

        self.assertIs(raised.exception, fatal)
        self.assertEqual(tuple(dict(scene) for scene in scenes), originals)
        self.assertEqual(
            (
                session.project,
                session.sidecar_path,
                session.link_status,
                session.dirty_reasons,
            ),
            before,
        )
        close.assert_called_once_with(opened_projects[0])
        self.assertFalse(lazy_values[0].loaded)

    def test_multi_scene_relink_opens_once_and_closes_old_project_once(self):
        session = self.create_session()
        blend = self.root / "scene" / "view.blend"
        blend.parent.mkdir()
        old_sidecar = blend.with_suffix(".cbq")
        first = {}
        second = {}
        session.mark_dirty("import")
        self.save_for_scenes(
            session=session,
            scenes=(first, second),
            blend_path=blend,
        )
        candidate = self.root / "data" / "candidate.cbq"
        save_project(candidate, sample_project())
        previous = session.project
        record_open, opened_projects, lazy_values = (
            self.loaded_candidate_recorder(
                project_service._open_project_with_manifest
            )
        )

        with patch.object(
            project_service,
            "_open_project_with_manifest",
            side_effect=record_open,
        ) as opened, patch.object(
            project_service,
            "close_project",
            wraps=project_service.close_project,
        ) as close:
            result = project_service.relink_project_session_for_scenes(
                session=session,
                scenes=(first, second),
                sidecar_path=candidate,
                blend_path=blend,
            )

        self.assertEqual(result.status, ProjectServiceStatus.CONNECTED)
        opened.assert_called_once()
        close.assert_called_once_with(previous)
        self.assertIs(session.project, opened_projects[0])
        self.assertIs(result.project, session.project)
        self.assertTrue(lazy_values[0].loaded)
        self.assertEqual(
            lazy_values[0][0][1].tolist(),
            [0.0, 0.0, 0.74],
        )
        expected = {key: first[key] for key in LINK_KEYS}
        self.assertEqual({key: second[key] for key in LINK_KEYS}, expected)
        self.assertEqual(
            first[SIDECAR_LOCATOR_KEY],
            os.path.relpath(candidate, blend.parent),
        )
        self.assertNotEqual(session.sidecar_path, old_sidecar.resolve())

    def test_multi_scene_relink_failure_restores_all_and_closes_candidate(self):
        class FailingScene(dict):
            fail_next = False

            def __setitem__(self, key, value):
                if key == MANIFEST_HASH_KEY and self.fail_next:
                    self.fail_next = False
                    raise RuntimeError("second Scene write failed")
                super().__setitem__(key, value)

        session = self.create_session(project=sample_project())
        blend = self.root / "rollback.blend"
        first = {}
        second = FailingScene()
        session.mark_dirty("import")
        self.save_for_scenes(
            session=session,
            scenes=(first, second),
            blend_path=blend,
        )
        candidate = self.root / "candidate-lazy.cbq"
        save_project(candidate, sample_project())
        originals = (dict(first), dict(second))
        previous = session.project
        opened_projects = []
        lazy_values = []
        real_open = project_service._open_project_with_manifest

        def record_open(*args, **kwargs):
            project, manifest = real_open(*args, **kwargs)
            values = project.datasets[FRAMES_ID].data.values
            values[0]
            opened_projects.append(project)
            lazy_values.append(values)
            return project, manifest

        second.fail_next = True
        with patch.object(
            project_service,
            "_open_project_with_manifest",
            side_effect=record_open,
        ) as opened, patch.object(
            project_service,
            "close_project",
            wraps=project_service.close_project,
        ) as close:
            with self.assertRaisesRegex(
                RuntimeError,
                "second Scene write failed",
            ):
                project_service.relink_project_session_for_scenes(
                    session=session,
                    scenes=(first, second),
                    sidecar_path=candidate,
                    blend_path=blend,
                )

        opened.assert_called_once()
        close.assert_called_once_with(opened_projects[0])
        self.assertFalse(lazy_values[0].loaded)
        self.assertIs(session.project, previous)
        self.assertEqual((first, second), originals)

    def test_multi_scene_relink_incomplete_rollback_is_structured(self):
        class RollbackFailingScene(dict):
            fail_restore = False

            def __setitem__(self, key, value):
                if (
                    key == MANIFEST_HASH_KEY
                    and self.fail_restore
                    and value == "1" * 64
                ):
                    raise RuntimeError("first Scene rollback failed")
                super().__setitem__(key, value)

        class WriteFailingScene(dict):
            def __setitem__(self, key, value):
                if key == MANIFEST_HASH_KEY:
                    raise RuntimeError("second Scene write failed")
                super().__setitem__(key, value)

        session = self.create_session()
        candidate = self.root / "structured.cbq"
        save_project(candidate, session.project)
        first = RollbackFailingScene(
            {
                PROJECT_ID_KEY: "old",
                PROJECT_SCHEMA_KEY: "0.2",
                SIDECAR_LOCATOR_KEY: "old.cbq",
                MANIFEST_HASH_KEY: "1" * 64,
            }
        )
        second = WriteFailingScene()
        first.fail_restore = True
        with self.assertRaises(
            project_service.SceneLinkWriteRecoveryError
        ) as caught:
            project_service.relink_project_session_for_scenes(
                session=session,
                scenes=(first, second),
                sidecar_path=candidate,
            )

        error = caught.exception
        self.assertEqual(str(error.write_error), "second Scene write failed")
        self.assertEqual(
            tuple((failure.scene_index, failure.key) for failure in error.rollback_failures),
            ((0, MANIFEST_HASH_KEY),),
        )
        self.assertEqual(
            error.residual_keys,
            ((0, MANIFEST_HASH_KEY),),
        )

    def test_multi_scene_relink_adoption_failure_restores_links_and_candidate(self):
        session = self.create_session()
        candidate = self.root / "adoption-failure.cbq"
        save_project(candidate, session.project)
        scenes = ({}, {})
        originals = tuple(dict(scene) for scene in scenes)
        previous = session.project
        real_close = project_service.close_project
        closed = []

        def fail_previous(project):
            if project is previous:
                raise OSError("old project close failed")
            closed.append(project)
            return real_close(project)

        with patch.object(
            project_service,
            "close_project",
            side_effect=fail_previous,
        ):
            with self.assertRaisesRegex(OSError, "old project close failed"):
                project_service.relink_project_session_for_scenes(
                    session=session,
                    scenes=scenes,
                    sidecar_path=candidate,
                )

        self.assertIs(session.project, previous)
        self.assertEqual(tuple(dict(scene) for scene in scenes), originals)
        self.assertEqual(len(closed), 1)

    def test_single_scene_relink_delegates_to_multi_scene_service(self):
        session = self.create_session()
        scene = {}
        expected = project_service.ProjectServiceResult(
            ProjectServiceStatus.MISSING,
        )

        with patch.object(
            project_service,
            "relink_project_session_for_scenes",
            return_value=expected,
            create=True,
        ) as relink_many:
            result = relink_project_session(
                session=session,
                scene=scene,
                sidecar_path=self.root / "missing.cbq",
                blend_path=self.root / "view.blend",
            )

        self.assertIs(result, expected)
        relink_many.assert_called_once_with(
            session=session,
            scenes=(scene,),
            sidecar_path=self.root / "missing.cbq",
            blend_path=self.root / "view.blend",
        )

    def test_clear_cache_removes_only_derivation_and_render_namespaces(self):
        sidecar = self.root / "cache.cbq"
        session = self.create_session()
        session.mark_dirty("import")
        save_project(sidecar, QCProject(id=PROJECT_ID, schema_version="0.2"))
        (sidecar / "arrays" / "authoritative.npy").write_bytes(b"array-bytes")
        manifest_before = (sidecar / "manifest.json").read_bytes()
        arrays_before = tuple(
            (path.relative_to(sidecar), path.read_bytes())
            for path in sorted((sidecar / "arrays").glob("*"))
        )
        for namespace in ("derivation", "render", "parser", "source"):
            directory = sidecar / "cache" / namespace
            directory.mkdir(parents=True)
            (directory / "keep.bin").write_bytes(namespace.encode("ascii"))
        unknown = sidecar / "keep.txt"
        unknown.write_text("keep", encoding="utf-8")

        result = clear_derived_cache(sidecar_path=sidecar)

        self.assertEqual(result.removed_count, 2)
        self.assertFalse((sidecar / "cache" / "derivation").exists())
        self.assertFalse((sidecar / "cache" / "render").exists())
        self.assertTrue((sidecar / "cache" / "parser" / "keep.bin").is_file())
        self.assertTrue((sidecar / "cache" / "source" / "keep.bin").is_file())
        self.assertEqual(unknown.read_text(encoding="utf-8"), "keep")
        self.assertEqual((sidecar / "manifest.json").read_bytes(), manifest_before)
        self.assertEqual(
            tuple(
                (path.relative_to(sidecar), path.read_bytes())
                for path in sorted((sidecar / "arrays").glob("*"))
            ),
            arrays_before,
        )
        self.assertEqual(session.dirty_reasons, frozenset({"import"}))

    def test_clear_cache_without_cache_is_idempotent(self):
        sidecar = self.root / "empty.cbq"
        save_project(sidecar, QCProject(id=PROJECT_ID, schema_version="0.2"))

        first = clear_derived_cache(sidecar_path=sidecar)
        second = clear_derived_cache(sidecar_path=sidecar)

        self.assertEqual(first.removed_count, 0)
        self.assertEqual(second.removed_count, 0)

    def test_clear_cache_refuses_link_like_child_without_deleting_any_cache(self):
        sidecar = self.root / "linked-cache.cbq"
        save_project(sidecar, QCProject(id=PROJECT_ID, schema_version="0.2"))
        derivation = sidecar / "cache" / "derivation"
        render = sidecar / "cache" / "render"
        linked_child = derivation / "external"
        linked_child.mkdir(parents=True)
        render.mkdir(parents=True)
        (render / "keep.bin").write_bytes(b"render")

        with patch.object(
            project_service,
            "_is_link_like",
            side_effect=lambda path: Path(path) == linked_child,
        ):
            with self.assertRaisesRegex(ValueError, "linked cache child"):
                clear_derived_cache(sidecar_path=sidecar)

        self.assertTrue(linked_child.is_dir())
        self.assertEqual((render / "keep.bin").read_bytes(), b"render")

    def test_clear_cache_refuses_link_like_sidecar_root(self):
        sidecar = self.root / "linked-root.cbq"
        save_project(sidecar, QCProject(id=PROJECT_ID, schema_version="0.2"))
        manifest_before = (sidecar / "manifest.json").read_bytes()

        with patch.object(
            project_service,
            "_is_link_like",
            side_effect=lambda path: Path(path) == sidecar,
        ):
            with self.assertRaisesRegex(ValueError, "sidecar root"):
                clear_derived_cache(sidecar_path=sidecar)

        self.assertEqual((sidecar / "manifest.json").read_bytes(), manifest_before)

    def test_clear_cache_failure_returns_partial_report(self):
        sidecar = self.root / "partial-cache.cbq"
        save_project(sidecar, QCProject(id=PROJECT_ID, schema_version="0.2"))
        derivation = sidecar / "cache" / "derivation"
        render = sidecar / "cache" / "render"
        derivation.mkdir(parents=True)
        render.mkdir(parents=True)
        real_rmtree = project_service.shutil.rmtree

        def fail_render(path):
            if Path(path) == render:
                raise OSError("render cache is busy")
            return real_rmtree(path)

        with patch.object(project_service.shutil, "rmtree", side_effect=fail_render):
            result = clear_derived_cache(sidecar_path=sidecar)

        self.assertFalse(result.complete)
        self.assertEqual(result.removed_paths, (derivation,))
        self.assertEqual(result.failed_path, render)
        self.assertIn("render cache is busy", result.message)
        self.assertFalse(derivation.exists())
        self.assertTrue(render.is_dir())

    def test_public_exports_import_without_blender_or_optional_stacks(self):
        expected = {
            "ProjectServiceStatus",
            "clear_derived_cache",
            "relink_project_session",
            "save_project_session",
            "verify_project_session",
        }
        self.assertEqual(expected - set(core.__all__), set())
        code = (
            "import sys; import ChemBlender.core; "
            "forbidden={'bpy','cclib','iodata','gbasis','ase','pymatgen'}; "
            "raise SystemExit(bool(forbidden & set(sys.modules)))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_project_link_can_import_before_core_in_fresh_process(self):
        code = (
            "import sys; import ChemBlender.project_link; import ChemBlender.core; "
            "forbidden={'bpy','cclib','iodata','gbasis','ase','pymatgen'}; "
            "raise SystemExit(bool(forbidden & set(sys.modules)))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
