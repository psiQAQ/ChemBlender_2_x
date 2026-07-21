#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tomllib
import zipfile
from pathlib import Path, PurePosixPath


TAG_PATTERN = re.compile(r"v(\d+)\.(\d+)\.(\d+)")
CHECKSUM_PATTERN = re.compile(r"([0-9a-fA-F]{64})\s+\*?(.+)")
REQUIRED_FILES = {
    "blender_manifest.toml",
    "LICENSE",
    "Chem_Nodes.blend",
    "Chem_Nodes_En.blend",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _version_from_tag(tag: str) -> str:
    match = TAG_PATTERN.fullmatch(tag)
    if not match:
        raise ValueError(f"invalid release tag: {tag}")
    return ".".join(match.groups())


def _validate_archive_path(name: str) -> None:
    path = PurePosixPath(name)
    if not path.parts or "\\" in name or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe ZIP path: {name}")
    if "__pycache__" in path.parts or path.parts[0] in {"scripts", "tests"}:
        raise ValueError(f"development path in ZIP: {name}")
    if path.suffix.lower() == ".zip":
        raise ValueError(f"nested ZIP in package: {name}")


def verify_artifact(
    artifact_dir: Path, extension_root: Path, tag: str
) -> dict[str, str]:
    artifact_dir = artifact_dir.resolve()
    extension_root = extension_root.resolve()
    version = _version_from_tag(tag)
    package_name = f"chemblender-{version}.zip"
    checksum_name = f"chemblender-{version}.sha256"
    expected_files = {package_name, checksum_name}
    actual_files = {
        path.relative_to(artifact_dir).as_posix()
        for path in artifact_dir.rglob("*")
        if path.is_file()
    }
    if actual_files != expected_files:
        raise ValueError(
            f"artifact files must be {sorted(expected_files)}, got {sorted(actual_files)}"
        )

    package = artifact_dir / package_name
    checksum = artifact_dir / checksum_name
    checksum_match = CHECKSUM_PATTERN.fullmatch(
        checksum.read_text(encoding="utf-8").strip()
    )
    if not checksum_match or checksum_match.group(2) != package_name:
        raise ValueError(f"invalid checksum record: {checksum_name}")

    package_digest = _sha256(package)
    if package_digest != checksum_match.group(1).lower():
        raise ValueError(f"package checksum mismatch: {package_digest}")

    source_manifest = (extension_root / "blender_manifest.toml").read_bytes()
    manifest = tomllib.loads(source_manifest.decode("utf-8"))
    if manifest.get("version") != version:
        raise ValueError(
            f"tag version {version} does not match manifest {manifest.get('version')}"
        )
    declared_wheels = {
        str(PurePosixPath(wheel.removeprefix("./")))
        for wheel in manifest.get("wheels", [])
    }

    with zipfile.ZipFile(package) as archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise ValueError("duplicate ZIP entries")
        for name in names:
            _validate_archive_path(name)
        if archive.testzip() is not None:
            raise ValueError("ZIP CRC validation failed")
        archive_files = set(names)
        missing = REQUIRED_FILES - archive_files
        if missing:
            raise ValueError(f"required ZIP files missing: {sorted(missing)}")
        wheel_entries = {name for name in names if name.lower().endswith(".whl")}
        if wheel_entries != declared_wheels:
            raise ValueError(
                f"wheel entries must be {sorted(declared_wheels)}, got {sorted(wheel_entries)}"
            )
        packaged_manifest = tomllib.loads(
            archive.read("blender_manifest.toml").decode("utf-8")
        )
        if packaged_manifest != manifest:
            raise ValueError("packaged manifest differs from checked-out tag")

    return {
        "version": version,
        "package": package_name,
        "checksum": checksum_name,
        "package_sha256": package_digest,
        "checksum_sha256": _sha256(checksum),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a ChemBlender release artifact.")
    parser.add_argument("--artifact-dir", required=True, type=Path)
    parser.add_argument("--extension-root", type=Path, default=Path(__file__).parents[1])
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()

    try:
        result = verify_artifact(args.artifact_dir, args.extension_root, args.tag)
    except (OSError, ValueError, tomllib.TOMLDecodeError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
