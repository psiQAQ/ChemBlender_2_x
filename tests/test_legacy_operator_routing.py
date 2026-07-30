import hashlib
import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from ChemBlender.core import create_session
from ChemBlender.core.import_pipeline import ValidationMode


READER_BRIDGE = "ChemBlender.legacy.reader_bridge"
SCAFFOLD_BRIDGE = "ChemBlender.legacy.scaffold_bridge"
SCAFFOLD_MODULE = "ChemBlender.scaffold"
OUTPUT_MODULE = "ChemBlender.output"


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
            self.assertEqual(
                stage.canonical_parameters[stage.request.sources[0].id],
                {
                    "legacy_source_sha256": stage.content_hash,
                    "legacy_source_url": stage.source_url,
                },
            )

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


class LegacyOperatorRoutingTests(unittest.TestCase):
    def setUp(self):
        fake_bpy = ModuleType("bpy")
        fake_props = ModuleType("bpy.props")
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
        fake_bpy.types = SimpleNamespace(Operator=object, PropertyGroup=object)
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
                "ChemBlender._math": ModuleType("ChemBlender._math"),
                "ChemBlender.Chem_data": fake_data,
                "ChemBlender.mesh": ModuleType("ChemBlender.mesh"),
                "ChemBlender.node": ModuleType("ChemBlender.node"),
            },
        )
        self.modules.start()
        self.fake_bpy = fake_bpy
        for name in (SCAFFOLD_MODULE, OUTPUT_MODULE, SCAFFOLD_BRIDGE):
            sys.modules.pop(name, None)

    def tearDown(self):
        for name in (SCAFFOLD_MODULE, OUTPUT_MODULE, SCAFFOLD_BRIDGE):
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

    def test_legacy_cif_operator_uses_the_quick_import_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "legacy.cif"
            source.write_text("data_example\n", encoding="utf-8")
            scaffold, operator, context, calls = self._scaffold_context(source)
            with patch.object(
                scaffold.read,
                "read_Cryst",
                side_effect=AssertionError("legacy crystal parser must not run"),
            ):
                result = operator.execute(context)

        self.assertEqual(result, {"FINISHED"})
        self.assertEqual(calls[0][0], "quick_import")
        self.assertEqual(calls[0][2]["files"], [{"name": "legacy.cif"}])

    def test_legacy_pubchem_operator_passes_staged_source_provenance_to_quick_import(self):
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
        self.assertEqual(
            calls[0][2]["legacy_source_url"],
            stage.source_url,
        )
        self.assertEqual(calls[0][2]["legacy_source_hash"], stage.content_hash)

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


if __name__ == "__main__":
    unittest.main()
