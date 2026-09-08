import ast
import csv
import io
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import numpy

from ChemBlender.core import ArrayData, builtin_scene_presets
from ChemBlender.ui import grid as grid_ui, view_cache
from tests.test_view_cache_persistence import grid, project_with, plan_metadata


def sample_object(plan, source):
    class Object(dict):
        @property
        def matrix_world(self):
            raise AssertionError("scientific samples must not read the View transform")

    obj = Object(plan_metadata(plan))
    obj.update(cb_grid_sample_root=True, cb_grid_sample_contract=f"{plan.view_kind}_v1",
               cb_dataset_id=str(source.id), cb_dataset_revision=source.revision,
               cb_dataset_index=dict(plan.settings)["dataset_index"],
               cb_source_coordinate_unit=source.coordinate_unit, cb_value_unit=source.data.unit)
    obj.name = "Saved sample"
    obj.type = "CURVE" if plan.view_kind == "grid_profile" else "MESH"
    obj.data = object()
    return obj


class GridSampleUITests(unittest.TestCase):
    def setUp(self):
        self.grid = grid()
        self.project = project_with(self.grid)
        self.settings = {"origin": (0., 0., .2), "u_vector": (.4, 0., 0.),
                         "v_vector": (0., .4, 0.), "counts": (3, 3),
                         "color_min": 0., "color_max": 26., "symmetric": False}
        self.plan = grid_ui.plan_grid_view(self.project, self.grid.id, mode="slice",
                                          sample_settings=self.settings)

    def test_property_controls_preserve_both_dataset_indices_and_v2_contract(self):
        source = replace(self.grid, data=ArrayData(numpy.zeros((2, 3, 3, 3)),
                         ("dataset", "x", "y", "z"), self.grid.data.unit))
        prop = replace(source, id=uuid4(), semantic_role="electrostatic_potential",
                       data=replace(source.data, unit="hartree_per_elementary_charge"))
        project = project_with(source, prop)
        plan = grid_ui.plan_grid_view(project, source.id, mode="property_surface",
            dataset_index=1, property_grid_id=prop.id, property_dataset_index=1,
            color_min=-.3, color_max=.7, symmetric=False)
        self.assertEqual(plan.preset_version, "3")
        values = dict(plan.settings)
        self.assertEqual((values["surface_dataset_index"], values["property_dataset_index"]), (1, 1))
        self.assertEqual((values["color_min"], values["color_max"], values["symmetric"]), (-.3, .7, False))
        self.assertNotIn("show_colorbar", dict(builtin_scene_presets()["property_on_surface"].default_settings))

    def test_complete_multi_dataset_draw_keeps_the_dataset_selector_visible(self):
        tree = ast.parse(Path(grid_ui.__file__).read_text(encoding="utf-8"))
        draw = next(node for node in ast.walk(tree)
                    if isinstance(node, ast.FunctionDef) and node.name == "draw_grid_controls")
        namespace = dict(vars(grid_ui))
        namespace["CHEMBLENDER_OT_create_grid_view"] = SimpleNamespace(bl_idname="grid-view")
        exec(compile(ast.Module(body=[draw], type_ignores=[]), "grid controls", "exec"), namespace)
        props = []

        class Layout:
            enabled = True

            def separator(self):
                pass

            def label(self, **_kwargs):
                pass

            def prop(self, _settings, name, **_kwargs):
                props.append(name)

            def row(self, **_kwargs):
                return self

            def operator(self, *_args, **_kwargs):
                return SimpleNamespace()

        source = replace(self.grid, data=ArrayData(numpy.zeros((2, 3, 3, 3)),
                         ("dataset", "x", "y", "z"), self.grid.data.unit))
        settings = SimpleNamespace(isovalue=.05, symmetric=True)
        context = SimpleNamespace(scene=SimpleNamespace(objects=(), chemblender_grid=settings))
        session = SimpleNamespace(project=project_with(source), active_entity_id=source.id)
        namespace["draw_grid_controls"](Layout(), context, session)
        self.assertIn("dataset_index", props)
        self.assertNotIn("preset_id", props)
        self.assertIn("slice_counts", props)
        self.assertIn("profile_samples", props)

    def test_sampling_controls_share_the_scene_point_limit(self):
        class Layout:
            def label(self, **_kwargs):
                pass

            def row(self):
                self.created = SimpleNamespace(operator=lambda *_args, **_kwargs: SimpleNamespace())
                return self.created

        for counts, enabled in (((1000, 1000), True), ((1001, 1000), False)):
            layout = Layout()
            grid_ui._draw_sample_button(layout, SimpleNamespace(slice_counts=counts), "slice")
            self.assertEqual(layout.created.enabled, enabled)
            if not enabled:
                with self.assertRaisesRegex(ValueError, "sample points"):
                    grid_ui.plan_grid_view(self.project, self.grid.id, mode="slice",
                                           sample_settings={**self.settings, "counts": counts})

    def test_fit_and_load_use_grid_coordinates_and_saved_parameters(self):
        settings = SimpleNamespace()
        skew = replace(self.grid, step_vectors=((.2, .1, 0.), (0., -.3, 0.), (0., 0., .1)))
        grid_ui.fit_grid_sampling(settings, skew)
        numpy.testing.assert_allclose(settings.slice_origin, (0., 0., .1))
        numpy.testing.assert_allclose(settings.slice_u, (0., -.6, 0.))
        numpy.testing.assert_allclose(settings.slice_v, (.4, .2, 0.))
        numpy.testing.assert_allclose(settings.profile_end, (.4, -.4, .2))
        grid_ui.load_grid_view_settings(settings, self.plan)
        self.assertEqual(settings.slice_origin, self.settings["origin"])
        self.assertEqual(settings.slice_counts, (3, 3))
        self.assertEqual((settings.color_min, settings.color_max, settings.symmetric), (0., 26., False))

    def test_csv_uses_saved_scientific_plan_and_rejects_stale_bindings(self):
        obj = sample_object(self.plan, self.grid)
        original_values = self.grid.data.values.copy()
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "slice.csv"
            report = grid_ui.export_grid_view_sample(self.project, obj, path)
            self.assertTrue(report.written)
            content = path.read_text(encoding="utf-8")
            rows = list(csv.DictReader(io.StringIO("\n".join(content.splitlines()[1:]))))
            self.assertEqual(len(rows), 9)
            numpy.testing.assert_allclose([float(row["value"]) for row in rows],
                                          original_values[:, :, 1].ravel())
            self.assertTrue(all(row["coordinate_unit"] == "bohr" for row in rows))
            self.project.datasets[self.grid.id] = replace(self.grid, revision="changed")
            with self.assertRaisesRegex(view_cache.ViewCacheError, "stale"):
                grid_ui.export_grid_view_sample(self.project, obj, Path(temporary) / "stale.csv")
            self.assertFalse((Path(temporary) / "stale.csv").exists())
        numpy.testing.assert_array_equal(self.grid.data.values, original_values)

    def test_sample_recovery_checks_each_root_once_without_volume_cache(self):
        obj = sample_object(self.plan, self.grid)
        child = sample_object(self.plan, self.grid)
        child.pop("cb_grid_sample_root")
        child["cb_scene_settings_json"] = "bad child metadata is not a root"
        session = SimpleNamespace(project=self.project, dirty_reasons=set(),
                                  mark_dirty=Mock(), clear_dirty=Mock())
        with patch.object(view_cache, "_durable_cache_root", side_effect=AssertionError("external cache")):
            self.assertEqual(view_cache.repair_project_view_caches(
                session=session, objects=(obj, child), blend_path="unused.blend"), 1)
        obj["cb_scene_render_identity"] = "tampered"
        valid = sample_object(self.plan, self.grid)
        with self.assertRaisesRegex(view_cache.ViewCacheError, "stale"):
            view_cache.repair_project_view_caches(
                session=session, objects=(obj, child, valid), blend_path="unused.blend")
        self.assertTrue(obj["cb_view_stale"])
        self.assertFalse(obj["cb_report_eligible"])
        self.assertNotIn("cb_view_stale", valid)
        session.mark_dirty.assert_called_once_with("view_cache")

    def test_missing_geometry_still_allows_validated_scientific_export(self):
        obj = sample_object(self.plan, self.grid)
        obj.data = None
        with self.assertRaisesRegex(view_cache.ViewCacheError, "geometry"):
            view_cache.plan_grid_sample_view(obj, self.project)
        self.assertEqual(view_cache.plan_grid_sample_view(obj, self.project, require_geometry=False), self.plan)

    def test_rebuild_swaps_only_owned_data_and_children_and_rolls_back(self):
        class Matrix(numpy.ndarray):
            def inverted(self):
                return numpy.linalg.inv(self).view(Matrix)

        class Object(dict):
            library = None
            type = "MESH"

            def __init__(self, name, *, root=False):
                super().__init__(cb_grid_sample_component="slice" if root else "label")
                if root:
                    self["cb_grid_sample_root"] = True
                self.name, self.data = name, object()
                self.children, self._parent = [], None
                self.users_collection = (object(),)
                self.matrix_basis, self.matrix_parent_inverse = numpy.eye(4), numpy.eye(4)
                self.fail_once = False

            @property
            def matrix_world(self):
                return (self.parent.matrix_world @ self.matrix_parent_inverse @ self.matrix_basis
                        if self.parent is not None else self.matrix_basis.copy()).view(Matrix)

            @matrix_world.setter
            def matrix_world(self, value):
                self.matrix_basis = (numpy.linalg.inv(self.parent.matrix_world @ self.matrix_parent_inverse) @ value
                                     if self.parent is not None else value.copy())

            @property
            def parent(self):
                return self._parent

            @parent.setter
            def parent(self, value):
                if self._parent is not None:
                    self._parent.children.remove(self)
                self._parent = value
                if value is not None:
                    value.children.append(self)

            def __setitem__(self, key, value):
                if getattr(self, "fail_once", False) and key == "cb_scene_render_identity":
                    self.fail_once = False
                    raise RuntimeError("metadata swap failed")
                super().__setitem__(key, value)

        for failure in (None, "prepare", "swap"):
            with self.subTest(failure=failure):
                old, prepared = Object("Original", root=True), Object("Prepared", root=True)
                old["cb_scene_render_identity"], prepared["cb_scene_render_identity"] = "old", "new"
                old_label, new_label, user_child = Object("Old label"), Object("New label"), Object("User")
                user_child.clear()
                old_label.parent, user_child.parent, new_label.parent = old, old, prepared
                nested_user = Object("Nested user")
                nested_user.clear()
                nested_user.parent = old_label
                old.matrix_world = numpy.array([[0., -2., 0., 3.], [3., 0., 0., 4.],
                                                [0., 0., 1.5, 5.], [0., 0., 0., 1.]])
                old_label.matrix_basis[:3, 3] = (.5, .2, .1)
                nested_user.matrix_basis[:3, 3] = (.7, .8, .9)
                nested_world = nested_user.matrix_world.copy()
                old_data, new_data, transform = old.data, prepared.data, old.matrix_world
                original_metadata = dict(old)
                scene_module, adapter = ModuleType("ChemBlender.scene_preset_view"), ModuleType("ChemBlender.grid_sample_view")

                def apply(*_args, **_kwargs):
                    if failure == "prepare":
                        raise RuntimeError("prepare failed")
                    old.fail_once = failure == "swap"
                    return prepared, new_label

                removed = []
                scene_module.apply_scene_preset = apply

                def remove(obj):
                    removed.append((obj, obj.data, tuple(obj.children)))
                    # Mirror the adapter's promised preservation of user children
                    # when it removes the old owned label and root datablocks.
                    for owned in tuple(obj.children):
                        for user in tuple(owned.children):
                            world = user.matrix_world.copy()
                            user.parent = None
                            user.matrix_world = world

                adapter.remove_grid_sample_view = remove
                session = SimpleNamespace(project=self.project, mark_dirty=Mock())
                with patch.dict(sys.modules, {scene_module.__name__: scene_module, adapter.__name__: adapter}), patch.object(
                    view_cache, "plan_grid_sample_view", return_value=self.plan
                ):
                    if failure:
                        with self.assertRaisesRegex(RuntimeError, "failed"):
                            grid_ui.rebuild_grid_sample_view(session, old)
                        self.assertIs(old.data, old_data)
                        self.assertEqual(dict(old), original_metadata)
                        self.assertIs(old_label.parent, old)
                        self.assertIs(new_label.parent, prepared)
                        session.mark_dirty.assert_not_called()
                    else:
                        self.assertIs(grid_ui.rebuild_grid_sample_view(session, old), old)
                        self.assertIs(old.data, new_data)
                        self.assertIs(new_label.parent, old)
                        self.assertEqual(removed, [(prepared, old_data, (old_label,))])
                        session.mark_dirty.assert_called_once_with("view_cache")
                self.assertIs(user_child.parent, old)
                numpy.testing.assert_allclose(old.matrix_world, transform)
                numpy.testing.assert_allclose(nested_user.matrix_world, nested_world)


if __name__ == "__main__":
    unittest.main()
