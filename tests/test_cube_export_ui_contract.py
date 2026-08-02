import importlib
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
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
TWO_DATASETS = (
    Path(__file__).with_name("fixtures") / "cube" / "two-datasets.cube"
)


class _Property:
    def __init__(self, kind, **keywords):
        self.kind = kind
        self.keywords = keywords


def _property(kind):
    return lambda **keywords: _Property(kind, **keywords)


class _Operator:
    def report(self, levels, message):
        self.last_report = (levels, message)


class _WindowManager:
    def __init__(self):
        self.selected = None

    def fileselect_add(self, operator):
        self.selected = operator


class _Layout:
    def __init__(self):
        self.properties = []

    def prop(self, _owner, name):
        self.properties.append(name)

    def label(self, **_keywords):
        pass


class CubeExportUIContractTests(unittest.TestCase):
    def setUp(self):
        fake_bpy = ModuleType("bpy")
        props = ModuleType("bpy.props")
        for name, kind in (
            ("BoolProperty", "bool"),
            ("EnumProperty", "enum"),
            ("FloatProperty", "float"),
            ("IntProperty", "int"),
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

    def test_cube_format_filter_and_selected_grid_default(self):
        module = self.export
        operator_type = module.CHEMBLENDER_OT_export_project_entity
        self.assertIn("cube", {item[0] for item in module._FORMAT_ITEMS})
        self.assertIn(
            "*.cube",
            operator_type.__annotations__["filter_glob"].keywords["default"],
        )

        batch = CUBE_READER.parse(SHEARED)
        project = self._project(batch)
        operator = operator_type()
        operator.format_name = "extxyz"
        operator.missing_value_token = ""
        context = SimpleNamespace(scene=object())
        session = SimpleNamespace(project=project, active_entity_id=self._grid(batch).id)
        with (
            patch.object(module, "get_scene_session", return_value=session),
            patch.object(
                module,
                "preview_export_selection",
                return_value=SimpleNamespace(entries=()),
            ),
        ):
            operator._selection_and_preview(context, default_format=True)

        self.assertEqual(operator.format_name, "cube")

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
            "ChemBlender.core.exporters.cube.export_cube",
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

    def test_unset_multi_dataset_invoke_opens_dialog_but_execute_fails_closed(self):
        batch = CUBE_READER.parse(TWO_DATASETS)
        project = self._project(batch)
        module = self.export
        update = (
            module.CHEMBLENDER_OT_export_project_entity
            .__annotations__["format_name"]
            .keywords["update"]
        )

        class _UpdatingExportOperator(
            module.CHEMBLENDER_OT_export_project_entity
        ):
            def __setattr__(self, name, value):
                object.__setattr__(self, name, value)
                if name == "format_name" and getattr(
                    self,
                    "_updates_enabled",
                    False,
                ):
                    update(self, self._update_context)

        operator = _UpdatingExportOperator()
        operator._updates_enabled = False
        operator.format_name = "extxyz"
        operator.missing_value_token = ""
        operator.cube_dataset_index = -1
        operator.confirm_loss = False
        manager = _WindowManager()
        context = SimpleNamespace(scene=object(), window_manager=manager)
        operator._update_context = context
        operator._updates_enabled = True
        session = SimpleNamespace(project=project, active_entity_id=self._grid(batch).id)

        with (
            patch.object(module, "get_scene_session", return_value=session),
            patch.object(module, "preview_cube_export", create=True) as preview,
        ):
            result = operator.invoke(context, None)

        self.assertEqual(result, {"RUNNING_MODAL"})
        self.assertIs(manager.selected, operator)
        self.assertEqual(operator.format_name, "cube")
        self.assertEqual(operator.loss_preview, "Select Dataset Index")
        preview.assert_not_called()

        with TemporaryDirectory() as directory:
            destination = Path(directory) / "selected.cube"
            operator.filepath = str(destination)
            with patch.object(module, "get_scene_session", return_value=session):
                result = operator.execute(context)
            self.assertEqual(result, {"CANCELLED"})
            self.assertFalse(destination.exists())

    def test_dataset_index_control_is_shown_only_for_multi_dataset_cube(self):
        operator = self.export.CHEMBLENDER_OT_export_project_entity()
        operator.format_name = "cube"
        operator.loss_preview = "No data loss"
        operator.confirm_loss = False
        operator._preview_report = None

        operator._cube_requires_dataset_index = True
        operator.layout = _Layout()
        operator.draw(None)
        self.assertIn("cube_dataset_index", operator.layout.properties)

        operator._cube_requires_dataset_index = False
        operator.layout = _Layout()
        operator.draw(None)
        self.assertNotIn("cube_dataset_index", operator.layout.properties)
