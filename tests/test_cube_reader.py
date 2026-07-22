from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from ChemBlender.core import (
    DatasetStatus,
    Grid3D,
    IssueKind,
    QCProject,
    ReaderRegistry,
    SniffMatch,
)
from ChemBlender.core.cube import CUBE_READER, sniff_cube


ROOT = Path(__file__).resolve().parents[1]
SHEARED = ROOT / "tests" / "fixtures" / "cube" / "sheared.cube"
TWO_DATASETS = (
    ROOT / "tests" / "fixtures" / "cube" / "two-datasets.cube"
)


class CubeReaderTests(unittest.TestCase):
    def test_sniff_and_registry_recognize_cube(self):
        result = sniff_cube(SHEARED, SHEARED.read_bytes())
        self.assertEqual(result.match, SniffMatch.EXACT)
        self.assertIs(
            ReaderRegistry((CUBE_READER,)).select(SHEARED),
            CUBE_READER,
        )

    def test_parse_normalizes_sheared_grid_and_structure(self):
        batch = CUBE_READER.parse(SHEARED)
        structure = batch.structures[0]
        grid = batch.datasets[0]
        self.assertIsInstance(grid, Grid3D)
        self.assertEqual(structure.atomic_numbers, (8,))
        self.assertEqual(structure.coordinates.unit, "bohr")
        self.assertEqual(grid.origin, (0.0, 0.0, 0.0))
        self.assertEqual(
            grid.step_vectors,
            ((1.0, 0.0, 0.0), (0.2, 1.0, 0.0), (0.0, 0.3, 1.0)),
        )
        self.assertEqual(grid.data.dims, ("x", "y", "z"))
        self.assertEqual(grid.data.shape, (2, 2, 2))
        self.assertEqual(grid.coordinate_unit, "bohr")
        self.assertEqual(grid.data.unit, "unknown")
        self.assertIs(grid.status, DatasetStatus.AMBIGUOUS)
        self.assertEqual(grid.data.values[1, 0, 1], 5.0)
        point = tuple(
            grid.origin[axis]
            + grid.step_vectors[0][axis]
            + grid.step_vectors[1][axis]
            + grid.step_vectors[2][axis]
            for axis in range(3)
        )
        self.assertEqual(point, (1.2, 1.3, 1.0))
        self.assertEqual(
            {issue.path for issue in batch.report.issues},
            {"grid.semantic_role", "grid.data.unit"},
        )
        QCProject(id=uuid4(), schema_version="0.1").commit(batch)

    def test_parse_preserves_and_deinterleaves_dataset_ids(self):
        batch = CUBE_READER.parse(TWO_DATASETS)
        grid = batch.datasets[0]
        self.assertEqual(grid.data.dims, ("dataset", "x", "y", "z"))
        self.assertEqual(grid.data.shape, (2, 2, 2, 1))
        self.assertEqual(grid.data.values[0, 1, 0, 0], 12.0)
        self.assertEqual(grid.data.values[1, 1, 1, 0], 103.0)
        parameters = dict(batch.provenance[0].parameters)
        self.assertEqual(parameters["dataset_ids"], (5, 7))
        self.assertTrue(
            any(
                issue.kind is IssueKind.WARNING
                and issue.path == "grid.voxel_counts"
                for issue in batch.report.issues
            )
        )

    def test_parse_supports_positive_nval_without_ids(self):
        content = b"""title
field
1 0 0 0 2
1 1 0 0
1 0 1 0
2 0 0 1
1 1.0 0 0 0
1.0 10.0 2.0 20.0
"""
        batch = self.parse_bytes(content)
        grid = batch.datasets[0]
        self.assertEqual(grid.data.shape, (2, 1, 1, 2))
        self.assertEqual(grid.data.values[0, 0, 0, 1], 2.0)
        self.assertEqual(grid.data.values[1, 0, 0, 1], 20.0)
        self.assertNotIn("dataset_ids", dict(batch.provenance[0].parameters))

    def test_nondefault_nuclear_charge_is_reported(self):
        content = SHEARED.read_bytes().replace(b"8.000000", b"6.000000", 1)
        batch = self.parse_bytes(content)
        self.assertIn(
            (IssueKind.UNSUPPORTED, "atom_nuclear_charge"),
            {(issue.kind, issue.path) for issue in batch.report.issues},
        )

    def test_parse_rejects_invalid_cube_boundaries(self):
        base = SHEARED.read_bytes()
        cases = (
            base.replace(b"    1    0.000000", b"    0    0.000000", 1),
            base.replace(b"    2    1.000000", b"    0    1.000000", 1),
            base.replace(b"    2    0.200000    1.000000", b"    2    2.000000    0.000000", 1),
            base.replace(b" 6.0 7.0", b" 6.0"),
            base + b" 8.0\n",
            base.replace(b" 0.0 1.0", b" nan 1.0", 1),
            TWO_DATASETS.read_bytes().replace(b"    2    5    7", b"    2    5", 1),
            TWO_DATASETS.read_bytes().replace(
                b"   -1    0.100000    0.200000    0.300000",
                b"   -1    0.100000    0.200000    0.300000 2",
                1,
            ),
        )
        for content in cases:
            with self.subTest(content=content[:100]):
                with self.assertRaises(ValueError):
                    self.parse_bytes(content)

    @staticmethod
    def parse_bytes(content):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "input.cube"
            source.write_bytes(content)
            return CUBE_READER.parse(source)


if __name__ == "__main__":
    unittest.main()
