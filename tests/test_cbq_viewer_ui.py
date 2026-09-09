"""CBQ-only boundaries and independent, transactional Viewer package export."""

import ast
from pathlib import Path
import shutil
import unittest
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import numpy

from cbq_core.model import ArrayData, ImportBatch, QCProject, Structure
from cbq_core.session import close_session, create_session
from cbq_core.sidecar import close_project, open_project, save_project
from cbq_core.package_import import preview_package
from cbq_core.project_service import save_project_session_for_scenes, ProjectServiceStatus
from ChemBlender.runtime.registration import REGISTER_MODULE_NAMES
from ChemBlender.ui import cbq_import


ROOT = Path(__file__).resolve().parents[1]


class CBQViewerUITests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.structure = Structure(uuid4(), "test-structure", (1,),
            ArrayData(numpy.array([[1., 2., 3.]]), ("atom", "xyz"), "angstrom"))
        project = QCProject(uuid4(), "1.1")
        project.commit(ImportBatch(structures=(self.structure,)))
        self.session = create_session(temp_parent=self.root, project=project)

    def tearDown(self):
        close_session(self.session)
        self.temporary.cleanup()

    def test_package_selection_accepts_only_cbq_or_its_manifest(self):
        source = save_project(self.root / "input.cbq", self.session.project)
        self.assertEqual(cbq_import.package_path(str(source)), source)
        self.assertEqual(cbq_import.package_path(str(source / "manifest.json")), source)
        for value in ("", str(self.root), str(source / "arrays")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                cbq_import.package_path(value)

    def test_export_detaches_lazy_arrays_from_original_package(self):
        source = save_project(self.root / "source.cbq", self.session.project)
        self.session.project = open_project(source)
        self.session.sidecar_path = source
        active = self.session.project
        destination = cbq_import.export_package(self.session, str(self.root / "copy.cbq"))
        self.assertIs(self.session.project, active)
        self.assertEqual(self.session.sidecar_path, source)
        close_project(active)
        shutil.rmtree(source)
        exported = open_project(destination, verify_arrays=True)
        try:
            numpy.testing.assert_array_equal(
                exported.structures[self.structure.id].coordinates.values,
                self.structure.coordinates.values)
        finally:
            close_project(exported)

    def test_export_refuses_existing_or_nested_active_package(self):
        source = save_project(self.root / "source.cbq", self.session.project)
        self.session.sidecar_path = source
        before = (source / "manifest.json").read_bytes()
        for value in (str(source), str(source / "nested.cbq")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                cbq_import.export_package(self.session, value)
        self.assertEqual((source / "manifest.json").read_bytes(), before)

    def test_export_failure_removes_staging_and_keeps_destination_absent(self):
        destination = self.root / "copy.cbq"
        before = set(self.root.iterdir())
        original = save_project

        def fail(path, project):
            original(path, project)
            raise OSError("injected write failure")

        with patch.object(cbq_import, "save_project", side_effect=fail):
            with self.assertRaisesRegex(OSError, "injected"):
                cbq_import.export_package(self.session, str(destination))
        self.assertFalse(destination.exists())
        self.assertEqual(set(self.root.iterdir()), before)

    def test_review_is_invalid_after_input_path_changes(self):
        import json
        source = save_project(self.root / "first.cbq", self.session.project)
        other = save_project(self.root / "other.cbq", self.session.project)
        from dataclasses import asdict
        document = {"path": str(source), **asdict(preview_package(self.session, source))}
        settings = SimpleNamespace(input_path=str(source), preview_json=json.dumps(document))
        self.assertIsNotNone(cbq_import._preview_document(settings))
        settings.input_path = str(other)
        self.assertIsNone(cbq_import._preview_document(settings))
        settings.input_path = str(source)
        malformed = [[], None, 42, {"path": str(source)},
            {**document, "counts": {"new": True, "reused": 0}},
            {**document, "counts": {"new": -1, "reused": 0}},
            {**document, "manifest_sha256": "not-a-hash"},
            {**document, "conflicts": [None]}, {**document, "readiness": "text"}]
        for value in malformed:
            with self.subTest(value=value):
                settings.preview_json = json.dumps(value)
                self.assertIsNone(cbq_import._preview_document(settings))

    def test_import_advances_saved_scene_links_to_published_generation(self):
        blend = self.root / "scene.blend"
        scene = {}
        saved = save_project_session_for_scenes(
            session=self.session, scenes=(scene,), blend_path=blend)
        self.assertIs(saved.status, ProjectServiceStatus.CONNECTED)
        previous_hash = saved.manifest_sha256
        saved_path = self.session.sidecar_path
        before = {p.relative_to(saved_path): p.read_bytes()
                  for p in saved_path.rglob("*") if p.is_file()}
        incoming = QCProject(uuid4(), "1.1")
        other = Structure(uuid4(), "other-structure", (2,),
            ArrayData(numpy.array([[4., 5., 6.]]), ("atom", "xyz"), "angstrom"))
        incoming.commit(ImportBatch(structures=(other,)))
        path = save_project(self.root / "incoming.cbq", incoming)
        preview = preview_package(self.session, path)
        result, link = cbq_import.import_reviewed_package(self.session,
            {"path": str(path), "manifest_sha256": preview.manifest_sha256},
            scenes=(scene,), blend_path=blend)
        self.assertIs(link.status, ProjectServiceStatus.CONNECTED)
        self.assertNotEqual(link.manifest_sha256, previous_hash)
        self.assertEqual(scene["cbq_manifest_sha256"], link.manifest_sha256)
        self.assertIn(other.id, self.session.project.structures)
        self.assertFalse(result.cleanup_warnings)
        self.assertEqual(before, {p.relative_to(saved_path): p.read_bytes()
                                  for p in saved_path.rglob("*") if p.is_file()})
        temporary = self.session.sidecar_path
        self.assertEqual(temporary.parent, self.session.temporary_root)
        shutil.rmtree(path)
        saved = save_project_session_for_scenes(
            session=self.session, scenes=(scene,), blend_path=blend)
        self.assertIs(saved.status, ProjectServiceStatus.CONNECTED)
        self.assertEqual(self.session.sidecar_path, saved_path)
        self.assertFalse(self.session.dirty)
        root = self.session.temporary_root
        close_session(self.session)
        self.assertFalse(root.exists())
        self.assertFalse(temporary.exists())
        # A fresh session must use only the explicitly saved package.
        self.session = create_session(temp_parent=self.root,
            project=open_project(saved_path, verify_arrays=True))
        self.assertEqual(set(self.session.project.structures), {self.structure.id, other.id})
        numpy.testing.assert_array_equal(self.session.project.structures[other.id].coordinates.values,
                                         other.coordinates.values)

    def test_invalid_existing_scene_link_rejects_import_before_publication(self):
        blend = self.root / "scene.blend"
        scene = {}
        save_project_session_for_scenes(session=self.session, scenes=(scene,), blend_path=blend)
        before = self.session.project
        scene["cbq_manifest_sha256"] = "0" * 64
        with patch.object(cbq_import, "import_package", side_effect=AssertionError("unexpected import")):
            with self.assertRaisesRegex(ValueError, "conflicting"):
                cbq_import.import_reviewed_package(self.session, {}, scenes=(scene,), blend_path=blend)
        self.assertIs(self.session.project, before)

    def test_post_commit_ui_failure_reports_committed_import(self):
        import importlib.util
        import json
        import sys
        from dataclasses import asdict
        from types import ModuleType
        incoming = QCProject(uuid4(), "1.1")
        other = Structure(uuid4(), "incoming", (2,),
            ArrayData(numpy.array([[4., 5., 6.]]), ("atom", "xyz"), "angstrom"))
        incoming.commit(ImportBatch(structures=(other,)))
        path = save_project(self.root / "incoming.cbq", incoming)
        preview = preview_package(self.session, path)
        settings = SimpleNamespace(input_path=str(path), allow_duplicate_sources=False,
            preview_json=json.dumps({"path": str(path), **asdict(preview)}), last_result="")
        context = SimpleNamespace(scene=SimpleNamespace(chemblender_cbq=settings,
            chemblender_project_browser=SimpleNamespace(active_entity_id="")))
        reports = []
        class Operator:
            def report(self, levels, message):
                reports.append((levels, message))
        bpy = ModuleType("bpy")
        bpy.types = SimpleNamespace(Operator=Operator, PropertyGroup=object)
        bpy.data = SimpleNamespace(scenes=(), filepath="")
        bpy.path = SimpleNamespace(abspath=lambda value: value)
        props = ModuleType("bpy.props")
        props.BoolProperty = props.PointerProperty = props.StringProperty = lambda **kwargs: None
        session_ui = ModuleType("ChemBlender.ui.session")
        session_ui.get_scene_session = lambda scene: self.session
        session_ui._record_result = lambda result: None
        def fail(session):
            raise RuntimeError("browser refresh failed")
        session_ui._notify_session_mutation = fail
        modules = {"bpy": bpy, "bpy.props": props, "ChemBlender.ui.session": session_ui,
            "ChemBlender.ui.orbital_export": SimpleNamespace(_EXPORTS={}),
            "ChemBlender.ui.grid": SimpleNamespace(_ACTIVE_VOLUME_OPERATORS={})}
        with patch.dict(sys.modules, modules):
            spec = importlib.util.spec_from_file_location("ChemBlender.ui._cbq_import_test", cbq_import.__file__)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            settings.allow_duplicate_sources = True
            module._review(context)
            self.assertFalse(settings.allow_duplicate_sources)
            operator = module.CHEMBLENDER_OT_import_cbq()
            operator.filepath = ""
            self.assertEqual(operator.execute(context), {"FINISHED"}, reports)
        self.assertIn(self.structure.id, self.session.project.structures)
        self.assertIn(other.id, self.session.project.structures)
        self.assertEqual(settings.preview_json, "")
        self.assertTrue(any("WARNING" in levels and "imported" in message.lower()
                            and "browser refresh failed" in message for levels, message in reports))

    def test_registered_ui_has_no_scientific_dependency_or_computation_entrypoint(self):
        self.assertIn(".ui.cbq_import", REGISTER_MODULE_NAMES)
        for name in ("quick_import", "import_preview", "scientific_edit", "export", "migration",
                     "scientific_import", "wavefunction_import", "topology_import"):
            self.assertNotIn(".ui." + name, REGISTER_MODULE_NAMES)
            self.assertFalse((ROOT / "ChemBlender" / "ui" / (name + ".py")).exists())
        for path in (ROOT / "ChemBlender" / "ui").rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
                if isinstance(node, ast.ImportFrom):
                    self.assertFalse((node.module or "").startswith("chemblender_prepare"), str(path))
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn(alias.name.split(".")[0], {"rdkit", "gemmi", "gbasis", "iodata"}, str(path))
        self.assertFalse((ROOT / "ChemBlender/runtime/reader_api_bridge.py").exists())


if __name__ == "__main__":
    unittest.main()
