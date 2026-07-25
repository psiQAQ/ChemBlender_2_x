import importlib
import sys
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from ChemBlender.core import close_session, create_session
from ChemBlender.core.sidecar import save_project
from ChemBlender.core.import_pipeline.request import (
    ImportRequest,
    ImportSource,
    ValidationMode,
)
from ChemBlender.core.import_pipeline.staging import StagedImportSession
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
                "quality",
                "conflict_id",
                "conflict_action",
                "conflict_target_revision_id",
                "allowed_actions",
                "default_view",
                "blocking",
                "blocking_reason",
            },
        )
        self.assertTrue(
            all(
                value.kind in {"bool", "enum", "string"}
                for value in annotations.values()
            )
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

    def test_confirm_calls_transaction_once_creates_real_structure_plans(self):
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
        original = self.module.commit_import_preview

        def commit_once(*args):
            calls.append(args)
            return original(*args)

        def apply(plan, project, *, collection):
            self.assertEqual(plan.preset_id, "structure_publication")
            self.assertIn(plan.bindings[0].entity_id, project.structures)
            self.assertIsNotNone(collection)
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
        self.assertGreaterEqual(len(self.session.project.structures), 2)
        self.assertEqual(self.session.dirty_reasons, frozenset({"import"}))
        self.assertEqual(state.browser_revision, 1)
        self.assertIsNone(state.preview)
        self.assertEqual(result.status, "committed")
        self.assertGreaterEqual(result.created_view_count, 0)

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

        def fail_after_creating_generation(project_session, *_args):
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
            "tests/fixtures/xyz/water.xyz",
            "tests/fixtures/cube/sheared.cube",
        )
        rows = self.module.project_import_preview(
            self.session,
            state,
            registry,
        )
        created = SimpleNamespace(type="MESH", data=None)
        calls = 0

        def fail_second(*_args, **_kwargs):
            nonlocal calls
            calls += 1
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
        self.assertGreaterEqual(len(self.session.project.structures), 2)
        self.assertEqual(
            self.fake_bpy.data.objects.removed,
            [(created, True)],
        )
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

        def delayed_commit(*args):
            entered.set()
            release.wait(2)
            return original(*args)

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
        self.assertIsNotNone(job.result)
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

        def delayed(*args):
            entered.set()
            release.wait(2)
            return original(*args)

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
                if result == {"FINISHED"}:
                    break
                time.sleep(0.01)

        self.assertEqual(result, {"FINISHED"})
        self.assertGreaterEqual(len(self.session.project.structures), 1)
        self.assertIn(("timer_remove", timer), calls)
        self.assertIn(("progress_end",), calls)
        self.assertTrue(
            any(call[:2] == ("progress_update", 100) for call in calls),
            calls,
        )
        self.assertLess(
            calls.index(("progress_update", 100)),
            calls.index(("progress_end",)),
        )

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
