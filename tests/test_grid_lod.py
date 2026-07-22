import unittest
from uuid import UUID

import numpy

from ChemBlender.core import ArrayData, DatasetStatus, Grid3D
from ChemBlender.core.grid_lod import (
    derive_grid_lod,
    surface_render_cache_key,
    volume_render_cache_key,
)


GRID_ID = UUID("10000000-0000-0000-0000-000000000001")
STRUCTURE_ID = UUID("20000000-0000-0000-0000-000000000002")


class SliceOnlyArray:
    def __init__(self, values):
        self._values = numpy.asarray(values)
        self.shape = self._values.shape
        self.dtype = self._values.dtype
        self.accessed = []

    def __getitem__(self, key):
        self.accessed.append(key)
        return self._values[key]

    def __array__(self, dtype=None, copy=None):
        raise AssertionError("LOD must not materialize the full source grid")


def grid(values, *, revision="grid-r1", dims=("dataset", "x", "y", "z")):
    source = SliceOnlyArray(values)
    return (
        Grid3D(
            id=GRID_ID,
            revision=revision,
            semantic_role="electron_density",
            domain="grid",
            data=ArrayData(source, dims, "electron_per_cubic_bohr"),
            status=DatasetStatus.COMPLETE,
            source_calculation=None,
            provenance_ids=(),
            origin=(1.0, 2.0, 3.0),
            step_vectors=(
                (0.5, 0.0, 0.0),
                (0.1, 0.4, 0.0),
                (0.0, 0.2, 0.3),
            ),
            coordinate_unit="bohr",
            structure_id=STRUCTURE_ID,
        ),
        source,
    )


class GridLodTests(unittest.TestCase):
    def test_multidataset_lod_uses_one_lazy_slice_and_preserves_affine_semantics(self):
        source_values = numpy.arange(2 * 5 * 6 * 7).reshape((2, 5, 6, 7))
        source_grid, source = grid(source_values)
        batch = derive_grid_lod(source_grid, strides=(2, 3, 2), dataset_index=1)
        lod = batch.datasets[0]

        self.assertEqual(
            source.accessed,
            [(1, slice(None, None, 2), slice(None, None, 3), slice(None, None, 2))],
        )
        self.assertTrue(
            numpy.array_equal(lod.data.values, source_values[1, ::2, ::3, ::2])
        )
        self.assertEqual(lod.data.dims, ("x", "y", "z"))
        self.assertEqual(lod.origin, source_grid.origin)
        self.assertTrue(numpy.allclose(
            lod.step_vectors,
            ((1.0, 0.0, 0.0), (0.3, 1.2, 0.0), (0.0, 0.4, 0.6)),
        ))
        self.assertEqual(lod.data.unit, source_grid.data.unit)
        self.assertEqual(lod.coordinate_unit, source_grid.coordinate_unit)
        self.assertEqual(lod.structure_id, STRUCTURE_ID)
        self.assertEqual(batch.provenance[0].parent_ids, (GRID_ID,))
        self.assertTrue(numpy.array_equal(source_values, numpy.arange(source_values.size).reshape(source_values.shape)))

    def test_identity_is_stable_and_invalidates_at_the_correct_layers(self):
        source_grid, _ = grid(numpy.zeros((2, 5, 6, 7)))
        first = derive_grid_lod(source_grid, strides=(2, 2, 2), dataset_index=0)
        second = derive_grid_lod(source_grid, strides=(2, 2, 2), dataset_index=0)
        changed_stride = derive_grid_lod(
            source_grid, strides=(2, 3, 2), dataset_index=0
        )
        changed_dataset = derive_grid_lod(
            source_grid, strides=(2, 2, 2), dataset_index=1
        )
        changed_source, _ = grid(
            numpy.zeros((2, 5, 6, 7)), revision="grid-r2"
        )
        changed_revision = derive_grid_lod(
            changed_source, strides=(2, 2, 2), dataset_index=0
        )
        self.assertEqual(first.datasets[0].id, second.datasets[0].id)
        self.assertEqual(first.datasets[0].revision, second.datasets[0].revision)
        self.assertNotEqual(first.datasets[0].revision, changed_stride.datasets[0].revision)
        self.assertNotEqual(first.datasets[0].revision, changed_dataset.datasets[0].revision)
        self.assertNotEqual(first.datasets[0].revision, changed_revision.datasets[0].revision)

        lod = first.datasets[0]
        volume = volume_render_cache_key(lod, dataset_index=0)
        self.assertEqual(volume, volume_render_cache_key(lod, dataset_index=0))
        self.assertNotEqual(
            volume,
            volume_render_cache_key(lod, dataset_index=0, adapter_version="2"),
        )
        surface = surface_render_cache_key(lod, dataset_index=0, isovalue=0.05)
        self.assertNotEqual(
            surface,
            surface_render_cache_key(lod, dataset_index=0, isovalue=0.06),
        )
        self.assertNotEqual(
            surface,
            surface_render_cache_key(
                lod,
                dataset_index=0,
                isovalue=0.05,
                volume_adapter_version="2",
            ),
        )

    def test_dataset_selection_and_stride_validation_are_explicit(self):
        multi, _ = grid(numpy.zeros((2, 5, 6, 7)))
        with self.assertRaises(ValueError):
            derive_grid_lod(multi, strides=(2, 2, 2))
        with self.assertRaises(IndexError):
            derive_grid_lod(multi, strides=(2, 2, 2), dataset_index=2)
        for strides in ((1, 1, 1), (2, 0, 2), (2, True, 2), (2, 2)):
            with self.subTest(strides=strides):
                with self.assertRaises((TypeError, ValueError)):
                    derive_grid_lod(multi, strides=strides, dataset_index=0)

        scalar, _ = grid(
            numpy.zeros((5, 6, 7)), dims=("x", "y", "z")
        )
        derive_grid_lod(scalar, strides=(2, 2, 2))
        with self.assertRaises(IndexError):
            derive_grid_lod(scalar, strides=(2, 2, 2), dataset_index=1)

    def test_surface_cache_rejects_non_finite_isovalue(self):
        source_grid, _ = grid(numpy.zeros((2, 5, 6, 7)))
        with self.assertRaises(ValueError):
            surface_render_cache_key(
                source_grid, dataset_index=0, isovalue=float("nan")
            )


if __name__ == "__main__":
    unittest.main()
