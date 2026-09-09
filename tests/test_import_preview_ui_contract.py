import importlib
import json
import sys
import threading
import time
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4

from cbq_core.model import DatasetStatus
from cbq_core.sidecar import close_project
from cbq_core.session import close_session
from cbq_core.session import create_session
from cbq_core.sidecar import open_project
from chemblender_prepare.core.import_pipeline.grouping import GroupingEvidence
from chemblender_prepare.core.import_pipeline.grouping import SourceGroupSuggestion
from chemblender_prepare.core.import_pipeline.conformer_grouping import suggest_staged_conformer_groups
from cbq_core.sidecar import save_project
from chemblender_prepare.core.import_pipeline.request import ImportRequest
from chemblender_prepare.core.import_pipeline.request import ImportSource
from chemblender_prepare.core.import_pipeline.request import ValidationMode
from chemblender_prepare.core.import_pipeline.staging import StagedImportSession
from chemblender_prepare.core.formats.extxyz import parse_extxyz
from cbq_core.storage.publication import PublicationCancelled
from chemblender_prepare.reader_api.import_pipeline_bridge import preflight_reader_plugins
from chemblender_prepare.reader_api.registry import builtin_reader_plugin_registry


ROOT = Path(__file__).resolve().parents[1]
MODULE = "ChemBlender.ui.import_preview"
PROPERTIES_MODULE = "ChemBlender.ui.properties"


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


class _Objects:
    def __init__(self):
        self.removed = []

    def remove(self, obj, *, do_unlink):
        self.removed.append((obj, do_unlink))


class _RNACollection(list):
    def add(self):
        row = SimpleNamespace()
        self.append(row)
        return row


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


class ImportPreviewUIContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.fake_bpy = ModuleType("bpy")
        self.fake_props = ModuleType("bpy.props")
        for name, kind in (
            ("BoolProperty", "bool"),
            ("CollectionProperty", "collection"),
            ("EnumProperty", "enum"),
            ("FloatProperty", "float"),
            ("FloatVectorProperty", "float_vector"),
            ("IntProperty", "int"),
            ("IntVectorProperty", "int_vector"),
            ("PointerProperty", "pointer"),
            ("StringProperty", "string"),
        ):
            setattr(self.fake_props, name, _property(kind))
        self.fake_bpy.props = self.fake_props
        self.fake_bpy.types = SimpleNamespace(
            Operator=_Operator,
            PropertyGroup=_PropertyGroup,
        )
        self.fake_bpy.app = SimpleNamespace(background=True)
        self.fake_bpy.data = SimpleNamespace(
            objects=_Objects(),
            materials=[],
            batch_remove=lambda **_kwargs: None,
        )
        self.fake_bpy.context = SimpleNamespace(collection=object())
        self.modules = patch.dict(
            sys.modules,
            {"bpy": self.fake_bpy, "bpy.props": self.fake_props},
        )
        self.modules.start()
        self.addCleanup(self.modules.stop)
        for name in (MODULE, PROPERTIES_MODULE):
            sys.modules.pop(name, None)
        self.properties = importlib.import_module(PROPERTIES_MODULE)
        self.module = importlib.import_module(MODULE)
        self.session = create_session(temp_parent=Path(self.temporary.name))

    def tearDown(self):
        try:
            self.properties.clear_quick_import_state(self.session)
        except BaseException:
            pass
        try:
            if self.session.temporary_root.exists():
                close_session(self.session)
        except BaseException:
            pass
        self.modules.stop()
        for name in (MODULE, PROPERTIES_MODULE):
            sys.modules.pop(name, None)
        self.temporary.cleanup()

    def stage(self, *relative_paths):
        staging = self.properties.create_quick_import_staging(self.session)
        request = ImportRequest(
            sources=tuple(
                ImportSource((ROOT / relative).resolve())
                for relative in relative_paths
            ),
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

    def interactive_fixture(self, manager):
        registry, state = self.stage("tests/fixtures/xyz/water.xyz")
        context = SimpleNamespace(
            scene=SimpleNamespace(
                collection=object(),
                chemblender_quick_import=SimpleNamespace(
                    recent_summary="",
                ),
            ),
            window=object(),
            window_manager=manager,
        )
        operator = self.module.CHEMBLENDER_OT_confirm_import()
        operator.rows = _RNACollection()
        operator.blocking_reason = ""
        self.fake_bpy.app.background = False
        return registry, state, context, operator

    def assert_setup_failure_releases_owned_state(self, failure_step):
        calls = []
        timer = object()

        def operation(name, result=None):
            calls.append((name,))
            if name == failure_step:
                raise RuntimeError(f"{name} failed")
            return result

        manager = SimpleNamespace(
            event_timer_add=lambda *_args, **_kwargs: operation(
                "event_timer_add",
                timer,
            ),
            event_timer_remove=lambda _timer: operation(
                "event_timer_remove"
            ),
            progress_begin=lambda *_args: operation("progress_begin"),
            progress_update=lambda *_args: operation("progress_update"),
            progress_end=lambda: operation("progress_end"),
            modal_handler_add=lambda *_args: operation(
                "modal_handler_add"
            ),
        )
        registry, state, context, operator = self.interactive_fixture(
            manager
        )
        staging_root = state.staging_session.root
        start_patch = (
            patch.object(
                self.module._CommitJob,
                "start",
                side_effect=RuntimeError("thread.start failed"),
            )
            if failure_step == "thread.start"
            else patch.object(
                self.module._CommitJob,
                "start",
                self.module._CommitJob.start,
            )
        )
        with patch.object(
            self.module,
            "get_scene_session",
            return_value=self.session,
        ), patch.object(
            self.module,
            "get_reader_plugin_registry",
            return_value=registry,
        ), start_patch:
            result = operator.execute(context)

        self.assertEqual(result, {"CANCELLED"})
        self.assertIn(f"{failure_step} failed", operator.last_report[1])
        self.assertIsNone(state.active_job)
        self.assertIsNone(state.staging_session)
        self.assertIsNone(state.preview)
        self.assertFalse(staging_root.exists())
        if ("progress_end",) in calls and ("event_timer_remove",) in calls:
            self.assertLess(
                calls.index(("progress_end",)),
                calls.index(("event_timer_remove",)),
            )
        return calls

    @staticmethod
    def snapshot(session):
        project = session.project
        return (
            id(project),
            tuple(
                (name, tuple(getattr(project, name)))
                for name in project.__dataclass_fields__
                if isinstance(getattr(project, name), dict)
            ),
            session.dirty_reasons,
        )

    def test_import_preview_projects_and_draws_unavailable_reader_plugin(self):
        registry, _state = self.stage("tests/fixtures/xyz/water.xyz")
        unavailable = SimpleNamespace(
            plugin_id="org.example.failed",
            reader_ids=("failed-reader",),
            availability=SimpleNamespace(
                available=False,
                reason_code="plugin_registration_failed",
                detail="ValueError",
            ),
        )
        snapshot = SimpleNamespace(plugins=(unavailable,))
        operator = self.module.CHEMBLENDER_OT_confirm_import()
        operator.rows = _RNACollection()
        operator.grouping_suggestions = _RNACollection()
        operator.conformer_grouping_suggestions = _RNACollection()
        operator.blocking_reason = ""
        operator.reader_plugin_status = ""
        context = SimpleNamespace(scene=object())

        with patch.object(
            self.module,
            "get_scene_session",
            return_value=self.session,
        ), patch.object(
            self.module,
            "get_reader_plugin_registry",
            return_value=registry,
        ), patch.object(
            self.module,
            "refresh_reader_plugin_discovery",
            return_value=snapshot,
        ):
            operator._project(context)

        expected = (
            "Reader plugin org.example.failed (failed-reader) unavailable: "
            "plugin_registration_failed (ValueError)"
        )
        self.assertEqual(operator.reader_plugin_status, expected)

        labels = []
        operator.layout = SimpleNamespace(
            label=lambda **keywords: labels.append(keywords),
        )
        operator.rows = ()
        operator.grouping_suggestions = ()
        operator.conformer_grouping_suggestions = ()
        operator.draw(None)
        self.assertIn(
            {"text": expected, "icon": "ERROR"},
            labels,
        )

    def stage_two_candidate_conflict(self):
        for action in (None, "independent_copy"):
            registry, state = self.stage("tests/fixtures/xyz/water.xyz")
            rows = self.module.project_import_preview(
                self.session,
                state,
                registry,
            )
            if action is not None:
                rows[0].conflict_action = action
            self.module.commit_project_import(
                self.session,
                state,
                rows,
                collection=object(),
                apply_view=lambda *_args, **_kwargs: (),
            )
        return self.stage("tests/fixtures/xyz/water.xyz")

    def test_rna_rows_contain_only_small_projection_properties(self):
        row = self.module.CHEMBLENDER_PG_import_preview_row
        annotations = row.__annotations__

        self.assertEqual(
            set(annotations),
            {
                "source_id",
                "source_name",
                "reader_id",
                "reader_availability",
                "capability_summary",
                "frame_count",
                "atom_property_summary",
                "frame_property_summary",
                "lattice_pbc_summary",
                "assumed_unit_summary",
                "molecular_record_count",
                "molecular_version_summary",
                "molecular_recovery_summary",
                "molecular_topology_summary",
                "molecular_property_summary",
                "mol2_molecule_count",
                "mol2_atom_count",
                "mol2_bond_count",
                "mol2_molecule_types",
                "mol2_charge_types",
                "mol2_partial_charge_summary",
                "mol2_unsupported_sections",
                "grid_dataset_count",
                "grid_source_ids",
                "grid_sample_range",
                "grid_shape",
                "grid_coordinate_unit",
                "grid_value_unit",
                "grid_quality",
                "cif_block_count",
                "cif_valid_block_count",
                "cif_block_summary",
                "cif_site_summary",
                "cif_cell_summary",
                "cif_occupancy_adp_summary",
                "cif_declared_symmetry_summary",
                "cif_default_block_confirmed",
                "poscar_comment",
                "poscar_scale_summary",
                "poscar_cell_summary",
                "poscar_species_summary",
                "poscar_coordinate_mode",
                "poscar_selective_summary",
                "poscar_velocity_summary",
                "poscar_species_assignment",
                "poscar_requires_species_assignment",
                "conformer_suggestion_count",
                "quality",
                "conflict_id",
                "conflict_action",
                "conflict_candidates",
                "allowed_actions",
                "default_view",
                "default_view_label",
                "blocking",
                "blocking_reason",
            },
        )
        self.assertTrue(
            all(
                value.kind in {"bool", "collection", "enum", "int", "string"}
                for value in annotations.values()
            )
        )
        candidate = (
            self.module.CHEMBLENDER_PG_import_conflict_candidate
        )
        self.assertEqual(
            set(candidate.__annotations__),
            {
                "revision_id",
                "source_id",
                "display_label",
                "created_entity_count",
                "selected",
            },
        )
        self.assertTrue(
            all(
                value.kind in {"bool", "int", "string"}
                for value in candidate.__annotations__.values()
            )
        )
        evidence = self.module.CHEMBLENDER_PG_import_grouping_evidence
        self.assertEqual(
            set(evidence.__annotations__),
            {
                "evidence_id",
                "source_revision_ids",
                "kind",
                "summary",
                "metric",
                "metric_unit",
                "selected",
            },
        )
        suggestion = self.module.CHEMBLENDER_PG_import_grouping_suggestion
        self.assertEqual(
            set(suggestion.__annotations__),
            {
                "suggestion_id",
                "source_count",
                "confidence",
                "requires_review",
                "grouping_action",
                "review_confirmed",
                "evidence",
            },
        )
        conformer_evidence = (
            self.module.CHEMBLENDER_PG_import_conformer_evidence
        )
        self.assertEqual(
            set(conformer_evidence.__annotations__),
            {
                "record_id",
                "record_key",
                "kind",
                "atom_mapping",
                "requires_review",
            },
        )
        conformer_suggestion = (
            self.module.CHEMBLENDER_PG_import_conformer_suggestion
        )
        self.assertEqual(
            set(conformer_suggestion.__annotations__),
            {
                "suggestion_id",
                "record_count",
                "requires_review",
                "hidden_review_count",
                "grouping_action",
                "review_confirmed",
                "evidence",
            },
        )

    def test_projection_uses_live_reader_and_conflict_metadata(self):
        registry, state = self.stage("tests/fixtures/xyz/water.xyz")
        rows = self.module.project_import_preview(
            self.session,
            state,
            registry,
        )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.reader_id, "xyz")
        self.assertEqual(row.reader_availability, "available")
        self.assertIn("structure", row.capability_summary)
        self.assertFalse(row.blocking)
        self.assertEqual(state.preview.conflict_ids, ())
        self.assertEqual(row.default_view_label, "Default view: Structure")

        self.module.commit_project_import(
            self.session,
            state,
            rows,
            collection=object(),
            apply_view=lambda *_args, **_kwargs: (),
        )
        registry, state = self.stage("tests/fixtures/xyz/water.xyz")
        rows = self.module.project_import_preview(
            self.session,
            state,
            registry,
        )
        self.assertTrue(rows[0].conflict_id)
        self.assertEqual(
            rows[0].conflict_action,
            "reuse_existing",
        )
        self.assertEqual(
            state.preview.conflict_ids,
            (state.conflicts[0].id,),
        )



    def test_molecular_preview_and_conformer_choice_are_small_and_explicit(self):
        registry, state = self.stage("tests/fixtures/sdf/records.sdf")

        rows = self.module.project_import_preview(
            self.session,
            state,
            registry,
        )
        row = rows[0]
        self.assertEqual(row.molecular_record_count, 2)
        self.assertEqual(row.molecular_version_summary, "V2000: 2")
        self.assertEqual(row.molecular_recovery_summary, "none")
        self.assertIn("sanitized", row.molecular_topology_summary)
        self.assertIn("raw fields", row.molecular_property_summary)
        self.assertIn("typed columns", row.molecular_property_summary)
        self.assertEqual(row.conformer_suggestion_count, 1)

        suggestions = self.module.project_conformer_suggestions(state)
        self.assertEqual(len(suggestions), 1)
        suggestion = suggestions[0]
        self.assertEqual(suggestion.record_count, 2)
        self.assertEqual(suggestion.grouping_action, "keep_independent")
        self.assertFalse(suggestion.review_confirmed)
        self.assertEqual(len(suggestion.evidence), 2)
        self.assertTrue(
            all(
                item.record_id
                and item.record_key
                and item.kind
                and item.atom_mapping
                for item in suggestion.evidence
            )
        )
        decisions = self.module.import_commit_decisions(
            state,
            rows,
            conformer_rows=suggestions,
            project_session=self.session,
        )
        self.assertEqual(decisions.conformer_grouping_decisions, ())

        suggestion.grouping_action = "accept_group"
        suggestion.review_confirmed = suggestion.requires_review
        decisions = self.module.import_commit_decisions(
            state,
            rows,
            conformer_rows=suggestions,
            project_session=self.session,
        )
        self.assertEqual(
            decisions.conformer_grouping_decisions[0].suggestion.id,
            UUID(suggestion.suggestion_id),
        )
        result = self.module.commit_project_import(
            self.session,
            state,
            rows,
            conformer_rows=suggestions,
            collection=object(),
            apply_view=lambda *_args, **_kwargs: (),
        )
        self.assertEqual(result.status, "committed")
        self.assertEqual(
            sum(
                type(dataset).__name__ == "ConformerSet"
                for dataset in self.session.project.datasets.values()
            ),
            1,
        )
        reopened = open_project(result.commit_result.sidecar_path)
        try:
            self.assertEqual(
                sum(
                    type(dataset).__name__ == "ConformerSet"
                    for dataset in reopened.datasets.values()
                ),
                1,
            )
        finally:
            close_project(reopened)







    def test_cube_projection_shows_grid_volume_default(self):
        registry, state = self.stage(
            "tests/fixtures/cube/sheared.cube"
        )

        row = self.module.project_import_preview(
            self.session,
            state,
            registry,
        )[0]

        self.assertEqual(
            row.default_view_label,
            "Default view: Grid Volume",
        )
        self.assertEqual(row.grid_dataset_count, 1)
        self.assertEqual(row.grid_shape, "2 × 2 × 2")
        self.assertEqual(row.grid_coordinate_unit, "bohr")
        self.assertEqual(row.grid_value_unit, "unknown")
        self.assertEqual(row.grid_quality, "ambiguous")


    def test_projection_refreshes_grouping_snapshot_without_confirming_it(self):
        registry, state = self.stage(
            "tests/fixtures/xyz/water.xyz",
            "tests/fixtures/xyz/water-trajectory.xyz",
        )

        rows = self.module.project_import_preview(
            self.session,
            state,
            registry,
        )

        self.assertTrue(state.preview.grouping_suggestion_ids)
        result = self.module.commit_project_import(
            self.session,
            state,
            rows,
            collection=object(),
            apply_view=lambda *_args, **_kwargs: (),
        )
        self.assertEqual(result.status, "committed")
        self.assertEqual(result.commit_result.calculation_group_ids, ())

    def test_two_candidate_target_projection_starts_unselected(self):
        registry, state = self.stage_two_candidate_conflict()

        row = self.module.project_import_preview(
            self.session,
            state,
            registry,
        )[0]

        self.assertEqual(len(row.conflict_candidates), 2)
        self.assertEqual(
            tuple(
                candidate.revision_id
                for candidate in row.conflict_candidates
            ),
            tuple(
                str(candidate.revision_id)
                for candidate in state.conflicts[0].candidates
            ),
        )
        self.assertEqual(
            tuple(
                (
                    candidate.source_id,
                    candidate.created_entity_count,
                    candidate.selected,
                )
                for candidate in row.conflict_candidates
            ),
            tuple(
                (
                    str(candidate.source_id),
                    len(candidate.created_entity_ids),
                    False,
                )
                for candidate in state.conflicts[0].candidates
            ),
        )
        self.assertTrue(
            all(
                candidate.display_label
                for candidate in row.conflict_candidates
            )
        )
        self.assertEqual(
            tuple(
                item[0]
                for item in self.module._conflict_action_items(row, None)
            ),
            tuple(row.allowed_actions.split(",")),
        )

    def test_target_decision_requires_one_live_candidate_and_binds_either(self):
        registry, state = self.stage_two_candidate_conflict()
        row = self.module.project_import_preview(
            self.session,
            state,
            registry,
        )[0]
        row.conflict_action = "reuse_existing"

        with self.assertRaisesRegex(ValueError, "select.*target"):
            self.module.import_commit_decisions(
                state,
                (row,),
                project_session=self.session,
            )

        conflict = state.conflicts[0]
        for selected_index, expected in enumerate(conflict.candidates):
            for index, candidate in enumerate(row.conflict_candidates):
                candidate.selected = index == selected_index
            decisions = self.module.import_commit_decisions(
                state,
                (row,),
                project_session=self.session,
            )
            self.assertEqual(
                decisions.conflict_decisions[
                    conflict.id
                ].existing_revision_id,
                expected.revision_id,
            )

        forged = replace(
            row,
            conflict_candidates=(
                replace(
                    row.conflict_candidates[0],
                    revision_id=str(uuid4()),
                    selected=True,
                ),
                replace(row.conflict_candidates[1], selected=False),
            ),
        )
        with self.assertRaisesRegex(ValueError, "target.*allowed"):
            self.module.import_commit_decisions(
                state,
                (forged,),
                project_session=self.session,
            )

    def test_grouping_projection_defaults_to_keep_independent(self):
        registry, state = self.stage(
            "tests/fixtures/xyz/water.xyz",
            "tests/fixtures/xyz/water-trajectory.xyz",
        )
        rows = self.module.project_import_preview(
            self.session,
            state,
            registry,
        )

        suggestions = self.module.project_grouping_suggestions(state)

        self.assertEqual(len(suggestions), 1)
        suggestion = suggestions[0]
        self.assertEqual(suggestion.source_count, 2)
        self.assertIn(suggestion.confidence, {"high", "medium", "low"})
        self.assertFalse(suggestion.requires_review)
        self.assertEqual(suggestion.grouping_action, "keep_independent")
        self.assertTrue(suggestion.evidence)
        self.assertTrue(
            all(
                UUID(item.evidence_id)
                and item.source_revision_ids
                and item.kind
                and item.summary
                and isinstance(item.metric, str)
                and isinstance(item.metric_unit, str)
                for item in suggestion.evidence
            )
        )
        decisions = self.module.import_commit_decisions(
            state,
            rows,
            grouping_rows=suggestions,
            project_session=self.session,
        )
        self.assertEqual(decisions.grouping_decisions, ())

    def test_accept_group_uses_selected_evidence_and_round_trips(self):
        registry, state = self.stage(
            "tests/fixtures/xyz/water.xyz",
            "tests/fixtures/xyz/water-trajectory.xyz",
        )
        rows = self.module.project_import_preview(
            self.session,
            state,
            registry,
        )
        suggestions = self.module.project_grouping_suggestions(state)
        suggestions[0].grouping_action = "accept_group"
        suggestions[0].evidence[-1].selected = False
        selected_ids = tuple(
            UUID(item.evidence_id)
            for item in suggestions[0].evidence
            if item.selected
        )

        result = self.module.commit_project_import(
            self.session,
            state,
            rows,
            grouping_rows=suggestions,
            collection=object(),
            apply_view=lambda *_args, **_kwargs: (),
        )

        self.assertEqual(len(result.commit_result.calculation_group_ids), 1)
        group = next(iter(self.session.project.calculation_groups.values()))
        self.assertEqual(group.evidence_ids, tuple(sorted(selected_ids, key=str)))
        reopened = open_project(result.commit_result.sidecar_path)
        try:
            self.assertEqual(
                reopened.calculation_groups,
                self.session.project.calculation_groups,
            )
        finally:
            close_project(reopened)

    def test_review_group_requires_separate_confirmation(self):
        registry, state = self.stage(
            "tests/fixtures/xyz/water.xyz",
            "tests/fixtures/xyz/water-trajectory.xyz",
        )
        revisions = tuple(
            state.staging_session.result(
                row.staged_batch_ids[0]
            ).source_revisions[0].id
            for row in state.preview.source_previews
        )
        evidence = GroupingEvidence(
            kind="periodic_equivalence_conflict",
            source_revision_ids=revisions,
            summary="primitive/conventional review",
            metric=2.0,
            metric_unit="cell_volume_ratio",
        )
        live = SourceGroupSuggestion(
            source_revision_ids=revisions,
            evidence=(evidence,),
        )
        with patch.object(
            self.module,
            "suggest_source_groups",
            return_value=(live,),
        ):
            rows = self.module.project_import_preview(
                self.session,
                state,
                registry,
            )
            suggestions = self.module.project_grouping_suggestions(state)
            suggestions[0].grouping_action = "accept_group"
            with self.assertRaisesRegex(ValueError, "review.*confirm"):
                self.module.import_commit_decisions(
                    state,
                    rows,
                    grouping_rows=suggestions,
                    project_session=self.session,
                )
            suggestions[0].review_confirmed = True
            decisions = self.module.import_commit_decisions(
                state,
                rows,
                grouping_rows=suggestions,
                project_session=self.session,
            )

        self.assertEqual(
            decisions.grouping_decisions[0].evidence_ids,
            (evidence.id,),
        )

    def test_changed_grouping_suggestion_fails_closed(self):
        registry, state = self.stage(
            "tests/fixtures/xyz/water.xyz",
            "tests/fixtures/xyz/water-trajectory.xyz",
        )
        rows = self.module.project_import_preview(
            self.session,
            state,
            registry,
        )
        suggestions = self.module.project_grouping_suggestions(state)

        with patch.object(
            self.module,
            "suggest_source_groups",
            return_value=(),
        ):
            with self.assertRaisesRegex(ValueError, "grouping.*changed"):
                self.module.import_commit_decisions(
                    state,
                    rows,
                    grouping_rows=suggestions,
                    project_session=self.session,
                )

    def test_invalid_conflict_action_is_rejected_against_live_conflict(self):
        registry, state = self.stage("tests/fixtures/xyz/water.xyz")
        rows = self.module.project_import_preview(
            self.session,
            state,
            registry,
        )
        self.module.commit_project_import(
            self.session,
            state,
            rows,
            collection=object(),
            apply_view=lambda *_args, **_kwargs: (),
        )
        registry, state = self.stage("tests/fixtures/xyz/water.xyz")
        row = self.module.project_import_preview(
            self.session,
            state,
            registry,
        )[0]
        row.conflict_action = "new_revision"

        with self.assertRaisesRegex(ValueError, "allowed"):
            self.module.commit_project_import(
                self.session,
                state,
                (row,),
                collection=object(),
                apply_view=lambda *_args, **_kwargs: (),
            )

    def test_cancel_discards_staging_without_project_or_scene_changes(self):
        _registry, state = self.stage(
            "tests/fixtures/xyz/water.xyz",
            "tests/fixtures/cube/sheared.cube",
        )
        before = self.snapshot(self.session)
        root = state.staging_session.root
        scene_objects = tuple(self.fake_bpy.data.objects.removed)

        self.module.cancel_project_import(self.session)

        self.assertEqual(self.snapshot(self.session), before)
        self.assertEqual(tuple(self.fake_bpy.data.objects.removed), scene_objects)
        self.assertFalse(root.exists())
        self.assertIsNone(state.preview)
        self.assertIsNone(state.staging_session)

    def test_public_preview_cancellation_updates_visible_summary(self):
        for operator_name, method in (
            ("CHEMBLENDER_OT_confirm_import", "cancel"),
            ("CHEMBLENDER_OT_cancel_import", "execute"),
        ):
            with self.subTest(operator=operator_name):
                _registry, state = self.stage("tests/fixtures/xyz/water.xyz")
                before = self.snapshot(self.session)
                settings = SimpleNamespace(recent_summary="1 source(s) staged via xyz")
                context = SimpleNamespace(
                    scene=SimpleNamespace(chemblender_quick_import=settings)
                )
                operator = getattr(self.module, operator_name)()
                with patch.object(self.module, "get_scene_session", return_value=self.session):
                    getattr(operator, method)(context)
                self.assertEqual(settings.recent_summary, "Import cancelled")
                self.assertIsNone(state.staging_session)
                self.assertIsNone(state.preview)
                self.assertEqual(self.snapshot(self.session), before)

    def test_canonical_diagnostics_survive_staging_cleanup_for_ui_actions(self):
        _registry, state = self.stage("tests/fixtures/xyz/water.xyz")
        report = state.diagnostics_report

        self.assertEqual(
            report["schema_name"],
            "chemblender_import_report",
        )
        self.assertEqual(report["schema_version"], 1)

        self.properties.discard_quick_import_preview(self.session)

        self.assertIs(state.diagnostics_report, report)
        self.assertIsNone(state.preview)
        self.assertIsNone(state.staging_session)

    def test_public_preview_rna_matches_dialog_and_clears_after_cancel(self):
        _registry, state = self.stage("tests/fixtures/xyz/water.xyz")
        session_ui = importlib.import_module("ChemBlender.ui.session")
        settings = SimpleNamespace(id_data=object())
        getter = self.properties.CHEMBLENDER_PG_quick_import.__annotations__[
            "preview_json"
        ].keywords["get"]
        with patch.object(session_ui, "get_scene_session", return_value=self.session):
            document = json.loads(getter(settings))
            self.assertEqual(len(document["rows"]), 1)
            self.assertIn("name", document["rows"][0])
            self.assertEqual(document["rows"][0]["reader_id"], "xyz")
            self.assertEqual(document["rows"][0]["quality"], "complete")
            self.assertFalse(document["rows"][0]["blocking"])
            self.assertTrue(document["rows"][0]["default_view"])
            self.module.cancel_project_import(self.session)
            self.assertEqual(getter(settings), "")

    def test_confirm_calls_transaction_once_creates_format_aware_plans(self):
        registry, state = self.stage(
            "tests/fixtures/xyz/water.xyz",
            "tests/fixtures/cube/sheared.cube",
        )
        rows = self.module.project_import_preview(
            self.session,
            state,
            registry,
        )
        calls = []
        view_calls = []
        original = self.module.commit_import_preview

        def commit_once(*args, **kwargs):
            calls.append(args)
            return original(*args, **kwargs)

        def apply(plan, project, *, collection, cache_root=None):
            binding = plan.bindings[0]
            registry = (
                project.structures
                if binding.entity_kind == "structure"
                else project.datasets
            )
            self.assertIn(binding.entity_id, registry)
            self.assertIsNotNone(collection)
            view_calls.append((plan.preset_id, cache_root))
            return ()

        with patch.object(
            self.module,
            "commit_import_preview",
            side_effect=commit_once,
        ):
            result = self.module.commit_project_import(
                self.session,
                state,
                rows,
                collection=object(),
                apply_view=apply,
            )

        self.assertEqual(len(calls), 1)
        self.assertEqual(
            tuple(value[0] for value in view_calls),
            ("structure_publication", "grid_volume"),
        )
        self.assertIsNone(view_calls[0][1])
        self.assertEqual(
            view_calls[1][1],
            self.session.temporary_root / "view-cache",
        )
        self.assertTrue(view_calls[1][1].is_dir())
        self.assertGreaterEqual(len(self.session.project.structures), 2)
        self.assertEqual(self.session.dirty_reasons, frozenset({"import"}))
        self.assertEqual(state.browser_revision, 1)
        self.assertIsNone(state.preview)
        self.assertEqual(result.status, "committed")
        self.assertGreaterEqual(result.created_view_count, 0)

    def test_disabled_default_view_creates_nothing_and_advances_browser_once(self):
        registry, state = self.stage(
            "tests/fixtures/cube/sheared.cube"
        )
        rows = self.module.project_import_preview(
            self.session,
            state,
            registry,
        )
        rows[0].default_view = False
        view_calls = []

        result = self.module.commit_project_import(
            self.session,
            state,
            rows,
            collection=object(),
            apply_view=lambda *_args, **_kwargs: view_calls.append(
                (_args, _kwargs)
            ),
        )

        self.assertEqual(view_calls, [])
        self.assertEqual(result.created_view_count, 0)
        self.assertEqual(state.browser_revision, 1)

    def test_direct_confirmation_preserves_explicit_default_view_choice(self):
        registry, state = self.stage("tests/fixtures/xyz/water.xyz")
        rows = self.module.project_import_preview(self.session, state, registry)
        rows[0].default_view = False
        operator = self.module.CHEMBLENDER_OT_confirm_import()
        operator.rows = _RNACollection()
        self.module._copy_projections(operator.rows, rows)
        operator.properties = SimpleNamespace(is_property_set=lambda name: name == "rows")
        context = SimpleNamespace(scene=SimpleNamespace(
            collection=object(), chemblender_quick_import=SimpleNamespace(recent_summary="")
        ))
        with (
            patch.object(self.module, "get_scene_session", return_value=self.session),
            patch.object(self.module, "get_reader_plugin_registry", return_value=registry),
            patch.object(self.module, "apply_scene_preset", return_value=()) as view,
        ):
            result = operator.execute(context)
        self.assertEqual(result, {"FINISHED"})
        view.assert_not_called()
        self.assertEqual(len(self.session.project.structures), 1)

    def test_new_revision_never_creates_an_automatic_default_view(self):
        revision_id = uuid4()
        row = SimpleNamespace(
            conflict_id=str(uuid4()),
            conflict_action="new_revision",
            default_view=True,
        )
        result = SimpleNamespace(
            committed_source_revision_ids=(revision_id,),
            project=SimpleNamespace(
                source_revisions={
                    revision_id: SimpleNamespace(
                        created_entity_ids=(uuid4(),),
                    )
                },
                structures={},
                datasets={},
            ),
        )

        with patch.object(self.module, "plan_default_view") as planner:
            plans = self.module._committed_default_view_plans(
                result,
                (row,),
            )

        self.assertEqual(plans, ())
        planner.assert_not_called()

    def test_normal_import_preserves_unresolved_revision_prompts(self):
        existing = self.module.RevisionViewPrompt(
            current_revision_id=uuid4(),
            new_revision_id=uuid4(),
        )
        registry, state = self.stage("tests/fixtures/xyz/water.xyz")
        state.revision_prompts = (existing,)
        rows = self.module.project_import_preview(
            self.session,
            state,
            registry,
        )

        self.module.commit_project_import(
            self.session,
            state,
            rows,
            collection=object(),
            apply_view=lambda *_args, **_kwargs: (),
        )

        self.assertEqual(state.revision_prompts, (existing,))

    def test_revision_prompt_merge_is_stable_and_pair_deduplicated(self):
        first = self.module.RevisionViewPrompt(
            current_revision_id=uuid4(),
            new_revision_id=uuid4(),
        )
        second = self.module.RevisionViewPrompt(
            current_revision_id=uuid4(),
            new_revision_id=uuid4(),
        )
        duplicate = self.module.RevisionViewPrompt(
            current_revision_id=first.current_revision_id,
            new_revision_id=first.new_revision_id,
        )

        merged = self.module._merge_revision_prompts(
            (first, second),
            (duplicate, first),
        )

        self.assertEqual(merged, (first, second))

    def test_new_revision_prompt_records_exact_revision_pair(self):
        source_id = uuid4()
        conflict_id = uuid4()
        current_revision_id = uuid4()
        new_revision_id = uuid4()
        row = SimpleNamespace(
            source_id=str(source_id),
            conflict_id=str(conflict_id),
            conflict_action="new_revision",
        )
        candidate = SimpleNamespace(
            revision_id=current_revision_id,
        )
        conflict = SimpleNamespace(
            id=conflict_id,
            staged_source_id=source_id,
            candidates=(candidate,),
        )
        result = SimpleNamespace(
            committed_source_revision_ids=(new_revision_id,),
            project=SimpleNamespace(
                source_revisions={
                    new_revision_id: SimpleNamespace()
                },
            ),
        )

        prompts = self.module._committed_revision_prompts(
            result,
            (row,),
            (conflict,),
        )

        self.assertEqual(len(prompts), 1)
        self.assertEqual(
            prompts[0].current_revision_id,
            current_revision_id,
        )
        self.assertEqual(prompts[0].new_revision_id, new_revision_id)
        self.assertEqual(prompts[0].action, "keep_current")

    def test_sequential_xyz_cube_commits_rotate_owned_sidecar_generation(self):
        registry, state = self.stage("tests/fixtures/xyz/water.xyz")
        rows = self.module.project_import_preview(
            self.session,
            state,
            registry,
        )
        self.module.commit_project_import(
            self.session,
            state,
            rows,
            collection=object(),
            apply_view=lambda *_args, **_kwargs: (),
        )
        first_generation = self.session.sidecar_path
        self.assertTrue(first_generation.is_dir())
        self.assertRegex(first_generation.name, r"^g[0-9a-f]{8}\.cbq$")

        registry, state = self.stage("tests/fixtures/cube/sheared.cube")
        rows = self.module.project_import_preview(
            self.session,
            state,
            registry,
        )
        self.module.commit_project_import(
            self.session,
            state,
            rows,
            collection=object(),
            apply_view=lambda *_args, **_kwargs: (),
        )
        second_generation = self.session.sidecar_path

        self.assertNotEqual(first_generation, second_generation)
        self.assertRegex(second_generation.name, r"^g[0-9a-f]{8}\.cbq$")
        self.assertFalse(first_generation.exists())
        self.assertTrue(second_generation.is_dir())
        self.assertEqual(
            tuple(self.session.temporary_root.glob("*.cbq")),
            (second_generation,),
        )

    def test_failed_commit_restores_session_and_removes_failed_generation(self):
        registry, state = self.stage("tests/fixtures/xyz/water.xyz")
        rows = self.module.project_import_preview(
            self.session,
            state,
            registry,
        )
        self.module.commit_project_import(
            self.session,
            state,
            rows,
            collection=object(),
            apply_view=lambda *_args, **_kwargs: (),
        )
        original_path = self.session.sidecar_path
        original_project = self.session.project
        original_dirty = self.session.dirty_reasons
        original_manifest = (original_path / "manifest.json").read_bytes()

        registry, state = self.stage("tests/fixtures/cube/sheared.cube")
        rows = self.module.project_import_preview(
            self.session,
            state,
            registry,
        )
        observed_paths = []

        def fail_after_creating_generation(
            project_session,
            *_args,
            **_kwargs,
        ):
            observed_paths.append(project_session.sidecar_path)
            project_session.sidecar_path.mkdir()
            (project_session.sidecar_path / "partial").write_bytes(b"partial")
            raise OSError("simulated publication failure")

        with patch.object(
            self.module,
            "commit_import_preview",
            side_effect=fail_after_creating_generation,
        ):
            with self.assertRaisesRegex(OSError, "publication failure"):
                self.module.commit_project_import(
                    self.session,
                    state,
                    rows,
                    collection=object(),
                    apply_view=lambda *_args, **_kwargs: (),
                )

        self.assertEqual(len(observed_paths), 1)
        self.assertNotEqual(observed_paths[0], original_path)
        self.assertFalse(observed_paths[0].exists())
        self.assertIs(self.session.project, original_project)
        self.assertEqual(self.session.sidecar_path, original_path)
        self.assertEqual(self.session.dirty_reasons, original_dirty)
        self.assertEqual(
            (original_path / "manifest.json").read_bytes(),
            original_manifest,
        )


    def test_generation_cleanup_failure_is_reported_without_losing_data(self):
        registry, state = self.stage("tests/fixtures/xyz/water.xyz")
        rows = self.module.project_import_preview(
            self.session,
            state,
            registry,
        )
        self.module.commit_project_import(
            self.session,
            state,
            rows,
            collection=object(),
            apply_view=lambda *_args, **_kwargs: (),
        )
        first_generation = self.session.sidecar_path

        registry, state = self.stage("tests/fixtures/cube/sheared.cube")
        rows = self.module.project_import_preview(
            self.session,
            state,
            registry,
        )
        original_cleanup = self.module._remove_owned_temporary_generation

        def fail_old_generation(project_session, path):
            if path == first_generation:
                raise OSError("generation cleanup failed")
            return original_cleanup(project_session, path)

        with patch.object(
            self.module,
            "_remove_owned_temporary_generation",
            side_effect=fail_old_generation,
        ):
            result = self.module.commit_project_import(
                self.session,
                state,
                rows,
                collection=object(),
                apply_view=lambda *_args, **_kwargs: (),
            )

        self.assertEqual(result.status, "data committed; cleanup pending")
        self.assertTrue(first_generation.exists())
        self.assertNotEqual(self.session.sidecar_path, first_generation)
        self.assertGreaterEqual(len(self.session.project.datasets), 1)


    def test_view_failure_removes_prior_objects_but_keeps_committed_data(self):
        registry, state = self.stage(
            "tests/fixtures/cube/sheared.cube",
            "tests/fixtures/xyz/water.xyz",
        )
        rows = self.module.project_import_preview(
            self.session,
            state,
            registry,
        )
        created = SimpleNamespace(type="VOLUME", data=None, modifiers=(), children=())
        calls = 0
        presets = []

        def fail_second(plan, *_args, **_kwargs):
            nonlocal calls
            calls += 1
            presets.append(plan.preset_id)
            if calls == 1:
                return (created,)
            raise RuntimeError("simulated view failure")

        result = self.module.commit_project_import(
            self.session,
            state,
            rows,
            collection=object(),
            apply_view=fail_second,
        )

        self.assertEqual(result.status, "data committed; view failed")
        self.assertEqual(presets, ["grid_volume", "structure_publication"])
        self.assertGreaterEqual(len(self.session.project.structures), 2)
        self.assertEqual(
            self.fake_bpy.data.objects.removed,
            [(created, True)],
        )
        self.assertEqual(state.browser_revision, 1)
        self.assertIsNone(state.preview)

    def test_fatal_view_failure_removes_prior_objects_before_reraising(self):
        registry, state = self.stage(
            "tests/fixtures/cube/sheared.cube",
            "tests/fixtures/xyz/water.xyz",
        )
        rows = self.module.project_import_preview(
            self.session,
            state,
            registry,
        )
        created = SimpleNamespace(type="MESH", data=None, modifiers=(), children=())
        calls = 0
        fatal = GeneratorExit("view generation stopped")

        def fail_second(_plan, *_args, **_kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                return (created,)
            raise fatal

        with self.assertRaises(GeneratorExit) as raised:
            self.module.commit_project_import(
                self.session,
                state,
                rows,
                collection=object(),
                apply_view=fail_second,
            )

        self.assertIs(raised.exception, fatal)
        self.assertEqual(
            self.fake_bpy.data.objects.removed,
            [(created, True)],
        )

    def test_quick_import_structure_preset_creates_biological_default_view(self):
        registry, state = self.stage("tests/fixtures/pdb/conect.pdb")
        rows = self.module.project_import_preview(
            self.session,
            state,
            registry,
        )
        scene_preset_view = importlib.import_module(
            "ChemBlender.scene_preset_view"
        )
        created = {}

        class View(dict):
            children = ()
            parent = None

        def capture(*args, **kwargs):
            created["args"] = args
            created["kwargs"] = kwargs
            return View()

        self.fake_bpy.context.scene = SimpleNamespace(
            chemblender_topology=SimpleNamespace(
                decisions_json=json.dumps(
                    {
                        str(uuid4()): {
                            "accepted": None,
                            "rejected": [],
                        }
                    }
                )
            )
        )
        with patch.object(
            scene_preset_view,
            "create_structure_view",
            side_effect=capture,
        ):
            result = self.module.commit_project_import(
                self.session,
                state,
                rows,
                collection=object(),
                apply_view=scene_preset_view.apply_scene_preset,
            )

        structure = created["args"][0]
        hierarchy = created["kwargs"]["biological_hierarchy"]
        properties = created["kwargs"]["atomic_properties"]
        self.assertEqual(result.status, "committed")
        self.assertEqual(hierarchy.structure_id, structure.id)
        self.assertEqual(
            {value.semantic_role for value in properties},
            {"occupancy", "b_factor"},
        )
        self.assertEqual(created["args"][1].structure_id, structure.id)
        self.assertTrue(created["args"][2].attach_ball_and_stick)

    def test_quick_import_rejects_stale_current_structure_topology_decision(self):
        registry, state = self.stage("tests/fixtures/pdb/conect.pdb")
        rows = self.module.project_import_preview(
            self.session,
            state,
            registry,
        )
        staged_source = state.preview.source_previews[0]
        batch = state.staging_session.result(
            staged_source.staged_batch_ids[0]
        )
        structure = batch.structures[0]
        self.fake_bpy.context.scene = SimpleNamespace(
            chemblender_topology=SimpleNamespace(
                decisions_json=json.dumps(
                    {
                        str(structure.id): {
                            "accepted": str(uuid4()),
                            "rejected": [],
                        }
                    }
                )
            )
        )
        scene_preset_view = importlib.import_module(
            "ChemBlender.scene_preset_view"
        )
        with patch.object(
            scene_preset_view,
            "create_structure_view",
        ) as create:
            result = self.module.commit_project_import(
                self.session,
                state,
                rows,
                collection=object(),
                apply_view=scene_preset_view.apply_scene_preset,
            )

        self.assertEqual(result.status, "data committed; view failed")
        create.assert_not_called()

    def test_view_failure_uses_surface_cleanup_for_prior_surface_objects(self):
        registry, state = self.stage(
            "tests/fixtures/cube/sheared.cube",
            "tests/fixtures/xyz/water.xyz",
        )
        rows = self.module.project_import_preview(
            self.session,
            state,
            registry,
        )
        surface = SimpleNamespace(
            type="VOLUME",
            children=(),
            data=SimpleNamespace(users=0),
            modifiers=(SimpleNamespace(node_group={"cbq_contract": "isosurface_v1"}),),
        )
        property_surface = SimpleNamespace(
            type="VOLUME",
            children=(),
            data=SimpleNamespace(users=0),
            modifiers=(SimpleNamespace(node_group={"cbq_contract": "property_surface_v1"}),),
        )
        ordinary = SimpleNamespace(type="MESH", data=None, modifiers=(), children=())
        calls = 0

        def fail_second(_plan, *_args, **_kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                return (surface, property_surface, ordinary)
            raise RuntimeError("simulated later view failure")

        scene_preset_view = importlib.import_module(
            "ChemBlender.scene_preset_view"
        )
        cleaned_surfaces = []
        with patch.object(
            scene_preset_view,
            "remove_surface_object",
            side_effect=cleaned_surfaces.append,
        ):
            result = self.module.commit_project_import(
                self.session,
                state,
                rows,
                collection=object(),
                apply_view=fail_second,
            )

        self.assertEqual(result.status, "data committed; view failed")
        self.assertEqual(cleaned_surfaces, [property_surface, surface])
        self.assertEqual(
            self.fake_bpy.data.objects.removed,
            [(ordinary, True)],
        )
        self.assertGreaterEqual(len(self.session.project.structures), 2)
        self.assertEqual(state.browser_revision, 1)
        self.assertIsNone(state.preview)

    def test_background_operator_reports_post_commit_view_failure_as_warning(self):
        registry, _state = self.stage("tests/fixtures/xyz/water.xyz")
        context = SimpleNamespace(
            scene=SimpleNamespace(
                collection=object(),
                chemblender_quick_import=SimpleNamespace(
                    recent_summary="",
                ),
            ),
        )
        operator = self.module.CHEMBLENDER_OT_confirm_import()
        operator.rows = _RNACollection()
        operator.blocking_reason = ""

        with patch.object(
            self.module,
            "get_scene_session",
            return_value=self.session,
        ), patch.object(
            self.module,
            "get_reader_plugin_registry",
            return_value=registry,
        ), patch.object(
            self.module,
            "apply_scene_preset",
            side_effect=RuntimeError("simulated view failure"),
        ):
            result = operator.execute(context)

        self.assertEqual(result, {"FINISHED"})
        self.assertEqual(operator.last_report[0], {"WARNING"})
        self.assertEqual(
            operator.last_report[1],
            "data committed; view failed",
        )
        self.assertEqual(
            context.scene.chemblender_quick_import.recent_summary,
            "data committed; view failed",
        )

    def test_post_commit_cleanup_failure_reports_committed_and_is_retryable(self):
        registry, state = self.stage("tests/fixtures/xyz/water.xyz")
        rows = self.module.project_import_preview(
            self.session,
            state,
            registry,
        )
        with patch.object(
            StagedImportSession,
            "discard",
            side_effect=OSError("cleanup failed"),
        ):
            result = self.module.commit_project_import(
                self.session,
                state,
                rows,
                collection=object(),
                apply_view=lambda *_args, **_kwargs: (),
            )

        self.assertEqual(result.status, "data committed; cleanup pending")
        self.assertGreaterEqual(len(self.session.project.structures), 1)
        self.assertEqual(state.browser_revision, 1)
        self.assertIsNotNone(state.preview)
        self.module.cancel_project_import(self.session)
        self.assertIsNone(state.preview)

    def test_blocking_preview_operator_rejects_confirm(self):
        registry, state = self.stage("tests/fixtures/xyz/water.xyz")
        preview = state.preview
        state.preview = type(preview)(
            preview.session_id,
            tuple(
                type(row)(
                    source_id=row.source_id,
                    source_path=row.source_path,
                    selected_reader_id=row.selected_reader_id,
                    content_hash=row.content_hash,
                    byte_size=row.byte_size,
                    capabilities=row.capabilities,
                    diagnostic_ids=row.diagnostic_ids,
                )
                for row in preview.source_previews
            ),
            diagnostic_ids=preview.diagnostic_ids,
        )
        context = SimpleNamespace(
            scene=SimpleNamespace(
                collection=object(),
                chemblender_quick_import=SimpleNamespace(
                    recent_summary="",
                ),
            ),
        )
        operator = self.module.CHEMBLENDER_OT_confirm_import()
        operator.rows = _RNACollection()
        operator.blocking_reason = ""

        with patch.object(
            self.module,
            "get_scene_session",
            return_value=self.session,
        ), patch.object(
            self.module,
            "get_reader_plugin_registry",
            return_value=registry,
        ):
            result = operator.execute(context)

        self.assertEqual(result, {"CANCELLED"})
        self.assertIn("staged batch", operator.last_report[1])
        self.assertEqual(len(self.session.project.structures), 0)

    def test_session_cleanup_waits_for_an_active_commit_owner(self):
        registry, state = self.stage("tests/fixtures/xyz/water.xyz")
        rows = self.module.project_import_preview(
            self.session,
            state,
            registry,
        )
        entered = threading.Event()
        release = threading.Event()
        original = self.module.commit_import_preview

        def delayed_commit(*args, **kwargs):
            entered.set()
            release.wait(2)
            return original(*args, **kwargs)

        job = self.module._CommitJob(
            self.session,
            state.staging_session,
            state.preview,
            self.module.import_commit_decisions(state, rows),
        )
        with patch.object(
            self.module,
            "commit_import_preview",
            side_effect=delayed_commit,
        ):
            self.properties.store_quick_import_job(
                self.session,
                state.staging_session,
                job,
            )
            job.start()
            self.assertTrue(entered.wait(1))
            cleanup = threading.Thread(
                target=self.properties.clear_quick_import_state,
                args=(self.session,),
            )
            cleanup.start()
            time.sleep(0.55)
            self.assertTrue(cleanup.is_alive())
            release.set()
            cleanup.join(2)

        self.assertFalse(cleanup.is_alive())
        self.assertIsInstance(job.error, self.module.ImportCancelled)
        self.assertNotIn(
            self.session.id,
            self.properties._QUICK_IMPORT_STATES,
        )

    def test_interactive_confirm_is_modal_and_cancel_does_not_claim_rollback(self):
        registry, state = self.stage("tests/fixtures/xyz/water.xyz")
        entered = threading.Event()
        release = threading.Event()
        original = self.module.commit_import_preview
        calls = []
        timer = object()
        manager = SimpleNamespace(
            event_timer_add=lambda interval, *, window: (
                calls.append(("timer_add", interval, window)) or timer
            ),
            event_timer_remove=lambda value: calls.append(
                ("timer_remove", value)
            ),
            progress_begin=lambda low, high: calls.append(
                ("progress_begin", low, high)
            ),
            progress_update=lambda value: calls.append(
                ("progress_update", value)
            ),
            progress_end=lambda: calls.append(("progress_end",)),
            modal_handler_add=lambda value: calls.append(("modal", value)),
        )
        context = SimpleNamespace(
            scene=SimpleNamespace(
                collection=object(),
                chemblender_quick_import=SimpleNamespace(
                    recent_summary="",
                ),
            ),
            window=object(),
            window_manager=manager,
        )
        operator = self.module.CHEMBLENDER_OT_confirm_import()
        operator.rows = _RNACollection()
        operator.blocking_reason = ""
        self.fake_bpy.app.background = False

        def delayed(*args, **kwargs):
            entered.set()
            release.wait(2)
            return original(*args, **kwargs)

        with patch.object(
            self.module,
            "get_scene_session",
            return_value=self.session,
        ), patch.object(
            self.module,
            "get_reader_plugin_registry",
            return_value=registry,
        ), patch.object(
            self.module,
            "commit_import_preview",
            side_effect=delayed,
        ), patch.object(
            self.module,
            "apply_scene_preset",
            return_value=(),
        ):
            started = time.monotonic()
            result = operator.execute(context)
            elapsed = time.monotonic() - started
            self.assertEqual(result, {"RUNNING_MODAL"})
            self.assertLess(elapsed, 0.5)
            self.assertTrue(entered.wait(1))
            self.assertEqual(
                operator.modal(context, SimpleNamespace(type="ESC")),
                {"RUNNING_MODAL"},
            )
            self.assertIn("cannot undo", operator.last_report[1])
            release.set()
            for _ in range(100):
                result = operator.modal(
                    context,
                    SimpleNamespace(type="TIMER"),
                )
                if result != {"RUNNING_MODAL"}:
                    break
                time.sleep(0.01)

        self.assertEqual(result, {"CANCELLED"})
        self.assertEqual(len(self.session.project.structures), 0)
        self.assertIn(("timer_remove", timer), calls)
        self.assertIn(("progress_end",), calls)
        self.assertFalse(
            any(call[:2] == ("progress_update", 100) for call in calls),
            calls,
        )

    def test_commit_job_forwards_materialization_progress_and_cancellation(self):
        observed = {}
        expected = object()

        def commit(
            project_session,
            staging,
            preview,
            decisions,
            *,
            progress,
            is_cancelled,
        ):
            observed["arguments"] = (
                project_session,
                staging,
                preview,
                decisions,
            )
            observed["is_cancelled"] = is_cancelled
            progress("materialize", 1, 4)
            return expected

        job = self.module._CommitJob(
            self.session,
            object(),
            object(),
            object(),
        )
        with patch.object(
            self.module,
            "_commit_to_fresh_generation",
            side_effect=commit,
        ):
            job._run()

        self.assertIs(job.result, expected)
        self.assertIsNone(job.error)
        self.assertEqual(job.drain_progress(), ("materialize", 1, 4))
        self.assertEqual(job.task.snapshot().state.value, "succeeded")
        self.assertFalse(observed["is_cancelled"]())
        job.cancel()
        self.assertTrue(observed["is_cancelled"]())
        self.assertEqual(job.task.snapshot().state.value, "succeeded")

    def test_commit_job_marks_publication_cancellation_cancelled(self):
        job = self.module._CommitJob(
            self.session,
            object(),
            object(),
            object(),
        )
        with patch.object(
            self.module,
            "_commit_to_fresh_generation",
            side_effect=PublicationCancelled("cancelled before publish"),
        ):
            job._run()

        self.assertIsInstance(job.error, PublicationCancelled)
        self.assertIsNone(job.result)
        self.assertEqual(job.task.snapshot().state.value, "cancelled")

    def test_modal_fatal_worker_error_rethrows_after_cleanup(self):
        timer = object()
        manager = SimpleNamespace(
            event_timer_add=lambda *_args, **_kwargs: timer,
            event_timer_remove=lambda _value: None,
            progress_begin=lambda *_args: None,
            progress_update=lambda *_args: None,
            progress_end=lambda: None,
            modal_handler_add=lambda *_args: None,
        )
        registry, state, context, operator = self.interactive_fixture(
            manager
        )
        staging_root = state.staging_session.root

        with (
            patch.object(
                self.module,
                "get_scene_session",
                return_value=self.session,
            ),
            patch.object(
                self.module,
                "get_reader_plugin_registry",
                return_value=registry,
            ),
            patch.object(
                self.module,
                "commit_import_preview",
                side_effect=MemoryError("worker exhausted memory"),
            ),
        ):
            self.assertEqual(operator.execute(context), {"RUNNING_MODAL"})
            self.assertTrue(operator._job.join(2))
            with self.assertRaisesRegex(MemoryError, "exhausted memory"):
                operator.modal(context, SimpleNamespace(type="TIMER"))

        self.assertIsNone(state.active_job)
        self.assertIsNone(state.staging_session)
        self.assertFalse(staging_root.exists())

    def test_fatal_ownership_cleanup_is_not_hidden_by_prior_error(self):
        operator = self.module.CHEMBLENDER_OT_confirm_import()
        job = SimpleNamespace(project_session=self.session)
        fatal = MemoryError("ownership cleanup exhausted memory")

        with patch.object(
            self.module,
            "finish_quick_import_job",
            side_effect=fatal,
        ), patch.object(
            self.module,
            "discard_quick_import_preview",
        ) as discard:
            with self.assertRaises(MemoryError) as raised:
                operator._finish_modal_ownership(
                    job,
                    None,
                    OSError("UI cleanup failed"),
                )

        self.assertIs(raised.exception, fatal)
        discard.assert_called_once_with(self.session)

    def test_modal_finalization_fatal_releases_ui_and_ownership(self):
        operator = self.module.CHEMBLENDER_OT_confirm_import()
        released = []
        job = SimpleNamespace(
            project_session=self.session,
            done=True,
            error=None,
            join=lambda _timeout: True,
            release_ui=lambda: released.append(True),
            timer_pending=False,
            abandon_ui=lambda: None,
        )
        operator._job = job
        state = self.properties.get_quick_import_state(self.session)
        state.active_job = job
        context = SimpleNamespace(window_manager=object())

        with patch.object(
            operator,
            "_finalize_committed_job",
            side_effect=MemoryError("finalization exhausted memory"),
        ):
            with self.assertRaises(MemoryError):
                operator.modal(context, SimpleNamespace(type="TIMER"))

        self.assertEqual(released, [True])
        self.assertIsNone(state.active_job)

    def test_modal_retries_timer_cleanup_before_reraising_finalization_fatal(self):
        operator = self.module.CHEMBLENDER_OT_confirm_import()
        releases = []
        job = SimpleNamespace(
            project_session=self.session,
            done=True,
            error=None,
            join=lambda _timeout: True,
            timer_pending=True,
            abandon_ui=lambda: None,
        )

        def release():
            releases.append(True)
            if len(releases) == 1:
                raise OSError("timer cleanup failed")
            job.timer_pending = False

        job.release_ui = release
        operator._job = job
        state = self.properties.get_quick_import_state(self.session)
        state.active_job = job
        context = SimpleNamespace(window_manager=object())
        fatal = MemoryError("finalization exhausted memory")

        with patch.object(
            operator,
            "_finalize_committed_job",
            side_effect=fatal,
        ):
            self.assertEqual(
                operator.modal(
                    context,
                    SimpleNamespace(type="TIMER"),
                ),
                {"RUNNING_MODAL"},
            )
            self.assertIs(state.active_job, job)
            with self.assertRaises(MemoryError) as raised:
                operator.modal(
                    context,
                    SimpleNamespace(type="TIMER"),
                )

        self.assertIs(raised.exception, fatal)
        self.assertEqual(releases, [True, True])
        self.assertIsNone(state.active_job)

    def test_modal_retries_timer_cleanup_without_repeating_commit_finalization(self):
        calls = []
        timer = object()
        timer_failures = 1

        def remove(value):
            nonlocal timer_failures
            calls.append(("timer_remove", value))
            if timer_failures:
                timer_failures -= 1
                raise OSError("timer cleanup failed")

        manager = SimpleNamespace(
            event_timer_add=lambda *_args, **_kwargs: timer,
            event_timer_remove=remove,
            progress_begin=lambda *_args: calls.append(
                ("progress_begin",)
            ),
            progress_update=lambda value: calls.append(
                ("progress_update", value)
            ),
            progress_end=lambda: calls.append(("progress_end",)),
            modal_handler_add=lambda *_args: None,
        )
        registry, state, context, operator = self.interactive_fixture(
            manager
        )
        views = []
        with patch.object(
            self.module,
            "get_scene_session",
            return_value=self.session,
        ), patch.object(
            self.module,
            "get_reader_plugin_registry",
            return_value=registry,
        ), patch.object(
            self.module,
            "apply_scene_preset",
            side_effect=lambda *_args, **_kwargs: (
                views.append("view") or ()
            ),
        ):
            self.assertEqual(operator.execute(context), {"RUNNING_MODAL"})
            self.assertTrue(operator._job.join(2))
            self.assertEqual(
                operator.modal(context, SimpleNamespace(type="TIMER")),
                {"RUNNING_MODAL"},
            )
            self.assertIs(state.active_job, operator._job)
            self.assertIsNone(state.preview)
            self.assertEqual(state.browser_revision, 1)
            self.assertEqual(
                operator.modal(context, SimpleNamespace(type="TIMER")),
                {"FINISHED"},
            )

        self.assertIsNone(state.active_job)
        self.assertEqual(views, ["view"])
        self.assertEqual(
            calls.count(("timer_remove", timer)),
            2,
        )
        self.assertEqual(calls.count(("progress_end",)), 1)

    def test_progress_cleanup_failure_after_timer_removal_still_finalizes(self):
        timer = object()
        calls = []
        manager = SimpleNamespace(
            event_timer_add=lambda *_args, **_kwargs: timer,
            event_timer_remove=lambda value: calls.append(
                ("timer_remove", value)
            ),
            progress_begin=lambda *_args: None,
            progress_update=lambda *_args: None,
            progress_end=lambda: (_ for _ in ()).throw(
                OSError("progress cleanup failed")
            ),
            modal_handler_add=lambda *_args: None,
        )
        registry, state, context, operator = self.interactive_fixture(
            manager
        )
        with patch.object(
            self.module,
            "get_scene_session",
            return_value=self.session,
        ), patch.object(
            self.module,
            "get_reader_plugin_registry",
            return_value=registry,
        ), patch.object(
            self.module,
            "apply_scene_preset",
            return_value=(),
        ):
            self.assertEqual(operator.execute(context), {"RUNNING_MODAL"})
            self.assertTrue(operator._job.join(2))
            result = operator.modal(
                context,
                SimpleNamespace(type="TIMER"),
            )

        self.assertEqual(result, {"FINISHED"})
        self.assertIsNone(state.active_job)
        self.assertIsNone(state.preview)
        self.assertEqual(state.browser_revision, 1)
        self.assertEqual(
            context.scene.chemblender_quick_import.recent_summary,
            "data committed; cleanup pending",
        )
        self.assertEqual(operator.last_report[0], {"WARNING"})
        self.assertIn(("timer_remove", timer), calls)

    def test_timer_setup_failure_releases_active_job_and_staging(self):
        calls = self.assert_setup_failure_releases_owned_state(
            "event_timer_add"
        )
        self.assertNotIn(("event_timer_remove",), calls)
        self.assertNotIn(("progress_end",), calls)

    def test_progress_setup_failure_releases_timer_and_active_state(self):
        calls = self.assert_setup_failure_releases_owned_state(
            "progress_update"
        )
        self.assertIn(("progress_end",), calls)
        self.assertIn(("event_timer_remove",), calls)

    def test_progress_begin_failure_releases_only_owned_timer(self):
        calls = self.assert_setup_failure_releases_owned_state(
            "progress_begin"
        )
        self.assertNotIn(("progress_end",), calls)
        self.assertIn(("event_timer_remove",), calls)

    def test_modal_handler_setup_failure_releases_ui_and_active_state(self):
        calls = self.assert_setup_failure_releases_owned_state(
            "modal_handler_add"
        )
        self.assertIn(("progress_end",), calls)
        self.assertIn(("event_timer_remove",), calls)

    def test_thread_start_failure_releases_ui_active_job_and_staging(self):
        calls = self.assert_setup_failure_releases_owned_state(
            "thread.start"
        )
        self.assertIn(("progress_end",), calls)
        self.assertIn(("event_timer_remove",), calls)

    def test_setup_failure_report_preserves_cleanup_error_notes(self):
        timer = object()
        progress_failures = 1
        timer_failures = 1

        def end_progress():
            nonlocal progress_failures
            if progress_failures:
                progress_failures -= 1
                raise OSError("progress release failed")

        def remove_timer(value):
            nonlocal timer_failures
            self.assertIs(value, timer)
            if timer_failures:
                timer_failures -= 1
                raise OSError("timer release failed")

        manager = SimpleNamespace(
            event_timer_add=lambda *_args, **_kwargs: timer,
            event_timer_remove=remove_timer,
            progress_begin=lambda *_args: None,
            progress_update=lambda *_args: (_ for _ in ()).throw(
                RuntimeError("setup progress failed")
            ),
            progress_end=end_progress,
            modal_handler_add=lambda *_args: None,
        )
        registry, state, context, operator = self.interactive_fixture(
            manager
        )
        staging = state.staging_session
        with patch.object(
            self.module,
            "get_scene_session",
            return_value=self.session,
        ), patch.object(
            self.module,
            "get_reader_plugin_registry",
            return_value=registry,
        ):
            result = operator.execute(context)

        self.assertEqual(result, {"CANCELLED"})
        self.assertIn("setup progress failed", operator.last_report[1])
        self.assertIn("progress release failed", operator.last_report[1])
        self.assertIn("timer release failed", operator.last_report[1])
        job = state.active_job
        self.assertIsNotNone(job)
        self.assertIs(state.staging_session, staging)
        self.assertTrue(staging.root.exists())
        self.assertIs(job._window_manager, manager)
        self.assertIs(job._timer, timer)
        self.assertTrue(job._progress_started)

        self.properties.clear_quick_import_state(self.session)

        fresh_state = self.properties.get_quick_import_state(self.session)
        self.assertIsNone(fresh_state.active_job)
        self.assertIsNone(fresh_state.staging_session)
        self.assertIsNone(job._window_manager)
        self.assertIsNone(job._timer)
        self.assertFalse(job._progress_started)
        self.assertFalse(staging.root.exists())

    def test_invoke_projects_rows_and_opens_modal_dialog(self):
        registry, _state = self.stage("tests/fixtures/xyz/water.xyz")
        calls = []
        context = SimpleNamespace(
            scene=SimpleNamespace(collection=object()),
            window_manager=SimpleNamespace(
                invoke_props_dialog=lambda operator, *, width: (
                    calls.append((operator, width))
                    or {"RUNNING_MODAL"}
                )
            ),
        )
        operator = self.module.CHEMBLENDER_OT_confirm_import()
        operator.rows = _RNACollection()
        operator.blocking_reason = ""

        with patch.object(
            self.module,
            "get_scene_session",
            return_value=self.session,
        ), patch.object(
            self.module,
            "get_reader_plugin_registry",
            return_value=registry,
        ):
            result = operator.invoke(context, None)

        self.assertEqual(result, {"RUNNING_MODAL"})
        self.assertEqual(calls, [(operator, 720)])
        self.assertEqual(len(operator.rows), 1)

    def test_invoke_does_not_convert_fatal_errors_to_cancelled(self):
        context = SimpleNamespace(scene=object())
        for fatal_type in (
            KeyboardInterrupt,
            SystemExit,
            GeneratorExit,
            MemoryError,
        ):
            with self.subTest(fatal_type=fatal_type.__name__):
                operator = self.module.CHEMBLENDER_OT_confirm_import()
                with patch.object(
                    operator,
                    "_project",
                    side_effect=fatal_type("fatal projection"),
                ):
                    with self.assertRaises(fatal_type):
                        operator.invoke(context, None)

    def test_commit_job_ui_cleanup_is_independent_and_retryable(self):
        calls = []
        timer = object()
        timer_failures = 1

        def remove(value):
            nonlocal timer_failures
            calls.append(("timer_remove", value))
            if timer_failures:
                timer_failures -= 1
                raise OSError("timer cleanup failed")

        manager = SimpleNamespace(
            event_timer_remove=remove,
            progress_end=lambda: calls.append(("progress_end",)),
        )
        job = self.module._CommitJob(
            self.session,
            object(),
            object(),
            object(),
        )
        job.attach_ui(manager, timer)
        job.mark_progress_started()

        with self.assertRaisesRegex(OSError, "timer cleanup failed"):
            job.release_ui()

        self.assertIn(("progress_end",), calls)
        job.release_ui()
        self.assertEqual(
            calls.count(("timer_remove", timer)),
            2,
        )

    def test_commit_job_start_failure_is_not_marked_started(self):
        job = self.module._CommitJob(
            self.session,
            object(),
            object(),
            object(),
        )
        with patch.object(
            job._thread,
            "start",
            side_effect=RuntimeError("start failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "start failed"):
                job.start()

        self.assertTrue(job.join(0))


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
