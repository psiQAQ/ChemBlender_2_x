import importlib
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from ChemBlender.core import QCProject, create_session, close_session, parse_cif
from ChemBlender.core.import_pipeline.conformer_grouping import (
    suggest_staged_conformer_groups,
)
from ChemBlender.core.import_pipeline.request import (
    ImportRequest,
    ImportSource,
    ValidationMode,
)
from ChemBlender.reader_api.import_pipeline_bridge import (
    preflight_reader_plugins,
)
from ChemBlender.reader_api.registry import builtin_reader_plugin_registry
from ChemBlender.ui.project_browser.model import BrowserMode, build_browser_rows


ROOT = Path(__file__).resolve().parents[1]
MULTI = ROOT / "tests" / "fixtures" / "cif" / "multi-block.cif"
MIXED = ROOT / "tests" / "fixtures" / "cif" / "mixed-site-data.cif"
HAS_GEMMI = importlib.util.find_spec("gemmi") is not None
if HAS_GEMMI:
    import gemmi  # noqa: F401  # keep native types loaded across module patches


class _Property:
    def __init__(self, kind, **keywords):
        self.kind = kind
        self.keywords = keywords


def _property(kind):
    return lambda **keywords: _Property(kind, **keywords)


class _Operator:
    def report(self, levels, message):
        self.last_report = (levels, message)


class _PropertyGroup:
    pass


@unittest.skipUnless(HAS_GEMMI, "Gemmi dependency unavailable")
class CIFProductFlowTests(unittest.TestCase):
    def setUp(self):
        self.fake_bpy = ModuleType("bpy")
        props = ModuleType("bpy.props")
        for name, kind in (
            ("BoolProperty", "bool"),
            ("CollectionProperty", "collection"),
            ("EnumProperty", "enum"),
            ("FloatProperty", "float"),
            ("IntProperty", "int"),
            ("PointerProperty", "pointer"),
            ("StringProperty", "string"),
        ):
            setattr(props, name, _property(kind))
        self.fake_bpy.props = props
        self.fake_bpy.types = SimpleNamespace(
            Operator=_Operator,
            PropertyGroup=_PropertyGroup,
        )
        self.fake_bpy.app = SimpleNamespace(background=True)
        self.fake_bpy.data = SimpleNamespace(
            objects=SimpleNamespace(remove=lambda *_args, **_kwargs: None),
            batch_remove=lambda **_kwargs: None,
        )
        self.fake_bpy.context = SimpleNamespace(collection=object())
        self.modules = patch.dict(
            sys.modules,
            {"bpy": self.fake_bpy, "bpy.props": props},
        )
        self.modules.start()
        for name in (
            "ChemBlender.ui.export",
            "ChemBlender.ui.import_preview",
            "ChemBlender.ui.properties",
        ):
            sys.modules.pop(name, None)
        self.properties = importlib.import_module("ChemBlender.ui.properties")
        self.preview_module = importlib.import_module(
            "ChemBlender.ui.import_preview"
        )
        self.export_module = importlib.import_module("ChemBlender.ui.export")
        self.temporary = tempfile.TemporaryDirectory()
        self.session = create_session(temp_parent=Path(self.temporary.name))

    def tearDown(self):
        try:
            self.properties.clear_quick_import_state(self.session)
        except BaseException:
            pass
        try:
            close_session(self.session)
        except BaseException:
            pass
        self.modules.stop()
        for name in (
            "ChemBlender.ui.export",
            "ChemBlender.ui.import_preview",
            "ChemBlender.ui.properties",
        ):
            sys.modules.pop(name, None)
        self.temporary.cleanup()

    def stage(self, source):
        staging = self.properties.create_quick_import_staging(self.session)
        request = ImportRequest(
            sources=(ImportSource(source),),
            validation_mode=ValidationMode.BALANCED,
        )
        registry = builtin_reader_plugin_registry()
        preview = preflight_reader_plugins(
            request,
            registry,
            staging,
            progress=lambda *_args: None,
            is_cancelled=lambda: False,
        )
        self.properties.store_quick_import_preview(
            self.session,
            staging,
            preview,
            conformer_grouping_suggestions=suggest_staged_conformer_groups(
                preview,
                staging,
            ),
        )
        return registry, self.properties.get_quick_import_state(self.session)

    def test_preview_summarizes_cif_and_requires_multi_block_confirmation(self):
        registry, state = self.stage(MULTI)
        rows = self.preview_module.project_import_preview(
            self.session,
            state,
            registry,
        )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row.cif_block_count, row.cif_valid_block_count), (2, 2))
        self.assertIn("first", row.cif_block_summary)
        self.assertIn("4 sites", row.cif_site_summary)
        self.assertIn("4.12", row.cif_cell_summary)
        self.assertFalse(row.cif_default_block_confirmed)
        with self.assertRaisesRegex(ValueError, "CIF default block"):
            self.preview_module.import_commit_decisions(state, rows)

        row.cif_default_block_confirmed = True
        self.preview_module.import_commit_decisions(state, rows)

    def test_browser_exposes_site_occupancy_disorder_and_adp_summaries(self):
        batch = parse_cif(MIXED)
        project = QCProject(uuid4(), "0.2")
        project.commit(batch)

        rows = build_browser_rows(
            project,
            mode=BrowserMode.BY_DATA,
            session_id=uuid4(),
            browser_revision=1,
        )
        labels = tuple(row.label for row in rows)

        self.assertTrue(any("Sites: 2" in label for label in labels))
        self.assertTrue(any("Occupancy:" in label for label in labels))
        self.assertTrue(any("Disorder:" in label for label in labels))
        self.assertTrue(any("ADP:" in label for label in labels))

    def test_background_cif_export_uses_bound_envelope(self):
        batch = parse_cif(MIXED)
        project = QCProject(uuid4(), "0.2")
        project.commit(batch)
        structure = batch.structures[0]
        selection = self.export_module.resolve_export_selection(
            project,
            structure.id,
        )
        self.assertIs(selection.cif_envelope, batch.cif_envelopes[0])
        preview = self.export_module.preview_export_selection(selection, "cif")
        self.assertEqual(preview.format, "cif")
        self.assertTrue(
            any(entry.code == "preserve:unknown_content" for entry in preview.entries)
        )

        destination = Path(self.temporary.name) / "exported.cif"
        job = self.export_module.ExportJob(
            destination,
            selection,
            format_name="cif",
            confirm_loss=False,
            missing_value_token=None,
        )
        job._run()

        self.assertIsNone(job.error)
        self.assertTrue(job.result.written)
        self.assertEqual(
            parse_cif(destination).structures[0].periodic.site_labels,
            structure.periodic.site_labels,
        )


if __name__ == "__main__":
    unittest.main()
