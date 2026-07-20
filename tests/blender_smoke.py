import sys
from importlib.metadata import version
from pathlib import Path

import bpy


def assert_enabled(module_key):
    assert module_key in bpy.context.preferences.addons
    assert hasattr(bpy.types.Object, "cif_original")
    assert hasattr(bpy.types.Object, "cif_current")
    assert hasattr(bpy.types.Scene, "my_tool")


def assert_disabled(module_key):
    assert module_key not in bpy.context.preferences.addons
    assert not hasattr(bpy.types.Object, "cif_original")
    assert not hasattr(bpy.types.Object, "cif_current")
    assert not hasattr(bpy.types.Scene, "my_tool")


arguments = sys.argv[sys.argv.index("--") + 1 :]
assert len(arguments) == 1, "expected one extension ZIP path"
package = Path(arguments[0]).resolve()
assert package.is_file(), package

result = bpy.ops.extensions.package_install_files(
    filepath=str(package),
    repo="user_default",
    enable_on_install=True,
    overwrite=True,
)
assert result == {"FINISHED"}, result

module_key = "bl_ext.user_default.chemblender"
assert_enabled(module_key)

import rdkit

assert rdkit.__version__
assert version("rdkit") == "2026.3.3"

for _ in range(2):
    assert bpy.ops.preferences.addon_disable(module=module_key) == {"FINISHED"}
    assert_disabled(module_key)
    assert bpy.ops.preferences.addon_enable(module=module_key) == {"FINISHED"}
    assert_enabled(module_key)

assert bpy.ops.preferences.addon_disable(module=module_key) == {"FINISHED"}
assert_disabled(module_key)
print("PASS: ChemBlender extension lifecycle")
