"""Run with Blender --background --disable-autoexec --python this_file -- ..."""

import argparse
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description="Export a legacy blend as CBQ and a display recovery report")
    parser.add_argument("--output", required=True, help="New directory containing project.cbq and migration.json")
    parser.add_argument("--preview", action="store_true", help="Print recovery report without writing files")
    parser.add_argument("--cancel-file")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else None)
    # Blender executes --python files without installing the external package.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from chemblender_prepare.legacy.export import export_legacy_scene
    result = export_legacy_scene(args.output, preview=args.preview, cancel_file=args.cancel_file)
    print(json.dumps(result, ensure_ascii=True, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
