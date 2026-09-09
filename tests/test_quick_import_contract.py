import importlib
import sys
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from cbq_core.session import ProjectSession
from cbq_core.session import create_session
from chemblender_prepare.core.import_pipeline.preview import ImportPreview
from chemblender_prepare.core.import_pipeline.preview import SourcePreview
from chemblender_prepare.core.import_pipeline.preflight import ImportCancelled
from chemblender_prepare.core.import_pipeline.request import ValidationMode
from chemblender_prepare.core.import_pipeline.staging import StagedImportSession


ROOT = Path(__file__).resolve().parents[1]
PROPERTIES_MODULE = "ChemBlender.ui.properties"
QUICK_IMPORT_MODULE = "ChemBlender.ui.quick_import"
CBQ_IMPORT_MODULE = "ChemBlender.ui.cbq_import"


class _Property:
    def __init__(self, kind, **keywords):
        self.kind = kind
        self.keywords = keywords


class _Operator:
    def report(self, levels, message):
        self.last_report = (levels, message)


class _PropertyGroup:
    pass


class _Panel:
    pass


class _OperatorFileListElement:
    pass


class _Scene:
    pass


def _property(kind):
    return lambda **keywords: _Property(kind, **keywords)


class QuickImportContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.fake_bpy = ModuleType("bpy")
        self.fake_props = ModuleType("bpy.props")
        self.fake_props.IntProperty = _property("int")
        self.fake_props.BoolProperty = _property("bool")
        self.fake_props.CollectionProperty = _property("collection")
        self.fake_props.EnumProperty = _property("enum")
        self.fake_props.FloatProperty = _property("float")
        self.fake_props.PointerProperty = _property("pointer")
        self.fake_props.StringProperty = _property("string")
        self.fake_bpy.props = self.fake_props
        self.fake_bpy.types = SimpleNamespace(
            Operator=_Operator,
            OperatorFileListElement=_OperatorFileListElement,
            Panel=_Panel,
            PropertyGroup=_PropertyGroup,
            Scene=_Scene,
        )
        self.handlers = SimpleNamespace(
            load_pre=[],
            persistent=lambda callback: callback,
        )
        self.fake_bpy.app = SimpleNamespace(
            background=True,
            handlers=self.handlers,
        )
        self.modules = patch.dict(
            sys.modules,
            {"bpy": self.fake_bpy, "bpy.props": self.fake_props, "bmesh": ModuleType("bmesh")},
        )
        self.modules.start()
        self.addCleanup(self.modules.stop)
        for name in (PROPERTIES_MODULE, QUICK_IMPORT_MODULE, CBQ_IMPORT_MODULE, "ChemBlender.ui.mesh_edit"):
            sys.modules.pop(name, None)

    def tearDown(self):
        cbq = sys.modules.get(CBQ_IMPORT_MODULE)
        if cbq is not None:
            cbq.unregister()
        properties = sys.modules.get(PROPERTIES_MODULE)
        if properties is not None:
            properties.unregister()
        self.modules.stop()
        for name in (PROPERTIES_MODULE, QUICK_IMPORT_MODULE, CBQ_IMPORT_MODULE, "ChemBlender.ui.mesh_edit"):
            sys.modules.pop(name, None)
        self.temporary.cleanup()







    @staticmethod
    def project_snapshot(session):
        project = session.project
        return (
            id(project),
            project.id,
            project.schema_version,
            tuple(
                (
                    name,
                    tuple(getattr(project, name).items()),
                )
                for name in project.__dataclass_fields__
                if isinstance(getattr(project, name), dict)
            ),
            session.dirty_reasons,
        )

    def operator_context(self):
        settings = SimpleNamespace(
            validation_mode=ValidationMode.BALANCED.value,
            recent_summary="",
        )
        window_manager = SimpleNamespace()
        return SimpleNamespace(
            scene=SimpleNamespace(
                chemblender_quick_import=settings,
            ),
            window=object(),
            window_manager=window_manager,
        )

    def operator_for(self, source):
        module = importlib.import_module(QUICK_IMPORT_MODULE)
        operator = module.CHEMBLENDER_OT_quick_import()
        operator.directory = str(source.parent)
        operator.files = [SimpleNamespace(name=source.name)]
        operator.validation_mode = ValidationMode.BALANCED.value
        return module, operator


    def test_discard_failure_retains_owner_for_successful_retry(self):
        source = Path(self.temporary.name) / "failed.xyz"
        source.write_text("1\nA\nH 0 0 0\n", encoding="utf-8")
        module, operator = self.operator_for(source)
        properties = importlib.import_module(PROPERTIES_MODULE)
        project_session = create_session(temp_parent=Path(self.temporary.name))
        original_discard = StagedImportSession.discard
        calls = 0

        def fail_once(staging):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("discard failed")
            return original_discard(staging)

        with patch.object(
            module,
            "get_scene_session",
            return_value=project_session,
        ), patch.object(
            module,
            "get_reader_plugin_registry",
            return_value=object(),
        ), patch.object(
            module,
            "preflight_reader_plugins",
            side_effect=ImportCancelled("cancelled"),
        ), patch.object(
            StagedImportSession,
            "discard",
            fail_once,
        ):
            result = operator.execute(self.operator_context())

        self.assertEqual(result, {"CANCELLED"})
        state = properties._QUICK_IMPORT_STATES[project_session.id]
        self.assertTrue(state.staging_session.root.exists())
        properties.clear_quick_import_state(project_session)
        self.assertNotIn(project_session.id, properties._QUICK_IMPORT_STATES)
        self.assertFalse(state.staging_session.root.exists())

    def test_interactive_preflight_is_modal_reports_progress_and_cancels(self):
        source = Path(self.temporary.name) / "slow.xyz"
        source.write_text("1\nA\nH 0 0 0\n", encoding="utf-8")
        module, operator = self.operator_for(source)
        properties = importlib.import_module(PROPERTIES_MODULE)
        project_session = create_session(temp_parent=Path(self.temporary.name))
        started = threading.Event()
        cancelled = threading.Event()
        timer = object()
        calls = []
        context = self.operator_context()
        context.window_manager.event_timer_add = (
            lambda interval, window: calls.append(
                ("timer_add", interval, window)
            )
            or timer
        )
        context.window_manager.event_timer_remove = (
            lambda value: calls.append(("timer_remove", value))
        )
        context.window_manager.modal_handler_add = (
            lambda value: calls.append(("modal", value))
        )
        context.window_manager.progress_begin = (
            lambda minimum, maximum: calls.append(
                ("progress_begin", minimum, maximum)
            )
        )
        context.window_manager.progress_update = (
            lambda value: calls.append(("progress_update", value))
        )
        context.window_manager.progress_end = (
            lambda: calls.append(("progress_end",))
        )
        self.fake_bpy.app.background = False

        def slow(
            _request,
            _registry,
            _staging,
            *,
            canonical_parameters_by_source=None,
            progress,
            is_cancelled,
            _batch_attachment=None,
        ):
            self.assertIsNone(canonical_parameters_by_source)
            self.assertTrue(callable(_batch_attachment))
            progress("hash", 1, 3)
            started.set()
            while not is_cancelled():
                time.sleep(0.001)
            cancelled.set()
            raise ImportCancelled("cancelled")

        with patch.object(
            module,
            "get_scene_session",
            return_value=project_session,
        ), patch.object(
            module,
            "get_reader_plugin_registry",
            return_value=object(),
        ), patch.object(
            module,
            "preflight_reader_plugins",
            side_effect=slow,
        ):
            result = operator.execute(context)
            self.assertEqual(result, {"RUNNING_MODAL"})
            self.assertTrue(started.wait(1))
            operator.modal(context, SimpleNamespace(type="TIMER"))
            operator.modal(context, SimpleNamespace(type="ESC"))
            self.assertTrue(cancelled.wait(1))
            for _ in range(100):
                result = operator.modal(
                    context,
                    SimpleNamespace(type="TIMER"),
                )
                if result == {"CANCELLED"}:
                    break
                time.sleep(0.001)

        self.assertEqual(result, {"CANCELLED"})
        self.assertTrue(
            any(call[0] == "progress_update" for call in calls),
            calls,
        )
        self.assertIn(("timer_remove", timer), calls)
        self.assertIn(("progress_end",), calls)
        self.assertNotIn(project_session.id, properties._QUICK_IMPORT_STATES)

    def test_modal_does_not_consume_late_cancelled_preflight_result(self):
        module = importlib.import_module(QUICK_IMPORT_MODULE)
        operator = module.CHEMBLENDER_OT_quick_import()
        task = module.Task()
        task.start("preflight")
        task.request_cancel()
        task.complete(object(), "preview ready")
        job = SimpleNamespace(
            done=True,
            error=None,
            task=task,
            staging=object(),
            preview=None,
            conformer_suggestions=None,
            drain_progress=lambda: None,
            join=lambda _timeout: True,
            release_ui=lambda: None,
            timer_pending=False,
            abandon_ui=lambda: None,
        )
        operator._job = job
        operator._project_session = object()
        operator.report = lambda *_args: None

        with (
            patch.object(module, "finish_quick_import_job"),
            patch.object(module, "clear_quick_import_state") as clear,
            patch.object(module, "store_quick_import_preview") as store,
            patch.object(
                module.CHEMBLENDER_OT_quick_import,
                "_finish_preview",
                return_value={"FINISHED"},
            ),
        ):
            result = operator.modal(
                SimpleNamespace(window_manager=SimpleNamespace()),
                SimpleNamespace(type="TIMER"),
            )

        self.assertEqual(result, {"CANCELLED"})
        store.assert_not_called()
        clear.assert_called_once()

    def test_modal_retries_timer_cleanup_before_reraising_progress_fatal(self):
        module = importlib.import_module(QUICK_IMPORT_MODULE)
        operator = module.CHEMBLENDER_OT_quick_import()
        session = object()
        releases = []
        progress_calls = []
        job = SimpleNamespace(
            done=True,
            error=None,
            drain_progress=lambda: ("hash", 1, 2),
            cancel=Mock(),
            join=Mock(return_value=True),
            timer_pending=True,
            abandon_ui=Mock(),
        )

        def release():
            releases.append(True)
            if len(releases) == 1:
                raise OSError("timer cleanup failed")
            job.timer_pending = False

        job.release_ui = release
        operator._job = job
        operator._project_session = session
        operator.report = lambda *_args: None
        context = SimpleNamespace(
            window_manager=SimpleNamespace(
                progress_update=lambda _value: (
                    progress_calls.append(True)
                    or (_ for _ in ()).throw(
                        MemoryError("progress exhausted memory")
                    )
                )
            )
        )

        with (
            patch.object(module, "finish_quick_import_job") as finish,
            patch.object(module, "clear_quick_import_state") as clear,
        ):
            self.assertEqual(
                operator.modal(
                    context,
                    SimpleNamespace(type="TIMER"),
                ),
                {"RUNNING_MODAL"},
            )
            self.assertIs(operator._job, job)
            with self.assertRaisesRegex(MemoryError, "exhausted memory"):
                operator.modal(
                    context,
                    SimpleNamespace(type="TIMER"),
                )

        self.assertEqual(progress_calls, [True])
        self.assertEqual(releases, [True, True])
        job.cancel.assert_called_once_with()
        job.join.assert_called_once_with(None)
        finish.assert_called_once_with(session, job)
        clear.assert_called_once_with(session)
        self.assertIsNone(operator._job)

    def test_modal_join_fatal_releases_ui_and_staging_before_reraising(self):
        module = importlib.import_module(QUICK_IMPORT_MODULE)
        operator = module.CHEMBLENDER_OT_quick_import()
        session = object()
        fatal = GeneratorExit("join stopped")
        releases = []

        def join(timeout):
            if timeout == 0:
                raise fatal
            return True

        job = SimpleNamespace(
            done=True,
            error=None,
            drain_progress=lambda: None,
            cancel=Mock(),
            join=join,
            timer_pending=False,
            release_ui=lambda: releases.append(True),
            abandon_ui=Mock(),
        )
        operator._job = job
        operator._project_session = session
        context = SimpleNamespace(window_manager=SimpleNamespace())

        with (
            patch.object(module, "finish_quick_import_job") as finish,
            patch.object(module, "clear_quick_import_state") as clear,
        ):
            with self.assertRaises(GeneratorExit) as raised:
                operator.modal(
                    context,
                    SimpleNamespace(type="TIMER"),
                )

        self.assertIs(raised.exception, fatal)
        self.assertEqual(releases, [True])
        job.cancel.assert_called_once_with()
        finish.assert_called_once_with(session, job)
        clear.assert_called_once_with(session)
        self.assertIsNone(operator._job)

    def test_interactive_preflight_completion_opens_preview_dialog(self):
        module = importlib.import_module(QUICK_IMPORT_MODULE)
        operator = module.CHEMBLENDER_OT_quick_import()
        operator.validation_mode = ValidationMode.BALANCED.value
        operator.options = SimpleNamespace(is_invoke=True)
        preview = ImportPreview(
            session_id=uuid4(),
            source_previews=(),
        )
        calls = []
        self.fake_bpy.app.background = False
        self.fake_bpy.ops = SimpleNamespace(
            chemblender=SimpleNamespace(
                confirm_import=lambda mode: calls.append(mode)
                or {"RUNNING_MODAL"}
            )
        )
        context = self.operator_context()

        result = operator._finish_preview(context, preview)

        self.assertEqual(result, {"FINISHED"})
        self.assertEqual(calls, ["INVOKE_DEFAULT"])

    def test_direct_execute_preflight_waits_without_opening_a_dialog(self):
        module = importlib.import_module(QUICK_IMPORT_MODULE)
        operator = module.CHEMBLENDER_OT_quick_import()
        operator.options = SimpleNamespace(is_invoke=False)
        operator.validation_mode = ValidationMode.BALANCED.value
        preview = ImportPreview(session_id=uuid4(), source_previews=())
        calls = []
        self.fake_bpy.app.background = False
        self.fake_bpy.ops = SimpleNamespace(
            chemblender=SimpleNamespace(
                confirm_import=lambda mode: calls.append(mode) or {"RUNNING_MODAL"}
            )
        )
        self.assertEqual(operator._finish_preview(self.operator_context(), preview), {"FINISHED"})
        self.assertEqual(calls, [])

    def test_replacing_and_unregistering_preview_discards_staging_roots(self):
        properties = importlib.import_module(PROPERTIES_MODULE)
        project_session = create_session(temp_parent=Path(self.temporary.name))

        first = properties.create_quick_import_staging(project_session)
        first_root = first.root
        properties.store_quick_import_preview(
            project_session,
            first,
            ImportPreview(first.id, ()),
        )
        second = properties.create_quick_import_staging(project_session)
        properties.store_quick_import_preview(
            project_session,
            second,
            ImportPreview(second.id, ()),
        )

        self.assertFalse(first_root.exists())
        self.assertTrue(second.root.exists())
        properties.unregister()
        self.assertFalse(second.root.exists())
        self.assertEqual(properties._QUICK_IMPORT_STATES, {})

    def test_property_registration_is_reversible_and_load_clears_staging(self):
        properties = importlib.import_module(PROPERTIES_MODULE)
        project_session = create_session(temp_parent=Path(self.temporary.name))
        staging = properties.create_quick_import_staging(project_session)
        properties.store_quick_import_preview(
            project_session,
            staging,
            ImportPreview(staging.id, ()),
        )

        properties.register()
        owned_property = _Scene.chemblender_quick_import
        properties.register()
        self.assertTrue(hasattr(_Scene, "chemblender_quick_import"))
        self.assertIs(
            _Scene.chemblender_quick_import,
            owned_property,
        )
        self.assertEqual(
            self.handlers.load_pre.count(properties._load_pre_handler),
            1,
        )
        self.handlers.load_pre[0](None)

        self.assertFalse(staging.root.exists())
        properties.unregister()
        self.assertFalse(hasattr(_Scene, "chemblender_quick_import"))
        self.assertEqual(self.handlers.load_pre, [])

    def test_registration_refuses_preexisting_foreign_scene_property(self):
        properties = importlib.import_module(CBQ_IMPORT_MODULE)
        foreign_property = _Property("foreign")
        _Scene.chemblender_cbq = foreign_property
        try:
            with self.assertRaisesRegex(
                RuntimeError,
                "already owned",
            ):
                properties.register()

            self.assertIs(
                _Scene.chemblender_cbq,
                foreign_property,
            )
            self.assertEqual(self.handlers.load_pre, [])
            properties.unregister()
            self.assertIs(
                _Scene.chemblender_cbq,
                foreign_property,
            )
        finally:
            if hasattr(_Scene, "chemblender_cbq"):
                del _Scene.chemblender_cbq

    def test_unregister_preserves_later_foreign_scene_property_replacement(self):
        properties = importlib.import_module(CBQ_IMPORT_MODULE)
        properties.register()
        foreign_property = _Property("replacement")
        _Scene.chemblender_cbq = foreign_property
        try:
            properties.unregister()

            self.assertIs(
                _Scene.chemblender_cbq,
                foreign_property,
            )
            self.assertEqual(self.handlers.load_pre, [])
        finally:
            if hasattr(_Scene, "chemblender_cbq"):
                del _Scene.chemblender_cbq

    def test_registration_identity_probe_failure_removes_created_property(self):
        properties = importlib.import_module(CBQ_IMPORT_MODULE)

        with patch.object(
            importlib.import_module(PROPERTIES_MODULE),
            "_scene_property_identity",
            side_effect=(None, None),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "registration failed",
            ):
                properties.register()

        self.assertFalse(hasattr(_Scene, "chemblender_cbq"))
        self.assertIsNone(properties._OWNED_SCENE_PROPERTY)

    def test_viewer_panels_offer_cbq_and_local_mesh_edit_entry_points(self):
        from ChemBlender.runtime.registration import REGISTER_MODULE_NAMES
        cbq_import = importlib.import_module(CBQ_IMPORT_MODULE)
        mesh_edit = importlib.import_module("ChemBlender.ui.mesh_edit")
        self.assertIn(".ui.cbq_import", REGISTER_MODULE_NAMES)
        self.assertIn(".ui.mesh_edit", REGISTER_MODULE_NAMES)
        self.assertNotIn(".ui.quick_import", REGISTER_MODULE_NAMES)
        self.assertNotIn(".panel", REGISTER_MODULE_NAMES)
        layout = Mock()
        context = SimpleNamespace(scene=SimpleNamespace(chemblender_cbq=SimpleNamespace(
            input_path="", preview_json="", last_result="")))
        cbq_import.draw_cbq_import(layout, context)
        calls = layout.box.return_value
        self.assertEqual(calls.row.return_value.operator.call_args_list[0].args[0],
                         "chemblender.preview_cbq")
        self.assertEqual(calls.row.return_value.operator.call_args_list[1].args[0],
                         "chemblender.import_cbq")
        calls.operator.assert_any_call("chemblender.export_cbq", icon="EXPORT")
        layout.reset_mock()
        mesh_edit.CHEMBLENDER_PT_mesh_edit.draw(SimpleNamespace(layout=layout),
            SimpleNamespace(active_object=SimpleNamespace(mode="OBJECT")))
        layout.operator.assert_any_call("object.editmode_toggle", text="Edit Mesh")
        layout.operator.assert_any_call("chemblender.apply_mesh_edits")


class ExternalImportSelectionTests(unittest.TestCase):
    """Former raw Blender import contracts now run at the external entrypoint."""
    def test_external_file_selector_replaces_selection_and_cancel_preserves_it(self):
        from chemblender_prepare.gui import PrepareWindow, command_arguments
        window = PrepareWindow.__new__(PrepareWindow)
        window.root = Mock()
        window.sources = Mock()
        paths = ("D:/inputs with spaces/a.xyz", "D:/inputs with spaces/b.xyz")
        with patch("tkinter.filedialog.askopenfilenames", side_effect=[paths, ()]) as select:
            window.choose_sources()
            window.choose_sources()
        self.assertEqual(select.call_count, 2)
        select.assert_called_with(parent=window.root)
        window.sources.delete.assert_called_once_with("1.0", "end")
        window.sources.insert.assert_called_once_with("1.0", "\n".join(paths))
        args = command_arguments({"command": "convert", "sources": "\n".join(paths),
                                  "output": "result.cbq"})
        self.assertEqual(args[2:4], list(paths))
        self.assertEqual(args[args.index("--validation-mode") + 1], "balanced")

    def test_directory_and_missing_file_inputs_publish_nothing(self):
        from contextlib import redirect_stdout
        import io
        import json
        from chemblender_prepare.cli import main
        with TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.xyz"
            first.write_text("1\nfirst\nH 0 0 0\n", encoding="utf-8")
            for source in (root / "missing.xyz", root):
                with self.subTest(source=source), redirect_stdout(io.StringIO()) as stdout:
                    output = root / "result.cbq"
                    self.assertNotEqual(main(["convert", str(first), str(source), "-o", str(output), "--json"]), 0)
                    self.assertEqual(json.loads(stdout.getvalue())["status"], "error")
                    self.assertFalse(output.exists())
                    self.assertEqual(first.read_text(encoding="utf-8"), "1\nfirst\nH 0 0 0\n")

    def test_gui_validation_mode_reaches_real_multifile_worker_and_cbq(self):
        from contextlib import redirect_stdout
        import io
        import json
        from chemblender_prepare import cli
        from chemblender_prepare.gui import command_arguments
        from cbq_core.sidecar import open_project, close_project
        with TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / "first.xyz", root / "second.xyz"
            first.write_text("1\nfirst\nH 0 0 0\n", encoding="utf-8")
            second.write_text("1\nsecond\nHe 1 0 0\n", encoding="utf-8")
            output = root / "result.cbq"
            args = command_arguments({"command": "convert",
                "sources": f"{first}\n{second}", "output": str(output),
                "validation-mode": "maximum"})
            with patch.object(cli, "_run_worker", wraps=cli._run_worker) as worker:
                with redirect_stdout(io.StringIO()) as stdout:
                    self.assertEqual(cli.main(args), 0)
            self.assertEqual(len(worker.call_args_list), 2)
            for call in worker.call_args_list:
                self.assertEqual(call.args[0].parameters["validation_mode"], "maximum")
            self.assertEqual(json.loads(stdout.getvalue())["status"], "success")
            first.unlink()
            second.unlink()
            project = open_project(output, verify_arrays=True)
            try:
                self.assertEqual(len(project.structures), 2)
                self.assertEqual({s.display_name for s in project.sources.values()},
                                 {"first.xyz", "second.xyz"})
            finally:
                close_project(project)

    def test_unknown_suffix_uses_content_sniff_at_external_entry(self):
        from contextlib import redirect_stdout
        import io
        import json
        from chemblender_prepare.cli import main
        with TemporaryDirectory() as directory:
            source = Path(directory) / "water.dropped"
            source.write_text("1\nwater\nH 0 0 0\n", encoding="utf-8")
            with redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(main(["inspect", str(source), "--json"]), 0)
            self.assertEqual(json.loads(stdout.getvalue())["metadata"]["reader_id"], "xyz")

    def test_gui_rejects_unknown_validation_mode_before_launch(self):
        from chemblender_prepare.gui import command_arguments
        with self.assertRaisesRegex(ValueError, "validation"):
            command_arguments({"command": "convert", "sources": "input.xyz",
                               "output": "new.cbq", "validation-mode": "unchecked"})


if __name__ == "__main__":
    unittest.main()
