import json
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
    SidecarCompatibilityError,
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

    def test_verify_identical_scene_links_adopts_project_once(self):
        sidecar = self.root / "identical.cbq"
        stored = QCProject(id=PROJECT_ID, schema_version="0.2")
        save_project(sidecar, stored)
        first = self.linked_scene(sidecar, stored)
        second = dict(first)
        session = self.create_session()

        with patch.object(
            project_service,
            "_adopt_project",
            wraps=project_service._adopt_project,
        ) as adopt:
            result = self.verify_for_scenes(
                session=session,
                scenes=(first, second),
            )

        self.assertEqual(result.status, ProjectServiceStatus.CONNECTED)
        self.assertEqual(session.project.id, PROJECT_ID)
        adopt.assert_called_once()

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

    def test_relink_uuid_mismatch_does_not_depend_on_exception_wording(self):
        sidecar = self.root / "other-wording.cbq"
        save_project(sidecar, QCProject(id=UUID(int=2), schema_version="0.2"))
        session = self.create_session()

        with patch(
            "ChemBlender.project_link.write_project_link",
            side_effect=SidecarCompatibilityError("wording changed"),
        ):
            result = relink_project_session(
                session=session,
                scene={},
                sidecar_path=sidecar,
            )

        self.assertEqual(result.status, ProjectServiceStatus.MISMATCH)

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
