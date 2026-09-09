import importlib
import json
import sys
import time
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from cbq_core.model import DatasetStatus
from cbq_core.session import close_session
from cbq_core.session import create_session
from chemblender_prepare.core.import_pipeline.conformer_grouping import suggest_staged_conformer_groups
from chemblender_prepare.core.import_pipeline.request import ImportRequest
from chemblender_prepare.core.import_pipeline.request import ImportSource
from chemblender_prepare.core.import_pipeline.staging import StagedImportSession
from chemblender_prepare.reader_api.import_pipeline_bridge import preflight_reader_plugins
from chemblender_prepare.reader_api.registry import builtin_reader_plugin_registry


ROOT = Path(__file__).resolve().parents[1]


class ExternalPreviewTransactionTests(unittest.TestCase):
    def test_missing_batch_blocks_confirm_with_visible_reason(self):
        from chemblender_prepare.core.import_pipeline import transaction
        with TemporaryDirectory() as temporary:
            session = create_session(temp_parent=Path(temporary))
            staging = StagedImportSession.create(temp_parent=Path(temporary))
            try:
                preview = preflight_reader_plugins(
                    ImportRequest(sources=(ImportSource(ROOT / "tests/fixtures/xyz/water.xyz"),)),
                    builtin_reader_plugin_registry(), staging)
                preview = replace(preview, staged_batch_ids=(), source_previews=tuple(
                    replace(row, staged_batch_ids=()) for row in preview.source_previews))
                before = session.project
                with self.assertRaisesRegex(ValueError, "staged batch"):
                    transaction.commit_import_preview(session, staging, preview,
                                                      transaction.ImportCommitDecisions())
                self.assertIs(session.project, before)
                self.assertIsNone(session.sidecar_path)
                self.assertFalse(list(session.temporary_root.glob("*.cbq")))
            finally:
                staging.discard()
                close_session(session)

    def test_changed_conformer_suggestion_fails_closed_in_transaction(self):
        from chemblender_prepare.core.import_pipeline import transaction
        with TemporaryDirectory() as temporary:
            session = create_session(temp_parent=Path(temporary))
            staging = StagedImportSession.create(temp_parent=Path(temporary))
            try:
                preview = preflight_reader_plugins(
                    ImportRequest(sources=(ImportSource(ROOT / "tests/fixtures/sdf/records.sdf"),)),
                    builtin_reader_plugin_registry(), staging)
                suggestions = suggest_staged_conformer_groups(preview, staging)
                self.assertTrue(suggestions)
                suggestion = suggestions[0]
                decisions = transaction.ImportCommitDecisions(conformer_grouping_decisions=(
                    transaction.ConformerGroupingDecision(suggestion, suggestion.requires_review),))
                before = session.project
                before_files = set(session.temporary_root.rglob("*"))
                with patch.object(transaction, "suggest_conformer_groups", return_value=()), patch.object(
                    transaction, "solidify_session", side_effect=AssertionError("stale evidence published")
                ) as publication:
                    with self.assertRaisesRegex(ValueError, "conformer grouping decision does not match live staging"):
                        transaction.commit_import_preview(session, staging, preview, decisions)
                publication.assert_not_called()
                self.assertIs(session.project, before)
                self.assertFalse(session.project.structures)
                self.assertEqual(set(session.temporary_root.rglob("*")), before_files)
            finally:
                staging.discard()
                close_session(session)


class ExternalExtXYZPreviewTests(unittest.TestCase):
    def test_inspection_failure_discards_owned_staging(self):
        import io
        from contextlib import redirect_stdout
        from chemblender_prepare.cli import main
        from chemblender_prepare.core.import_pipeline.staging import StagedImportSession
        original = StagedImportSession.create
        roots = []
        def create(**kwargs):
            staging = original(**kwargs)
            roots.append(staging.root)
            return staging
        with TemporaryDirectory() as directory:
            source = Path(directory) / "sample.extxyz"
            source.write_text("1\nProperties=species:S:1:pos:R:3\nH 0 0 0\n", encoding="utf-8")
            stream = io.StringIO()
            with patch.object(StagedImportSession, "create", side_effect=create), patch(
                "chemblender_prepare.extxyz_preview.extxyz_preview_summary", side_effect=RuntimeError("summary failed")
            ), redirect_stdout(stream):
                code = main(["inspect", str(source), "--json"])
            self.assertEqual(code, 1)
            self.assertIn("summary failed", stream.getvalue())
            self.assertTrue(roots)
            self.assertTrue(all(not root.exists() for root in roots))
            self.assertEqual(list(Path(directory).iterdir()), [source])

    def test_extxyz_preview_summary_reports_frames_properties_cell_and_units(self):
        with TemporaryDirectory() as temporary:
            source = Path(temporary) / "force.extxyz"
            source.write_text(
                "\n".join(
                    (
                        "1",
                        'Lattice="4 0 0 0 4 0 0 0 4" '
                        "Properties=species:S:1:pos:R:3:force:R:3 "
                        'pbc="T F T" energy=-1.25',
                        "C 0 0 0 1 2 3",
                        "1",
                        'Lattice="5 0 0 0 5 0 0 0 5" '
                        "Properties=species:S:1:pos:R:3:force:R:3 "
                        'pbc="F F F" energy=-1.0',
                        "C 0.1 0 0 2 3 4",
                        "",
                    )
                ),
                encoding="utf-8",
            )
            import io
            from contextlib import redirect_stdout
            from chemblender_prepare.cli import main
            stream = io.StringIO()
            with redirect_stdout(stream):
                code = main(["inspect", str(source), "--json"])
            self.assertEqual(code, 0, stream.getvalue())
            summary = SimpleNamespace(**json.loads(stream.getvalue())["metadata"]["extxyz"])

            self.assertEqual(summary.frame_count, 2)
            self.assertEqual(summary.atom_properties, ["atomic_force"])
            self.assertEqual(
                summary.frame_properties,
                ["cell", "energy", "pbc"],
            )
            self.assertTrue(summary.has_lattice)
            self.assertEqual(summary.pbc, [True, False, True])
            self.assertTrue(summary.pbc_changes)
            self.assertEqual(
                tuple(summary.assumed_units),
                (
                    "electron_volt was assumed because extXYZ declared no unit",
                    "electron_volt_per_angstrom was assumed because extXYZ "
                    "declared no unit",
                ),
            )


class ExternalMol2PreviewTests(unittest.TestCase):
    def inspect(self, source):
        import io
        from contextlib import redirect_stdout
        from chemblender_prepare.cli import main
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = main(["inspect", str(source), "--json"])
        result = json.loads(stream.getvalue())
        self.assertEqual(code, 0, result)
        return result["metadata"]["mol2"]

    def test_counts_types_charges_and_unsupported_sections(self):
        row = self.inspect(ROOT / "tests/fixtures/mol2/small.mol2")
        self.assertEqual((row["molecule_count"], row["atom_count"], row["interpreted_bond_count"]), (1, 2, 1))
        self.assertEqual(row["molecule_types"], "SMALL")
        self.assertEqual(row["charge_types"], "USER_CHARGES")
        self.assertEqual(row["partial_charge_summary"], "available (complete)")
        self.assertEqual(row["unsupported_sections"], "SET")

    def test_unsupported_bonds_are_diagnosed_without_invented_topology(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "unknown.mol2"
            source.write_bytes((ROOT / "tests/fixtures/mol2/small.mol2").read_bytes().replace(
                b"7 10 42 1", b"7 10 42 un"))
            row = self.inspect(source)
            self.assertEqual((row["interpreted_bond_count"], row["interpreted_topology_count"]), (0, 0))
            self.assertTrue(any("unsupported MOL2 bond type 'un'" in value["message"] for value in row["diagnostics"]))
            self.assertEqual(row["molecule_count"], 1)

    def test_partial_charge_coverage_counts_molecules(self):
        from chemblender_prepare.core.formats.mol2 import parse_mol2
        with TemporaryDirectory() as directory:
            source = Path(directory) / "mixed.mol2"
            source.write_text("@<TRIPOS>MOLECULE\ncharged\n1 0 0 0 0\nSMALL\nUSER_CHARGES\n"
                              "@<TRIPOS>ATOM\n1 C1 0 0 0 C.3 1 RES -0.1\n"
                              "@<TRIPOS>MOLECULE\nuncharged\n1 0 0 0 0\nSMALL\nNO_CHARGES\n"
                              "@<TRIPOS>ATOM\n1 He1 1 0 0 He\n", encoding="utf-8")
            row = self.inspect(source)
            batch = parse_mol2(source)
            self.assertEqual(len(batch.structures), 2)
            self.assertEqual({value.structure_id for value in batch.datasets if value.semantic_role == "partial_charge"},
                             {batch.structures[0].id})
            self.assertEqual(row["partial_charge_summary"], "1/2 molecules available")

    def test_gui_child_reports_interpreted_bonds(self):
        from chemblender_prepare.gui import CliProcess, command_arguments
        args = command_arguments({"command": "inspect", "sources": str(ROOT / "tests/fixtures/mol2/small.mol2")})
        job = CliProcess(args)
        try:
            result = None
            deadline = time.monotonic() + 20
            while result is None and time.monotonic() < deadline:
                result = job.poll()
                time.sleep(0.01)
            self.assertIsNotNone(result)
            self.assertEqual(result.status.value, "success")
            self.assertEqual(result.metadata["mol2"]["interpreted_bond_count"], 1)
        finally:
            if job.process.poll() is None:
                job.cancel()
                job.process.wait(timeout=10)
            job.close()


class ScenePresetApplicationTests(unittest.TestCase):
    def setUp(self):
        import importlib.util
        bpy = SimpleNamespace(data=SimpleNamespace(materials=[]))
        self.enterContext(patch.dict(sys.modules, {"bpy": bpy}))
        spec = importlib.util.spec_from_file_location(
            "ChemBlender._scene_preset_rollback_test", ROOT / "ChemBlender/scene_preset_view.py")
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def test_scene_preset_rolls_back_partial_objects_before_fatal_reraises(self):
        scene_preset_view = self.module
        created = object()
        fatal = GeneratorExit("linked view stopped")
        plan = SimpleNamespace(
            view_kind="electronic_spectrum_linked",
            settings=(("selection_index", 0),),
        )
        removed = []

        with (
            patch.object(scene_preset_view, "_selected_or_unique_topology", return_value=None),
            patch.object(
                scene_preset_view,
                "validate_scene_plan",
                return_value=plan,
            ),
            patch.object(
                scene_preset_view,
                "_entities",
                return_value={
                    "structure": object(),
                    "spectrum": object(),
                    "states": object(),
                },
            ),
            patch.object(
                scene_preset_view,
                "create_structure_view",
                return_value=created,
            ),
            patch.object(
                scene_preset_view,
                "link_stick_spectrum_selection",
                side_effect=fatal,
            ),
            patch.object(
                scene_preset_view,
                "_remove_objects",
                side_effect=lambda objects: removed.extend(objects),
            ),
        ):
            with self.assertRaises(GeneratorExit) as raised:
                scene_preset_view.apply_scene_preset(
                    plan,
                    object(),
                    collection=object(),
                )

        self.assertIs(raised.exception, fatal)
        self.assertEqual(removed, [created])




class PreparedDefaultViewTests(unittest.TestCase):
    """Pure display planning consumes the real external reader preflight output."""
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.session = create_session(temp_parent=Path(self.temporary.name))
        self.addCleanup(close_session, self.session)

    def stage(self, relative):
        staging = StagedImportSession.create(temp_parent=Path(self.temporary.name))
        self.addCleanup(staging.discard)
        registry = builtin_reader_plugin_registry()
        preview = preflight_reader_plugins(
            ImportRequest(sources=(ImportSource(ROOT / relative),)),
            registry, staging)
        return registry, SimpleNamespace(staging_session=staging, preview=preview)

    def test_default_view_planner_prioritizes_real_grid_and_signed_roles(self):
        default_views = importlib.import_module(
            "ChemBlender.ui.default_views"
        )
        _registry, cube_state = self.stage(
            "tests/fixtures/cube/sheared.cube"
        )
        cube_batch = cube_state.staging_session.result(
            cube_state.preview.source_previews[0].staged_batch_ids[0]
        )
        cube_revision = cube_batch.source_revisions[0]
        cube_grid = cube_batch.datasets[0]
        cube_plan = default_views.plan_default_view(
            cube_revision,
            {value.id: value for value in cube_batch.structures},
            {value.id: value for value in cube_batch.datasets},
        )

        self.assertEqual(cube_grid.status, DatasetStatus.AMBIGUOUS)
        self.assertEqual(
            cube_plan.source_revision_id,
            cube_revision.id,
        )
        self.assertEqual(cube_plan.preset_id, "grid_volume")
        self.assertEqual(cube_plan.bindings, (("grid", cube_grid.id),))
        self.assertEqual(cube_plan.settings, (("dataset_index", 0),))
        self.assertEqual(cube_plan.display_label, "Grid Volume")
        self.assertFalse(hasattr(cube_plan, "__dict__"))
        with self.assertRaises(FrozenInstanceError):
            cube_plan.preset_id = "changed"
        self.assertEqual(
            default_views.describe_default_view(cube_plan),
            "Default view: Grid Volume",
        )

        signed_grid = replace(
            cube_grid,
            semantic_role="molecular_orbital",
            data=replace(cube_grid.data, unit="dimensionless"),
            status=DatasetStatus.COMPLETE,
        )
        signed_plan = default_views.plan_default_view(
            cube_revision,
            {value.id: value for value in cube_batch.structures},
            {signed_grid.id: signed_grid},
        )
        self.assertEqual(signed_plan.preset_id, "signed_isosurface")
        self.assertEqual(signed_plan.display_label, "Signed Isosurface")
        spin_plan = default_views.plan_default_view(
            cube_revision,
            {value.id: value for value in cube_batch.structures},
            {
                signed_grid.id: replace(
                    signed_grid,
                    semantic_role="spin_density",
                )
            },
        )
        self.assertEqual(spin_plan.preset_id, "signed_isosurface")
        density_plan = default_views.plan_default_view(
            cube_revision,
            {value.id: value for value in cube_batch.structures},
            {
                signed_grid.id: replace(
                    signed_grid,
                    semantic_role="electron_density",
                )
            },
        )
        self.assertEqual(density_plan.preset_id, "grid_volume")

        _registry, xyz_state = self.stage(
            "tests/fixtures/xyz/water.xyz"
        )
        xyz_batch = xyz_state.staging_session.result(
            xyz_state.preview.source_previews[0].staged_batch_ids[0]
        )
        xyz_plan = default_views.plan_default_view(
            xyz_batch.source_revisions[0],
            {value.id: value for value in xyz_batch.structures},
            {value.id: value for value in xyz_batch.datasets},
        )
        self.assertEqual(xyz_plan.preset_id, "structure_publication")
        self.assertEqual(xyz_plan.display_label, "Structure")
        self.assertIsNone(
            default_views.plan_default_view(
                replace(
                    xyz_batch.source_revisions[0],
                    created_entity_ids=(),
                ),
                {},
                {},
            )
        )
        self.assertEqual(
            default_views.describe_default_view(None),
            "Default view: No supported visual data",
        )

    def test_default_view_planner_skips_grid_units_unsupported_by_adapters(self):
        default_views = importlib.import_module(
            "ChemBlender.ui.default_views"
        )
        _registry, state = self.stage(
            "tests/fixtures/cube/sheared.cube"
        )
        batch = state.staging_session.result(
            state.preview.source_previews[0].staged_batch_ids[0]
        )
        revision = batch.source_revisions[0]
        grid = batch.datasets[0]
        structures = {value.id: value for value in batch.structures}
        structure_ids = tuple(structures)

        for unit in ("unknown", "nanometer"):
            with self.subTest(unit=unit):
                unsupported = replace(
                    grid,
                    id=uuid4(),
                    coordinate_unit=unit,
                )
                unsupported_revision = replace(
                    revision,
                    created_entity_ids=(
                        unsupported.id,
                        *structure_ids,
                    ),
                )
                fallback = default_views.plan_default_view(
                    unsupported_revision,
                    structures,
                    {unsupported.id: unsupported},
                )
                self.assertEqual(
                    fallback.preset_id,
                    "structure_publication",
                )
                self.assertIsNone(
                    default_views.plan_default_view(
                        replace(
                            unsupported_revision,
                            created_entity_ids=(unsupported.id,),
                        ),
                        {},
                        {unsupported.id: unsupported},
                    )
                )

        unsupported = replace(
            grid,
            id=uuid4(),
            coordinate_unit="nanometer",
        )
        next_grid = default_views.plan_default_view(
            replace(
                revision,
                created_entity_ids=(
                    unsupported.id,
                    grid.id,
                    *structure_ids,
                ),
            ),
            structures,
            {
                unsupported.id: unsupported,
                grid.id: grid,
            },
        )
        self.assertEqual(next_grid.preset_id, "grid_volume")
        self.assertEqual(next_grid.bindings, (("grid", grid.id),))

        unsupported_signed = replace(
            unsupported,
            semantic_role="molecular_orbital",
            data=replace(unsupported.data, unit="dimensionless"),
            status=DatasetStatus.COMPLETE,
        )
        signed_fallback = default_views.plan_default_view(
            replace(
                revision,
                created_entity_ids=(
                    unsupported_signed.id,
                    grid.id,
                    *structure_ids,
                ),
            ),
            structures,
            {
                unsupported_signed.id: unsupported_signed,
                grid.id: grid,
            },
        )
        self.assertEqual(signed_fallback.preset_id, "grid_volume")
        self.assertEqual(signed_fallback.bindings, (("grid", grid.id),))


if __name__ == "__main__":
    unittest.main()
