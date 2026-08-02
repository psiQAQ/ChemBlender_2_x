import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from uuid import uuid4

import numpy

from ChemBlender.core import (
    ArrayData,
    CubeExport,
    export_cube,
    preview_cube_export,
)
from ChemBlender.core.cube import CUBE_READER
from ChemBlender.core.model import AtomicProperty, Grid3D


BOHR_TO_ANGSTROM = 0.529177210903
FIXTURES = Path(__file__).with_name("fixtures") / "cube"
SHEARED = FIXTURES / "sheared.cube"
TWO_DATASETS = FIXTURES / "two-datasets.cube"


class CubeExporterTests(unittest.TestCase):
    @staticmethod
    def scalar():
        return CUBE_READER.parse(SHEARED)

    @staticmethod
    def multi():
        return CUBE_READER.parse(TWO_DATASETS)

    @staticmethod
    def grid(batch):
        return next(value for value in batch.datasets if isinstance(value, Grid3D))

    @staticmethod
    def charge(batch):
        return next(
            value for value in batch.datasets if isinstance(value, AtomicProperty)
        )

    @staticmethod
    def lines(exported):
        return exported.text.splitlines()

    def test_scalar_output_is_deterministic_affine_ascii_cube(self):
        batch = self.scalar()
        first = export_cube(batch)
        second = export_cube(batch)
        grid = self.grid(batch)
        charge = self.charge(batch)
        reordered = SimpleNamespace(
            structures={batch.structures[0].id: batch.structures[0]},
            datasets={charge.id: charge, grid.id: grid},
            provenance={batch.provenance[0].id: batch.provenance[0]},
        )

        self.assertEqual(first, second)
        self.assertEqual(first.text, export_cube(reordered).text)
        self.assertIsInstance(first, CubeExport)
        with self.assertRaises(FrozenInstanceError):
            first.text = "changed"
        self.assertTrue(first.text.isascii())
        self.assertTrue(first.text.endswith("\n"))
        self.assertFalse(first.text.endswith("\n\n"))
        self.assertNotIn("-0.000000000000E+00", first.text)

        lines = self.lines(first)
        self.assertEqual(lines[:2], [
            "ChemBlender deterministic Cube export",
            "selected scalar dataset",
        ])
        origin = lines[2].split()
        self.assertEqual(int(origin[0]), 1)
        self.assertEqual(tuple(float(value) for value in origin[1:]), (0.0, 0.0, 0.0))
        axes = tuple(lines[index].split() for index in range(3, 6))
        self.assertEqual(tuple(int(fields[0]) for fields in axes), (2, 2, 2))
        self.assertEqual(
            tuple(tuple(float(value) for value in fields[1:]) for fields in axes),
            grid.step_vectors,
        )
        atom = lines[6].split()
        self.assertEqual(int(atom[0]), 8)
        self.assertEqual(float(atom[1]), 8.0)
        self.assertEqual(tuple(float(value) for value in atom[2:]), (0.0, 0.0, 0.0))
        self.assertTrue(all(len(line.split()) <= 6 for line in lines[7:]))
        self.assertEqual(
            tuple(float(value) for line in lines[7:] for value in line.split()),
            tuple(float(value) for value in range(8)),
        )
        self.assertFalse(first.report.written)

    def test_equivalent_bohr_and_angstrom_entities_export_identically(self):
        bohr = self.scalar()
        structure = bohr.structures[0]
        grid = self.grid(bohr)
        charge = self.charge(bohr)
        angstrom_structure = replace(
            structure,
            coordinates=ArrayData(
                numpy.asarray(structure.coordinates.values) * BOHR_TO_ANGSTROM,
                ("atom", "xyz"),
                "angstrom",
            ),
        )
        angstrom_grid = replace(
            grid,
            origin=tuple(value * BOHR_TO_ANGSTROM for value in grid.origin),
            step_vectors=tuple(
                tuple(value * BOHR_TO_ANGSTROM for value in row)
                for row in grid.step_vectors
            ),
            coordinate_unit="angstrom",
        )
        angstrom = replace(
            bohr,
            structures=(angstrom_structure,),
            datasets=(angstrom_grid, charge),
        )

        before_coordinates = numpy.array(angstrom_structure.coordinates.values, copy=True)
        before_origin = angstrom_grid.origin
        self.assertEqual(export_cube(bohr).text, export_cube(angstrom).text)
        numpy.testing.assert_array_equal(
            angstrom_structure.coordinates.values,
            before_coordinates,
        )
        self.assertEqual(angstrom_structure.coordinates.unit, "angstrom")
        self.assertEqual(angstrom_grid.origin, before_origin)
        self.assertEqual(angstrom_grid.coordinate_unit, "angstrom")

    def test_selected_dataset_preserves_trusted_id_and_values(self):
        batch = self.multi()
        for dataset_index, dataset_id, expected in (
            (0, 5, (10.0, 11.0, 12.0, 13.0)),
            (1, 7, (100.0, 101.0, 102.0, 103.0)),
        ):
            with self.subTest(dataset_index=dataset_index):
                exported = export_cube(batch, dataset_index=dataset_index)
                lines = self.lines(exported)
                self.assertEqual(int(lines[2].split()[0]), -1)
                self.assertEqual(
                    tuple(int(lines[index].split()[0]) for index in range(3, 6)),
                    (2, 2, 1),
                )
                self.assertEqual(tuple(int(value) for value in lines[7].split()), (1, dataset_id))
                self.assertEqual(
                    tuple(
                        float(value)
                        for line in lines[8:]
                        for value in line.split()
                    ),
                    expected,
                )

    def test_scalar_dataset_id_is_preserved_only_when_trustworthy(self):
        multi = self.multi()
        grid = self.grid(multi)
        provenance = multi.provenance[0]
        scalar_grid = replace(
            grid,
            data=ArrayData(
                numpy.asarray(grid.data.values)[0],
                ("x", "y", "z"),
                grid.data.unit,
            ),
        )
        trusted = replace(
            provenance,
            parameters=tuple(
                (key, (0,) if key == "dataset_ids" else 1 if key == "dataset_count" else value)
                for key, value in provenance.parameters
            ),
        )
        trusted_batch = replace(
            multi,
            datasets=(scalar_grid, self.charge(multi)),
            provenance=(trusted,),
        )
        trusted_lines = self.lines(export_cube(trusted_batch))
        self.assertEqual(int(trusted_lines[2].split()[0]), -1)
        self.assertEqual(tuple(int(value) for value in trusted_lines[7].split()), (1, 0))

        ordinary_lines = self.lines(export_cube(self.scalar()))
        self.assertEqual(int(ordinary_lines[2].split()[0]), 1)
        self.assertNotEqual(ordinary_lines[7].split()[:2], ["1", "0"])

        malformed = replace(
            trusted,
            parameters=tuple(
                (key, (-1,) if key == "dataset_ids" else value)
                for key, value in trusted.parameters
            ),
        )
        malformed_batch = replace(trusted_batch, provenance=(malformed,))
        preview = preview_cube_export(malformed_batch)
        self.assertTrue(preview.requires_confirmation)
        self.assertEqual(tuple(entry.code for entry in preview.entries), ("dataset_id_omitted",))
        self.assertEqual(export_cube(malformed_batch).text, "")
        confirmed = export_cube(malformed_batch, confirm_loss=True)
        self.assertEqual(int(self.lines(confirmed)[2].split()[0]), 1)

    def test_missing_multi_dataset_id_is_normalized_with_confirmation(self):
        batch = self.multi()
        grid = replace(self.grid(batch), provenance_ids=())
        untrusted = replace(
            batch,
            datasets=(grid, self.charge(batch)),
            provenance=(),
        )

        preview = preview_cube_export(untrusted, dataset_index=1)
        self.assertEqual(tuple(entry.code for entry in preview.entries), ("dataset_id_normalized",))
        self.assertTrue(preview.requires_confirmation)
        self.assertEqual(export_cube(untrusted, dataset_index=1).text, "")
        exported = export_cube(untrusted, dataset_index=1, confirm_loss=True)
        self.assertEqual(tuple(int(value) for value in self.lines(exported)[7].split()), (1, 2))

    def test_dataset_id_lookup_does_not_traverse_provenance_lineage(self):
        batch = self.multi()
        source = batch.provenance[0]
        derived = replace(
            source,
            id=uuid4(),
            operation="resolve",
            parent_ids=(source.id,),
            parameters=(("format", "derived_grid"),),
        )
        grid = replace(self.grid(batch), provenance_ids=(derived.id,))
        projected = replace(
            batch,
            datasets=(grid, self.charge(batch)),
            provenance=(source, derived),
        )

        exported = export_cube(
            projected,
            dataset_index=1,
            confirm_loss=True,
        )
        self.assertEqual(
            tuple(int(value) for value in self.lines(exported)[7].split()),
            (1, 2),
        )
        self.assertEqual(
            tuple(entry.code for entry in exported.report.entries),
            ("dataset_id_normalized",),
        )

    def test_destination_uses_atomic_writer_and_report_tracks_publication(self):
        batch = self.scalar()
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "field.cube"
            exported = export_cube(batch, destination=destination)

            self.assertEqual(destination.read_text(encoding="utf-8"), exported.text)
            self.assertTrue(exported.report.written)
            self.assertEqual(exported.report.format, "cube")
            self.assertEqual(exported.report.frame_count, 1)


if __name__ == "__main__":
    unittest.main()
