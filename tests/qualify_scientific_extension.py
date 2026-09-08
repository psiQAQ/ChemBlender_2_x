"""Snapshot and qualify the evolving extension without touching a user profile."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tomllib
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]


def document(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if ROOT / ".agents" / "cache" not in output.parents:
        raise ValueError("qualification output must be a new project-cache directory")
    output.mkdir(parents=True, exist_ok=False)
    snapshot = output / "source" / "ChemBlender"
    source = ROOT / "ChemBlender"
    hashes = {}
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if not path.is_file() or "__pycache__" in relative.parts or path.suffix in {".zip", ".pyc"}:
            continue
        if path.is_symlink():
            raise ValueError(f"unexpected source symlink: {path}")
        data = path.read_bytes()
        target = snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        hashes[relative.as_posix()] = hashlib.sha256(data).hexdigest()
    document(output / "source-hashes.json", hashes)
    profile = output / "profile"
    profile.mkdir()
    env = dict(os.environ, BLENDER_USER_RESOURCES=str(profile), PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1")
    env.pop("PYTHONPATH", None)

    def run(name, command):
        with (output / (name + ".log")).open("wb") as log:
            result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
        print(name, result.returncode, flush=True)
        if result.returncode:
            raise RuntimeError(f"{name} failed; inspect {output / (name + '.log')}")

    scripts = snapshot / "scripts"
    run("wheel-inventory", [args.python, "-B", str(scripts / "dependency_inventory.py"),
        "--manifest", str(snapshot / "blender_manifest.toml"),
        "--output", str(output / "wheel-inventory.json"),
        "--license-copy-list", str(output / "wheel-license-copy-list.json")])
    run("validate-build", [args.python, "-B", str(scripts / "build_extension.py"),
        "--python", args.python, "--blender", args.blender, "--no-path-lookup"])
    manifest = tomllib.loads((snapshot / "blender_manifest.toml").read_text(encoding="utf-8"))
    package = snapshot / (manifest["id"] + "-" + manifest["version"] + ".zip")
    with ZipFile(package) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names)), "duplicate ZIP members"
        assert archive.testzip() is None
        for name in names:
            path = PurePosixPath(name)
            assert not path.is_absolute() and ".." not in path.parts and "\\" not in name and ":" not in name
            assert not ({"submodules", "worker", "scripts", "tests", ".agents", ".planning", "__pycache__"} & set(path.parts)), name
            assert not name.endswith((".pyc", ".zip", ".npy", ".cbq")), name
            if not name.endswith("/"):
                assert hashlib.sha256(archive.read(name)).hexdigest() == hashes[name], name
        required = {"__init__.py", "blender_manifest.toml", "LICENSE", "Chem_Nodes.blend", "Chem_Nodes_En.blend", "assets/Chem_Workspace.blend"}
        required.update("ui/" + item + ".py" for item in ("scientific_view", "scientific_import", "scientific_export", "topology_import"))
        assert required <= set(names), required - set(names)
        assert sorted(name for name in names if name.endswith(".whl")) == sorted(name.removeprefix("./") for name in manifest["wheels"])
    audit = {"package": str(package), "sha256": hashlib.sha256(package.read_bytes()).hexdigest(),
             "bytes": package.stat().st_size, "member_count": len(names), "members": names,
             "status": "Passed", "scope": "initial snapshot qualification; not a release gate"}
    document(output / "zip-audit.json", audit)
    runtime = ROOT / "tests" / "blender_scientific_extension_qualification.py"
    run("install", [args.blender, "--background", "--factory-startup", "--python-exit-code", "1",
        "--python", str(runtime), "--", "install", str(package), str(output / "install.json")])
    run("cold-start", [args.blender, "--background", "--python-exit-code", "1",
        "--python", str(runtime), "--", "cold", str(package), str(output / "cold-start.json")])
    current = {path.relative_to(source).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in source.rglob("*") if path.is_file()
        and "__pycache__" not in path.relative_to(source).parts and path.suffix not in {".zip", ".pyc"}}
    drift = sorted(name for name in hashes.keys() | current.keys() if hashes.get(name) != current.get(name))
    document(output / "qualification.json", {"status": "Passed", "scope": audit["scope"],
        "package": str(package), "profile": str(profile), "source_changed_since_snapshot": drift,
        "install": json.loads((output / "install.json").read_text()),
        "cold_start": json.loads((output / "cold-start.json").read_text())})
    print(package, flush=True)
    print(profile, flush=True)


if __name__ == "__main__":
    main()
