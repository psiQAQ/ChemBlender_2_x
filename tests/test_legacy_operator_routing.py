import ast
import hashlib
import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from ChemBlender.core import create_session
from ChemBlender.core.import_pipeline import ValidationMode
from ChemBlender.core.import_pipeline.parse import stage_import_batch


READER_BRIDGE = "ChemBlender.legacy.reader_bridge"
SCAFFOLD_BRIDGE = "ChemBlender.legacy.scaffold_bridge"
SCAFFOLD_MODULE = "ChemBlender.scaffold"
OUTPUT_MODULE = "ChemBlender.output"
PANEL_MODULE = "ChemBlender.panel"
CRYS_MODULE = "ChemBlender.crys_utils"


class _Response:
    def __init__(self, content, status_code=200):
        self.content = content
        self.status_code = status_code


class LegacyReaderBridgeTests(unittest.TestCase):
    def setUp(self):
        sys.modules.pop(READER_BRIDGE, None)
        self.bridge = importlib.import_module(READER_BRIDGE)

    def tearDown(self):
        sys.modules.pop(READER_BRIDGE, None)

    def test_file_and_smiles_build_unified_import_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "legacy.cif"
            source.write_text("data_example\n", encoding="utf-8")

            file_request = self.bridge.file_import_request(
                source,
                ValidationMode.STRICT,
            )

        smiles_request = self.bridge.smiles_import_request(
            "C/C=C/C",
            ValidationMode.BALANCED,
        )

        self.assertEqual(file_request.validation_mode, ValidationMode.STRICT)
        self.assertEqual(file_request.sources[0].path, source.resolve())
        self.assertEqual(smiles_request.validation_mode, ValidationMode.BALANCED)
        self.assertEqual(smiles_request.sources[0].text, "C/C=C/C")

    def test_pubchem_stages_owned_sdf_with_url_hash_and_request(self):
        payload = b"PubChem SDF\n$$$$\n"
        with tempfile.TemporaryDirectory() as directory:
            session = create_session(temp_parent=Path(directory))
            stage = self.bridge.stage_pubchem_import(
                "2244",
                session,
                fetch=lambda url, timeout: _Response(payload),
            )

            self.assertEqual(stage.diagnostics, ())
            self.assertEqual(stage.source_url,
                "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/2244/SDF",
            )
            self.assertEqual(stage.content_hash, hashlib.sha256(payload).hexdigest())
            self.assertEqual(stage.owner_id, session.id)
            self.assertEqual(stage.request.sources[0].path.read_bytes(), payload)
            self.assertTrue(stage.request.sources[0].path.is_relative_to(session.temporary_root))
            self.assertTrue(stage.metadata_path.is_file())

    def test_pubchem_network_failure_becomes_an_import_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            session = create_session(temp_parent=Path(directory))
            stage = self.bridge.stage_pubchem_import(
                "2244",
                session,
                fetch=lambda _url, timeout: (_ for _ in ()).throw(OSError("offline")),
            )

        self.assertIsNone(stage.request)
        self.assertEqual(stage.diagnostics[0].code, "legacy.pubchem_network")
        self.assertIn("offline", stage.diagnostics[0].message)

    def test_pubchem_name_lookup_escapes_a_path_separator(self):
        calls = []

        def fetch(url, timeout):
            calls.append((url, timeout))
            if url.endswith("/cids/JSON"):
                return SimpleNamespace(
                    status_code=200,
                    json=lambda: {"IdentifierList": {"CID": [2244]}},
                )
            return _Response(b"PubChem SDF\n$$$$\n")

        with tempfile.TemporaryDirectory() as directory:
            session = create_session(temp_parent=Path(directory))
            stage = self.bridge.stage_pubchem_import(
                "ethyl/alcohol",
                session,
                fetch=fetch,
            )

        self.assertIsNotNone(stage.request)
        self.assertEqual(
            calls[0][0],
            "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/"
            "name/ethyl%2Falcohol/cids/JSON",
        )

    def test_pubchem_source_is_reverified_before_canonical_parameters(self):
        payload = b"PubChem SDF\n$$$$\n"
        with tempfile.TemporaryDirectory() as directory:
            session = create_session(temp_parent=Path(directory))
            stage = self.bridge.stage_pubchem_import(
                "2244",
                session,
                fetch=lambda _url, timeout: _Response(payload),
            )

            parameters = self.bridge.verified_pubchem_parameters(
                stage.request.sources[0].path,
                session,
            )

        self.assertEqual(
            parameters,
            {
                "legacy_source_url": stage.source_url,
                "legacy_source_sha256": stage.content_hash,
            },
        )

    def test_pubchem_source_or_metadata_tampering_fails_closed(self):
        payload = b"PubChem SDF\n$$$$\n"
        with tempfile.TemporaryDirectory() as directory:
            session = create_session(temp_parent=Path(directory))
            stage = self.bridge.stage_pubchem_import(
                "2244",
                session,
                fetch=lambda _url, timeout: _Response(payload),
            )
            source = stage.request.sources[0].path
            source.write_bytes(b"tampered\n")

            with self.assertRaisesRegex(ValueError, "legacy.pubchem_untrusted"):
                self.bridge.verified_pubchem_parameters(source, session)

            source.write_bytes(payload)
            metadata = json.loads(stage.metadata_path.read_text(encoding="utf-8"))
            metadata["owner_session_id"] = "00000000-0000-0000-0000-000000000000"
            stage.metadata_path.write_text(
                json.dumps(metadata),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "legacy.pubchem_untrusted"):
                self.bridge.verified_pubchem_parameters(source, session)

    def test_pubchem_provenance_is_inspectable_after_project_commit(self):
        payload = b"PubChem SDF\n$$$$\n"
        with tempfile.TemporaryDirectory() as directory:
            session = create_session(temp_parent=Path(directory))
            stage = self.bridge.stage_pubchem_import(
                "2244",
                session,
                fetch=lambda _url, timeout: _Response(payload),
            )
            source, = stage.request.sources
            parameters = self.bridge.verified_pubchem_parameters(
                source.path,
                session,
            )
            batch = stage_import_batch(
                source=source,
                validation_mode=stage.request.validation_mode,
                content_hash=hashlib.sha256(source.path.read_bytes()).hexdigest(),
                byte_size=source.path.stat().st_size,
                plugin_id="test.reader",
                reader_id="test",
                reader_version="1",
                api_version="1",
                canonical_parameters=tuple(parameters.items()),
            )
            session.project.commit(batch)

        provenance, = session.project.provenance.values()
        revision, = session.project.source_revisions.values()
        self.assertEqual(provenance.source, stage.source_url)
        self.assertEqual(provenance.source_hash, stage.content_hash)
        self.assertEqual(
            dict(provenance.parameters),
            {
                "legacy_source_sha256": stage.content_hash,
                "legacy_source_url": stage.source_url,
            },
        )
        self.assertIn(provenance.id, revision.created_entity_ids)


class LegacyOperatorRoutingTests(unittest.TestCase):
    def setUp(self):
        fake_bpy = ModuleType("bpy")
        fake_props = ModuleType("bpy.props")
        fake_types = ModuleType("bpy.types")
        for name in (
            "BoolProperty",
            "CollectionProperty",
            "EnumProperty",
            "FloatProperty",
            "FloatVectorProperty",
            "IntProperty",
            "IntVectorProperty",
            "StringProperty",
        ):
            setattr(fake_props, name, lambda **_keywords: None)
        fake_bpy.props = fake_props
        fake_types.Operator = object
        fake_types.PropertyGroup = object
        fake_types.Panel = object
        fake_bpy.types = fake_types
        fake_bpy.context = SimpleNamespace(
            preferences=SimpleNamespace(view=SimpleNamespace(language="en_US")),
            scene=SimpleNamespace(cursor=SimpleNamespace(location=SimpleNamespace(x=0, y=0, z=0))),
        )
        fake_bpy.path = SimpleNamespace(abspath=lambda value: value)
        fake_bpy.ops = SimpleNamespace(
            chemblender=SimpleNamespace(),
            error=SimpleNamespace(custom_dialog=lambda *_args, **_kwargs: None),
        )
        fake_data = ModuleType("ChemBlender.Chem_data")
        fake_data.ELEMENTS_DEFAULT = {}
        fake_data.BONDS_DEFAULT = {"Default": (0, 0, 0, 1.0)}
        fake_data.SYMOP_OPERATIONS = {}
        fake_data.SPACE_GROUP_DATA = {}
        fake_data.metals = ()
        fake_data.preset_smiles = {
            "sugar": ("Sugar", "OC"),
            "amino": ("Amino acid", "NCC(=O)O"),
            "polymer": ("Polymer unit", "CC"),
        }
        self.modules = patch.dict(
            sys.modules,
            {
                "bpy": fake_bpy,
                "bpy.props": fake_props,
                "bpy.types": fake_types,
                "ChemBlender._math": ModuleType("ChemBlender._math"),
                "ChemBlender.Chem_data": fake_data,
                "ChemBlender.mesh": ModuleType("ChemBlender.mesh"),
                "ChemBlender.node": ModuleType("ChemBlender.node"),
            },
        )
        self.modules.start()
        self.fake_bpy = fake_bpy
        for name in (
            SCAFFOLD_MODULE,
            OUTPUT_MODULE,
            PANEL_MODULE,
            CRYS_MODULE,
            SCAFFOLD_BRIDGE,
        ):
            sys.modules.pop(name, None)

    def tearDown(self):
        for name in (
            SCAFFOLD_MODULE,
            OUTPUT_MODULE,
            PANEL_MODULE,
            CRYS_MODULE,
            SCAFFOLD_BRIDGE,
        ):
            sys.modules.pop(name, None)
        self.modules.stop()

    def _operation(self, calls, name):
        def invoke(*args, **kwargs):
            calls.append((name, args, kwargs))
            return {"FINISHED"}

        return invoke

    def _scaffold_context(self, filetext, *, choose="File"):
        calls = []
        self.fake_bpy.ops.chemblender = SimpleNamespace(
            quick_import=self._operation(calls, "quick_import"),
            import_smiles_text=self._operation(calls, "import_smiles_text"),
            export_project_entity=self._operation(calls, "export_project_entity"),
            apply_scientific_edits=self._operation(calls, "apply_scientific_edits"),
        )
        scaffold = importlib.import_module(SCAFFOLD_MODULE)
        operator = scaffold.MESH_OT_SCAFFOLD_BUILD()
        operator.filter = ""
        operator.report = lambda *_args: None
        context = SimpleNamespace(
            scene=SimpleNamespace(
                my_tool=SimpleNamespace(
                    choose=choose,
                    filetext=str(filetext),
                    pubchemtext="2244",
                    smilestext="",
                    Saccharides="sugar",
                    Amino_Acids="amino",
                    Polymer_Units="polymer",
                ),
                chemblender_quick_import=SimpleNamespace(validation_mode="strict"),
            ),
            window_manager=object(),
        )
        return scaffold, operator, context, calls

    def test_legacy_file_operator_uses_quick_import_for_cif_poscar_and_contcar(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ("legacy.cif", "POSCAR", "CONTCAR"):
                source = Path(directory) / name
                source.write_text("data_example\n", encoding="utf-8")
                scaffold, operator, context, calls = self._scaffold_context(source)
                with patch.object(
                    scaffold.read,
                    "read_Cryst",
                    side_effect=AssertionError(
                        "legacy crystal parser must not run"
                    ),
                ):
                    result = operator.execute(context)

                self.assertEqual(result, {"FINISHED"})
                self.assertEqual(calls[0][0], "quick_import")
                self.assertEqual(calls[0][2]["files"], [{"name": name}])

    def test_legacy_pubchem_operator_does_not_forward_trust_claims_to_quick_import(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "pubchem-2244.sdf"
            source.write_bytes(b"PubChem SDF\n$$$$\n")
            scaffold, operator, context, calls = self._scaffold_context(
                source,
                choose="PubChem",
            )
            stage = SimpleNamespace(
                request=SimpleNamespace(
                    sources=(SimpleNamespace(path=source),),
                    validation_mode=ValidationMode.STRICT,
                ),
                source_url="https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/2244/SDF",
                content_hash="a" * 64,
                diagnostics=(),
            )
            with (
                patch.object(scaffold, "get_scene_session", return_value=object()),
                patch.object(scaffold, "stage_pubchem_import", return_value=stage),
            ):
                result = operator.execute(context)

        self.assertEqual(result, {"FINISHED"})
        self.assertEqual(calls[0][0], "quick_import")
        self.assertNotIn("legacy_source_url", calls[0][2])
        self.assertNotIn("legacy_source_hash", calls[0][2])

    def test_scaffold_bridge_routes_export_and_scientific_changes_to_unified_operators(self):
        bridge = importlib.import_module(SCAFFOLD_BRIDGE)
        calls = []

        bridge.route_legacy_export(lambda operator_id: calls.append(operator_id))
        bridge.route_legacy_scientific_edit(lambda operator_id: calls.append(operator_id))

        self.assertEqual(
            calls,
            [
                "chemblender.export_project_entity",
                "chemblender.apply_scientific_edits",
            ],
        )

    def test_legacy_output_wrappers_forward_without_legacy_export_properties(self):
        output = importlib.import_module(OUTPUT_MODULE)
        calls = []
        self.fake_bpy.ops.chemblender = SimpleNamespace(
            export_project_entity=self._operation(calls, "export_project_entity"),
            apply_scientific_edits=self._operation(calls, "apply_scientific_edits"),
        )

        export_result = output.SaveMolButton().execute(SimpleNamespace())
        edit_result = output.UpdateCIFFromMesh().execute(SimpleNamespace())

        self.assertEqual(export_result, {"FINISHED"})
        self.assertEqual(edit_result, {"FINISHED"})
        self.assertEqual(
            [call[0] for call in calls],
            ["export_project_entity", "apply_scientific_edits"],
        )
        self.assertFalse(
            {"export_format", "mol_version", "vasp_coord_mode", "filepath"}
            & set(output.SaveMolButton.__annotations__)
        )

    def test_crystal_panel_hides_legacy_scaffold_actions_for_unified_views(self):
        fake_ex_package = ModuleType("ChemBlender.ex_package")
        fake_ex_package.safe_check_rdkit = lambda: True
        with patch.dict(sys.modules, {"ChemBlender.ex_package": fake_ex_package}):
            panel = importlib.import_module(PANEL_MODULE)

        calls = []

        class Layout:
            def label(self, **kwargs):
                calls.append(("label", kwargs))

            def operator(self, operator_id, **kwargs):
                calls.append(("operator", operator_id, kwargs))
                return SimpleNamespace()

        class UnifiedObject:
            def get(self, key, default=None):
                if key == "cb_structure_contract":
                    return "structure_view_v1"
                return default

        view = panel.CRYSTAL_PT_TOOLS()
        view.layout = Layout()
        view.draw(
            SimpleNamespace(
                active_object=UnifiedObject(),
                scene=SimpleNamespace(my_tool=SimpleNamespace()),
            )
        )

        self.assertEqual(
            [call[1] for call in calls if call[0] == "operator"],
            ["chemblender.apply_scientific_edits"],
        )

    def test_legacy_crystal_direct_write_operator_cancels_for_unified_view(self):
        fake_bmesh = ModuleType("bmesh")
        fake_mathutils = ModuleType("mathutils")
        with patch.dict(
            sys.modules,
            {"bmesh": fake_bmesh, "mathutils": fake_mathutils},
        ):
            crystal = importlib.import_module(CRYS_MODULE)

        reports = []

        class UnifiedObject:
            name = "unit_demo"

            def get(self, key, default=None):
                if key == "cb_structure_contract":
                    return "structure_view_v1"
                return default

        operator = crystal.SupercellButton()
        operator.report = lambda level, message: reports.append((level, message))
        result = operator.execute(SimpleNamespace(object=UnifiedObject()))

        self.assertEqual(result, {"CANCELLED"})
        self.assertIn("Apply Scientific Edits", reports[0][1])


class LegacyCallerInventoryTests(unittest.TestCase):
    def test_direct_crystal_writers_and_visible_panel_callers_have_an_ast_contract(self):
        root = Path(__file__).resolve().parents[1]
        crystal_tree = ast.parse((root / "ChemBlender" / "crys_utils.py").read_text(encoding="utf-8"))
        panel_tree = ast.parse((root / "ChemBlender" / "panel.py").read_text(encoding="utf-8"))

        def class_by_name(tree, name):
            return next(
                node for node in tree.body
                if isinstance(node, ast.ClassDef) and node.name == name
            )

        def called_names(node):
            return {
                ast.unparse(call.func)
                for call in ast.walk(node)
                if isinstance(call, ast.Call)
            }

        direct_writers = {
            "SupercellButton": {"mesh.copy_mesh_object", "node.Supercell"},
            "AddCellButton": {"mesh.unit_cell_edges"},
            "AddCrysScaffoldButton": {"mesh.create_object", "node.crys_expand"},
            "AddCoordPolyhedraButton": {"node.CoordPolyhedra"},
            "SymmetryDuplicate": {"bpy.data.meshes.new", "bpy.data.objects.new"},
        }
        for class_name, expected_calls in direct_writers.items():
            self.assertTrue(expected_calls <= called_names(class_by_name(crystal_tree, class_name)))

        panel = class_by_name(panel_tree, "CRYSTAL_PT_TOOLS")
        visible_callers = {
            call.args[0].value
            for call in ast.walk(panel)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "operator"
            and call.args
            and isinstance(call.args[0], ast.Constant)
            and isinstance(call.args[0].value, str)
        }
        self.assertEqual(
            visible_callers,
            {
                "chem.add_unit_cell",
                "chem.add_crys_scaffold",
                "chem.sel_symmetry",
                "chem.duplicate_symmetry",
                "chem.supercell",
                "chem.add_coordpolyhedra",
                "chem.avgfract",
                "chem.add_dummy",
                "chem.update_cif_from_mesh",
                "chem.view_set",
            },
        )


if __name__ == "__main__":
    unittest.main()
