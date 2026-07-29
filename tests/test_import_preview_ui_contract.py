import importlib
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

from ChemBlender.core import (
    DatasetStatus,
    close_project,
    close_session,
    create_session,
    open_project,
)
from ChemBlender.core.import_pipeline.grouping import (
    GroupingEvidence,
    SourceGroupSuggestion,
)
from ChemBlender.core.import_pipeline.conformer_grouping import (
    suggest_staged_conformer_groups,
)
from ChemBlender.core.sidecar import save_project
from ChemBlender.core.import_pipeline.request import (
    ImportRequest,
    ImportSource,
    ValidationMode,
)
from ChemBlender.core.import_pipeline.staging import StagedImportSession
from ChemBlender.core.formats.extxyz import parse_extxyz
from ChemBlender.reader_api.import_pipeline_bridge import preflight_reader_plugins
from ChemBlender.reader_api.registry import builtin_reader_plugin_registry


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
            ("IntProperty", "int"),
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
            batch_remove=lambda **_kwargs: None,
        )
        self.fake_bpy.context = SimpleNamespace(collection=object())
        self.modules = patch.dict(
            sys.modules,
            {"bpy": self.fake_bpy, "bpy.props": self.fake_props},
        )
        self.modules.start()
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

    def test_extxyz_preview_summary_reports_frames_properties_cell_and_units(self):
        source = Path(self.temporary.name) / "force.extxyz"
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
        batch = parse_extxyz(source)

        summary = self.module.extxyz_preview_summary(batch)

        self.assertEqual(summary.frame_count, 2)
        self.assertEqual(summary.atom_properties, ("atomic_force",))
        self.assertEqual(
            summary.frame_properties,
            ("cell", "energy", "pbc"),
        )
        self.assertTrue(summary.has_lattice)
        self.assertEqual(summary.pbc, (True, False, True))
        self.assertTrue(summary.pbc_changes)
        self.assertEqual(
            summary.assumed_units,
            (
                "electron_volt was assumed because extXYZ declared no unit",
                "electron_volt_per_angstrom was assumed because extXYZ "
                "declared no unit",
            ),
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

    def test_inline_smiles_reaches_preview_without_filesystem_locator_forgery(self):
        staging = self.properties.create_quick_import_staging(self.session)
        request = ImportRequest(
            sources=(ImportSource.smiles_text("CO"),),
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
        state = self.properties.get_quick_import_state(self.session)

        rows = self.module.project_import_preview(
            self.session,
            state,
            registry,
        )

        self.assertEqual(rows[0].reader_id, "smiles")
        self.assertEqual(rows[0].molecular_record_count, 1)
        batch = staging.result(preview.source_previews[0].staged_batch_ids[0])
        self.assertEqual(batch.source_revisions[0].locator, "inline:smiles")
        self.assertEqual(
            batch.source_revisions[0].locator_kind,
            "inline_text",
        )

    def test_recovered_sdf_record_failure_is_visible_but_does_not_block_commit(self):
        registry, state = self.stage("tests/fixtures/sdf/malformed-middle.sdf")
        source = state.preview.source_previews[0]
        batch = state.staging_session.result(source.staged_batch_ids[0])
        rows = self.module.project_import_preview(self.session, state, registry)

        self.assertEqual(rows[0].quality, "invalid")
        self.assertFalse(rows[0].blocking)
        result = self.module.commit_project_import(
            self.session,
            state,
            rows,
            collection=object(),
            apply_view=lambda *_args, **_kwargs: (),
        )
        self.assertEqual(result.status, "committed")
        records = tuple(
            sorted(
                self.session.project.molecular_records.values(),
                key=lambda item: item.source_record_index,
            )
        )
        self.assertEqual(tuple(item.source_record_index for item in records), (0, 2))
        self.assertEqual(
            tuple(item.code for item in self.session.project.diagnostics.values()),
            ("sdf.record_parse_failed",),
        )

        blocking_batch = replace(
            batch,
            diagnostics=(
                replace(
                    batch.diagnostics[0],
                    record_key=batch.molecular_records[0].record_key,
                ),
            ),
        )
        blocking_staging = SimpleNamespace(
            result=lambda _batch_id: blocking_batch,
        )
        _quality, blocking_reason = self.module._quality_and_blocking(
            blocking_staging, source
        )
        self.assertIn("sdf.record_parse_failed", blocking_reason)

        plugin_batch = replace(
            batch,
            diagnostics=(
                replace(
                    batch.diagnostics[0],
                    code="plugin.integrity_failure",
                    field_path="source.integrity",
                    recovery_action="plugin data must be repaired",
                ),
            ),
        )
        plugin_staging = SimpleNamespace(result=lambda _batch_id: plugin_batch)
        _quality, plugin_reason = self.module._quality_and_blocking(
            plugin_staging, source
        )
        self.assertIn("plugin.integrity_failure", plugin_reason)

        failed = Path(self.temporary.name) / "all-failed.sdf"
        failed.write_bytes(
            (ROOT / "tests/fixtures/mol/water-v2000.mol")
            .read_bytes()
            .replace(b" O   ", b" Xx  ", 1)
            + b"$$$$\n"
        )
        _failed_registry, failed_state = self.stage(failed)
        _quality, failed_reason = self.module._quality_and_blocking(
            failed_state.staging_session,
            failed_state.preview.source_previews[0],
        )
        self.assertIn("sdf.record_parse_failed", failed_reason)

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

    def test_cached_conformer_suggestions_avoid_main_thread_regrouping(self):
        registry, state = self.stage("tests/fixtures/sdf/records.sdf")
        cached = suggest_staged_conformer_groups(
            state.preview,
            state.staging_session,
        )
        state.conformer_grouping_suggestions = cached

        with patch(
            "ChemBlender.core.import_pipeline.conformer_grouping."
            "suggest_staged_conformer_groups",
            side_effect=AssertionError("must not regroup in UI projection"),
        ):
            rows = self.module.project_import_preview(
                self.session,
                state,
                registry,
            )

        self.assertEqual(rows[0].conformer_suggestion_count, 1)
        self.assertIs(state.conformer_grouping_suggestions, cached)

    def test_missing_conformer_cache_does_not_regroup_on_ui_thread(self):
        registry, state = self.stage("tests/fixtures/sdf/records.sdf")
        state.conformer_grouping_suggestions = None

        with patch(
            "ChemBlender.core.import_pipeline.conformer_grouping."
            "suggest_staged_conformer_groups",
            side_effect=AssertionError("must not regroup in UI projection"),
        ):
            rows = self.module.project_import_preview(
                self.session,
                state,
                registry,
            )

        self.assertEqual(rows[0].conformer_suggestion_count, 0)
        self.assertEqual(state.conformer_grouping_suggestions, ())

    def test_changed_conformer_suggestion_fails_closed_in_transaction(self):
        registry, state = self.stage("tests/fixtures/sdf/records.sdf")
        rows = self.module.project_import_preview(
            self.session,
            state,
            registry,
        )
        suggestions = self.module.project_conformer_suggestions(state)
        suggestions[0].grouping_action = "accept_group"
        suggestions[0].review_confirmed = suggestions[0].requires_review
        transaction = importlib.import_module(
            "ChemBlender.core.import_pipeline.transaction"
        )

        with patch.object(
            transaction,
            "suggest_conformer_groups",
            return_value=(),
        ):
            with self.assertRaisesRegex(
                ValueError,
                "conformer grouping decision does not match live staging",
            ):
                self.module.commit_project_import(
                    self.session,
                    state,
                    rows,
                    conformer_rows=suggestions,
                    collection=object(),
                    apply_view=lambda *_args, **_kwargs: (),
                )

    def test_conformer_evidence_projection_is_bounded_outside_rna(self):
        evidence = tuple(
            SimpleNamespace(
                record_id=uuid4(),
                kind="complete_atom_maps",
                atom_mapping=(0,),
                requires_review=index == 24,
            )
            for index in range(25)
        )
        suggestion = SimpleNamespace(
            id=uuid4(),
            record_ids=tuple(item.record_id for item in evidence),
            record_keys=tuple(f"record-{index}" for index in range(25)),
            requires_review=True,
            evidence=evidence,
        )

        projected = self.module.project_conformer_suggestions(
            SimpleNamespace(
                conformer_grouping_suggestions=(suggestion,),
            )
        )[0]

        self.assertEqual(projected.record_count, 25)
        self.assertEqual(len(projected.evidence), 20)
        review = tuple(item for item in projected.evidence if item.requires_review)
        self.assertEqual(len(review), 1)
        self.assertEqual(review[0].record_key, "record-24")

    def test_hidden_conformer_review_evidence_is_fail_closed(self):
        evidence = tuple(
            SimpleNamespace(
                record_id=uuid4(),
                kind="ambiguous_atom_mapping",
                atom_mapping=(0,),
                requires_review=True,
            )
            for _ in range(25)
        )
        suggestion = SimpleNamespace(
            id=uuid4(),
            record_ids=tuple(item.record_id for item in evidence),
            record_keys=tuple(f"record-{index}" for index in range(25)),
            requires_review=True,
            evidence=evidence,
        )
        state = SimpleNamespace(
            conformer_grouping_suggestions=(suggestion,),
        )
        projected = self.module.project_conformer_suggestions(state)[0]

        self.assertEqual(len(projected.evidence), 20)
        self.assertTrue(all(item.requires_review for item in projected.evidence))
        self.assertEqual(projected.hidden_review_count, 5)
        projected.grouping_action = "accept_group"
        projected.review_confirmed = True
        with self.assertRaisesRegex(ValueError, "hidden review evidence"):
            self.module._conformer_grouping_decisions(state, (projected,))

    def test_conformer_atom_mapping_projection_is_bounded(self):
        evidence = SimpleNamespace(
            record_id=uuid4(),
            kind="complete_atom_maps",
            atom_mapping=tuple(range(1000)),
            requires_review=False,
        )
        suggestion = SimpleNamespace(
            id=uuid4(),
            record_ids=(evidence.record_id,),
            record_keys=("large-record",),
            requires_review=False,
            evidence=(evidence,),
        )

        mapping = self.module.project_conformer_suggestions(
            SimpleNamespace(
                conformer_grouping_suggestions=(suggestion,),
            )
        )[0].evidence[0].atom_mapping

        self.assertLessEqual(len(mapping), 160)
        self.assertIn("1000 atoms", mapping)
        self.assertIn("sha256:", mapping)

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

        self.module.cancel_project_import(self.session)
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

    def test_missing_batch_blocks_confirm_with_visible_reason(self):
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

        rows = self.module.project_import_preview(
            self.session,
            state,
            registry,
        )

        self.assertTrue(rows[0].blocking)
        self.assertIn("staged batch", rows[0].blocking_reason)
        with self.assertRaisesRegex(ValueError, "staged batch"):
            self.module.commit_project_import(
                self.session,
                state,
                rows,
                collection=object(),
                apply_view=lambda *_args, **_kwargs: (),
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

    def test_commit_keeps_external_saved_sidecar_while_using_new_generation(self):
        external = Path(self.temporary.name) / "saved.cbq"
        save_project(external, self.session.project)
        self.session.sidecar_path = external

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

        self.assertTrue(external.is_dir())
        self.assertNotEqual(self.session.sidecar_path, external)
        self.assertEqual(
            self.session.sidecar_path.parent,
            self.session.temporary_root,
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

    def test_close_session_removes_current_import_generation_and_session_root(self):
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
        root = self.session.temporary_root
        generation = self.session.sidecar_path

        self.assertTrue(generation.is_dir())
        close_session(self.session)

        self.assertFalse(generation.exists())
        self.assertFalse(root.exists())

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
        created = SimpleNamespace(type="VOLUME", data=None, modifiers=())
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
        created = SimpleNamespace(type="MESH", data=None, modifiers=())
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

    def test_scene_preset_rolls_back_partial_objects_before_fatal_reraises(self):
        scene_preset_view = importlib.import_module(
            "ChemBlender.scene_preset_view"
        )
        created = object()
        fatal = GeneratorExit("linked view stopped")
        plan = SimpleNamespace(
            view_kind="electronic_spectrum_linked",
            settings=(("selection_index", 0),),
        )
        removed = []

        with (
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
            data=SimpleNamespace(users=0),
            modifiers=({"cbq_contract": "isosurface_v1"},),
        )
        property_surface = SimpleNamespace(
            type="VOLUME",
            data=SimpleNamespace(users=0),
            modifiers=({"cbq_contract": "property_surface_v1"},),
        )
        ordinary = SimpleNamespace(type="MESH", data=None, modifiers=())
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
        self.assertFalse(observed["is_cancelled"]())
        job.cancel()
        self.assertTrue(observed["is_cancelled"]())

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


if __name__ == "__main__":
    unittest.main()
