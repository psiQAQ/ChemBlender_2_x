import importlib
import sys
import threading
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from ChemBlender.core import ProjectSession, create_session
from ChemBlender.core.import_pipeline.preview import ImportPreview, SourcePreview
from ChemBlender.core.import_pipeline.preflight import ImportCancelled
from ChemBlender.core.import_pipeline.request import ValidationMode
from ChemBlender.core.import_pipeline.staging import StagedImportSession


ROOT = Path(__file__).resolve().parents[1]
PROPERTIES_MODULE = "ChemBlender.ui.properties"
QUICK_IMPORT_MODULE = "ChemBlender.ui.quick_import"


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
        self.fake_props.CollectionProperty = _property("collection")
        self.fake_props.EnumProperty = _property("enum")
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
            {"bpy": self.fake_bpy, "bpy.props": self.fake_props},
        )
        self.modules.start()
        for name in (PROPERTIES_MODULE, QUICK_IMPORT_MODULE):
            sys.modules.pop(name, None)

    def tearDown(self):
        properties = sys.modules.get(PROPERTIES_MODULE)
        if properties is not None:
            properties.unregister()
        self.modules.stop()
        for name in (PROPERTIES_MODULE, QUICK_IMPORT_MODULE):
            sys.modules.pop(name, None)
        self.temporary.cleanup()

    def test_operator_properties_use_the_approved_contract(self):
        module = importlib.import_module(QUICK_IMPORT_MODULE)
        cls = module.CHEMBLENDER_OT_quick_import

        self.assertEqual(cls.bl_idname, "chemblender.quick_import")
        self.assertEqual(cls.__annotations__["files"].kind, "collection")
        self.assertIs(
            cls.__annotations__["files"].keywords["type"],
            _OperatorFileListElement,
        )
        self.assertEqual(cls.__annotations__["directory"].kind, "string")
        self.assertEqual(
            cls.__annotations__["directory"].keywords["subtype"],
            "DIR_PATH",
        )
        validation = cls.__annotations__["validation_mode"]
        self.assertEqual(validation.kind, "enum")
        self.assertEqual(
            tuple(item[0] for item in validation.keywords["items"]),
            tuple(mode.value for mode in ValidationMode),
        )
        self.assertEqual(
            validation.keywords["default"],
            ValidationMode.BALANCED.value,
        )

    def test_invoke_opens_file_selector(self):
        module = importlib.import_module(QUICK_IMPORT_MODULE)
        operator = module.CHEMBLENDER_OT_quick_import()
        selected = []
        context = SimpleNamespace(
            scene=SimpleNamespace(
                chemblender_quick_import=SimpleNamespace(
                    validation_mode=ValidationMode.STRICT.value,
                )
            ),
            window_manager=SimpleNamespace(
                fileselect_add=lambda value: selected.append(value)
            ),
        )

        result = operator.invoke(context, None)

        self.assertEqual(result, {"RUNNING_MODAL"})
        self.assertEqual(selected, [operator])
        self.assertEqual(
            operator.validation_mode,
            ValidationMode.STRICT.value,
        )

    def test_execute_stages_deterministic_preview_without_project_mutation(self):
        module = importlib.import_module(QUICK_IMPORT_MODULE)
        source_a = Path(self.temporary.name) / "a.xyz"
        source_b = Path(self.temporary.name) / "b.cube"
        source_a.write_text("1\nA\nH 0 0 0\n", encoding="utf-8")
        source_b.write_text("cube\n", encoding="utf-8")
        project_session = create_session(temp_parent=Path(self.temporary.name))
        self.assertIsInstance(project_session, ProjectSession)
        before = self.project_snapshot(project_session)
        scene_settings = SimpleNamespace(
            validation_mode=ValidationMode.MAXIMUM.value,
            recent_summary="",
        )
        context = SimpleNamespace(
            scene=SimpleNamespace(
                chemblender_quick_import=scene_settings,
            )
        )
        operator = module.CHEMBLENDER_OT_quick_import()
        operator.directory = self.temporary.name
        operator.files = [
            SimpleNamespace(name=source_b.name),
            SimpleNamespace(name=source_a.name),
        ]
        operator.validation_mode = ValidationMode.MAXIMUM.value
        captured = {}

        def preflight(request, registry, staging, **_callbacks):
            captured["request"] = request
            captured["registry"] = registry
            captured["staging"] = staging
            return ImportPreview(
                session_id=staging.id,
                source_previews=tuple(
                    SourcePreview(
                        source_id=source.id,
                        source_path=source.path,
                        selected_reader_id="fixture",
                    )
                    for source in request.sources
                ),
            )

        registry = object()
        with patch.object(
            module,
            "get_scene_session",
            return_value=project_session,
        ), patch.object(
            module,
            "get_reader_plugin_registry",
            return_value=registry,
        ), patch.object(
            module,
            "preflight_reader_plugins",
            side_effect=preflight,
        ):
            result = operator.execute(context)

        self.assertEqual(result, {"FINISHED"})
        self.assertEqual(
            tuple(source.path.name for source in captured["request"].sources),
            ("a.xyz", "b.cube"),
        )
        self.assertIs(
            captured["request"].validation_mode,
            ValidationMode.MAXIMUM,
        )
        self.assertIs(captured["registry"], registry)
        state = module.get_quick_import_state(project_session)
        self.assertIs(state.staging_session, captured["staging"])
        self.assertIsNotNone(state.preview)
        self.assertEqual(self.project_snapshot(project_session), before)
        self.assertIn("2", scene_settings.recent_summary)
        module.clear_quick_import_state(project_session)

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

    def test_staging_is_owned_immediately_and_fatal_cleanup_is_attempted(self):
        source = Path(self.temporary.name) / "fatal.xyz"
        source.write_text("1\nA\nH 0 0 0\n", encoding="utf-8")
        module, operator = self.operator_for(source)
        project_session = create_session(temp_parent=Path(self.temporary.name))
        captured = {}

        def fatal(_request, _registry, staging, **_callbacks):
            state = module.get_quick_import_state(project_session)
            self.assertIs(state.staging_session, staging)
            captured["root"] = staging.root
            raise KeyboardInterrupt

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
            side_effect=fatal,
        ):
            with self.assertRaises(KeyboardInterrupt):
                operator.execute(self.operator_context())

        self.assertFalse(captured["root"].exists())
        self.assertNotIn(
            project_session.id,
            importlib.import_module(PROPERTIES_MODULE)._QUICK_IMPORT_STATES,
        )

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

        def slow(_request, _registry, _staging, *, progress, is_cancelled):
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

    def test_modal_thread_start_failure_releases_owned_staging(self):
        source = Path(self.temporary.name) / "start-failure.xyz"
        source.write_text("1\nA\nH 0 0 0\n", encoding="utf-8")
        module, operator = self.operator_for(source)
        properties = importlib.import_module(PROPERTIES_MODULE)
        project_session = create_session(temp_parent=Path(self.temporary.name))
        context = self.operator_context()
        timer = object()
        context.window_manager.event_timer_add = (
            lambda _interval, *, window: timer
        )
        context.window_manager.event_timer_remove = lambda _timer: None
        context.window_manager.modal_handler_add = lambda _operator: None
        context.window_manager.progress_begin = (
            lambda _minimum, _maximum: None
        )
        context.window_manager.progress_end = lambda: None
        self.fake_bpy.app.background = False
        captured = {}
        original_create = module.create_quick_import_staging

        def create(session):
            staging = original_create(session)
            captured["root"] = staging.root
            return staging

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
            "create_quick_import_staging",
            side_effect=create,
        ), patch.object(
            threading.Thread,
            "start",
            side_effect=RuntimeError("thread start failed"),
        ):
            result = operator.execute(context)

        self.assertEqual(result, {"CANCELLED"})
        self.assertFalse(captured["root"].exists())
        self.assertNotIn(project_session.id, properties._QUICK_IMPORT_STATES)
        self.assertIn("thread start failed", operator.last_report[1])

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
        properties = importlib.import_module(PROPERTIES_MODULE)
        foreign_property = _Property("foreign")
        _Scene.chemblender_quick_import = foreign_property
        try:
            with self.assertRaisesRegex(
                RuntimeError,
                "already owned",
            ):
                properties.register()

            self.assertIs(
                _Scene.chemblender_quick_import,
                foreign_property,
            )
            self.assertEqual(self.handlers.load_pre, [])
            properties.unregister()
            self.assertIs(
                _Scene.chemblender_quick_import,
                foreign_property,
            )
        finally:
            if hasattr(_Scene, "chemblender_quick_import"):
                del _Scene.chemblender_quick_import

    def test_unregister_preserves_later_foreign_scene_property_replacement(self):
        properties = importlib.import_module(PROPERTIES_MODULE)
        properties.register()
        foreign_property = _Property("replacement")
        _Scene.chemblender_quick_import = foreign_property
        try:
            properties.unregister()

            self.assertIs(
                _Scene.chemblender_quick_import,
                foreign_property,
            )
            self.assertEqual(self.handlers.load_pre, [])
        finally:
            if hasattr(_Scene, "chemblender_quick_import"):
                del _Scene.chemblender_quick_import

    def test_registration_identity_probe_failure_removes_created_property(self):
        properties = importlib.import_module(PROPERTIES_MODULE)

        with patch.object(
            properties,
            "_scene_property_identity",
            side_effect=(None, None),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "registration failed",
            ):
                properties.register()

        self.assertFalse(hasattr(_Scene, "chemblender_quick_import"))
        self.assertIsNone(properties._OWNED_SCENE_PROPERTY)

    def test_panel_keeps_legacy_build_and_adds_quick_import_entry_points(self):
        legacy_source = (ROOT / "ChemBlender" / "panel.py").read_text(
            encoding="utf-8"
        )
        quick_import_source = (
            ROOT / "ChemBlender" / "ui" / "quick_import.py"
        ).read_text(encoding="utf-8")

        self.assertIn("class CHEM_PT_Build", legacy_source)
        self.assertIn(
            "class CHEMBLENDER_PT_quick_import",
            quick_import_source,
        )
        self.assertIn('"chemblender.quick_import"', quick_import_source)
        self.assertIn('"wm.save_mainfile"', quick_import_source)
        self.assertIn("Open Workspace", quick_import_source)


if __name__ == "__main__":
    unittest.main()
