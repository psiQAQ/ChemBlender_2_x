import array
import importlib
import importlib.util
import sys
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
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
    assert f"{module_key}.core.cube" in sys.modules
    assert f"{module_key}.core.mol_v2000" in sys.modules
    assert f"{module_key}.core.xyz" in sys.modules
    assert f"{module_key}.core.wavefunction_grid" in sys.modules
    assert "gbasis" not in sys.modules
    assert f"{module_key}.grid_volume" in sys.modules
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


def assert_grid_volume_adapter(module_key):
    import openvdb

    core = importlib.import_module(f"{module_key}.core")
    adapter = importlib.import_module(f"{module_key}.grid_volume")
    values = memoryview(array.array("d", range(8)))
    values = values.cast("B").cast("d", shape=(2, 2, 2))
    dataset_id = uuid4()
    grid = core.Grid3D(
        id=dataset_id,
        revision="grid-revision",
        semantic_role="molecular_orbital",
        domain="grid",
        data=core.ArrayData(
            values, ("x", "y", "z"), "inverse_bohr_to_three_halves"
        ),
        status=core.DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(),
        origin=(1.0, 2.0, 3.0),
        step_vectors=((1.0, 0.0, 0.0), (0.2, 1.0, 0.0), (0.0, 0.3, 1.0)),
        coordinate_unit="bohr",
    )
    with TemporaryDirectory() as directory:
        cache = Path(directory) / "grid.vdb"
        obj = adapter.create_grid_volume(
            grid,
            cache,
            collection=bpy.context.scene.collection,
        )
        volume = obj.data
        try:
            assert cache.is_file()
            assert obj.type == "VOLUME" and obj.matrix_world.is_identity
            assert len(volume.grids) == 1 and volume.grids["density"] is not None
            assert obj["cb_dataset_id"] == str(dataset_id)
            assert obj["cb_dataset_revision"] == "grid-revision"
            assert obj["cb_dataset_index"] == 0
            assert obj["cb_semantic_role"] == "molecular_orbital"
            assert obj["cb_value_unit"] == "inverse_bohr_to_three_halves"
            assert obj["cb_source_coordinate_unit"] == "bohr"
            assert obj["cb_display_coordinate_unit"] == "angstrom"
            cached = openvdb.read(str(cache), "density")
            assert cached.getAccessor().getValue((1, 0, 1)) == 5.0
            expected = tuple(value * 0.529177210903 for value in (2.2, 3.3, 4.0))
            actual = tuple(cached.transform.indexToWorld((1, 1, 1)))
            assert all(abs(a - b) < 1e-12 for a, b in zip(actual, expected))
        finally:
            bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.volumes.remove(volume)


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
assert_grid_volume_adapter(module_key)

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
