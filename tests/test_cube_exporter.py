import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import numpy

from ChemBlender.core import (
    ArrayData,
    AtomicIdentityData,
    CategoricalData,
    CubeExport,
    MolecularTopology,
    export_cube,
    preview_cube_export,
)
from ChemBlender.core.cube import CUBE_READER
from ChemBlender.core.model import AtomicProperty, Grid3D
from ChemBlender.core.sidecar import LazyNpyArray, _array_content_hash
from ChemBlender.core.exporters import ExportCancelled


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
        first = export_cube(batch, confirm_loss=True)
        second = export_cube(batch, confirm_loss=True)
        grid = self.grid(batch)
        charge = self.charge(batch)
        reordered = SimpleNamespace(
            structures={batch.structures[0].id: batch.structures[0]},
            datasets={charge.id: charge, grid.id: grid},
            provenance={batch.provenance[0].id: batch.provenance[0]},
        )

        self.assertEqual(first, second)
        self.assertEqual(first.text, export_cube(reordered, confirm_loss=True).text)
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
        self.assertEqual(
            export_cube(bohr, confirm_loss=True).text,
            export_cube(angstrom, confirm_loss=True).text,
        )
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
                exported = export_cube(
                    batch,
                    dataset_index=dataset_index,
                    confirm_loss=True,
                )
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
        trusted_lines = self.lines(export_cube(trusted_batch, confirm_loss=True))
        self.assertEqual(int(trusted_lines[2].split()[0]), -1)
        self.assertEqual(tuple(int(value) for value in trusted_lines[7].split()), (1, 0))

        ordinary_lines = self.lines(export_cube(self.scalar(), confirm_loss=True))
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
        self.assertIn("dataset_id_omitted", tuple(entry.code for entry in preview.entries))
        self.assertEqual(export_cube(malformed_batch).text, "")
        confirmed = export_cube(malformed_batch, confirm_loss=True)
        self.assertEqual(int(self.lines(confirmed)[2].split()[0]), 1)

        dangling_grid = replace(
            scalar_grid,
            provenance_ids=(trusted.id, uuid4()),
        )
        dangling_batch = replace(
            trusted_batch,
            datasets=(dangling_grid, self.charge(multi)),
        )
        dangling_preview = preview_cube_export(dangling_batch)
        self.assertIn(
            "dataset_id_omitted",
            tuple(entry.code for entry in dangling_preview.entries),
        )
        dangling_export = export_cube(dangling_batch, confirm_loss=True)
        self.assertEqual(int(self.lines(dangling_export)[2].split()[0]), 1)

    def test_missing_multi_dataset_id_is_normalized_with_confirmation(self):
        batch = self.multi()
        grid = replace(self.grid(batch), provenance_ids=())
        untrusted = replace(
            batch,
            datasets=(grid, self.charge(batch)),
            provenance=(),
        )

        preview = preview_cube_export(untrusted, dataset_index=1)
        self.assertIn("dataset_id_normalized", tuple(entry.code for entry in preview.entries))
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
        self.assertIn(
            "dataset_id_normalized",
            tuple(entry.code for entry in exported.report.entries),
        )

    def test_destination_uses_atomic_writer_and_report_tracks_publication(self):
        batch = self.scalar()
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "field.cube"
            exported = export_cube(
                batch,
                confirm_loss=True,
                destination=destination,
            )

            self.assertEqual(destination.read_text(encoding="utf-8"), exported.text)
            self.assertTrue(exported.report.written)
            self.assertEqual(exported.report.format, "cube")
            self.assertEqual(exported.report.frame_count, 1)

    def test_destination_yields_header_before_formatting_numeric_rows(self):
        observed = []

        def consume_first(_destination, chunks, *, is_cancelled=None):
            observed.append(next(iter(chunks)))

        with (
            patch(
                "ChemBlender.core.exporters.cube.atomic_write_chunks",
                side_effect=consume_first,
            ),
            patch(
                "ChemBlender.core.exporters.cube._number",
                side_effect=AssertionError("numeric rows formatted before first yield"),
            ),
        ):
            export_cube(
                self.scalar(),
                confirm_loss=True,
                destination=Path("unused.cube"),
            )

        self.assertEqual(observed, ["ChemBlender deterministic Cube export\n"])

    def test_destination_cancels_before_formatting_the_full_payload(self):
        from ChemBlender.core.exporters.cube import _number

        checks = 0
        numeric_rows = 0

        def cancel_before_first_write():
            nonlocal checks
            checks += 1
            return checks >= 3

        def count_number(value):
            nonlocal numeric_rows
            numeric_rows += 1
            return _number(value)

        with TemporaryDirectory() as directory:
            destination = Path(directory) / "field.cube"
            with patch(
                "ChemBlender.core.exporters.cube._number",
                side_effect=count_number,
            ):
                with self.assertRaises(ExportCancelled):
                    export_cube(
                        self.scalar(),
                        confirm_loss=True,
                        destination=destination,
                        is_cancelled=cancel_before_first_write,
                    )

            self.assertEqual(numeric_rows, 0)
            self.assertFalse(destination.exists())

    def test_near_degenerate_affine_grid_round_trips_without_becoming_singular(self):
        batch = self.scalar()
        grid = replace(
            self.grid(batch),
            step_vectors=(
                (1.0, 1.0, 0.0),
                (1.0, 1.0 + 1.0e-13, 0.0),
                (0.0, 0.0, 1.0),
            ),
        )
        candidate = replace(
            batch,
            datasets=(grid, self.charge(batch)),
        )

        with TemporaryDirectory() as directory:
            destination = Path(directory) / "near-degenerate.cube"
            export_cube(candidate, confirm_loss=True, destination=destination)
            restored = CUBE_READER.parse(destination)

        self.assertNotEqual(
            float(numpy.linalg.det(numpy.asarray(self.grid(restored).step_vectors))),
            0.0,
        )

    def test_source_calculation_is_reported_as_omitted_provenance(self):
        batch = self.scalar()
        grid = replace(
            self.grid(batch),
            source_calculation=uuid4(),
            provenance_ids=(),
        )
        charge = replace(self.charge(batch), provenance_ids=())
        candidate = replace(
            batch,
            datasets=(grid, charge),
            provenance=(),
        )

        preview = preview_cube_export(candidate)

        self.assertIn(
            "provenance_omitted",
            tuple(entry.code for entry in preview.entries),
        )

    def test_loss_preview_is_sorted_complete_and_blocks_publication(self):
        batch = self.scalar()
        structure = batch.structures[0]
        atom_count = len(structure.atomic_numbers)
        missing = CategoricalData(
            ArrayData(numpy.full(atom_count, -1, dtype=numpy.int64), ("atom",), "dimensionless"),
            (),
            -1,
        )
        identity = AtomicIdentityData(
            ArrayData(numpy.zeros(atom_count, dtype=numpy.int64), ("atom",), "dimensionless"),
            ArrayData(numpy.zeros(atom_count, dtype=numpy.int64), ("atom",), "dimensionless"),
            ArrayData(numpy.zeros(atom_count, dtype=numpy.int64), ("atom",), "dimensionless"),
            missing,
            missing,
        )
        topology = MolecularTopology(
            ArrayData(numpy.empty((0, 2), dtype=numpy.int64), ("bond", "endpoint"), "dimensionless"),
            ArrayData(numpy.empty(0, dtype=float), ("bond",), "dimensionless"),
        )
        structure = replace(
            structure,
            cell=ArrayData(numpy.eye(3), ("cell_vector", "xyz"), "bohr"),
            molecular_charge=0,
            molecular_multiplicity=1,
            topology=topology,
            atomic_identity=identity,
        )
        enriched = replace(batch, structures=(structure,))

        report = preview_cube_export(enriched)
        codes = tuple(entry.code for entry in report.entries)

        self.assertEqual(codes, tuple(sorted(codes)))
        self.assertEqual(
            codes,
            (
                "atomic_identity_omitted",
                "cell_periodicity_omitted",
                "comments_normalized",
                "grid_semantic_role_omitted",
                "grid_value_unit_omitted",
                "molecular_charge_omitted",
                "molecular_multiplicity_omitted",
                "project_identity_omitted",
                "provenance_omitted",
                "topology_omitted",
            ),
        )
        self.assertTrue(report.requires_confirmation)
        self.assertFalse(report.written)
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "blocked.cube"
            self.assertEqual(export_cube(enriched, destination=destination).text, "")
            self.assertFalse(destination.exists())

    def _lazy_batch(self, batch, directory, *, prefix="lazy"):
        structure = batch.structures[0]
        grid = self.grid(batch)
        charge = self.charge(batch)
        lazies = []

        def lazy(values, name):
            array = numpy.asarray(values)
            path = Path(directory) / f"{prefix}-{name}.npy"
            numpy.save(path, array)
            value = LazyNpyArray(
                path,
                array.shape,
                array.dtype,
                _array_content_hash(array)[0],
            )
            lazies.append(value)
            return value

        structure = replace(
            structure,
            coordinates=replace(
                structure.coordinates,
                values=lazy(structure.coordinates.values, "coordinates"),
            ),
        )
        grid = replace(grid, data=replace(grid.data, values=lazy(grid.data.values, "grid")))
        charge = replace(
            charge,
            data=replace(charge.data, values=lazy(charge.data.values, "charge")),
        )
        return replace(batch, structures=(structure,), datasets=(grid, charge)), tuple(lazies)

    def test_lazy_snapshot_ownership_and_mutation_gate(self):
        source = self.scalar()
        with TemporaryDirectory() as directory:
            for name, operation, error in (
                ("preview", lambda batch: preview_cube_export(batch), None),
                ("success", lambda batch: export_cube(batch, confirm_loss=True), None),
                (
                    "validation",
                    lambda batch: preview_cube_export(replace(batch, structures=())),
                    ValueError,
                ),
                (
                    "cancel",
                    lambda batch: export_cube(
                        batch,
                        confirm_loss=True,
                        is_cancelled=iter((False, True)).__next__,
                    ),
                    ExportCancelled,
                ),
            ):
                with self.subTest(name=name):
                    batch, lazies = self._lazy_batch(source, directory, prefix=name)
                    if error is None:
                        operation(batch)
                    else:
                        with self.assertRaises(error):
                            operation(batch)
                    self.assertTrue(all(not value.loaded for value in lazies))

            batch, lazies = self._lazy_batch(source, directory, prefix="preloaded")
            for value in lazies:
                numpy.asarray(value)
            preview_cube_export(batch)
            self.assertTrue(all(value.loaded for value in lazies))
            for value in lazies:
                value.close()

            batch, lazies = self._lazy_batch(source, directory, prefix="mutation")
            live_grid = lazies[1]
            destination = Path(directory) / "stable.cube"
            destination.write_bytes(b"previous")
            calls = 0

            def mutate():
                nonlocal calls
                calls += 1
                if calls == 2:
                    array = numpy.load(live_grid.path)
                    array.flat[0] += 1.0
                    numpy.save(live_grid.path, array)
                    live_grid.content_hash = _array_content_hash(array)[0]
                return False

            with self.assertRaisesRegex(ValueError, "inputs changed after snapshot"):
                export_cube(
                    batch,
                    confirm_loss=True,
                    destination=destination,
                    is_cancelled=mutate,
                )
            self.assertEqual(destination.read_bytes(), b"previous")
            self.assertTrue(all(not value.loaded for value in lazies))

    def test_atomic_failures_cancellation_and_fatal_errors_preserve_destination(self):
        batch = self.scalar()
        fatal_errors = (KeyboardInterrupt, SystemExit, GeneratorExit, MemoryError)
        for error_type in fatal_errors:
            with self.subTest(error=error_type.__name__):
                with self.assertRaises(error_type):
                    export_cube(
                        batch,
                        confirm_loss=True,
                        is_cancelled=lambda error_type=error_type: (_ for _ in ()).throw(error_type()),
                    )

        with TemporaryDirectory() as directory:
            destination = Path(directory) / "existing.cube"
            destination.write_bytes(b"previous")
            calls = 0

            def cancel_midway():
                nonlocal calls
                calls += 1
                return calls == 4

            with self.assertRaises(ExportCancelled):
                export_cube(
                    batch,
                    confirm_loss=True,
                    destination=destination,
                    is_cancelled=cancel_midway,
                )
            self.assertEqual(destination.read_bytes(), b"previous")
            self.assertEqual(tuple(Path(directory).glob(".*.tmp")), ())

            with patch("ChemBlender.core.exporters.xyz.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaisesRegex(OSError, "replace failed"):
                    export_cube(batch, confirm_loss=True, destination=destination)
            self.assertEqual(destination.read_bytes(), b"previous")
            self.assertEqual(tuple(Path(directory).glob(".*.tmp")), ())

            with (
                patch("pathlib.Path.open", side_effect=OSError("writer failed")),
                patch("pathlib.Path.unlink", side_effect=OSError("cleanup failed")),
            ):
                with self.assertRaisesRegex(OSError, "writer failed") as caught:
                    export_cube(batch, confirm_loss=True, destination=destination)
            self.assertTrue(any("cleanup failed" in note for note in caught.exception.__notes__))
            self.assertEqual(destination.read_bytes(), b"previous")

    def test_lazy_close_failure_preserves_primary_error(self):
        batch = self.scalar()
        coordinates = numpy.asarray(batch.structures[0].coordinates.values)

        class CloseFailure:
            shape = coordinates.shape
            dtype = coordinates.dtype
            loaded = False

            def __array__(self, dtype=None, copy=None):
                raise ValueError("snapshot failed")

            def close(self):
                raise OSError("close failed")

        structure = replace(
            batch.structures[0],
            coordinates=replace(batch.structures[0].coordinates, values=CloseFailure()),
        )
        broken = replace(batch, structures=(structure,))
        with self.assertRaisesRegex(ValueError, "snapshot failed") as caught:
            preview_cube_export(broken)
        self.assertTrue(any("close failed" in note for note in caught.exception.__notes__))

        class CloseOnlyFailure(CloseFailure):
            def __array__(self, dtype=None, copy=None):
                return numpy.array(coordinates, dtype=dtype, copy=True)

        structure = replace(
            batch.structures[0],
            coordinates=replace(batch.structures[0].coordinates, values=CloseOnlyFailure()),
        )
        with self.assertRaisesRegex(OSError, "close failed"):
            preview_cube_export(replace(batch, structures=(structure,)))

    def test_native_parse_cube_reimport_preserves_selected_science(self):
        source = self.multi()
        source_grid = self.grid(source)
        source_charge = self.charge(source)
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "round-trip.cube"
            export_cube(
                source,
                dataset_index=1,
                confirm_loss=True,
                destination=destination,
            )
            restored = CUBE_READER.parse(destination)

        restored_grid = self.grid(restored)
        restored_charge = self.charge(restored)
        self.assertEqual(source.structures[0].atomic_numbers, restored.structures[0].atomic_numbers)
        numpy.testing.assert_allclose(
            source.structures[0].coordinates.values,
            restored.structures[0].coordinates.values,
            rtol=0.0,
            atol=5.0e-12,
        )
        numpy.testing.assert_allclose(source_charge.data.values, restored_charge.data.values)
        numpy.testing.assert_allclose(source_grid.origin, restored_grid.origin, atol=5.0e-12)
        numpy.testing.assert_allclose(source_grid.step_vectors, restored_grid.step_vectors, atol=5.0e-12)
        self.assertEqual(source_grid.grid_shape, restored_grid.grid_shape)
        numpy.testing.assert_allclose(
            numpy.asarray(source_grid.data.values)[1],
            restored_grid.data.values,
        )
        parameters = dict(restored.provenance[0].parameters)
        self.assertEqual(parameters["dataset_ids"], (7,))


if __name__ == "__main__":
    unittest.main()
