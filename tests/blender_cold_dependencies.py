"""Read-only verification in a new Blender process after an extension update.

Run with saved extension preferences and --python-exit-code 1, then pass
--package <zip> --output <json> after Blender's -- separator.
"""
import argparse
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import sys
import zipfile

import bpy

parser = argparse.ArgumentParser()
parser.add_argument("--package", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
result = {"blender": bpy.app.version_string, "enabled": "bl_ext.user_default.chemblender" in bpy.context.preferences.addons,
          "package_sha256": hashlib.sha256(args.package.read_bytes()).hexdigest(), "modules": {}, "missing_or_changed": []}
numpy = importlib.import_module("numpy")
result["modules"]["numpy"] = {"file": numpy.__file__}
for name in ("rdkit", "gemmi"):
    result["modules"][name] = {"available": importlib.util.find_spec(name) is not None}
with zipfile.ZipFile(args.package) as package:
    assert not any(name.endswith(".whl") for name in package.namelist())
args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
assert result["enabled"], result
assert not result["missing_or_changed"], result["missing_or_changed"]
assert not result["modules"]["rdkit"]["available"], result["modules"]
assert not result["modules"]["gemmi"]["available"], result["modules"]
print("PASS: cold wheel-free extension and bundled NumPy")
