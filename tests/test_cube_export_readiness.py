import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from uuid import uuid4

import numpy

from ChemBlender.core import (
    ArrayData,
    AtomicProperty,
    CubeExportReadiness,
    CubeExportStatus,
    DatasetStatus,
    Grid3D,
    cube_export_readiness,
)
from ChemBlender.core.cube import CUBE_READER


FIXTURES = Path(__file__).with_name("fixtures") / "cube"
SHEARED = FIXTURES / "sheared.cube"
TWO_DATASETS = FIXTURES / "two-datasets.cube"


class CubeExportReadinessTests(unittest.TestCase):
    def scalar(self):
        return CUBE_READER.parse(SHEARED)

    def multi(self):
        return CUBE_READER.parse(TWO_DATASETS)

    @staticmethod
    def grid(batch):
        return next(value for value in batch.datasets if isinstance(value, Grid3D))

    @staticmethod
    def charge(batch):
        return next(
            value for value in batch.datasets if isinstance(value, AtomicProperty)
        )

    def test_scalar_fixture_is_ready_and_report_is_frozen(self):
        report = cube_export_readiness(self.scalar())

        self.assertEqual(report, CubeExportReadiness(CubeExportStatus.READY, ()))
        with self.assertRaises(FrozenInstanceError):
            report.status = CubeExportStatus.INVALID

    def test_missing_ambiguous_cross_linked_and_duplicate_entities_fail_closed(self):
        batch = self.scalar()
        grid = self.grid(batch)
        charge = self.charge(batch)
        cases = (
            (
                replace(batch, structures=()),
                CubeExportStatus.MISSING_ENTITY,
                ("structure.missing",),
            ),
            (
                replace(batch, datasets=(charge,)),
                CubeExportStatus.MISSING_ENTITY,
                ("grid.missing",),
            ),
            (
                replace(batch, datasets=(grid,)),
                CubeExportStatus.MISSING_ENTITY,
                ("dataset.nuclear_charge.missing",),
            ),
            (
                replace(batch, datasets=(replace(grid, structure_id=uuid4()), charge)),
                CubeExportStatus.MISSING_ENTITY,
                ("structure.missing",),
            ),
            (
                replace(batch, datasets=(grid, replace(grid, id=uuid4()), charge)),
                CubeExportStatus.AMBIGUOUS,
                ("grid.ambiguous",),
            ),
            (
                replace(batch, datasets=(grid, charge, replace(charge, id=uuid4()))),
                CubeExportStatus.AMBIGUOUS,
                ("dataset.nuclear_charge.ambiguous",),
            ),
            (
                replace(batch, datasets=(grid, replace(charge, id=grid.id))),
                CubeExportStatus.AMBIGUOUS,
                ("entity.uuid.duplicate",),
            ),
        )
        for project_entities, status, tokens in cases:
            with self.subTest(status=status, tokens=tokens):
                self.assertEqual(
                    cube_export_readiness(project_entities),
                    CubeExportReadiness(status, tokens),
                )

        mixed = replace(
            batch,
            structures=(batch.structures[0], batch.structures[0]),
            datasets=(charge,),
        )
        report = cube_export_readiness(mixed)
        self.assertEqual(report.tokens, tuple(sorted(report.tokens)))

    def test_zero_atoms_and_non_real_or_non_finite_arrays_are_invalid(self):
        batch = self.scalar()
        structure = batch.structures[0]
        grid = self.grid(batch)
        charge = self.charge(batch)
        empty_structure = replace(
            structure,
            atomic_numbers=(),
            coordinates=ArrayData(
                numpy.empty((0, 3), dtype=float),
                ("atom", "xyz"),
                "bohr",
            ),
        )
        empty_charge = replace(
            charge,
            data=ArrayData(numpy.empty((0,), dtype=float), ("atom",), "elementary_charge"),
        )
        complex_grid = replace(
            grid,
            data=ArrayData(
                numpy.ones(grid.data.shape, dtype=complex),
                grid.data.dims,
                grid.data.unit,
            ),
        )
        nan_charge = replace(
            charge,
            data=ArrayData(
                numpy.asarray((numpy.nan,)),
                ("atom",),
                "elementary_charge",
            ),
        )
        cases = (
            (
                replace(
                    batch,
                    structures=(empty_structure,),
                    datasets=(replace(grid, structure_id=empty_structure.id), empty_charge),
                ),
                ("structure.atom_count",),
            ),
            (replace(batch, datasets=(complex_grid, charge)), ("grid.data",)),
            (replace(batch, datasets=(grid, nan_charge)), ("dataset.nuclear_charge",)),
            (
                replace(
                    batch,
                    datasets=(
                        grid,
                        replace(charge, status=DatasetStatus.PARTIAL),
                    ),
                ),
                ("dataset.nuclear_charge",),
            ),
        )
        for project_entities, tokens in cases:
            with self.subTest(tokens=tokens):
                self.assertEqual(
                    cube_export_readiness(project_entities),
                    CubeExportReadiness(CubeExportStatus.INVALID, tokens),
                )

        live_batch = self.scalar()
        numpy.asarray(live_batch.structures[0].coordinates.values)[0, 0] = numpy.nan
        self.assertEqual(
            cube_export_readiness(live_batch),
            CubeExportReadiness(
                CubeExportStatus.INVALID,
                ("structure.coordinates",),
            ),
        )

    def test_live_array_shape_changes_are_invalid(self):
        structure_batch = self.scalar()
        object.__setattr__(
            structure_batch.structures[0].coordinates,
            "shape",
            (3, 1),
        )
        self.assertEqual(
            cube_export_readiness(structure_batch).tokens,
            ("structure.coordinates",),
        )

        grid_batch = self.scalar()
        object.__setattr__(self.grid(grid_batch).data, "shape", (8,))
        self.assertEqual(
            cube_export_readiness(grid_batch).tokens,
            ("grid.data",),
        )

    def test_dataset_selection_is_explicit_and_type_strict(self):
        scalar = self.scalar()
        multi = self.multi()
        ready_cases = ((scalar, None), (multi, 0), (multi, 1))
        for batch, dataset_index in ready_cases:
            with self.subTest(dataset_index=dataset_index):
                self.assertEqual(
                    cube_export_readiness(batch, dataset_index=dataset_index),
                    CubeExportReadiness(CubeExportStatus.READY, ()),
                )

        self.assertEqual(
            cube_export_readiness(multi),
            CubeExportReadiness(
                CubeExportStatus.MISSING_SELECTION,
                ("dataset_index.missing",),
            ),
        )
        for batch, dataset_index in (
            (scalar, 0),
            (multi, True),
            (multi, -1),
            (multi, 2),
            (multi, 1.0),
        ):
            with self.subTest(dataset_index=dataset_index):
                self.assertEqual(
                    cube_export_readiness(batch, dataset_index=dataset_index),
                    CubeExportReadiness(
                        CubeExportStatus.INVALID,
                        ("dataset_index.invalid",),
                    ),
                )

        grid = self.grid(multi)
        invalid = replace(
            multi,
            datasets=(
                replace(
                    grid,
                    data=ArrayData(
                        numpy.asarray(grid.data.values),
                        ("frame", "x", "y", "z"),
                        grid.data.unit,
                    ),
                ),
                self.charge(multi),
            ),
        )
        self.assertEqual(
            cube_export_readiness(invalid, dataset_index=0),
            CubeExportReadiness(
                CubeExportStatus.INVALID,
                ("grid.leading_dims",),
            ),
        )

    def test_coordinate_units_are_independent_and_fail_closed(self):
        batch = self.scalar()
        structure = batch.structures[0]
        grid = self.grid(batch)
        charge = self.charge(batch)
        angstrom_structure = replace(
            structure,
            coordinates=ArrayData(
                numpy.asarray(structure.coordinates.values),
                ("atom", "xyz"),
                "angstrom",
            ),
        )
        angstrom_grid = replace(grid, coordinate_unit="angstrom")
        for candidate in (
            replace(batch, structures=(angstrom_structure,)),
            replace(batch, datasets=(angstrom_grid, charge)),
        ):
            self.assertEqual(
                cube_export_readiness(candidate),
                CubeExportReadiness(CubeExportStatus.READY, ()),
            )

        for unit in ("unknown", "nanometer"):
            report = cube_export_readiness(
                replace(batch, datasets=(replace(grid, coordinate_unit=unit), charge))
            )
            self.assertEqual(
                report,
                CubeExportReadiness(
                    CubeExportStatus.UNSUPPORTED_UNIT,
                    ("grid.coordinate_unit",),
                ),
            )

        dimensionless_grid = self.scalar()
        object.__setattr__(
            self.grid(dimensionless_grid),
            "coordinate_unit",
            "dimensionless",
        )
        self.assertEqual(
            cube_export_readiness(dimensionless_grid),
            CubeExportReadiness(
                CubeExportStatus.UNSUPPORTED_UNIT,
                ("grid.coordinate_unit",),
            ),
        )

        invalid_structure = self.scalar()
        object.__setattr__(
            invalid_structure.structures[0].coordinates,
            "unit",
            "unknown",
        )
        self.assertEqual(
            cube_export_readiness(invalid_structure),
            CubeExportReadiness(
                CubeExportStatus.UNSUPPORTED_UNIT,
                ("structure.coordinates.unit",),
            ),
        )

        invalid_charge = replace(
            charge,
            data=ArrayData(
                numpy.asarray(charge.data.values),
                ("atom",),
                "dimensionless",
            ),
        )
        self.assertEqual(
            cube_export_readiness(replace(batch, datasets=(grid, invalid_charge))),
            CubeExportReadiness(
                CubeExportStatus.INVALID,
                ("dataset.nuclear_charge",),
            ),
        )

    def test_lazy_close_failure_does_not_replace_primary_exception(self):
        batch = self.scalar()
        coordinates = numpy.asarray(batch.structures[0].coordinates.values)

        class ReadAndCloseFailure:
            shape = coordinates.shape
            dtype = coordinates.dtype
            loaded = False

            def __array__(self, dtype=None, copy=None):
                raise MemoryError("read failed")

            def close(self):
                raise OSError("close failed")

        structure = replace(
            batch.structures[0],
            coordinates=replace(
                batch.structures[0].coordinates,
                values=ReadAndCloseFailure(),
            ),
        )

        with self.assertRaisesRegex(MemoryError, "read failed") as caught:
            cube_export_readiness(replace(batch, structures=(structure,)))
        self.assertTrue(any("close failed" in note for note in caught.exception.__notes__))


if __name__ == "__main__":
    unittest.main()
