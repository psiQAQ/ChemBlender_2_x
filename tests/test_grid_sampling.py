import csv
import io
import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

import numpy

from ChemBlender.core import ArrayData, DatasetStatus, Grid3D
from ChemBlender.core.exporters.xyz import ExportCancelled
from ChemBlender.core import grid_sampling as sampling
from tests.test_grid_lod import SliceOnlyArray


BOHR_TO_ANGSTROM = 0.529177210903


def field(points):
    return 1.5 + numpy.asarray(points) @ numpy.asarray([2., -3., .7])


def grid(*, steps=((.4, .1, 0), (-.05, .35, .08), (.02, -.04, -.3)),
         shape=(5, 4, 3), multidataset=False):
    origin = (-1.2, .4, 2.)
    indices = numpy.moveaxis(numpy.indices(shape), 0, -1)
    points = numpy.asarray(origin) + indices @ numpy.asarray(steps)
    values = field(points)
    if multidataset:
        values = numpy.stack((values, -5 + 10 * values))
    return Grid3D(
        id=uuid4(), revision="analytic-grid-v1", semantic_role="electrostatic_potential",
        domain="grid", data=ArrayData(values,
            ("dataset", "x", "y", "z") if multidataset else ("x", "y", "z"),
            "hartree_per_elementary_charge"), status=DatasetStatus.COMPLETE,
        source_calculation=None, provenance_ids=(uuid4(),), origin=origin,
        step_vectors=steps, coordinate_unit="bohr", structure_id=uuid4(),
    )


def world(grid, indices):
    return numpy.asarray(grid.origin) + numpy.asarray(indices) @ numpy.asarray(grid.step_vectors)


class GridSamplingTests(unittest.TestCase):
    def test_linear_field_on_orthogonal_rotated_skew_and_negative_axes(self):
        matrices = (
            ((.4, 0, 0), (0, .3, 0), (0, 0, .2)),
            ((0, .4, 0), (-.3, 0, 0), (0, 0, .2)),
            ((.4, .1, 0), (-.05, .35, .08), (.02, -.04, .3)),
            ((.4, .1, 0), (-.05, .35, .08), (.02, -.04, -.3)),
        )
        fractional = numpy.asarray([[0, 0, 0], [4, 3, 2], [.2, 1.7, .6], [2.1, 0, .5]])
        for steps in matrices:
            with self.subTest(steps=steps):
                source = grid(steps=steps)
                points = world(source, fractional)
                values, valid = sampling.sample_grid_points(source, points)
                numpy.testing.assert_array_equal(valid, True)
                numpy.testing.assert_allclose(values, field(points), rtol=2e-14, atol=2e-14)
                self.assertEqual(values.dtype, numpy.dtype("float64"))

    def test_trilinear_cross_terms_use_all_eight_corners(self):
        source = grid()
        def polynomial(indices):
            x, y, z = numpy.moveaxis(numpy.asarray(indices), -1, 0)
            return 2 + x - y + 3 * z + 2 * x * y - y * z + .5 * x * z + x * y * z
        indices = numpy.moveaxis(numpy.indices(source.grid_shape), 0, -1)
        source = replace(source, data=replace(source.data, values=polynomial(indices)))
        fractional = numpy.asarray([[.2, 1.7, .6], [3.9, 2.7, 1.8], [4, 3, 2]])
        values, valid = sampling.sample_grid_points(source, world(source, fractional))
        self.assertTrue(valid.all())
        numpy.testing.assert_allclose(values, polynomial(fractional), rtol=2e-14, atol=2e-14)

    def test_point_shape_units_empty_and_outside_domain(self):
        source = grid()
        points = world(source, [[[0, 0, 0], [4, 3, 2]], [[-.01, 1, 1], [2, 3.01, 1]]])
        values, valid = sampling.sample_grid_points(source, points * BOHR_TO_ANGSTROM,
                                                    coordinate_unit="angstrom")
        self.assertEqual(values.shape, (2, 2))
        numpy.testing.assert_array_equal(valid, [[True, True], [False, False]])
        numpy.testing.assert_allclose(values[0], field(points[0]), atol=2e-14)
        self.assertTrue(numpy.isnan(values[1]).all())
        scalar, scalar_valid = sampling.sample_grid_points(source, source.origin)
        self.assertEqual(scalar.shape, ())
        self.assertTrue(scalar_valid)
        self.assertAlmostEqual(float(scalar), field(source.origin))
        values, valid = sampling.sample_grid_points(source, numpy.empty((0, 3)))
        self.assertEqual(values.shape, (0,))
        self.assertEqual(valid.shape, (0,))
        converted = replace(source,
            origin=tuple(numpy.asarray(source.origin) * BOHR_TO_ANGSTROM),
            step_vectors=tuple(tuple(row) for row in numpy.asarray(source.step_vectors) * BOHR_TO_ANGSTROM),
            coordinate_unit="angstrom")
        result, mask = sampling.sample_grid_points(converted, points[0], coordinate_unit="bohr")
        numpy.testing.assert_allclose(result, field(points[0]), atol=2e-14)
        self.assertTrue(mask.all())

    def test_singleton_axes_have_no_phantom_neighbor(self):
        for shape in ((1, 4, 3), (1, 1, 3), (1, 1, 1)):
            with self.subTest(shape=shape):
                source = grid(shape=shape)
                fractional = (numpy.asarray(shape) - 1) * .37
                point = world(source, fractional)
                value, valid = sampling.sample_grid_points(source, point)
                self.assertTrue(valid)
                self.assertAlmostEqual(float(value), field(point))
                outside = point + numpy.asarray(source.step_vectors[0]) * .01
                value, valid = sampling.sample_grid_points(source, outside)
                self.assertFalse(valid)
                self.assertTrue(numpy.isnan(value))

    def test_selected_dataset_is_sampled_in_bounded_lazy_gathers(self):
        source = grid(multidataset=True)
        lazy = SliceOnlyArray(source.data.values)
        source = replace(source, data=replace(source.data, values=lazy))
        points = world(source, numpy.tile([.2, 1.7, .6], (31, 1)))
        with patch.object(sampling, "_SAMPLE_BLOCK_SIZE", 7):
            values, valid = sampling.sample_grid_points(source, points, dataset_index=1)
        self.assertTrue(valid.all())
        numpy.testing.assert_allclose(values, -5 + 10 * field(points))
        self.assertGreater(len(lazy.accessed), 8)
        self.assertTrue(all(key[0] == 1 and len(key[1]) <= 7 for key in lazy.accessed))

    def test_nonfinite_source_only_invalidates_contributing_stencil(self):
        source = grid(steps=((1, 0, 0), (0, 1, 0), (0, 0, 1)))
        values = source.data.values.copy()
        values[1, 1, 1] = numpy.nan
        source = replace(source, data=replace(source.data, values=values))
        points = world(source, [[0, 0, 0], [.5, .5, .5], [3, 2, 1]])
        result, valid = sampling.sample_grid_points(source, points)
        numpy.testing.assert_array_equal(valid, [True, False, True])
        self.assertTrue(numpy.isnan(result[1]))
        numpy.testing.assert_allclose(result[[0, 2]], field(points[[0, 2]]))

    def test_invalid_query_unit_dimensions_and_selection_are_rejected(self):
        source = grid(multidataset=True)
        for points in ([1., 2.], [[0, 0, numpy.nan]], [[numpy.inf, 0, 0]], [[1j, 0, 0]]):
            with self.subTest(points=points), self.assertRaises(ValueError):
                sampling.sample_grid_points(source, points, dataset_index=0)
        for index in (None, -1, 2, True, numpy.bool_(False), 1.2):
            with self.subTest(index=index), self.assertRaises((TypeError, ValueError, IndexError)):
                sampling.sample_grid_points(source, source.origin, dataset_index=index)
        for unit in ("unknown", "nanometer"):
            with self.subTest(unit=unit), self.assertRaises(ValueError):
                sampling.sample_grid_points(source, source.origin, dataset_index=0, coordinate_unit=unit)
        unsupported = replace(source, data=replace(source.data, dims=("spin", "x", "y", "z")))
        with self.assertRaises(ValueError):
            sampling.sample_grid_points(unsupported, source.origin, dataset_index=0)
        complex_grid = replace(source, data=replace(source.data, values=source.data.values.astype(complex)))
        with self.assertRaisesRegex(ValueError, "real numeric"):
            sampling.sample_grid_points(complex_grid, source.origin, dataset_index=0)

    def test_plane_and_profile_full_spans_include_endpoints(self):
        source = grid()
        origin = world(source, [.1, .2, .3])
        u = numpy.asarray(source.step_vectors[0]) * 3.7
        v = numpy.asarray(source.step_vectors[1]) * 2.6
        plane = sampling.plane_slice(source, origin=origin, u_vector=u, v_vector=v, counts=(9, 7))
        self.assertEqual(plane.points.shape, (9, 7, 3))
        self.assertIsNone(plane.distance)
        numpy.testing.assert_allclose(plane.points[0, 0], origin)
        numpy.testing.assert_allclose(plane.points[-1, -1], origin + u + v)
        self.assertTrue(plane.valid_mask.all())
        numpy.testing.assert_allclose(plane.values, field(plane.points), atol=2e-14)
        end = world(source, [3.8, 2.8, 1.7])
        profile = sampling.line_profile(source, start=origin, end=end, sample_count=17)
        self.assertTrue(profile.valid_mask.all())
        numpy.testing.assert_allclose(profile.values, field(profile.points), atol=2e-14)
        numpy.testing.assert_array_equal(profile.points[[0, -1]], [origin, end])
        numpy.testing.assert_allclose(profile.distance,
            numpy.linspace(0, numpy.linalg.norm(end - origin), 17), atol=2e-14)

    def test_metadata_validators_reject_degenerate_geometry_and_invalid_counts(self):
        plane = dict(origin=(0, 0, 0), u_vector=(1, 0, 0), v_vector=(0, 1, 0), counts=(3, 4))
        profile = dict(start=(0, 0, 0), end=(1, 0, 0), sample_count=3)
        self.assertEqual(sampling.validate_plane(**plane)["origin"], (0., 0., 0.))
        self.assertEqual(sampling.validate_profile(**profile)["dataset_index"], 0)
        for override in ({"u_vector": (0, 0, 0)}, {"v_vector": (2, 0, 0)},
                         {"origin": (numpy.nan, 0, 0)}, {"counts": (1, 4)},
                         {"counts": (True, 4)}, {"dataset_index": -1}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                sampling.validate_plane(**(plane | override))
        for override in ({"end": (0, 0, 0)}, {"start": (0, numpy.inf, 0)},
                         {"sample_count": 1}, {"sample_count": 3.2}, {"dataset_index": True}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                sampling.validate_profile(**(profile | override))


class GridSampleExportTests(unittest.TestCase):
    def settings(self, source):
        return dict(start=tuple(world(source, [-1, 1, 1])),
                    end=tuple(world(source, [4, 1, 1])), sample_count=11,
                    dataset_index=1, color_min=-2, color_max=2, radius=.05)

    def test_csv_preserves_affine_source_units_values_and_invalid_blanks(self):
        source = grid(multidataset=True)
        settings = self.settings(source)
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "profile.csv"
            report = sampling.export_grid_sample(path, source, kind="profile", settings=settings)
            content = path.read_text(encoding="utf-8")
            self.assertTrue(report.written)
            self.assertEqual(set(Path(temporary).iterdir()), {path})
        metadata_line, csv_text = content.split("\n", 1)
        metadata = json.loads(metadata_line[2:])
        self.assertEqual(metadata["grid_id"], str(source.id))
        self.assertEqual(metadata["grid_revision"], source.revision)
        self.assertEqual(metadata["grid_step_vectors"], [list(row) for row in source.step_vectors])
        self.assertEqual(metadata["sampling"]["dataset_index"], 1)
        self.assertNotIn("color_min", metadata["sampling"])
        rows = list(csv.DictReader(io.StringIO(csv_text)))
        self.assertEqual(len(rows), 11)
        self.assertEqual(rows[0]["value"], "")
        self.assertEqual(rows[0]["valid_mask"], "0")
        for row in rows:
            self.assertEqual(row["coordinate_unit"], "bohr")
            self.assertEqual(row["value_unit"], source.data.unit)
            if row["valid_mask"] == "1":
                point = [float(row[key]) for key in ("x", "y", "z")]
                self.assertAlmostEqual(float(row["value"]), -5 + 10 * field(point))
        self.assertAlmostEqual(float(rows[-1]["distance"]),
            numpy.linalg.norm(numpy.asarray(settings["end"]) - settings["start"]))

    def test_plane_csv_count_and_no_distance(self):
        source = grid()
        settings = dict(origin=source.origin,
            u_vector=tuple(numpy.asarray(source.step_vectors[0]) * 4),
            v_vector=tuple(numpy.asarray(source.step_vectors[1]) * 3), counts=(5, 4))
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "slice.csv"
            sampling.export_grid_sample(path, source, kind="plane", settings=settings)
            rows = list(csv.DictReader(io.StringIO(path.read_text().split("\n", 1)[1])))
        self.assertEqual(len(rows), 20)
        self.assertTrue(all(row["distance"] == "" and row["valid_mask"] == "1" for row in rows))

    def test_cancel_before_sampling_or_during_csv_preserves_existing_file(self):
        source = grid(multidataset=True)
        settings = self.settings(source)
        for threshold in (1, 10):
            with self.subTest(threshold=threshold), TemporaryDirectory() as temporary:
                path = Path(temporary) / "profile.csv"
                path.write_text("existing data", encoding="utf-8")
                calls = [0]
                def cancelled():
                    calls[0] += 1
                    return calls[0] >= threshold
                with self.assertRaises(ExportCancelled):
                    sampling.export_grid_sample(path, source, kind="profile", settings=settings,
                                                is_cancelled=cancelled)
                self.assertEqual(path.read_text(), "existing data")
                self.assertEqual(set(Path(temporary).iterdir()), {path})


if __name__ == "__main__":
    unittest.main()
