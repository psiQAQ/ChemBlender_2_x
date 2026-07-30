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

if __package__:
    from .artifact_size_report import (
        _bounded_outer_archive,
        _load_budget,
        build_report,
        canonical_json,
    )
    from .dependency_inventory import _license_target, _safe_members, _validate_schema
    from .release_metadata import parse_release_version, read_release_metadata
else:
    from artifact_size_report import (
        _bounded_outer_archive,
        _load_budget,
        build_report,
        canonical_json,
    )
    from dependency_inventory import _license_target, _safe_members, _validate_schema
    from release_metadata import parse_release_version, read_release_metadata


CHECKSUM_PATTERN = re.compile(r"([0-9a-fA-F]{64})\s+\*?(.+)")
REQUIRED_FILES = {
    "blender_manifest.toml",
    "LICENSE",
    "Chem_Nodes.blend",
    "Chem_Nodes_En.blend",
}
METADATA_MODES = frozenset({"package-ci", "release-assets"})
PACKAGE_CI_METADATA_FILES = {
    "artifact-size.json",
    "wheel-inventory.json",
    "wheel-license-copy-list.json",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _version_from_tag(tag: str) -> str:
    if type(tag) is not str or not tag.startswith("v"):
        raise ValueError(f"invalid release tag: {tag}")
    try:
        return parse_release_version(tag[1:]).value
    except ValueError as exc:
        raise ValueError(f"invalid release tag: {tag}") from exc


def _validate_archive_path(name: str) -> None:
    path = PurePosixPath(name)
    if "__pycache__" in path.parts or path.parts[0] in {"scripts", "tests"}:
        raise ValueError(f"development path in ZIP: {name}")
    if path.suffix.lower() == ".zip":
        raise ValueError(f"nested ZIP in package: {name}")


def _canonical_json_file(path: Path, label: str) -> bytes:
    try:
        contents = path.read_bytes()
        document = json.loads(contents.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid {label} metadata: {exc}") from exc
    if type(document) is not dict:
        raise ValueError(f"invalid {label} metadata: root must be an object")
    expected = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
    if contents != expected:
        raise ValueError(f"invalid {label} metadata: not canonical")
    return contents


def _tagged_dependency_metadata(
    extension_root: Path,
    inventory: bytes,
) -> tuple[dict[str, object], dict[str, object]]:
    with (extension_root / "dependencies.toml").open("rb") as stream:
        dependencies = _validate_schema(tomllib.load(stream))
    document = json.loads(inventory)
    wheels_document = document.get("wheels")
    if type(wheels_document) is not list:
        raise ValueError("wheel inventory does not match tagged dependencies")
    actual_by_filename: dict[str, dict[str, object]] = {}
    for wheel in wheels_document:
        if type(wheel) is not dict or type(wheel.get("filename")) is not str:
            raise ValueError("wheel inventory does not match tagged dependencies")
        filename = wheel["filename"]
        if filename in actual_by_filename:
            raise ValueError("wheel inventory does not match tagged dependencies")
        actual_by_filename[filename] = wheel
    required = sorted(
        (dependency for dependency in dependencies if dependency["required"]),
        key=lambda dependency: dependency["filename"],
    )
    if set(actual_by_filename) != {dependency["filename"] for dependency in required}:
        raise ValueError("wheel inventory does not match tagged dependencies")
    wheels: list[dict[str, object]] = []
    licenses: list[dict[str, str]] = []
    for dependency in required:
        filename = dependency["filename"]
        actual = actual_by_filename[filename]
        compressed_bytes = actual.get("compressed_bytes")
        unpacked_bytes = actual.get("unpacked_bytes")
        if (
            type(compressed_bytes) is not int
            or compressed_bytes <= 0
            or type(unpacked_bytes) is not int
            or unpacked_bytes <= 0
        ):
            raise ValueError("wheel inventory does not match tagged dependencies")
        item = dict(dependency)
        item["compressed_bytes"] = compressed_bytes
        item["unpacked_bytes"] = unpacked_bytes
        wheels.append(item)
        licenses.append(
            {
                "distribution": dependency["distribution"],
                "filename": filename,
                "source": dependency["license_source"],
                "target": _license_target(dependency),
                "version": dependency["version"],
            }
        )
    wheels.sort(key=lambda wheel: str(wheel["filename"]))
    licenses.sort(key=lambda license_entry: license_entry["filename"])
    return {"wheels": wheels}, {"licenses": licenses}


def _verify_package_metadata(
    artifact_dir: Path,
    extension_root: Path,
    package: Path,
    budget_path: Path,
) -> None:
    report_path = artifact_dir / "artifact-size.json"
    inventory_path = artifact_dir / "wheel-inventory.json"
    license_path = artifact_dir / "wheel-license-copy-list.json"
    report = _canonical_json_file(report_path, "artifact-size")
    inventory = _canonical_json_file(inventory_path, "wheel inventory")
    licenses = _canonical_json_file(license_path, "license copy list")
    expected_inventory, expected_licenses = _tagged_dependency_metadata(
        extension_root, inventory
    )
    if inventory != canonical_json(expected_inventory):
        raise ValueError("wheel inventory does not match tagged dependencies")
    if licenses != canonical_json(expected_licenses):
        raise ValueError("license copy list does not match tagged dependencies")
    expected = canonical_json(
        build_report(
            package,
            inventory_path,
            license_path,
            budget_path,
        )
    )
    if report != expected:
        raise ValueError("artifact-size metadata does not match package")


def verify_artifact(
    artifact_dir: Path,
    extension_root: Path,
    tag: str,
    *,
    metadata_mode: str,
    budget_path: Path | None = None,
) -> dict[str, str]:
    if metadata_mode not in METADATA_MODES:
        raise ValueError(f"invalid metadata mode: {metadata_mode}")
    if metadata_mode == "package-ci" and budget_path is None:
        raise ValueError("package-ci metadata mode requires a budget path")
    if metadata_mode == "release-assets" and budget_path is not None:
        raise ValueError("release-assets metadata mode must not have a budget path")
    budget = _load_budget(budget_path) if budget_path is not None else None
    artifact_dir = artifact_dir.resolve()
    extension_root = extension_root.resolve()
    metadata = read_release_metadata(extension_root)
    tag_version = _version_from_tag(tag)
    if tag_version != metadata.version:
        raise ValueError(
            f"tag version {tag_version} does not match manifest {metadata.version}"
        )
    version = metadata.version
    package_name = metadata.package_name
    checksum_name = metadata.checksum_name
    expected_files = {package_name, checksum_name}
    if metadata_mode == "package-ci":
        expected_files |= PACKAGE_CI_METADATA_FILES
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
    declared_wheels = {
        str(PurePosixPath(wheel.removeprefix("./")))
        for wheel in manifest.get("wheels", [])
    }

    with zipfile.ZipFile(package) as archive:
        members = _safe_members(archive)
        if budget is not None:
            _bounded_outer_archive(members, budget)
        names = list(members)
        for name in names:
            _validate_archive_path(name)
        if metadata_mode == "release-assets" and archive.testzip() is not None:
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
    if metadata_mode == "package-ci":
        _verify_package_metadata(
            artifact_dir,
            extension_root,
            package,
            budget_path,
        )

    return {
        "version": version,
        "package": package_name,
        "checksum": checksum_name,
        "package_sha256": package_digest,
        "checksum_sha256": _sha256(checksum),
        "metadata_mode": metadata_mode,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a ChemBlender release artifact.")
    parser.add_argument("--artifact-dir", required=True, type=Path)
    parser.add_argument("--extension-root", type=Path, default=Path(__file__).parents[1])
    parser.add_argument("--tag", required=True)
    parser.add_argument("--metadata-mode", required=True, choices=sorted(METADATA_MODES))
    parser.add_argument("--budget", type=Path)
    args = parser.parse_args()

    try:
        result = verify_artifact(
            args.artifact_dir,
            args.extension_root,
            args.tag,
            metadata_mode=args.metadata_mode,
            budget_path=args.budget,
        )
    except (OSError, ValueError, tomllib.TOMLDecodeError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
