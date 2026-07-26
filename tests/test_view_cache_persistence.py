import hashlib
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
from unittest.mock import Mock, patch
from uuid import uuid4

import numpy

from ChemBlender.core import (
    ArrayData,
    DatasetStatus,
    Grid3D,
    ImportBatch,
    ProjectSession,
    QCProject,
    builtin_scene_presets,
    plan_scene_preset,
    volume_render_cache_key,
)


class FakeGrids:
    def __init__(self):
        self.loads = 0
        self.fail_once = False

    def load(self):
        self.loads += 1
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("Blender grid reload failed")


class FakeVolume:
    def __init__(self, filepath):
        self.filepath = filepath
        self.grids = FakeGrids()


class FakeObject(dict):
    type = "VOLUME"

    def __init__(self, name, filepath, metadata):
        super().__init__(metadata)
        self.name = name
        self.data = FakeVolume(filepath)


def grid(role="electron_density"):
    return Grid3D(
        id=uuid4(),
        revision=f"{role}-r1",
        semantic_role=role,
        domain="grid",
        data=ArrayData(
            numpy.arange(27, dtype=float).reshape((3, 3, 3)),
            ("x", "y", "z"),
            "electron_per_cubic_bohr",
        ),
        status=DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(),
        origin=(0.0, 0.0, 0.0),
        step_vectors=((0.2, 0.0, 0.0), (0.0, 0.2, 0.0), (0.0, 0.0, 0.2)),
        coordinate_unit="bohr",
        structure_id=None,
    )


def project_with(*datasets):
    project = QCProject(uuid4(), "0.2")
    project.commit(ImportBatch(datasets=datasets))
    return project


def plan_metadata(plan):
    return {
        "cb_scene_preset_id": plan.preset_id,
        "cb_scene_preset_version": plan.preset_version,
        "cb_scene_view_kind": plan.view_kind,
        "cb_scene_render_identity": plan.render_identity,
        "cb_scene_settings_json": json.dumps(
            dict(plan.settings), sort_keys=True, separators=(",", ":")
        ),
        "cb_scene_bindings_json": json.dumps(
            {
                binding.name: {
                    "entity_id": str(binding.entity_id),
                    "revision": binding.revision,
                }
                for binding in plan.bindings
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
    }


class ViewCachePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.blend_path = self.root / "example.blend"
        self.sidecar = self.root / "example.cbq"
        self.sidecar.mkdir()
        self.grid = grid()
        self.project = project_with(self.grid)
        self.session = ProjectSession(
            uuid4(),
            self.project,
            self.root / "session",
            sidecar_path=self.sidecar,
            link_status="connected",
        )
        self.session.temporary_root.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def grid_object(self, *, old_path=None):
        plan = plan_scene_preset(
            builtin_scene_presets()["grid_volume"],
            self.project,
            {"grid": self.grid.id},
            {},
        )
        metadata = plan_metadata(plan)
        metadata.update(
            {
                "cb_dataset_id": str(self.grid.id),
                "cb_dataset_revision": self.grid.revision,
                "cb_dataset_index": 0,
                "cb_cache_format_version": 1,
                "cb_render_cache_key": volume_render_cache_key(
                    self.grid, dataset_index=0
                ),
                "cb_cache_path": r"C:\untrusted\attacker.vdb",
            }
        )
        return FakeObject(
            "Grid Volume",
            str(old_path or self.root / "old.vdb"),
            metadata,
        )

    @staticmethod
    def ensured_path(_grid, path, **_kwargs):
        path = Path(path)
        path.touch()
        return path

    def test_grid_cache_target_is_derived_from_verified_sidecar(self):
        from ChemBlender.ui import view_cache

        obj = self.grid_object()
        expected = (
            self.sidecar
            / "cache"
            / "render"
            / "volume"
            / f"{volume_render_cache_key(self.grid, dataset_index=0)}.vdb"
        )

        with patch.object(
            view_cache,
            "_ensure_grid_volume_cache",
            side_effect=self.ensured_path,
        ) as ensure:
            repaired = view_cache.repair_project_view_caches(
                session=self.session,
                objects=(obj,),
                blend_path=self.blend_path,
            )

        self.assertEqual(repaired, 1)
        self.assertEqual(ensure.call_args.args[1], expected)
        self.assertEqual(obj["cb_cache_path"], str(expected))
        self.assertEqual(
            obj.data.filepath,
            f"//example.cbq/cache/render/volume/{expected.name}",
        )
        self.assertEqual(obj.data.grids.loads, 1)

    def test_signed_surface_uses_stable_render_identity_key(self):
        from ChemBlender.ui import view_cache

        plan = plan_scene_preset(
            builtin_scene_presets()["signed_isosurface"],
            self.project,
            {"grid": self.grid.id},
            {},
        )
        phase = "negative"
        key = hashlib.sha256(
            f"{plan.render_identity}:{phase}".encode("utf-8")
        ).hexdigest()
        metadata = plan_metadata(plan)
        metadata.update(
            {
                "cb_dataset_id": str(self.grid.id),
                "cb_dataset_revision": self.grid.revision,
                "cb_dataset_index": 0,
                "cb_cache_format_version": 1,
                "cb_render_cache_key": key,
                "cb_surface_phase": phase,
                "cb_cache_path": r"C:\outside\wrong.vdb",
            }
        )
        obj = FakeObject("Negative Surface", str(self.root / "old.vdb"), metadata)
        expected = self.sidecar / "cache" / "render" / "surface" / f"{key}.vdb"

        with patch.object(
            view_cache,
            "_ensure_signed_surface_cache",
            side_effect=self.ensured_path,
        ) as ensure:
            repaired = view_cache.repair_project_view_caches(
                session=self.session,
                objects=(obj,),
                blend_path=self.blend_path,
            )

        self.assertEqual(repaired, 1)
        self.assertEqual(ensure.call_args.args[1], expected)
        self.assertEqual(obj["cb_cache_path"], str(expected))

    def test_property_surface_validates_both_dataset_revisions(self):
        from ChemBlender.ui import view_cache

        prop = grid("electrostatic_potential")
        self.project.commit(ImportBatch(datasets=(prop,)))
        plan = plan_scene_preset(
            builtin_scene_presets()["property_on_surface"],
            self.project,
            {"surface_grid": self.grid.id, "property_grid": prop.id},
            {},
        )
        key = hashlib.sha256(
            f"{plan.render_identity}:property".encode("utf-8")
        ).hexdigest()
        metadata = plan_metadata(plan)
        metadata.update(
            {
                "cb_dataset_id": str(self.grid.id),
                "cb_dataset_revision": self.grid.revision,
                "cb_dataset_index": 0,
                "cb_property_dataset_id": str(prop.id),
                "cb_property_dataset_revision": prop.revision,
                "cb_property_dataset_index": 0,
                "cb_cache_format_version": 1,
                "cb_render_cache_key": key,
            }
        )
        obj = FakeObject("Property Surface", "old.vdb", metadata)

        def ensured(_surface, _property, path, **_kwargs):
            Path(path).touch()
            return path

        with patch.object(
            view_cache,
            "_ensure_property_surface_cache",
            side_effect=ensured,
        ) as ensure:
            self.assertEqual(
                view_cache.repair_project_view_caches(
                    session=self.session,
                    objects=(obj,),
                    blend_path=self.blend_path,
                ),
                1,
            )
        self.assertEqual(ensure.call_args.args[:2], (self.grid, prop))
        self.assertEqual(obj["cb_render_cache_key"], key)

    def test_failure_restores_old_path_and_marks_retry_dirty(self):
        from ChemBlender.ui import view_cache

        old_path = self.root / "verified-old.vdb"
        obj = self.grid_object(old_path=old_path)
        old_property = obj["cb_cache_path"]

        with patch.object(
            view_cache,
            "_ensure_grid_volume_cache",
            side_effect=OSError("cache promotion failed"),
        ):
            with self.assertRaisesRegex(
                view_cache.ViewCacheError, "Grid Volume.*cache promotion failed"
            ):
                view_cache.repair_project_view_caches(
                    session=self.session,
                    objects=(obj,),
                    blend_path=self.blend_path,
                )

        self.assertEqual(obj.data.filepath, str(old_path))
        self.assertEqual(obj["cb_cache_path"], old_property)
        self.assertEqual(obj.data.grids.loads, 0)
        self.assertEqual(self.session.dirty_reasons, frozenset({"view_cache"}))

    def test_fatal_writer_errors_bypass_fallback_and_keep_original_identity(self):
        from ChemBlender.ui import view_cache

        previous_sidecar = self.root / "previous.cbq"
        for name in ("volume", "surface"):
            (previous_sidecar / "cache" / "render" / name).mkdir(
                parents=True,
                exist_ok=True,
            )

        for error in (
            KeyboardInterrupt(),
            SystemExit(),
            GeneratorExit(),
            MemoryError("allocation failed"),
        ):
            with self.subTest(error=type(error).__name__):
                obj = self.grid_object()
                old_filepath = obj.data.filepath
                if "view_cache" in self.session.dirty_reasons:
                    self.session.clear_dirty("view_cache")
                with patch.object(
                    view_cache,
                    "_ensure_grid_volume_cache",
                    side_effect=error,
                ), patch.object(
                    view_cache,
                    "_validate_fallback_cache",
                ) as fallback:
                    with self.assertRaises(type(error)) as raised:
                        view_cache.repair_project_view_caches(
                            session=self.session,
                            objects=(obj,),
                            blend_path=self.blend_path,
                            previous_sidecar_path=previous_sidecar,
                        )

                self.assertIs(raised.exception, error)
                fallback.assert_not_called()
                self.assertEqual(obj.data.filepath, old_filepath)
                self.assertEqual(obj.data.grids.loads, 0)
                self.assertEqual(
                    self.session.dirty_reasons,
                    frozenset({"view_cache"}),
                )

    def test_previous_fallback_validation_preserves_fatal_identity(self):
        from ChemBlender.ui import view_cache

        previous_sidecar = self.root / "previous.cbq"
        key = volume_render_cache_key(self.grid, dataset_index=0)
        previous_cache = (
            previous_sidecar
            / "cache"
            / "render"
            / "volume"
            / f"{key}.vdb"
        )
        previous_cache.parent.mkdir(parents=True)
        (previous_sidecar / "cache" / "render" / "surface").mkdir()
        previous_cache.touch()
        obj = self.grid_object()
        fatal = MemoryError("fallback validation exhausted memory")
        validator_module = ModuleType("ChemBlender.grid_volume")
        validate = Mock(side_effect=fatal)
        validator_module._validate_vdb = validate

        with patch.object(
            view_cache,
            "_ensure_grid_volume_cache",
            side_effect=OSError("new cache write failed"),
        ), patch.dict(
            sys.modules,
            {"ChemBlender.grid_volume": validator_module},
        ):
            with self.assertRaises(MemoryError) as raised:
                view_cache.repair_project_view_caches(
                    session=self.session,
                    objects=(obj,),
                    blend_path=self.blend_path,
                    previous_sidecar_path=previous_sidecar,
                )

        self.assertIs(raised.exception, fatal)
        validate.assert_called_once()
        self.assertEqual(obj.data.grids.loads, 0)
        self.assertEqual(
            self.session.dirty_reasons,
            frozenset({"view_cache"}),
        )

    def test_current_fallback_reload_preserves_fatal_identity(self):
        from ChemBlender.ui import view_cache

        old_path = self.session.temporary_root / "view-cache" / "old.vdb"
        old_path.parent.mkdir()
        old_path.touch()
        obj = self.grid_object(old_path=old_path)
        fatal = KeyboardInterrupt()

        with patch.object(
            view_cache,
            "_ensure_grid_volume_cache",
            side_effect=OSError("new cache write failed"),
        ), patch.object(
            view_cache,
            "_validate_fallback_cache",
            return_value=True,
        ) as validate, patch.object(
            obj.data.grids,
            "load",
            side_effect=fatal,
        ):
            with self.assertRaises(KeyboardInterrupt) as raised:
                view_cache.repair_project_view_caches(
                    session=self.session,
                    objects=(obj,),
                    blend_path=self.blend_path,
                )

        self.assertIs(raised.exception, fatal)
        validate.assert_called_once()
        self.assertEqual(obj.data.filepath, str(old_path))
        self.assertEqual(
            self.session.dirty_reasons,
            frozenset({"view_cache"}),
        )

    def test_stale_metadata_fails_closed_without_using_cache_property(self):
        from ChemBlender.ui import view_cache

        obj = self.grid_object()
        old_path = obj.data.filepath
        obj["cb_dataset_revision"] = "stale"

        with patch.object(view_cache, "_ensure_grid_volume_cache") as ensure:
            with self.assertRaisesRegex(view_cache.ViewCacheError, "stale"):
                view_cache.repair_project_view_caches(
                    session=self.session,
                    objects=(obj,),
                    blend_path=self.blend_path,
                )

        ensure.assert_not_called()
        self.assertEqual(obj.data.filepath, old_path)
        self.assertEqual(self.session.dirty_reasons, frozenset({"view_cache"}))

    def test_blender_reload_failure_restores_and_reloads_old_cache(self):
        from ChemBlender.ui import view_cache

        old_path = self.session.temporary_root / "view-cache" / "old.vdb"
        old_path.parent.mkdir()
        old_path.touch()
        obj = self.grid_object(old_path=old_path)
        obj.data.grids.fail_once = True

        with patch.object(
            view_cache,
            "_ensure_grid_volume_cache",
            side_effect=self.ensured_path,
        ), patch.object(
            view_cache,
            "_validate_fallback_cache",
            return_value=True,
        ):
            with self.assertRaisesRegex(
                view_cache.ViewCacheError, "Blender grid reload failed"
            ):
                view_cache.repair_project_view_caches(
                    session=self.session,
                    objects=(obj,),
                    blend_path=self.blend_path,
                )

        self.assertEqual(obj.data.filepath, str(old_path))
        self.assertEqual(obj.data.grids.loads, 2)

    def test_save_as_failure_reprojects_verified_previous_sidecar_cache(self):
        from ChemBlender.ui import view_cache

        old_blend = self.root / "old" / "original.blend"
        old_sidecar = old_blend.with_suffix(".cbq")
        new_blend = self.root / "new" / "renamed.blend"
        new_sidecar = new_blend.with_suffix(".cbq")
        old_sidecar.mkdir(parents=True)
        new_sidecar.mkdir(parents=True)
        key = volume_render_cache_key(self.grid, dataset_index=0)
        old_cache = (
            old_sidecar / "cache" / "render" / "volume" / f"{key}.vdb"
        )
        old_cache.parent.mkdir(parents=True)
        (old_sidecar / "cache" / "render" / "surface").mkdir(parents=True)
        old_cache.touch()
        old_relative = (
            f"//{old_sidecar.name}/cache/render/volume/{old_cache.name}"
        )
        obj = self.grid_object(old_path=old_relative)
        obj["cb_cache_path"] = r"\\attacker.invalid\share\payload.vdb"
        self.session.sidecar_path = new_sidecar

        def fail_new_promotion(_grid, path, **_kwargs):
            path = Path(path)
            self.assertIn(new_sidecar, path.parents)
            raise OSError("new sidecar cache promotion failed")

        def validate_previous(**values):
            self.assertEqual(values["old_filepath"], str(old_cache))
            self.assertEqual(values["cache_root"], old_sidecar / "cache" / "render")
            return True

        with patch.object(
            view_cache,
            "_ensure_grid_volume_cache",
            side_effect=fail_new_promotion,
        ) as ensure, patch.object(
            view_cache,
            "_validate_fallback_cache",
            side_effect=validate_previous,
        ) as validate:
            with self.assertRaisesRegex(
                view_cache.ViewCacheError,
                "new sidecar cache promotion failed",
            ):
                view_cache.repair_project_view_caches(
                    session=self.session,
                    objects=(obj,),
                    blend_path=new_blend,
                    previous_sidecar_path=old_sidecar,
                )

        ensure.assert_called_once()
        validate.assert_called_once()
        self.assertEqual(
            view_cache._blender_absolute_path(obj.data.filepath, new_blend),
            old_cache,
        )
        self.assertNotEqual(obj.data.filepath, old_relative)
        self.assertEqual(obj.data.grids.loads, 1)
        self.assertEqual(obj["cb_cache_path"], str(old_cache))
        self.assertEqual(self.session.dirty_reasons, frozenset({"view_cache"}))

    def test_save_as_fallback_does_not_create_previous_cache_directories(self):
        from ChemBlender.ui import view_cache

        old_sidecar = self.root / "old" / "original.cbq"
        new_sidecar = self.root / "new" / "renamed.cbq"
        old_sidecar.mkdir(parents=True)
        new_sidecar.mkdir(parents=True)
        self.session.sidecar_path = new_sidecar
        obj = self.grid_object()

        with patch.object(
            view_cache,
            "_ensure_grid_volume_cache",
            side_effect=OSError("new sidecar cache promotion failed"),
        ), patch.object(
            view_cache,
            "_validate_fallback_cache",
            return_value=False,
        ):
            with self.assertRaisesRegex(
                view_cache.ViewCacheError,
                "new sidecar cache promotion failed",
            ):
                view_cache.repair_project_view_caches(
                    session=self.session,
                    objects=(obj,),
                    blend_path=self.root / "new" / "renamed.blend",
                    previous_sidecar_path=old_sidecar,
                )

        self.assertFalse((old_sidecar / "cache").exists())
        self.assertEqual(obj.data.grids.loads, 0)
        self.assertEqual(self.session.dirty_reasons, frozenset({"view_cache"}))

    def test_untrusted_old_filepath_is_not_loaded_during_failure_recovery(self):
        from ChemBlender.ui import view_cache

        old_path = r"\\attacker.invalid\share\payload.vdb"
        obj = self.grid_object(old_path=old_path)

        with patch.object(
            view_cache,
            "_ensure_grid_volume_cache",
            side_effect=OSError("cache promotion failed"),
        ), patch.object(
            view_cache,
            "_validate_fallback_cache",
            wraps=view_cache._validate_fallback_cache,
        ) as validate:
            with self.assertRaisesRegex(
                view_cache.ViewCacheError, "cache promotion failed"
            ):
                view_cache.repair_project_view_caches(
                    session=self.session,
                    objects=(obj,),
                    blend_path=self.blend_path,
                )

        validate.assert_called_once()
        self.assertEqual(obj.data.filepath, old_path)
        self.assertEqual(obj.data.grids.loads, 0)
        self.assertEqual(self.session.dirty_reasons, frozenset({"view_cache"}))

    def test_foreign_volume_is_untouched(self):
        from ChemBlender.ui import view_cache

        obj = FakeObject("Foreign", "foreign.vdb", {"cb_cache_path": "foreign.vdb"})
        before = dict(obj)

        with patch.object(view_cache, "_durable_cache_root") as durable:
            repaired = view_cache.repair_project_view_caches(
                session=self.session,
                objects=(obj,),
                blend_path=self.blend_path,
            )

        self.assertEqual(repaired, 0)
        durable.assert_not_called()
        self.assertFalse((self.sidecar / "cache").exists())
        self.assertEqual(obj.data.filepath, "foreign.vdb")
        self.assertEqual(dict(obj), before)

    def test_non_volume_is_untouched_without_inspecting_sidecar(self):
        from ChemBlender.ui import view_cache

        obj = self.grid_object()
        obj.type = "MESH"
        before = dict(obj)
        old_filepath = obj.data.filepath

        with patch.object(view_cache, "_durable_cache_root") as durable:
            repaired = view_cache.repair_project_view_caches(
                session=self.session,
                objects=(obj,),
                blend_path=self.blend_path,
            )

        self.assertEqual(repaired, 0)
        durable.assert_not_called()
        self.assertFalse((self.sidecar / "cache").exists())
        self.assertEqual(obj.data.filepath, old_filepath)
        self.assertEqual(dict(obj), before)

    def test_success_clears_only_view_cache_retry_reason(self):
        from ChemBlender.ui import view_cache

        self.session.sidecar_path = None
        self.session.link_status = "unlinked"
        self.session.mark_dirty("view_cache")
        self.session.mark_dirty("project_link")

        with patch.object(view_cache, "_durable_cache_root") as durable:
            repaired = view_cache.repair_project_view_caches(
                session=self.session,
                objects=(),
                blend_path=self.blend_path,
            )

        self.assertEqual(repaired, 0)
        durable.assert_not_called()
        self.assertFalse((self.sidecar / "cache").exists())
        self.assertEqual(self.session.dirty_reasons, frozenset({"project_link"}))

    def test_linked_render_cache_directory_is_rejected(self):
        from ChemBlender.ui import view_cache

        (self.sidecar / "cache" / "render").mkdir(parents=True)
        obj = self.grid_object()

        with patch.object(
            view_cache,
            "_is_link_like",
            side_effect=lambda path: path.name == "render",
        ), patch.object(view_cache, "_ensure_grid_volume_cache") as ensure:
            with self.assertRaisesRegex(view_cache.ViewCacheError, "unsafe"):
                view_cache.repair_project_view_caches(
                    session=self.session,
                    objects=(obj,),
                    blend_path=self.blend_path,
                )
        ensure.assert_not_called()
        self.assertEqual(self.session.dirty_reasons, frozenset({"view_cache"}))

    def test_final_vdb_link_is_rejected_before_writer_and_preserves_target(self):
        from ChemBlender.ui import view_cache

        obj = self.grid_object()
        key = volume_render_cache_key(self.grid, dataset_index=0)
        expected = (
            self.sidecar / "cache" / "render" / "volume" / f"{key}.vdb"
        )
        expected.parent.mkdir(parents=True)
        outside = self.root / "outside.vdb"
        original = b"external cache must remain unchanged"
        outside.write_bytes(original)

        with patch.object(
            view_cache,
            "_is_link_like",
            side_effect=lambda path: path == expected,
        ), patch.object(view_cache, "_ensure_grid_volume_cache") as ensure:
            with self.assertRaisesRegex(view_cache.ViewCacheError, "unsafe"):
                view_cache.repair_project_view_caches(
                    session=self.session,
                    objects=(obj,),
                    blend_path=self.blend_path,
                )

        ensure.assert_not_called()
        self.assertFalse(expected.exists())
        self.assertEqual(outside.read_bytes(), original)
        self.assertEqual(self.session.dirty_reasons, frozenset({"view_cache"}))


if __name__ == "__main__":
    unittest.main()
