import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from cbq_core.model import DatasetStatus
from cbq_core.model import QCProject
from chemblender_prepare.core.formats.cif import parse_cif
from chemblender_prepare.core.formats.poscar import parse_poscar
from chemblender_prepare.core.exporters import PoscarExportSettings


ROOT = Path(__file__).resolve().parents[1]
CIF_SOURCE = ROOT / "tests" / "fixtures" / "cif" / "mixed-site-data.cif"
POSCAR_SOURCE = (
    ROOT / "tests" / "fixtures" / "poscar" / "cscl-selective.vasp"
)
class CrystalExternalExportContractTests(unittest.TestCase):
    def setUp(self):
        from chemblender_prepare import export_service
        self.export = export_service

    @staticmethod
    def _project(batch):
        project = QCProject(uuid4(), "0.2")
        project.commit(batch)
        return project

    def test_gui_forwards_cif_mode_and_drops_hidden_format_settings(self):
        from chemblender_prepare.gui import command_arguments
        values = {"command": "export", "sources": "project.cbq", "output": "out.cif",
                  "entity": str(uuid4()), "format": "cif", "cif-mode": "normalized",
                  "poscar-comment": "hidden", "poscar-include-selective-dynamics": "false"}
        argv = command_arguments(values)
        self.assertIn("--cif-mode", argv)
        self.assertFalse(any("poscar" in value for value in argv))
        values["format"] = "poscar"
        argv = command_arguments(values)
        self.assertNotIn("--cif-mode", argv)
        self.assertIn("--no-poscar-include-selective-dynamics", argv)

    def test_xyz_reports_periodic_loss_and_blocks_unconfirmed_worker(self):
        batch = parse_poscar(POSCAR_SOURCE)
        selection = self.export.resolve_export_selection(
            self._project(batch), batch.structures[0].id,
        )
        report = self.export.preview_export_selection(selection, "xyz")
        self.assertTrue(report.requires_confirmation)
        self.assertIn("omit:cell_pbc", {entry.code for entry in report.entries})
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "structure.xyz"
            with self.assertRaises(ValueError):
                self.export.export_selection(destination, selection, format_name="xyz", confirm_loss=False)
            self.assertFalse(destination.exists())
            confirmed = self.export.export_selection(
                destination, selection, format_name="xyz",
                confirm_loss=True, missing_value_token=None,
            )
            self.assertTrue(confirmed.written)
            self.assertTrue(destination.exists())

    def test_xyz_without_extra_scientific_data_needs_no_confirmation(self):
        from chemblender_prepare.core.xyz import parse_xyz
        batch = parse_xyz(ROOT / "tests/fixtures/xyz/water.xyz")
        selection = self.export.resolve_export_selection(
            self._project(batch), batch.structures[0].id,
        )
        report = self.export.preview_export_selection(selection, "xyz")
        self.assertFalse(report.requires_confirmation)

    def test_external_export_requires_an_explicit_destination(self):
        from chemblender_prepare.gui import command_arguments
        with self.assertRaisesRegex(ValueError, "output path"):
            command_arguments({"command": "export", "sources": "project.cbq", "format": "xyz"})

    def test_output_is_passed_literally_without_shell_interpretation(self):
        from chemblender_prepare.gui import command_arguments
        output = "folder with spaces/review $(literal).cif"
        argv = command_arguments({"command": "export", "sources": "project.cbq", "format": "cif", "output": output})
        self.assertEqual(argv[argv.index("--output") + 1], output)

    def test_cli_refuses_any_existing_destination_including_a_blend(self):
        from chemblender_prepare.cli import _new_output
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "review.blend"
            destination.write_bytes(b"existing Blender project")
            with self.assertRaises((ValueError, FileExistsError)):
                _new_output(destination, cbq=False)
            self.assertEqual(destination.read_bytes(), b"existing Blender project")

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
            with self.assertRaises(ValueError):
                self.export.export_selection(destination, selection, format_name="poscar",
                                             confirm_loss=False, poscar_settings=settings)
            self.assertFalse(destination.exists())

            accepted = self.export.export_selection(
                destination,
                selection,
                format_name="poscar",
                confirm_loss=True,
                missing_value_token=None,
                poscar_settings=settings,
            )
            self.assertTrue(accepted.written)
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

    def test_export_selection_uses_canonical_project_structure(self):
        batch = parse_poscar(POSCAR_SOURCE)
        project = self._project(batch)
        selection = self.export.resolve_export_selection(project, batch.structures[0].id)
        self.assertIs(selection.structure, batch.structures[0])
        self.assertEqual(len(selection.structure.atomic_numbers), 2)
        self.assertEqual(selection.structure.coordinates.unit, "angstrom")

    def test_preview_recomputes_destination_and_rejects_invalid_preserve(self):
        batch = parse_cif(CIF_SOURCE)
        selection = self.export.resolve_export_selection(self._project(batch), batch.structures[0].id)
        first = self.export.preview_export_selection(selection, "cif", destination=Path("first.cif"))
        second = self.export.preview_export_selection(selection, "cif", destination=Path("second.cif"))
        self.assertNotEqual(next(e for e in first.entries if e.code == "output_path"),
                            next(e for e in second.entries if e.code == "output_path"))
        with self.assertRaises(ValueError):
            self.export.preview_export_selection(replace(selection, cif_envelope=None), "cif", cif_mode="preserve")

    def test_cli_and_gui_expose_comment_and_target_volume_settings(self):
        from chemblender_prepare.cli import build_parser
        from chemblender_prepare.gui import command_arguments
        values = {"command": "export", "sources": "project.cbq", "output": "POSCAR",
                  "entity": str(uuid4()), "format": "poscar", "poscar-comment": "target-volume export",
                  "poscar-scale-policy": "target_volume", "poscar-target-volume": "72.0",
                  "poscar-coordinate-mode": "cartesian", "poscar-velocity-mode": "direct",
                  "poscar-include-selective-dynamics": "false"}
        args = build_parser().parse_args(command_arguments(values))
        self.assertEqual(args.poscar_comment, "target-volume export")
        self.assertEqual(args.poscar_scale_policy, "target_volume")
        self.assertEqual(args.poscar_target_volume, 72.)
        self.assertEqual(args.poscar_coordinate_mode, "cartesian")
        self.assertEqual(args.poscar_velocity_mode, "direct")
        self.assertFalse(args.poscar_include_selective_dynamics)


if __name__ == "__main__":
    unittest.main()
