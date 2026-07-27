import importlib
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from ChemBlender.core.exporters import ExportCancelled
from tests.test_project_browser_model import (
    FORCE_ID,
    FRAME_SET_ID,
    STRUCTURE_ID,
    sample_trajectory_project,
)


MODULE = "ChemBlender.ui.export"


class _Property:
    def __init__(self, kind, **keywords):
        self.kind = kind
        self.keywords = keywords


def _property(kind):
    return lambda **keywords: _Property(kind, **keywords)


class _Operator:
    def report(self, levels, message):
        self.last_report = (levels, message)


class ExtXYZWorkflowTests(unittest.TestCase):
    def setUp(self):
        fake_bpy = ModuleType("bpy")
        fake_props = ModuleType("bpy.props")
        for name, kind in (
            ("BoolProperty", "bool"),
            ("EnumProperty", "enum"),
            ("StringProperty", "string"),
        ):
            setattr(fake_props, name, _property(kind))
        fake_bpy.props = fake_props
        fake_bpy.types = SimpleNamespace(Operator=_Operator)
        fake_bpy.app = SimpleNamespace(background=True)
        self.modules = patch.dict(
            sys.modules,
            {"bpy": fake_bpy, "bpy.props": fake_props},
        )
        self.modules.start()
        sys.modules.pop(MODULE, None)

    def tearDown(self):
        sys.modules.pop(MODULE, None)
        self.modules.stop()

    def test_frame_set_selection_resolves_structure_and_related_properties(self):
        module = importlib.import_module(MODULE)

        selection = module.resolve_export_selection(
            sample_trajectory_project(),
            FRAME_SET_ID,
        )

        self.assertEqual(selection.structure.id, STRUCTURE_ID)
        self.assertEqual(selection.frame_set.id, FRAME_SET_ID)
        self.assertEqual(
            tuple(item.id for item in selection.properties),
            (FORCE_ID,),
        )
        report = module.preview_export_selection(selection, "extxyz")
        self.assertFalse(report.written)
        self.assertFalse(report.requires_confirmation)

    def test_cancelled_background_export_leaves_no_destination_or_temporary(self):
        module = importlib.import_module(MODULE)
        selection = module.resolve_export_selection(
            sample_trajectory_project(),
            FRAME_SET_ID,
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "trajectory.extxyz"
            job = module.ExportJob(
                destination,
                selection,
                format_name="extxyz",
                confirm_loss=False,
                missing_value_token=None,
            )

            job.cancel()
            job.start()
            self.assertTrue(job.join(5))

            self.assertTrue(job.done)
            self.assertIsInstance(job.error, ExportCancelled)
            self.assertFalse(destination.exists())
            self.assertEqual(tuple(root.iterdir()), ())

    def test_export_operator_rna_is_small_and_module_is_explicit_root(self):
        module = importlib.import_module(MODULE)
        registration = importlib.import_module(
            "ChemBlender.runtime.registration"
        )

        self.assertIn(".ui.export", registration.REGISTER_MODULE_NAMES)
        operator = module.CHEMBLENDER_OT_export_project_entity
        self.assertEqual(operator.__module__, MODULE)
        self.assertTrue(
            all(
                value.kind in {"bool", "enum", "string"}
                for value in operator.__annotations__.values()
            )
        )


if __name__ == "__main__":
    unittest.main()
