import importlib
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from time import sleep
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


class _WindowManager:
    def __init__(self, fail_at=None):
        self.fail_at = fail_at
        self.calls = []
        self.timer = object()

    def _call(self, name):
        self.calls.append(name)
        if self.fail_at == name:
            raise RuntimeError(f"{name} failed")

    def event_timer_add(self, _interval, *, window):
        self._call("event_timer_add")
        return self.timer

    def event_timer_remove(self, timer):
        self.assert_timer(timer)
        self._call("event_timer_remove")

    def progress_begin(self, _low, _high):
        self._call("progress_begin")

    def progress_update(self, _value):
        self._call("progress_update")

    def progress_end(self):
        self._call("progress_end")

    def modal_handler_add(self, _operator):
        self._call("modal_handler_add")

    def assert_timer(self, timer):
        if timer is not self.timer:
            raise AssertionError("unexpected timer")


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

    def test_modal_setup_failures_release_owned_ui_in_reverse_order(self):
        module = importlib.import_module(MODULE)
        module.bpy.app.background = False
        session = SimpleNamespace(
            project=sample_trajectory_project(),
            active_entity_id=FRAME_SET_ID,
        )
        cases = (
            (
                "progress_begin",
                (
                    "event_timer_add",
                    "progress_begin",
                    "event_timer_remove",
                ),
            ),
            (
                "modal_handler_add",
                (
                    "event_timer_add",
                    "progress_begin",
                    "progress_update",
                    "modal_handler_add",
                    "progress_end",
                    "event_timer_remove",
                ),
            ),
            (
                "job.start",
                (
                    "event_timer_add",
                    "progress_begin",
                    "progress_update",
                    "modal_handler_add",
                    "progress_end",
                    "event_timer_remove",
                ),
            ),
        )
        for failure, expected_calls in cases:
            with self.subTest(failure=failure):
                manager = _WindowManager(
                    None if failure == "job.start" else failure
                )
                context = SimpleNamespace(
                    scene=object(),
                    window=object(),
                    window_manager=manager,
                )
                operation = module.CHEMBLENDER_OT_export_project_entity()
                operation.filepath = "trajectory.extxyz"
                operation.format_name = "extxyz"
                operation.confirm_loss = False
                operation.missing_value_token = ""
                start_patch = (
                    patch.object(
                        module.ExportJob,
                        "start",
                        side_effect=RuntimeError("job.start failed"),
                    )
                    if failure == "job.start"
                    else patch.object(module.ExportJob, "start")
                )
                with (
                    patch.object(
                        module,
                        "get_scene_session",
                        return_value=session,
                    ),
                    start_patch,
                ):
                    result = operation.execute(context)

                self.assertEqual(result, {"CANCELLED"})
                self.assertEqual(tuple(manager.calls), expected_calls)
                self.assertIsNone(getattr(operation, "_job", None))
                self.assertIsNone(getattr(operation, "_timer", None))

    def test_operator_cancel_joins_worker_and_releases_ui_once(self):
        module = importlib.import_module(MODULE)
        selection = module.resolve_export_selection(
            sample_trajectory_project(),
            FRAME_SET_ID,
        )
        started = Event()

        def wait_for_cancel(*_args, is_cancelled, **_keywords):
            started.set()
            while not is_cancelled():
                sleep(0.001)
            raise ExportCancelled("export cancelled")

        manager = _WindowManager()
        job = module.ExportJob(
            "trajectory.extxyz",
            selection,
            format_name="extxyz",
            confirm_loss=False,
            missing_value_token=None,
        )
        job.attach_ui(manager, manager.timer)
        manager.progress_begin(0, 100)
        job.mark_progress_started()
        operation = module.CHEMBLENDER_OT_export_project_entity()
        operation._job = job
        operation._timer = manager.timer
        with patch.object(module, "export_extxyz", wait_for_cancel):
            job.start()
            self.assertTrue(started.wait(1))
            operation.cancel(SimpleNamespace(window_manager=manager))

        self.assertTrue(job.done)
        self.assertTrue(job.join(0))
        self.assertIsInstance(job.error, ExportCancelled)
        self.assertEqual(
            tuple(manager.calls),
            ("progress_begin", "progress_end", "event_timer_remove"),
        )
        self.assertIsNone(operation._job)
        self.assertIsNone(operation._timer)
        operation.cancel(SimpleNamespace(window_manager=manager))
        self.assertEqual(
            tuple(manager.calls),
            ("progress_begin", "progress_end", "event_timer_remove"),
        )


if __name__ == "__main__":
    unittest.main()
