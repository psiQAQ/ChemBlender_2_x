import importlib
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import numpy

from ChemBlender.core import (
    ArrayData,
    AtomicProperty,
    Grid3D,
    ImportBatch,
    QCProject,
    QualityStatus,
    TopologyRecord,
    TopologySource,
    preview_cube_export,
)
from ChemBlender.core.cube import CUBE_READER


MODULE = "ChemBlender.ui.export"
SHEARED = Path(__file__).with_name("fixtures") / "cube" / "sheared.cube"


class _Property:
    def __init__(self, kind, **keywords):
        self.kind = kind
        self.keywords = keywords


def _property(kind):
    return lambda **keywords: _Property(kind, **keywords)


class _Operator:
    def report(self, levels, message):
        self.last_report = (levels, message)


class CubeExportUIContractTests(unittest.TestCase):
    def setUp(self):
        fake_bpy = ModuleType("bpy")
        props = ModuleType("bpy.props")
        for name, kind in (
            ("BoolProperty", "bool"),
            ("EnumProperty", "enum"),
            ("FloatProperty", "float"),
            ("StringProperty", "string"),
        ):
            setattr(props, name, _property(kind))
        fake_bpy.props = props
        fake_bpy.types = SimpleNamespace(Operator=_Operator)
        fake_bpy.app = SimpleNamespace(background=True)
        self.modules = patch.dict(
            sys.modules,
            {"bpy": fake_bpy, "bpy.props": props},
        )
        self.modules.start()
        sys.modules.pop(MODULE, None)
        self.export = importlib.import_module(MODULE)

    def tearDown(self):
        sys.modules.pop(MODULE, None)
        self.modules.stop()

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
