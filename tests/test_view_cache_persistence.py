import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
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
        self.assertEqual(self.session.dirty_reasons, frozenset({"view_cache"}))

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

        old_path = self.root / "old.vdb"
        obj = self.grid_object(old_path=old_path)
        obj.data.grids.fail_once = True

        with patch.object(
            view_cache,
            "_ensure_grid_volume_cache",
            side_effect=self.ensured_path,
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

    def test_foreign_volume_is_untouched(self):
        from ChemBlender.ui import view_cache

        obj = FakeObject("Foreign", "foreign.vdb", {"cb_cache_path": "foreign.vdb"})

        repaired = view_cache.repair_project_view_caches(
            session=self.session,
            objects=(obj,),
            blend_path=self.blend_path,
        )

        self.assertEqual(repaired, 0)
        self.assertEqual(obj.data.filepath, "foreign.vdb")
        self.assertEqual(obj["cb_cache_path"], "foreign.vdb")

    def test_success_clears_only_view_cache_retry_reason(self):
        from ChemBlender.ui import view_cache

        self.session.mark_dirty("view_cache")
        self.session.mark_dirty("project_link")

        repaired = view_cache.repair_project_view_caches(
            session=self.session,
            objects=(),
            blend_path=self.blend_path,
        )

        self.assertEqual(repaired, 0)
        self.assertEqual(self.session.dirty_reasons, frozenset({"project_link"}))

    def test_linked_render_cache_directory_is_rejected(self):
        from ChemBlender.ui import view_cache

        (self.sidecar / "cache" / "render").mkdir(parents=True)

        with patch.object(
            view_cache,
            "_is_link_like",
            side_effect=lambda path: path.name == "render",
        ):
            with self.assertRaisesRegex(view_cache.ViewCacheError, "unsafe"):
                view_cache.repair_project_view_caches(
                    session=self.session,
                    objects=(),
                    blend_path=self.blend_path,
                )


if __name__ == "__main__":
    unittest.main()
