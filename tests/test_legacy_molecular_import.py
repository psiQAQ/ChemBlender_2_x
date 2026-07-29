import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch


MODULE = "ChemBlender.read"
SCAFFOLD_MODULE = "ChemBlender.scaffold"


class LegacyMolecularImportTests(unittest.TestCase):
    def setUp(self):
        fake_bpy = ModuleType("bpy")
        fake_props = ModuleType("bpy.props")
        for name in (
            "CollectionProperty",
            "FloatProperty",
            "IntProperty",
            "StringProperty",
        ):
            setattr(fake_props, name, lambda **_keywords: None)
        fake_bpy.props = fake_props
        fake_bpy.types = SimpleNamespace(Operator=object, PropertyGroup=object)
        fake_bpy.context = SimpleNamespace(
            preferences=SimpleNamespace(
                view=SimpleNamespace(language="en_US")
            ),
            scene=SimpleNamespace(
                cursor=SimpleNamespace(location=SimpleNamespace(x=0, y=0, z=0))
            )
        )
        fake_bpy.path = SimpleNamespace(abspath=lambda value: value)
        fake_bpy.ops = SimpleNamespace(
            chemblender=SimpleNamespace(),
            error=SimpleNamespace(custom_dialog=lambda *_args, **_kwargs: None),
        )
        fake_math = ModuleType("ChemBlender._math")
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
                "ChemBlender._math": fake_math,
                "ChemBlender.Chem_data": fake_data,
                "ChemBlender.mesh": ModuleType("ChemBlender.mesh"),
                "ChemBlender.node": ModuleType("ChemBlender.node"),
            },
        )
        self.modules.start()
        self.fake_bpy = fake_bpy
        sys.modules.pop(MODULE, None)
        sys.modules.pop(SCAFFOLD_MODULE, None)
        self.module = importlib.import_module(MODULE)

    def tearDown(self):
        sys.modules.pop(MODULE, None)
        sys.modules.pop(SCAFFOLD_MODULE, None)
        self.modules.stop()

    def scaffold_fixture(self, choose, **inputs):
        calls = []

        def operation(name):
            def invoke(*args, **kwargs):
                calls.append((name, args, kwargs))
                return {"FINISHED"}

            return invoke

        self.fake_bpy.ops.chemblender = SimpleNamespace(
            import_smiles_text=operation("import_smiles_text"),
            quick_import=operation("quick_import"),
        )
        scaffold = importlib.import_module(SCAFFOLD_MODULE)
        operator = scaffold.MESH_OT_SCAFFOLD_BUILD()
        operator.filter = ""
        reports = []
        operator.report = lambda levels, message: reports.append((levels, message))
        mytool = SimpleNamespace(
            choose=choose,
            filetext=inputs.get("filetext", ""),
            smilestext=inputs.get("smilestext", ""),
            Saccharides=inputs.get("Saccharides", "sugar"),
            Amino_Acids=inputs.get("Amino_Acids", "amino"),
            Polymer_Units=inputs.get("Polymer_Units", "polymer"),
        )
        context = SimpleNamespace(
            scene=SimpleNamespace(
                my_tool=mytool,
                chemblender_quick_import=SimpleNamespace(
                    validation_mode="strict"
                ),
            ),
            window_manager=object(),
        )
        return operator, context, calls, reports

    def test_none_and_mol2_are_controlled_unsupported_inputs(self):
        with patch.object(self.module, "check_type", return_value=None):
            with self.assertRaisesRegex(
                ValueError,
                "Unsupported molecular input",
            ):
                self.module.read_MOL("not a molecule")

        with patch.object(self.module, "check_type", return_value="mol2"):
            with self.assertRaisesRegex(
                NotImplementedError,
                "MOL2 is not supported",
            ):
                self.module.read_MOL("molecule.mol2")

    def test_smiles_parse_none_fails_before_add_hydrogens(self):
        fake_rdkit = ModuleType("rdkit")
        fake_chem = ModuleType("rdkit.Chem")
        add_hydrogens = Mock(
            side_effect=RuntimeError("AddHs must not receive None")
        )
        fake_chem.AllChem = SimpleNamespace()
        fake_chem.MolFromSmiles = Mock(return_value=None)
        fake_chem.AddHs = add_hydrogens
        fake_rdkit.Chem = fake_chem

        with (
            patch.dict(
                sys.modules,
                {"rdkit": fake_rdkit, "rdkit.Chem": fake_chem},
            ),
            patch.object(self.module, "check_type", return_value="smiles"),
        ):
            with self.assertRaisesRegex(
                ValueError,
                "Unable to parse smiles molecular input",
            ):
                self.module.read_MOL("invalid")

        add_hydrogens.assert_not_called()

    def test_cid_parse_none_fails_before_2d_to_3d_conversion(self):
        fake_rdkit = ModuleType("rdkit")
        fake_chem = ModuleType("rdkit.Chem")
        convert = Mock(
            side_effect=RuntimeError("mol_2D_to_3D must not receive None")
        )
        fake_chem.AllChem = SimpleNamespace()
        fake_chem.MolFromMolBlock = Mock(return_value=None)
        fake_rdkit.Chem = fake_chem

        with (
            patch.dict(
                sys.modules,
                {"rdkit": fake_rdkit, "rdkit.Chem": fake_chem},
            ),
            patch.object(self.module, "check_type", return_value="cid"),
            patch.object(
                self.module,
                "download_sdf_from_pubchem",
                return_value=(b"invalid", None, None),
            ),
            patch.object(self.module, "mol_2D_to_3D", convert),
        ):
            with self.assertRaisesRegex(
                ValueError,
                "Unable to parse cid molecular input",
            ):
                self.module.read_MOL("123")

        convert.assert_not_called()

    def test_legacy_file_action_delegates_exact_quick_import_payload(self):
        source = (Path.cwd() / "fixtures" / "records.sdf").resolve()
        operator, context, calls, reports = self.scaffold_fixture(
            "File",
            filetext=str(source),
        )

        self.assertEqual(operator.execute(context), {"FINISHED"})
        self.assertEqual(
            calls,
            [
                (
                    "quick_import",
                    ("EXEC_DEFAULT",),
                    {
                        "directory": str(source.parent),
                        "files": [{"name": source.name}],
                        "validation_mode": "strict",
                    },
                )
            ],
        )
        self.assertEqual(reports, [])

    def test_legacy_canonical_contcar_routes_to_quick_import(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "CONTCAR"
            source.touch()
            operator, context, calls, reports = self.scaffold_fixture(
                "File",
                filetext=str(source),
            )

            self.assertEqual(operator.execute(context), {"FINISHED"})

        self.assertEqual(calls[0][0], "quick_import")
        self.assertEqual(calls[0][2]["files"], [{"name": "CONTCAR"}])
        self.assertEqual(reports, [])

    def test_legacy_smiles_action_delegates_exact_reader_api_payload(self):
        operator, context, calls, reports = self.scaffold_fixture(
            "SMILES",
            smilestext="C/C=C/C",
        )

        self.assertEqual(operator.execute(context), {"FINISHED"})
        self.assertEqual(
            calls,
            [
                (
                    "import_smiles_text",
                    ("EXEC_DEFAULT",),
                    {
                        "smiles_text": "C/C=C/C",
                        "validation_mode": "strict",
                    },
                )
            ],
        )
        self.assertEqual(reports, [])

    def test_builtin_smiles_actions_delegate_to_reader_api(self):
        cases = (
            ("Saccharides", "OC"),
            ("Amino_Acids", "NCC(=O)O"),
            ("Polymer_Units", "CC"),
        )
        for choose, expected_smiles in cases:
            with self.subTest(choose=choose):
                operator, context, calls, reports = self.scaffold_fixture(
                    choose
                )
                with patch.object(
                    self.module,
                    "read_MOL",
                    side_effect=AssertionError("read_MOL must not be called"),
                ) as read_mol:
                    result = operator.execute(context)

                self.assertEqual(result, {"FINISHED"})
                self.assertEqual(
                    calls,
                    [
                        (
                            "import_smiles_text",
                            ("EXEC_DEFAULT",),
                            {
                                "smiles_text": expected_smiles,
                                "validation_mode": "strict",
                            },
                        )
                    ],
                )
                self.assertEqual(reports, [])
                read_mol.assert_not_called()

    def test_legacy_mol2_action_routes_to_quick_import(self):
        source = (
            Path(__file__).with_name("fixtures")
            / "mol2"
            / "substructure.mol2"
        ).resolve()
        operator, context, calls, reports = self.scaffold_fixture(
            "File",
            filetext=str(source),
        )

        self.assertEqual(operator.execute(context), {"FINISHED"})
        self.assertEqual(
            calls,
            [
                (
                    "quick_import",
                    ("EXEC_DEFAULT",),
                    {
                        "directory": str(source.parent),
                        "files": [{"name": source.name}],
                        "validation_mode": "strict",
                    },
                )
            ],
        )
        self.assertEqual(reports, [])


if __name__ == "__main__":
    unittest.main()
