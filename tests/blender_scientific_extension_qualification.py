"""Installed-package entry checks; only a private project-cache profile is allowed."""

import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import sys
from zipfile import ZipFile

import bpy


ROOT = Path(__file__).resolve().parents[1]
mode, package_name, report_name = sys.argv[sys.argv.index("--") + 1:]
assert mode in {"install", "cold"}
profile = Path(os.environ["BLENDER_USER_RESOURCES"]).resolve(strict=True)
assert ROOT / ".agents" / "cache" in profile.parents
package = Path(package_name).resolve(strict=True)
module_key = "bl_ext.user_default.chemblender"
assert bpy.app.version >= (5, 1, 0)
repository = next(repo for repo in bpy.context.preferences.extensions.repos if repo.module == "user_default")
extension_directory = Path(repository.directory).resolve() / "chemblender"
assert profile in extension_directory.parents, extension_directory
assert profile in Path(bpy.utils.user_resource("EXTENSIONS")).resolve().parents
if mode == "install":
    assert module_key not in sys.modules
    assert not extension_directory.exists()
    assert bpy.ops.extensions.package_install_files(filepath=str(package), repo="user_default",
        enable_on_install=True, overwrite=False) == {"FINISHED"}
assert module_key in bpy.context.preferences.addons
module = importlib.import_module(module_key)
assert Path(module.__file__).resolve().parent == extension_directory
assert not any(name == "ChemBlender" or name.startswith("ChemBlender.") for name in sys.modules)
for forbidden in ("iodata", "gbasis", "scipy", "pymatgen", "pyprocar", "phonopy", "pyscf", "cclib"):
    assert not any(name == forbidden or name.startswith(forbidden + ".") for name in sys.modules), forbidden
with ZipFile(package) as archive:
    for name in archive.namelist():
        if name.endswith(".py"):
            assert hashlib.sha256((extension_directory / name).read_bytes()).digest() == hashlib.sha256(archive.read(name)).digest(), name

registration = importlib.import_module(module_key + ".runtime.registration")
bridge = importlib.import_module(module_key + ".runtime.reader_api_bridge")
ui_names = ("scientific_import", "scientific_view", "scientific_export", "topology_import")
properties = tuple("chemblender_" + name for name in ui_names)


def inventory():
    classes = registration._registered_classes
    for name, prop in zip(ui_names, properties):
        assert ".ui." + name in registration.REGISTER_MODULE_NAMES
        owned = [cls for cls in classes if cls.__module__ == module_key + ".ui." + name]
        assert owned and all(cls.is_registered for cls in owned), name
        assert hasattr(bpy.types.Scene, prop), prop
    readers = bridge.get_reader_plugin_registry().descriptors
    assert len(readers) == 22, len(readers)
    assert "chemblender.reader_api.v1" in bpy.app.driver_namespace
    return {"classes": sorted(cls.__module__ + "." + cls.__name__ for cls in classes),
            "readers": sorted(item.reader_id for item in readers)}


initial = inventory()
if mode == "install":
    for iteration in range(2):
        owned = registration._registered_classes
        assert bpy.ops.preferences.addon_disable(module=module_key) == {"FINISHED"}
        assert module_key not in bpy.context.preferences.addons
        assert all(not cls.is_registered for cls in owned)
        assert all(not hasattr(bpy.types.Scene, prop) for prop in properties)
        assert "chemblender.reader_api.v1" not in bpy.app.driver_namespace
        assert not any(getattr(callback, "__module__", "").startswith(module_key + ".")
            for name in ("load_pre", "load_post", "save_pre", "save_post", "frame_change_pre", "frame_change_post")
            for callback in getattr(bpy.app.handlers, name))
        if iteration == 1:
            # Re-importing the entry module exercises the explicit runtime
            # dispatcher without invalidating core class identities.
            module = importlib.reload(module)
        assert bpy.ops.preferences.addon_enable(module=module_key) == {"FINISHED"}
        assert inventory() == initial
    assert bpy.ops.wm.save_userpref() == {"FINISHED"}

import numpy
import rdkit
import gemmi
from rdkit import Chem
from rdkit.Chem import AllChem

assert rdkit.__version__ == "2026.03.3", rdkit.__version__
assert gemmi.__version__ == "0.7.5"
for dependency in (rdkit, gemmi):
    assert profile in Path(dependency.__file__).resolve().parents, dependency.__file__
assert profile not in Path(numpy.__file__).resolve().parents
molecule = Chem.AddHs(Chem.MolFromSmiles("CCO"))
assert AllChem.EmbedMolecule(molecule, randomSeed=0xC0FFEE) == 0
assert molecule.GetConformer().GetNumAtoms() == 9
assert gemmi.UnitCell(3, 3, 3, 90, 90, 90).volume == 27
for name in ("Chem_Nodes.blend", "Chem_Nodes_En.blend", "assets/Chem_Workspace.blend"):
    with bpy.data.libraries.load(str(extension_directory / name), link=False) as (source, _target):
        assert source.node_groups or source.workspaces, name
result = {"status": "Passed", "mode": mode, "version": bpy.app.version_string,
    "system": platform.system(), "executable": bpy.app.binary_path,
    "extension": str(extension_directory), "module_key": module_key,
    "profile": str(profile), "new_ui_modules": ui_names, "registration": initial,
    "rdkit": {"version": rdkit.__version__, "file": rdkit.__file__},
    "gemmi": {"version": gemmi.__version__, "file": gemmi.__file__},
    "numpy": {"version": numpy.__version__, "file": numpy.__file__}}
Path(report_name).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print("SCIENTIFIC_EXTENSION_QUALIFICATION_PASSED", mode, extension_directory)
