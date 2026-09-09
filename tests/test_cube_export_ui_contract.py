import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

import numpy

from cbq_core.model import ArrayData
from cbq_core.model import AtomicProperty
from cbq_core.model import Grid3D
from cbq_core.model import ImportBatch
from cbq_core.model import QCProject
from cbq_core.model import QualityStatus
from cbq_core.model import TopologyRecord
from cbq_core.model import TopologySource
from chemblender_prepare.core.exporters.cube import preview_cube_export
from chemblender_prepare.core.cube import CUBE_READER
from chemblender_prepare.core.exporters import ExportCancelled


SHEARED = Path(__file__).with_name("fixtures") / "cube" / "sheared.cube"
TWO_DATASETS = (
    Path(__file__).with_name("fixtures") / "cube" / "two-datasets.cube"
)


class CubeExternalExportContractTests(unittest.TestCase):
    def setUp(self):
        from chemblender_prepare import export_service
        self.export = export_service

    @staticmethod
    def _project(batch):
        project = QCProject(uuid4(), "1.0")
        project.commit(batch)
        return project

    @staticmethod
    def _grid(batch):
        return next(value for value in batch.datasets if isinstance(value, Grid3D))

    @staticmethod
    def _charge(batch):
        return next(
            value for value in batch.datasets if isinstance(value, AtomicProperty)
        )

    def _select_grid(self, project, grid):
        try:
            return self.export.resolve_export_selection(project, grid.id)
        except ValueError as error:
            self.fail(f"Grid3D should be exportable: {error}")

    def _preview_cube(self, selection, *, dataset_index=None):
        try:
            return self.export.preview_export_selection(
                selection,
                "cube",
                dataset_index=dataset_index,
            )
        except (TypeError, ValueError) as error:
            self.fail(f"Cube preview should be available: {error}")

    @staticmethod
    def _topology(structure, provenance_id):
        return TopologyRecord(
            id=uuid4(),
            revision="cube-ui-topology",
            structure_id=structure.id,
            bond_indices=ArrayData(
                numpy.empty((0, 2), dtype=numpy.int64),
                ("bond", "endpoint"),
                "dimensionless",
            ),
            bond_orders=ArrayData(
                numpy.empty((0,), dtype=float),
                ("bond",),
                "dimensionless",
            ),
            aromatic_flags=None,
            stereo_labels=(),
            source_kind=TopologySource.EXPLICIT_FILE,
            quality_status=QualityStatus.COMPLETE,
            inference_parameters=(),
            provenance_ids=(provenance_id,),
        )

    def test_selected_grid_projects_exact_cube_context(self):
        batch = CUBE_READER.parse(SHEARED)
        project = self._project(batch)
        structure = batch.structures[0]
        grid = self._grid(batch)
        charge = self._charge(batch)
        provenance = batch.provenance[0]
        topology = self._topology(structure, provenance.id)
        sibling_grid = replace(grid, id=uuid4(), revision="sibling-grid")
        project.commit(
            ImportBatch(
                topologies=(topology,),
                datasets=(sibling_grid,),
            )
        )
        unrelated = CUBE_READER.parse(SHEARED)
        project.commit(unrelated)

        selection = self._select_grid(project, grid)
        entities = self.export._cube_entities(selection)

        self.assertIs(selection.structure, structure)
        self.assertIs(selection.grid, grid)
        self.assertEqual(selection.properties, (charge,))
        self.assertEqual(entities.structures, (structure,))
        self.assertEqual(entities.datasets, (grid, charge))
        self.assertEqual(entities.provenance, (provenance,))
        self.assertEqual(entities.topologies, (topology,))
        self.assertNotIn(sibling_grid, entities.datasets)
        self.assertNotIn(self._grid(unrelated), entities.datasets)

    def test_grid_selection_rejects_missing_or_cross_linked_structure(self):
        batch = CUBE_READER.parse(SHEARED)
        structure = batch.structures[0]
        grid = self._grid(batch)

        missing = self._project(batch)
        del missing.structures[structure.id]
        with self.assertRaises(ValueError):
            self.export.resolve_export_selection(missing, grid.id)

        cross_linked = self._project(batch)
        cross_linked.structures[structure.id] = replace(structure, id=uuid4())
        with self.assertRaises(ValueError):
            self.export.resolve_export_selection(cross_linked, grid.id)

        non_grid = self._project(batch)
        with self.assertRaises(ValueError):
            self.export.resolve_export_selection(non_grid, self._charge(batch).id)

    def test_invalid_selection_reports_supported_scientific_entities(self):
        project = self._project(CUBE_READER.parse(SHEARED))
        with self.assertRaisesRegex(TypeError, "Structure, FrameSet or Grid3D"):
            self.export.resolve_export_selection(project, "not-a-uuid")
        with self.assertRaisesRegex(ValueError, "Structure, FrameSet or Grid3D"):
            self.export.resolve_export_selection(project, uuid4())

    def test_projection_preserves_missing_and_ambiguous_charge_for_core_preview(self):
        missing_batch = CUBE_READER.parse(SHEARED)
        missing_project = self._project(missing_batch)
        missing_grid = self._grid(missing_batch)
        del missing_project.datasets[self._charge(missing_batch).id]

        missing_selection = self._select_grid(missing_project, missing_grid)
        missing_entities = self.export._cube_entities(missing_selection)
        self.assertEqual(missing_entities.datasets, (missing_grid,))
        with self.assertRaisesRegex(ValueError, "dataset.nuclear_charge.missing"):
            preview_cube_export(missing_entities)

        ambiguous_batch = CUBE_READER.parse(SHEARED)
        ambiguous_project = self._project(ambiguous_batch)
        ambiguous_grid = self._grid(ambiguous_batch)
        charge = self._charge(ambiguous_batch)
        second_charge = replace(charge, id=uuid4(), revision="second-charge")
        ambiguous_project.commit(ImportBatch(datasets=(second_charge,)))

        ambiguous_selection = self._select_grid(
            ambiguous_project,
            ambiguous_grid,
        )
        ambiguous_entities = self.export._cube_entities(ambiguous_selection)
        self.assertEqual(
            tuple(
                value
                for value in ambiguous_entities.datasets
                if isinstance(value, AtomicProperty)
            ),
            (charge, second_charge),
        )
        with self.assertRaisesRegex(
            ValueError,
            "dataset.nuclear_charge.ambiguous",
        ):
            preview_cube_export(ambiguous_entities)

    def test_cli_accepts_cube_without_silently_selecting_a_dataset(self):
        from chemblender_prepare.cli import build_parser
        args = build_parser().parse_args([
            "export", "project.cbq", "--entity", str(uuid4()),
            "--format", "cube", "--output", "selected.cube",
        ])
        self.assertEqual(args.format, "cube")
        self.assertIsNone(args.dataset_index)

    def test_cube_preview_is_read_only_and_requires_explicit_multi_dataset_index(self):
        scalar_batch = CUBE_READER.parse(SHEARED)
        scalar_selection = self._select_grid(
            self._project(scalar_batch),
            self._grid(scalar_batch),
        )
        expected_scalar = preview_cube_export(
            self.export._cube_entities(scalar_selection),
            dataset_index=None,
        )
        with patch(
            "chemblender_prepare.core.exporters.cube.export_cube",
        ) as writer:
            self.assertEqual(self._preview_cube(scalar_selection), expected_scalar)
        writer.assert_not_called()

        multi_batch = CUBE_READER.parse(TWO_DATASETS)
        multi_selection = self._select_grid(
            self._project(multi_batch),
            self._grid(multi_batch),
        )
        with self.assertRaisesRegex(ValueError, "dataset_index.missing"):
            self.export.preview_export_selection(
                multi_selection,
                "cube",
                dataset_index=None,
            )
        expected_multi = preview_cube_export(
            self.export._cube_entities(multi_selection),
            dataset_index=1,
        )
        self.assertEqual(
            self._preview_cube(multi_selection, dataset_index=1),
            expected_multi,
        )

    def test_unset_multi_dataset_export_fails_without_creating_a_file(self):
        batch = CUBE_READER.parse(TWO_DATASETS)
        selection = self._select_grid(self._project(batch), self._grid(batch))
        with TemporaryDirectory() as directory:
            destination = Path(directory) / "selected.cube"
            with self.assertRaisesRegex(ValueError, "dataset_index.missing"):
                self.export.export_selection(destination, selection, format_name="cube", confirm_loss=True)
            self.assertFalse(destination.exists())
            self.assertEqual(tuple(Path(directory).iterdir()), ())

    def test_gui_forwards_only_an_explicit_dataset_selection(self):
        from chemblender_prepare.gui import command_arguments
        values = {"command": "export", "sources": "project.cbq", "output": "selected.cube",
                  "format": "cube", "entity": str(uuid4()), "dataset_index": ""}
        self.assertNotIn("--dataset-index", command_arguments(values))
        values["dataset_index"] = "1"
        argv = command_arguments(values)
        self.assertEqual(argv[argv.index("--dataset-index") + 1], "1")

    def test_cube_export_preserves_unconfirmed_destination(self):
        batch = CUBE_READER.parse(SHEARED)
        selection = self._select_grid(self._project(batch), self._grid(batch))
        self.assertTrue(self._preview_cube(selection).requires_confirmation)

        with TemporaryDirectory() as directory:
            destination = Path(directory) / "selected.cube"
            destination.write_bytes(b"prior destination\n")
            report = self.export.export_selection(
                destination,
                selection,
                format_name="cube",
                confirm_loss=False,
                missing_value_token=None,
                dataset_index=None,
            )
            self.assertFalse(report.written)
            self.assertEqual(destination.read_bytes(), b"prior destination\n")

    def test_cube_export_writes_scalar_and_selected_multi_dataset(self):
        cases = (
            (CUBE_READER.parse(SHEARED), None),
            (CUBE_READER.parse(TWO_DATASETS), 1),
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for batch, dataset_index in cases:
                with self.subTest(dataset_index=dataset_index):
                    grid = self._grid(batch)
                    selection = self._select_grid(self._project(batch), grid)
                    destination = root / f"selected-{dataset_index}.cube"
                    report = self.export.export_selection(
                        destination,
                        selection,
                        format_name="cube",
                        confirm_loss=True,
                        missing_value_token=None,
                        dataset_index=dataset_index,
                    )
                    self.assertTrue(report.written)
                    reparsed = CUBE_READER.parse(destination)
                    reparsed_grid = self._grid(reparsed)
                    expected = numpy.asarray(grid.data.values)
                    if dataset_index is not None:
                        expected = expected[dataset_index]
                    numpy.testing.assert_allclose(reparsed_grid.data.values, expected)
                    self.assertEqual(
                        reparsed.structures[0].atomic_numbers,
                        selection.structure.atomic_numbers,
                    )

    def test_cancelled_cube_export_preserves_destination_and_cleans_temporary(self):
        batch = CUBE_READER.parse(SHEARED)
        selection = self._select_grid(self._project(batch), self._grid(batch))
        with TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "selected.cube"
            destination.write_bytes(b"prior destination\n")
            with self.assertRaises(ExportCancelled):
                self.export.export_selection(destination, selection, format_name="cube",
                                             confirm_loss=True, is_cancelled=lambda: True)
            self.assertEqual(destination.read_bytes(), b"prior destination\n")
            self.assertEqual(tuple(root.iterdir()), (destination,))
