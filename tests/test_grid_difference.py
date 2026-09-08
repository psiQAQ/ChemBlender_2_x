from concurrent.futures import CancelledError
from dataclasses import replace
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

import numpy

from ChemBlender.core.grid_difference import derive_grid_difference
from ChemBlender.core.model import ArrayData, DatasetStatus, Grid3D, ImportBatch, QCProject, Structure
from ChemBlender.core.sidecar import close_project, open_project, save_project


def density(structure_id, values, **changes):
    values = numpy.asarray(values)
    return Grid3D(**{
        "id": uuid4(), "revision": "density-v1", "semantic_role": "electron_density",
        "domain": "grid", "data": ArrayData(values,
            ("dataset", "x", "y", "z") if values.ndim == 4 else ("x", "y", "z"),
            "electron_per_cubic_bohr"), "status": DatasetStatus.COMPLETE,
        "source_calculation": None, "provenance_ids": (), "origin": (1., 2., 3.),
        "step_vectors": ((.5, .1, 0.), (0., .5, 0.), (0., 0., -.5)),
        "coordinate_unit": "bohr", "structure_id": structure_id, **changes,
    })


class GridDifferenceTests(unittest.TestCase):
    def setUp(self):
        self.structure_id = uuid4()
        self.left = density(self.structure_id, numpy.arange(8).reshape(2, 2, 2))
        self.right = density(self.structure_id, numpy.full((2, 2, 2), 3))

    def test_signed_subtraction_is_owned_chunk_independent_and_reversible(self):
        before = self.left.data.values.copy()
        first = derive_grid_difference(self.left, self.right, chunk_size=3)
        repeated = derive_grid_difference(self.left, self.right, chunk_size=1)
        reverse = derive_grid_difference(self.right, self.left)
        result = first.datasets[0]
        numpy.testing.assert_array_equal(result.data.values, before - 3.)
        numpy.testing.assert_array_equal(reverse.datasets[0].data.values, -result.data.values)
        numpy.testing.assert_array_equal(self.left.data.values, before)
        self.assertFalse(numpy.shares_memory(result.data.values, self.left.data.values))
        self.assertEqual(result.id, repeated.datasets[0].id)
        self.assertNotEqual(result.revision, reverse.datasets[0].revision)
        self.assertEqual(result.semantic_role, "difference_density")
        self.assertEqual(result.structure_id, self.structure_id)
        self.assertEqual(result.step_vectors, self.left.step_vectors)
        self.assertEqual(result.data.unit, self.left.data.unit)
        self.assertEqual(first.provenance[0].parent_ids, (self.left.id, self.right.id))

    def test_dataset_selection_and_noncontiguous_inputs(self):
        multiple = density(self.structure_id, numpy.stack((self.left.data.values, self.left.data.values * 2)))
        noncontiguous = replace(self.right, data=ArrayData(self.right.data.values[:, :, ::-1],
                                                        ("x", "y", "z"), self.right.data.unit))
        result = derive_grid_difference(multiple, noncontiguous, left_dataset_index=1).datasets[0]
        numpy.testing.assert_array_equal(result.data.values, self.left.data.values * 2. - 3.)
        with self.assertRaises(IndexError):
            derive_grid_difference(multiple, noncontiguous, left_dataset_index=2)
        with self.assertRaises(TypeError):
            derive_grid_difference(multiple, noncontiguous, left_dataset_index=True)

    def test_rejects_scientific_mismatches_without_alignment(self):
        changes = (
            {"structure_id": uuid4()}, {"structure_id": None},
            {"status": DatasetStatus.PARTIAL}, {"semantic_role": "spin_density"},
            {"coordinate_unit": "angstrom"}, {"origin": (1. + 1e-10, 2., 3.)},
            {"step_vectors": ((.6, .1, 0.), (0., .5, 0.), (0., 0., -.5))},
            {"data": ArrayData(numpy.ones((1, 2, 2)), ("x", "y", "z"), self.right.data.unit)},
            {"data": ArrayData(numpy.ones((2, 2, 2)), ("x", "y", "z"), "electron_per_cubic_angstrom")},
        )
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                derive_grid_difference(self.left, replace(self.right, **change))

    def test_rejects_nonfinite_complex_and_overflow(self):
        for value in (numpy.nan, numpy.inf, 1. + 2.j):
            right = density(self.structure_id, numpy.full((2, 2, 2), value))
            with self.subTest(value=value), self.assertRaises(ValueError):
                derive_grid_difference(self.left, right, chunk_size=1)
        maximum = numpy.finfo(float).max
        with self.assertRaisesRegex(ValueError, "non-finite"):
            derive_grid_difference(density(self.structure_id, numpy.full((2, 2, 2), maximum)),
                                   density(self.structure_id, numpy.full((2, 2, 2), -maximum)))

    def test_cancellation_before_and_during_subtraction_leaves_inputs_unchanged(self):
        before = self.left.data.values.copy()
        for calls_before_cancel in (0, 4):
            calls = iter([False] * calls_before_cancel + [True])
            with self.assertRaises(CancelledError):
                derive_grid_difference(self.left, self.right, chunk_size=1,
                                       cancel_check=lambda: next(calls))
        numpy.testing.assert_array_equal(self.left.data.values, before)
        for chunk_size in (0, -1, True, 1.5):
            with self.assertRaises((ValueError, TypeError)):
                derive_grid_difference(self.left, self.right, chunk_size=chunk_size)

    def test_both_sources_roundtrip_in_existing_sidecar(self):
        structure = Structure(id=self.structure_id, revision="structure-v1", atomic_numbers=(1,),
                              coordinates=ArrayData(numpy.zeros((1, 3)), ("atom", "xyz"), "bohr"))
        project = QCProject(id=uuid4(), schema_version="0.1")
        project.commit(ImportBatch(structures=(structure,), datasets=(self.left, self.right)))
        batch = derive_grid_difference(self.left, self.right)
        project.commit(batch)
        with tempfile.TemporaryDirectory() as directory:
            path = save_project(Path(directory) / "density.cbq", project)
            restored = open_project(path)
            try:
                result = restored.datasets[batch.datasets[0].id]
                numpy.testing.assert_array_equal(result.data.values, self.left.data.values - self.right.data.values)
                self.assertEqual(restored.provenance[batch.provenance[0].id].parent_ids,
                                 (self.left.id, self.right.id))
            finally:
                close_project(restored)
