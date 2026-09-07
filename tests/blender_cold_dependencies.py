"""Read-only verification in a new Blender process after an extension update.

Run with saved extension preferences and --python-exit-code 1, then pass
--package <zip> --output <json> after Blender's -- separator.
"""
import argparse
import hashlib
import importlib
import io
import json
from pathlib import Path
import sys
import zipfile

import bpy

parser = argparse.ArgumentParser()
parser.add_argument("--package", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
repo = next(r for r in bpy.context.preferences.extensions.repos if r.module == "user_default")
site = Path(repo.directory).parent / f".local/lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"
result = {"blender": bpy.app.version_string, "enabled": "bl_ext.user_default.chemblender" in bpy.context.preferences.addons,
          "package_sha256": hashlib.sha256(args.package.read_bytes()).hexdigest(), "modules": {}, "missing_or_changed": []}
for name in ("numpy", "rdkit.Chem", "gemmi"):
    try:
        module = importlib.import_module(name)
        result["modules"][name] = {"file": module.__file__}
        if name != "numpy":
            assert Path(module.__file__).is_relative_to(site), module.__file__
    except Exception as error:
        result["modules"][name] = {"error": f"{type(error).__name__}: {error}"}
with zipfile.ZipFile(args.package) as package:
    for name in package.namelist():
        if not name.endswith(".whl"):
            continue
        with zipfile.ZipFile(io.BytesIO(package.read(name))) as wheel:
            for member in wheel.namelist():
                if Path(member).suffix not in {".py", ".pyd", ".dll"}:
                    continue
                installed = site / member
                if not installed.is_file() or installed.read_bytes() != wheel.read(member):
                    result["missing_or_changed"].append(member)
args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
assert result["enabled"], result
assert not result["missing_or_changed"], result["missing_or_changed"]
assert not any("error" in value for value in result["modules"].values()), result["modules"]
print("PASS: cold extension dependency imports and wheel members")
