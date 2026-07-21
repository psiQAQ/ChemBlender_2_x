import importlib.util
import sys
from importlib.metadata import version
from pathlib import Path
from zipfile import ZipFile

import bpy


def assert_package_contents(package):
    required = {
        "blender_manifest.toml",
        "LICENSE",
        "Chem_Nodes.blend",
        "Chem_Nodes_En.blend",
        "wheels/rdkit-2026.3.3-cp313-cp313-win_amd64.whl",
    }
    forbidden_prefixes = ("scripts/", "tests/", "__pycache__/")

    with ZipFile(package) as archive:
        names = {entry.filename.replace("\\", "/") for entry in archive.infolist()}

    assert required <= names, required - names
    assert not any(name.startswith(forbidden_prefixes) for name in names)
    assert not any(name.endswith(".zip") for name in names)
    assert [name for name in names if name.endswith(".whl")] == [
        "wheels/rdkit-2026.3.3-cp313-cp313-win_amd64.whl"
    ]


def assert_enabled(module_key):
    assert module_key in bpy.context.preferences.addons
    assert f"{module_key}.core.xyz" in sys.modules
    assert hasattr(bpy.types.Object, "cif_original")
    assert hasattr(bpy.types.Object, "cif_current")
    assert hasattr(bpy.types.Scene, "my_tool")


def assert_disabled(module_key):
    assert module_key not in bpy.context.preferences.addons
    assert not hasattr(bpy.types.Object, "cif_original")
    assert not hasattr(bpy.types.Object, "cif_current")
    assert not hasattr(bpy.types.Scene, "my_tool")


def assert_installed_blend_libraries(module_key):
    spec = importlib.util.find_spec(module_key)
    assert spec is not None and spec.submodule_search_locations
    extension_root = Path(next(iter(spec.submodule_search_locations)))
    expected_node_groups = {
        "Chem_Nodes.blend": 174,
        "Chem_Nodes_En.blend": 171,
    }

    for filename, expected_count in expected_node_groups.items():
        blend_file = extension_root / filename
        assert blend_file.is_file(), blend_file
        with bpy.data.libraries.load(str(blend_file), link=False) as (data_from, _):
            assert len(data_from.node_groups) == expected_count, filename


arguments = sys.argv[sys.argv.index("--") + 1 :]
assert len(arguments) in (1, 2), "expected ZIP path and optional --keep-enabled"
assert len(arguments) == 1 or arguments[1] == "--keep-enabled"
keep_enabled = arguments[1:] == ["--keep-enabled"]
package = Path(arguments[0]).resolve()
assert package.is_file(), package
assert_package_contents(package)

result = bpy.ops.extensions.package_install_files(
    filepath=str(package),
    repo="user_default",
    enable_on_install=True,
    overwrite=True,
)
assert result == {"FINISHED"}, result

module_key = "bl_ext.user_default.chemblender"
assert_enabled(module_key)
assert_installed_blend_libraries(module_key)

for _ in range(2):
    assert bpy.ops.preferences.addon_disable(module=module_key) == {"FINISHED"}
    assert_disabled(module_key)
    assert bpy.ops.preferences.addon_enable(module=module_key) == {"FINISHED"}
    assert_enabled(module_key)

import rdkit
from rdkit import Chem
from rdkit.Chem import AllChem

assert rdkit.__version__
assert version("rdkit") == "2026.3.3"
molecule = Chem.AddHs(Chem.MolFromSmiles("CCO"))
assert molecule is not None
assert AllChem.EmbedMolecule(molecule, randomSeed=0xC0FFEE) == 0

if keep_enabled:
    print("PASS: ChemBlender extension installed and enabled")
else:
    assert bpy.ops.preferences.addon_disable(module=module_key) == {"FINISHED"}
    assert_disabled(module_key)
    print("PASS: ChemBlender extension lifecycle")
