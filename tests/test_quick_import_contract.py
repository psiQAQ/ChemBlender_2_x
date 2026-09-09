import importlib
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch


PROPERTIES_MODULE = "ChemBlender.ui.properties"
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
        for name in (PROPERTIES_MODULE, CBQ_IMPORT_MODULE, "ChemBlender.ui.mesh_edit"):
            sys.modules.pop(name, None)

    def tearDown(self):
        cbq = sys.modules.get(CBQ_IMPORT_MODULE)
        if cbq is not None:
            cbq.unregister()
        properties = sys.modules.get(PROPERTIES_MODULE)
        if properties is not None:
            properties.unregister()
        self.modules.stop()
        for name in (PROPERTIES_MODULE, CBQ_IMPORT_MODULE, "ChemBlender.ui.mesh_edit"):
            sys.modules.pop(name, None)
        self.temporary.cleanup()




















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
