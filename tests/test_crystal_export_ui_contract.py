import importlib
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from ChemBlender.core import DatasetStatus, QCProject, parse_cif, parse_poscar
from ChemBlender.core.exporters import PoscarExportSettings


ROOT = Path(__file__).resolve().parents[1]
CIF_SOURCE = ROOT / "tests" / "fixtures" / "cif" / "mixed-site-data.cif"
POSCAR_SOURCE = (
    ROOT / "tests" / "fixtures" / "poscar" / "cscl-selective.vasp"
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


class CrystalExportUIContractTests(unittest.TestCase):
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
        project = QCProject(uuid4(), "0.2")
        project.commit(batch)
        return project

    def test_cif_mode_is_explicit_and_preview_lists_complete_plan(self):
        batch = parse_cif(CIF_SOURCE)
        project = self._project(batch)
        selection = self.export.resolve_export_selection(
            project,
            batch.structures[0].id,
        )
        destination = Path("normalized.cif")

        preserve = self.export.preview_export_selection(
            selection,
            "cif",
            cif_mode="preserve",
            destination=destination,
        )
        normalized = self.export.preview_export_selection(
            selection,
            "cif",
            cif_mode="normalized",
            destination=destination,
        )

        self.assertIn("target:cif_preserve", {entry.code for entry in preserve.entries})
        self.assertIn(
            "preserve:unknown_content",
            {entry.code for entry in preserve.entries},
        )
        self.assertFalse(preserve.requires_confirmation)
        self.assertTrue(
            any(
                entry.message.startswith("Preserved:")
                for entry in preserve.entries
            )
        )
        self.assertIn(
            "target:cif_normalized",
            {entry.code for entry in normalized.entries},
        )
        self.assertIn(
            "omit:unknown_content",
            {entry.code for entry in normalized.entries},
        )
        self.assertIn("structure:source", {entry.code for entry in normalized.entries})
        self.assertIn("output_path", {entry.code for entry in normalized.entries})
        self.assertTrue(normalized.requires_confirmation)
        self.assertTrue(
            any(
                entry.message.startswith("Omitted:")
                for entry in normalized.entries
            )
        )

    def test_standardized_structure_is_reported_as_derived(self):
        batch = parse_poscar(POSCAR_SOURCE)
        source = batch.structures[0]
        derived = replace(source, id=uuid4(), revision="standardized-r1")
        project = self._project(batch)
        project.structures[derived.id] = derived
        project.symmetry_results[uuid4()] = SimpleNamespace(
            structure_id=source.id,
            standardized_structure_id=derived.id,
        )

        selection = self.export.resolve_export_selection(project, derived.id)
        report = self.export.preview_export_selection(
            selection,
            "poscar",
            destination=Path("POSCAR"),
        )

        self.assertEqual(selection.source_structure_id, source.id)
        self.assertIn("structure:derived", {entry.code for entry in report.entries})

    def test_poscar_settings_control_preview_and_loss_confirmation(self):
        batch = parse_poscar(POSCAR_SOURCE)
        project = self._project(batch)
        selection = self.export.resolve_export_selection(
            project,
            batch.structures[0].id,
        )
        settings = PoscarExportSettings(
            comment="normalized",
            coordinate_mode="cartesian",
            scale_policy="unit",
            include_selective_dynamics=False,
            velocity_mode="direct",
        )

        report = self.export.preview_export_selection(
            selection,
            "poscar",
            poscar_settings=settings,
            destination=Path("POSCAR"),
        )

        codes = {entry.code for entry in report.entries}
        self.assertIn("coordinates_cartesian", codes)
        self.assertIn("selective_dynamics_omitted", codes)
        self.assertTrue(report.requires_confirmation)

        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "POSCAR"
            blocked = self.export.ExportJob(
                destination,
                selection,
                format_name="poscar",
                confirm_loss=False,
                missing_value_token=None,
                poscar_settings=settings,
            )
            blocked._run()
            self.assertIsInstance(blocked.error, ValueError)
            self.assertFalse(destination.exists())

            accepted = self.export.ExportJob(
                destination,
                selection,
                format_name="poscar",
                confirm_loss=True,
                missing_value_token=None,
                poscar_settings=settings,
            )
            accepted._run()
            self.assertIsNone(accepted.error)
            reparsed = parse_poscar(destination)
            source_numbers = batch.structures[0].atomic_numbers
            self.assertEqual(
                reparsed.structures[0].atomic_numbers,
                source_numbers,
            )
            self.assertEqual(source_numbers, (55, 17))
            self.assertFalse(
                any(
                    item.semantic_role == "selective_dynamics"
                    for item in reparsed.datasets
                )
            )

    def test_partial_or_ambiguous_related_data_requires_confirmation(self):
        batch = parse_poscar(POSCAR_SOURCE)
        selection = self.export.resolve_export_selection(
            self._project(batch),
            batch.structures[0].id,
        )
        selection = self.export.ExportSelection(
            structure=selection.structure,
            frame_set=None,
            properties=(
                SimpleNamespace(
                    id=uuid4(),
                    semantic_role="custom_property",
                    status=DatasetStatus.PARTIAL,
                ),
            ),
        )

        report = self.export.preview_export_selection(selection, "poscar")

        self.assertTrue(report.requires_confirmation)
        self.assertIn(
            "quality:partial",
            {entry.code for entry in report.entries},
        )

    def test_operator_resolves_project_entity_not_evaluated_view_geometry(self):
        module = self.export
        operation = module.CHEMBLENDER_OT_export_project_entity()
        operation.format_name = "poscar"
        operation.missing_value_token = ""
        operation.cif_mode = "normalized"
        operation.poscar_coordinate_mode = "direct"
        operation.poscar_scale_policy = "unit"
        operation.poscar_include_selective_dynamics = True
        operation.poscar_velocity_mode = "cartesian"
        selected_id = uuid4()
        project = object()
        selection = module.ExportSelection(
            structure=SimpleNamespace(periodic=object()),
            frame_set=None,
            properties=(),
        )
        context = SimpleNamespace(
            scene=object(),
            active_object=SimpleNamespace(
                data="evaluated supercell mesh must not be exported"
            ),
        )
        session = SimpleNamespace(
            project=project,
            active_entity_id=selected_id,
        )
        report = SimpleNamespace(entries=())

        with (
            patch.object(module, "get_scene_session", return_value=session),
            patch.object(
                module,
                "resolve_export_selection",
                return_value=selection,
            ) as resolve,
            patch.object(
                module,
                "preview_export_selection",
                return_value=report,
            ),
        ):
            operation._selection_and_preview(context)

        resolve.assert_called_once_with(project, selected_id)

    def test_filepath_refreshes_preview_and_invalid_choice_clears_stale_plan(self):
        module = self.export
        operation = module.CHEMBLENDER_OT_export_project_entity()
        operation.filepath = "old.cif"
        operation.format_name = "cif"
        operation.missing_value_token = ""
        operation.cif_mode = "normalized"
        operation._preview_report = object()
        selection = module.ExportSelection(
            structure=SimpleNamespace(periodic=object()),
            frame_set=None,
            properties=(),
        )
        session = SimpleNamespace(project=object(), active_entity_id=uuid4())
        report = SimpleNamespace(entries=())
        context = SimpleNamespace(scene=object())
        update = (
            module.CHEMBLENDER_OT_export_project_entity
            .__annotations__["filepath"]
            .keywords["update"]
        )

        with (
            patch.object(module, "get_scene_session", return_value=session),
            patch.object(
                module,
                "resolve_export_selection",
                return_value=selection,
            ),
            patch.object(
                module,
                "preview_export_selection",
                return_value=report,
            ) as preview,
        ):
            operation.filepath = "new.cif"
            update(operation, context)

        self.assertIs(operation._preview_report, report)
        self.assertEqual(
            preview.call_args.kwargs["destination"],
            "new.cif",
        )

        with (
            patch.object(module, "get_scene_session", return_value=session),
            patch.object(
                module,
                "resolve_export_selection",
                return_value=selection,
            ),
            patch.object(
                module,
                "preview_export_selection",
                side_effect=ValueError("preserve requires source envelope"),
            ),
        ):
            update(operation, context)

        self.assertIsNone(operation._preview_report)
        self.assertEqual(
            operation.loss_preview,
            "preserve requires source envelope",
        )

    def test_operator_exposes_comment_and_target_volume_settings(self):
        import numpy

        batch = parse_poscar(POSCAR_SOURCE)
        selection = self.export.resolve_export_selection(
            self._project(batch),
            batch.structures[0].id,
        )
        operation = self.export.CHEMBLENDER_OT_export_project_entity()
        operation.poscar_comment = "target-volume export"
        operation.poscar_coordinate_mode = "direct"
        operation.poscar_scale_policy = "target_volume"
        operation.poscar_target_volume = abs(
            float(numpy.linalg.det(selection.structure.cell.values))
        )
        operation.poscar_include_selective_dynamics = True
        operation.poscar_velocity_mode = "cartesian"

        settings = operation._poscar_settings(selection)

        self.assertEqual(settings.comment, "target-volume export")
        self.assertEqual(settings.scale_policy, "target_volume")
        self.assertEqual(
            settings.target_volume,
            operation.poscar_target_volume,
        )


if __name__ == "__main__":
    unittest.main()
