import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import UUID

import ChemBlender.project_link as project_link
from ChemBlender.core import QCProject, close_project, save_project
from ChemBlender.core.sidecar import SidecarCompatibilityError
from ChemBlender.project_link import (
    MANIFEST_HASH_KEY,
    PROJECT_ID_KEY,
    PROJECT_SCHEMA_KEY,
    SIDECAR_LOCATOR_KEY,
    ProjectLinkStatus,
    _resolve_sidecar_path,
    _sidecar_locator,
    resolve_project_link,
    write_project_link,
)


PROJECT_ID = UUID("10000000-0000-0000-0000-000000000001")


class ProjectLinkPureTests(unittest.TestCase):
    def test_locator_is_relative_to_saved_blend_and_resolves_without_bpy(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            blend = root / "scenes" / "view.blend"
            sidecar = root / "projects" / "sample.cbq"

            locator = _sidecar_locator(sidecar, blend_path=blend)

            self.assertFalse(Path(locator).is_absolute())
            self.assertEqual(
                _resolve_sidecar_path(locator, blend_path=blend),
                sidecar.resolve(),
            )

    def test_locator_falls_back_to_absolute_path_across_windows_drives(self):
        locator = _sidecar_locator(
            Path("D:/projects/sample.cbq"),
            blend_path=Path("C:/scenes/view.blend"),
        )

        self.assertTrue(Path(locator).is_absolute())

    def test_write_stores_verified_manifest_hash_after_all_checks(self):
        with TemporaryDirectory() as directory:
            sidecar = Path(directory) / "sample.cbq"
            project = QCProject(id=PROJECT_ID, schema_version="0.2")
            save_project(sidecar, project)
            manifest = json.loads(
                (sidecar / "manifest.json").read_text(encoding="utf-8")
            )
            scene = {"preserve": "yes"}

            write_project_link(scene, project, sidecar)

            self.assertEqual(scene[PROJECT_ID_KEY], str(PROJECT_ID))
            self.assertEqual(scene[PROJECT_SCHEMA_KEY], "0.2")
            self.assertEqual(scene[MANIFEST_HASH_KEY], manifest["manifest_sha256"])
            self.assertIn(SIDECAR_LOCATOR_KEY, scene)

    def test_write_normalizes_supported_v01_project_to_verified_sidecar_schema(self):
        with TemporaryDirectory() as directory:
            sidecar = Path(directory) / "sample.cbq"
            project = QCProject(id=PROJECT_ID, schema_version="0.1")
            save_project(sidecar, project)
            scene = {}

            write_project_link(scene, project, sidecar)

            self.assertEqual(scene[PROJECT_SCHEMA_KEY], "0.2")

    def test_each_scene_assignment_failure_restores_mixed_link_state(self):
        class FailingScene(dict):
            def __init__(self, failure_key):
                super().__init__(
                    {
                        "preserve": "yes",
                        PROJECT_ID_KEY: "old-project",
                        SIDECAR_LOCATOR_KEY: "old.cbq",
                    }
                )
                self.failure_key = failure_key
                self.fail = True

            def __setitem__(self, key, value):
                if self.fail and key == self.failure_key:
                    self.fail = False
                    raise RuntimeError("scene write failed")
                super().__setitem__(key, value)

        with TemporaryDirectory() as directory:
            sidecar = Path(directory) / "sample.cbq"
            project = QCProject(id=PROJECT_ID, schema_version="0.2")
            save_project(sidecar, project)
            initial = {
                "preserve": "yes",
                PROJECT_ID_KEY: "old-project",
                SIDECAR_LOCATOR_KEY: "old.cbq",
            }
            for failure_key in (
                PROJECT_ID_KEY,
                PROJECT_SCHEMA_KEY,
                SIDECAR_LOCATOR_KEY,
                MANIFEST_HASH_KEY,
            ):
                with self.subTest(failure_key=failure_key):
                    scene = FailingScene(failure_key)

                    with self.assertRaisesRegex(
                        RuntimeError,
                        "scene write failed",
                    ):
                        write_project_link(scene, project, sidecar)

                    self.assertEqual(scene, initial)

    def test_rollback_failures_are_collected_and_report_residual_keys(self):
        class RollbackFailingScene(dict):
            def __init__(self, rollback_operation):
                super().__init__(
                    {
                        "preserve": "yes",
                        PROJECT_ID_KEY: "old-project",
                        SIDECAR_LOCATOR_KEY: "old.cbq",
                    }
                )
                self.rollback_operation = rollback_operation
                self.assignment_failed = False
                self.rollback_failures = set()

            def __setitem__(self, key, value):
                if (
                    not self.assignment_failed
                    and key == MANIFEST_HASH_KEY
                ):
                    self.assignment_failed = True
                    raise RuntimeError("assignment failed")
                if (
                    self.assignment_failed
                    and "set" not in self.rollback_failures
                    and self.rollback_operation in ("set", "both")
                    and key == SIDECAR_LOCATOR_KEY
                    and value == "old.cbq"
                ):
                    self.rollback_failures.add("set")
                    raise RuntimeError("rollback set failed")
                super().__setitem__(key, value)

            def __delitem__(self, key):
                if (
                    self.assignment_failed
                    and "delete" not in self.rollback_failures
                    and self.rollback_operation in ("delete", "both")
                    and key == PROJECT_SCHEMA_KEY
                ):
                    self.rollback_failures.add("delete")
                    raise RuntimeError("rollback delete failed")
                super().__delitem__(key)

        with TemporaryDirectory() as directory:
            sidecar = Path(directory) / "sample.cbq"
            project = QCProject(id=PROJECT_ID, schema_version="0.2")
            save_project(sidecar, project)

            for operation, expected_failures, residual_keys in (
                (
                    "set",
                    [
                        (
                            SIDECAR_LOCATOR_KEY,
                            "set",
                            "rollback set failed",
                        )
                    ],
                    (SIDECAR_LOCATOR_KEY,),
                ),
                (
                    "delete",
                    [
                        (
                            PROJECT_SCHEMA_KEY,
                            "delete",
                            "rollback delete failed",
                        )
                    ],
                    (PROJECT_SCHEMA_KEY,),
                ),
                (
                    "both",
                    [
                        (
                            SIDECAR_LOCATOR_KEY,
                            "set",
                            "rollback set failed",
                        ),
                        (
                            PROJECT_SCHEMA_KEY,
                            "delete",
                            "rollback delete failed",
                        ),
                    ],
                    (PROJECT_SCHEMA_KEY, SIDECAR_LOCATOR_KEY),
                ),
            ):
                with self.subTest(operation=operation):
                    scene = RollbackFailingScene(operation)

                    with self.assertRaises(RuntimeError) as caught:
                        write_project_link(scene, project, sidecar)

                    error = caught.exception
                    self.assertEqual(
                        type(error).__name__,
                        "_ProjectLinkWriteRecoveryError",
                    )
                    self.assertEqual(str(error.write_error), "assignment failed")
                    self.assertEqual(
                        [
                            (failure.key, failure.operation, str(failure.error))
                            for failure in error.rollback_errors
                        ],
                        expected_failures,
                    )
                    self.assertIs(error.__cause__, error.write_error)
                    self.assertEqual(error.residual_keys, residual_keys)
                    self.assertEqual(scene[PROJECT_ID_KEY], "old-project")
                    self.assertEqual(
                        PROJECT_SCHEMA_KEY in scene,
                        PROJECT_SCHEMA_KEY in residual_keys,
                    )
                    self.assertEqual(
                        scene[SIDECAR_LOCATOR_KEY],
                        (
                            str(sidecar.resolve())
                            if SIDECAR_LOCATOR_KEY in residual_keys
                            else "old.cbq"
                        ),
                    )
                    self.assertNotIn(MANIFEST_HASH_KEY, scene)

    def test_write_rejects_project_mismatch_without_partial_scene_update(self):
        with TemporaryDirectory() as directory:
            sidecar = Path(directory) / "sample.cbq"
            stored = QCProject(id=PROJECT_ID, schema_version="0.2")
            different = QCProject(id=UUID(int=2), schema_version="0.2")
            save_project(sidecar, stored)
            scene = {"preserve": "yes"}

            with self.assertRaises(SidecarCompatibilityError):
                write_project_link(scene, different, sidecar)

            self.assertEqual(scene, {"preserve": "yes"})

    def test_resolve_detects_valid_new_generation_without_mutating_scene(self):
        with TemporaryDirectory() as directory:
            sidecar = Path(directory) / "sample.cbq"
            project = QCProject(id=PROJECT_ID, schema_version="0.2")
            save_project(sidecar, project)
            scene = {"preserve": "yes"}
            write_project_link(scene, project, sidecar)
            before = dict(scene)

            save_project(sidecar, project)
            with patch(
                "ChemBlender.project_link.close_project",
                wraps=close_project,
            ) as close:
                result = resolve_project_link(scene)

            self.assertEqual(result.status, ProjectLinkStatus.MISMATCH)
            self.assertIsNone(result.project)
            self.assertEqual(scene, before)
            close.assert_called_once()

    def test_resolve_detects_uuid_mismatch_and_leaves_scene_unchanged(self):
        with TemporaryDirectory() as directory:
            sidecar = Path(directory) / "sample.cbq"
            project = QCProject(id=PROJECT_ID, schema_version="0.2")
            save_project(sidecar, project)
            scene = {}
            write_project_link(scene, project, sidecar)
            scene[PROJECT_ID_KEY] = str(UUID(int=2))
            before = dict(scene)

            result = resolve_project_link(scene)

            self.assertEqual(result.status, ProjectLinkStatus.MISMATCH)
            self.assertIsNone(result.project)
            self.assertEqual(scene, before)

    def test_resolve_connected_returns_verified_project(self):
        with TemporaryDirectory() as directory:
            sidecar = Path(directory) / "sample.cbq"
            project = QCProject(id=PROJECT_ID, schema_version="0.2")
            save_project(sidecar, project)
            scene = {}
            write_project_link(scene, project, sidecar)

            result = resolve_project_link(scene)
            try:
                self.assertEqual(result.status, ProjectLinkStatus.CONNECTED)
                self.assertEqual(result.project.id, PROJECT_ID)
            finally:
                close_project(result.project)

    def test_missing_hash_in_legacy_scene_link_is_invalid(self):
        scene = {
            PROJECT_ID_KEY: str(PROJECT_ID),
            PROJECT_SCHEMA_KEY: "0.1",
            SIDECAR_LOCATOR_KEY: "legacy.cbq",
        }

        result = resolve_project_link(scene)

        self.assertEqual(result.status, ProjectLinkStatus.INVALID)
        self.assertIsNone(result.path)

    def test_resolve_preserves_verify_arrays_keyword(self):
        with TemporaryDirectory() as directory:
            sidecar = Path(directory) / "sample.cbq"
            project = QCProject(id=PROJECT_ID, schema_version="0.2")
            save_project(sidecar, project)
            scene = {}
            write_project_link(scene, project, sidecar)

            with patch(
                "ChemBlender.project_link._open_project_with_manifest",
                wraps=project_link._open_project_with_manifest,
            ) as opener:
                result = resolve_project_link(scene, verify_arrays=False)
            try:
                self.assertEqual(result.status, ProjectLinkStatus.CONNECTED)
                self.assertFalse(opener.call_args.kwargs["verify_arrays"])
            finally:
                close_project(result.project)

    def test_invalid_locator_is_explicit(self):
        scene = {
            PROJECT_ID_KEY: str(PROJECT_ID),
            PROJECT_SCHEMA_KEY: "0.2",
            SIDECAR_LOCATOR_KEY: "\0",
            MANIFEST_HASH_KEY: "0" * 64,
        }

        result = resolve_project_link(scene)

        self.assertEqual(result.status, ProjectLinkStatus.INVALID)
        self.assertIsNone(result.path)

    def test_legacy_sidecar_cannot_supply_a_forged_manifest_hash(self):
        fixture = (
            Path(__file__).resolve().parent
            / "fixtures"
            / "sidecar"
            / "model-v01"
        )
        scene = {
            PROJECT_ID_KEY: "10000000-0000-0000-0000-000000000001",
            PROJECT_SCHEMA_KEY: "0.1",
            SIDECAR_LOCATOR_KEY: str(fixture),
            MANIFEST_HASH_KEY: "0" * 64,
        }

        result = resolve_project_link(scene)

        self.assertEqual(result.status, ProjectLinkStatus.INCOMPATIBLE)
        self.assertIsNone(result.project)


if __name__ == "__main__":
    unittest.main()
