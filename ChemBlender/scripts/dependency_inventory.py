#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import tomllib
import zipfile
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    path.write_text(text + "\n", encoding="utf-8", newline="\n")
    return text


def _safe_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = archive.infolist()
    names: set[str] = set()
    for member in members:
        name = member.filename.replace("\\", "/")
        if member.is_dir():
            name = name.removesuffix("/")
        parts = name.split("/")
        if (
            not name
            or name.startswith("/")
            or (len(name) >= 2 and name[0].isalpha() and name[1] == ":")
            or any(part in {"", ".", ".."} for part in parts)
        ):
            raise ValueError(f"unsafe wheel member path: {member.filename}")
        if name in names:
            raise ValueError(f"duplicate wheel member path: {member.filename}")
        names.add(name)
    return members


def inventory(
    inventory_path: Path, wheel_dir: Path, manifest_path: Path | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    with inventory_path.open("rb") as handle:
        config = tomllib.load(handle)
    dependencies = config["dependency"]
    if manifest_path is not None:
        with manifest_path.open("rb") as handle:
            manifest = tomllib.load(handle)
        expected_wheels = [
            f"./wheels/{dependency['filename']}"
            for dependency in dependencies
            if dependency["required"]
        ]
        if manifest.get("wheels") != expected_wheels:
            raise ValueError("manifest wheel paths must equal required inventory")
    wheels: list[dict[str, Any]] = []
    licenses: list[dict[str, str]] = []
    for dependency in dependencies:
        if not dependency["required"]:
            continue
        wheel = wheel_dir / dependency["filename"]
        actual_sha256 = _sha256(wheel)
        if actual_sha256 != dependency["sha256"]:
            raise ValueError(f"wheel hash mismatch: {wheel.name}")
        with zipfile.ZipFile(wheel) as archive:
            members = _safe_members(archive)
            member_names = {member.filename for member in members}
            if dependency["license_source"] not in member_names:
                raise ValueError(f"license source missing: {dependency['license_source']}")
            unpacked_bytes = sum(member.file_size for member in members)
        compressed_bytes = wheel.stat().st_size
        if compressed_bytes > dependency["max_compressed_bytes"]:
            raise ValueError(f"compressed size exceeds budget: {wheel.name}")
        if unpacked_bytes > dependency["max_unpacked_bytes"]:
            raise ValueError(f"unpacked size exceeds budget: {wheel.name}")
        item = dict(dependency)
        item["compressed_bytes"] = compressed_bytes
        item["unpacked_bytes"] = unpacked_bytes
        wheels.append(item)
        license_name = Path(dependency["license_source"]).name
        licenses.append(
            {
                "distribution": dependency["distribution"],
                "filename": dependency["filename"],
                "source": dependency["license_source"],
                "target": f"licenses/{dependency['distribution']}-{dependency['version']}-{license_name}",
                "version": dependency["version"],
            }
        )
    wheels.sort(key=lambda item: item["filename"])
    licenses.sort(key=lambda item: item["filename"])
    return {"wheels": wheels}, {"licenses": licenses}


def main(argv: list[str] | None = None) -> int:
    extension_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Verify ChemBlender wheel inventory.")
    parser.add_argument("--inventory", type=Path, default=extension_root / "dependencies.toml")
    parser.add_argument("--wheel-dir", type=Path, default=extension_root / "wheels")
    parser.add_argument("--output", type=Path, default=Path("wheel-inventory.json"))
    parser.add_argument("--license-copy-list", type=Path, default=Path("wheel-license-copy-list.json"))
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args(argv)
    try:
        wheel_inventory, license_copy_list = inventory(
            args.inventory, args.wheel_dir, args.manifest
        )
        output = _write_json(args.output, wheel_inventory)
        _write_json(args.license_copy_list, license_copy_list)
    except (KeyError, OSError, ValueError, zipfile.BadZipFile, tomllib.TOMLDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
