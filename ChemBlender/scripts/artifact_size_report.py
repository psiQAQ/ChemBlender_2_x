#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

if __package__:
    from .dependency_inventory import _safe_members
else:
    from dependency_inventory import _safe_members


SCHEMA_VERSION = "1"
SECTION_NAMES = ("code", "resources", "wheels", "other")
CODE_SUFFIXES = {".py", ".pyi", ".pyd", ".dll", ".so", ".dylib"}
RESOURCE_SUFFIXES = {".blend", ".png", ".jpg", ".jpeg", ".svg", ".json", ".toml"}
RESOURCE_NAMES = {"LICENSE", "COPYING", "NOTICE", "README.md", "blender_manifest.toml"}


def _sha256_bytes(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_archive_members(archive: zipfile.ZipFile):
    try:
        return _safe_members(archive)
    except ValueError as exc:
        raise ValueError(str(exc).replace("wheel", "archive")) from exc


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid {label}: {exc}") from exc
    if type(data) is not dict:
        raise ValueError(f"invalid {label}: root must be an object")
    return data


def _nonempty_text(value: Any, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"invalid {label}")
    return value


def _positive_int(value: Any, label: str, *, allow_zero: bool = False) -> int:
    if type(value) is not int or value < (0 if allow_zero else 1):
        raise ValueError(f"invalid {label}")
    return value


def _load_budget(path: Path) -> dict[str, Any]:
    budget = _read_json(path, "budget schema")
    if set(budget) != {
        "schema_version",
        "baseline_package_bytes",
        "allowed_unexplained_growth_bytes",
        "existing_wheel_distributions",
        "new_wheel_budget",
    }:
        raise ValueError("invalid budget schema: unexpected fields")
    if budget["schema_version"] != SCHEMA_VERSION:
        raise ValueError("invalid budget schema: schema_version")
    baseline = _positive_int(budget["baseline_package_bytes"], "budget schema baseline")
    allowed_growth = _positive_int(
        budget["allowed_unexplained_growth_bytes"],
        "budget schema allowed growth",
        allow_zero=True,
    )
    existing = budget["existing_wheel_distributions"]
    if type(existing) is not list or not existing:
        raise ValueError("invalid budget schema: existing wheels")
    existing_distributions = [_nonempty_text(value, "budget schema existing wheel") for value in existing]
    if existing_distributions != sorted(set(existing_distributions)):
        raise ValueError("invalid budget schema: existing wheels must be sorted and unique")
    new = budget["new_wheel_budget"]
    if type(new) is not dict or set(new) != {
        "max_compressed_bytes_per_wheel",
        "max_unpacked_bytes_per_wheel",
        "max_compressed_bytes_total",
        "approved_wheels",
    }:
        raise ValueError("invalid budget schema: new wheel budget")
    approved = new["approved_wheels"]
    if type(approved) is not list:
        raise ValueError("invalid budget schema: approved wheels")
    approved_distributions: list[str] = []
    for item in approved:
        if type(item) is not dict or set(item) != {"distribution", "rationale"}:
            raise ValueError("invalid budget schema: approved wheel")
        distribution = _nonempty_text(item["distribution"], "approved wheel distribution")
        _nonempty_text(item["rationale"], "approved wheel rationale")
        approved_distributions.append(distribution)
    if approved_distributions != sorted(set(approved_distributions)):
        raise ValueError("invalid budget schema: approved wheels must be sorted and unique")
    if set(existing_distributions) & set(approved_distributions):
        raise ValueError("invalid budget schema: existing and approved wheels overlap")
    return {
        "baseline_package_bytes": baseline,
        "allowed_unexplained_growth_bytes": allowed_growth,
        "existing_wheel_distributions": existing_distributions,
        "max_compressed_bytes_per_wheel": _positive_int(
            new["max_compressed_bytes_per_wheel"], "budget schema compressed wheel limit"
        ),
        "max_unpacked_bytes_per_wheel": _positive_int(
            new["max_unpacked_bytes_per_wheel"], "budget schema unpacked wheel limit"
        ),
        "max_compressed_bytes_total": _positive_int(
            new["max_compressed_bytes_total"], "budget schema total wheel limit"
        ),
        "approved_distributions": approved_distributions,
    }


def _load_inventory(inventory_path: Path, license_path: Path) -> list[dict[str, Any]]:
    inventory = _read_json(inventory_path, "wheel inventory")
    wheels = inventory.get("wheels")
    if type(wheels) is not list or not wheels:
        raise ValueError("invalid wheel inventory: wheels")
    required = {
        "distribution",
        "version",
        "filename",
        "sha256",
        "spdx_license",
        "license_source",
        "compressed_bytes",
        "unpacked_bytes",
    }
    parsed: list[dict[str, Any]] = []
    for wheel in wheels:
        if type(wheel) is not dict or not required.issubset(wheel):
            raise ValueError("invalid wheel inventory: wheel fields")
        value = {key: wheel[key] for key in required}
        for key in required - {"compressed_bytes", "unpacked_bytes"}:
            _nonempty_text(value[key], f"wheel inventory {key}")
        if (
            "/" in value["filename"]
            or "\\" in value["filename"]
            or not value["filename"].endswith(".whl")
        ):
            raise ValueError("invalid wheel inventory: filename")
        _positive_int(value["compressed_bytes"], "wheel inventory compressed bytes")
        _positive_int(value["unpacked_bytes"], "wheel inventory unpacked bytes")
        parsed.append(value)
    if [wheel["filename"] for wheel in parsed] != sorted(
        {wheel["filename"] for wheel in parsed}
    ):
        raise ValueError("invalid wheel inventory: filenames must be sorted and unique")
    if len({wheel["distribution"] for wheel in parsed}) != len(parsed):
        raise ValueError("invalid wheel inventory: duplicate distribution")

    licenses = _read_json(license_path, "license copy list").get("licenses")
    if type(licenses) is not list:
        raise ValueError("invalid license copy list: licenses")
    expected_licenses = [
        {
            "distribution": wheel["distribution"],
            "filename": wheel["filename"],
            "source": wheel["license_source"],
            "target": (
                f"licenses/{wheel['distribution']}-{wheel['version']}-"
                f"{PurePosixPath(wheel['license_source']).name}"
            ),
            "version": wheel["version"],
        }
        for wheel in parsed
    ]
    if licenses != expected_licenses:
        raise ValueError("license copy list does not match wheel inventory")
    return parsed


def _section(name: str) -> str:
    path = PurePosixPath(name)
    if path.suffix.lower() == ".whl":
        return "wheels"
    if path.suffix.lower() in CODE_SUFFIXES:
        return "code"
    if path.name in RESOURCE_NAMES or path.suffix.lower() in RESOURCE_SUFFIXES:
        return "resources"
    return "other"


def _member_document(name: str, info: zipfile.ZipInfo) -> dict[str, int | str]:
    return {
        "compressed_bytes": info.compress_size,
        "path": name,
        "unpacked_bytes": info.file_size,
    }


def _wheel_report(
    archive: zipfile.ZipFile, member: tuple[zipfile.ZipInfo, bool, int], wheel: dict[str, Any]
) -> dict[str, Any]:
    info, is_directory, _ = member
    if is_directory:
        raise ValueError(f"wheel package member is a directory: {wheel['filename']}")
    contents = archive.read(info)
    if len(contents) != wheel["compressed_bytes"]:
        raise ValueError(f"wheel size mismatch: {wheel['filename']}")
    if _sha256_bytes(contents) != wheel["sha256"]:
        raise ValueError(f"wheel hash mismatch: {wheel['filename']}")
    try:
        with zipfile.ZipFile(io.BytesIO(contents)) as nested:
            members = _safe_archive_members(nested)
            if nested.testzip() is not None:
                raise ValueError(f"nested wheel CRC validation failed: {wheel['filename']}")
    except zipfile.BadZipFile as exc:
        raise ValueError(f"invalid wheel archive: {wheel['filename']}") from exc
    license_member = members.get(wheel["license_source"])
    if license_member is None or license_member[1]:
        raise ValueError(f"wheel license source missing: {wheel['filename']}")
    nested_compressed = sum(member_info.compress_size for member_info, _, _ in members.values())
    nested_unpacked = sum(member_info.file_size for member_info, _, _ in members.values())
    if nested_unpacked != wheel["unpacked_bytes"]:
        raise ValueError(f"wheel unpacked size mismatch: {wheel['filename']}")
    return {
        "distribution": wheel["distribution"],
        "filename": wheel["filename"],
        "license": {
            "source": wheel["license_source"],
            "spdx_license": wheel["spdx_license"],
            "target": (
                f"licenses/{wheel['distribution']}-{wheel['version']}-"
                f"{PurePosixPath(wheel['license_source']).name}"
            ),
        },
        "nested_compressed_bytes": nested_compressed,
        "nested_unpacked_bytes": nested_unpacked,
        "outer_compressed_bytes": info.compress_size,
        "package_member": f"wheels/{wheel['filename']}",
        "sha256": wheel["sha256"],
        "wheel_bytes": len(contents),
    }


def build_report(
    package: Path, inventory_path: Path, license_path: Path, budget_path: Path
) -> dict[str, Any]:
    package = package.resolve()
    budget = _load_budget(budget_path)
    wheels = _load_inventory(inventory_path, license_path)
    distributions = {wheel["distribution"] for wheel in wheels}
    if not set(budget["existing_wheel_distributions"]).issubset(distributions):
        raise ValueError("budget existing wheel is absent from inventory")
    new_distributions = sorted(distributions - set(budget["existing_wheel_distributions"]))
    if new_distributions != budget["approved_distributions"]:
        raise ValueError("new wheel is not approved by the budget")

    sections: dict[str, dict[str, Any]] = {
        name: {"compressed_bytes": 0, "members": [], "unpacked_bytes": 0}
        for name in SECTION_NAMES
    }
    expected_members = {f"wheels/{wheel['filename']}": wheel for wheel in wheels}
    try:
        with zipfile.ZipFile(package) as archive:
            members = _safe_archive_members(archive)
            if archive.testzip() is not None:
                raise ValueError("package ZIP CRC validation failed")
            files = {
                name: member
                for name, member in members.items()
                if not member[1]
            }
            actual_wheels = {name for name in files if name.lower().endswith(".whl")}
            if actual_wheels != set(expected_members):
                raise ValueError("package wheel members do not match inventory")
            for name, member in sorted(files.items()):
                info, _, _ = member
                section = sections[_section(name)]
                document = _member_document(name, info)
                section["members"].append(document)
                section["compressed_bytes"] += info.compress_size
                section["unpacked_bytes"] += info.file_size
            wheel_documents = [
                _wheel_report(archive, files[f"wheels/{wheel['filename']}"], wheel)
                for wheel in wheels
            ]
    except zipfile.BadZipFile as exc:
        raise ValueError(f"invalid package ZIP: {package}") from exc

    new_wheels = [
        wheel
        for wheel in wheel_documents
        if wheel["distribution"] not in budget["existing_wheel_distributions"]
    ]
    new_compressed = sum(wheel["wheel_bytes"] for wheel in new_wheels)
    new_unpacked = sum(wheel["nested_unpacked_bytes"] for wheel in new_wheels)
    for wheel in new_wheels:
        if wheel["wheel_bytes"] > budget["max_compressed_bytes_per_wheel"]:
            raise ValueError(f"new wheel compressed size exceeds budget: {wheel['filename']}")
        if wheel["nested_unpacked_bytes"] > budget["max_unpacked_bytes_per_wheel"]:
            raise ValueError(f"new wheel unpacked size exceeds budget: {wheel['filename']}")
    if new_compressed > budget["max_compressed_bytes_total"]:
        raise ValueError("new wheel compressed total exceeds budget")

    package_bytes = package.stat().st_size
    actual_growth = package_bytes - budget["baseline_package_bytes"]
    if actual_growth > budget["allowed_unexplained_growth_bytes"]:
        raise ValueError("package growth exceeds budget")
    member_compressed = sum(section["compressed_bytes"] for section in sections.values())
    member_unpacked = sum(section["unpacked_bytes"] for section in sections.values())
    return {
        "baseline": {
            "actual_growth_bytes": actual_growth,
            "allowed_unexplained_growth_bytes": budget["allowed_unexplained_growth_bytes"],
            "baseline_package_bytes": budget["baseline_package_bytes"],
        },
        "new_wheel_allowance": {
            "approved_distributions": budget["approved_distributions"],
            "compressed_bytes": new_compressed,
            "max_compressed_bytes": budget["max_compressed_bytes_total"],
            "unpacked_bytes": new_unpacked,
        },
        "package": {
            "bytes": package_bytes,
            "member_compressed_bytes": member_compressed,
            "member_unpacked_bytes": member_unpacked,
            "sha256": _sha256(package),
        },
        "schema_version": SCHEMA_VERSION,
        "sections": sections,
        "wheels": wheel_documents,
    }


def canonical_json(report: dict[str, Any]) -> bytes:
    return json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


def _write_atomic(path: Path, contents: bytes) -> None:
    if not path.parent.is_dir():
        raise ValueError(f"output parent does not exist: {path.parent}")
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=".cbi-", suffix=".tmp")
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise ValueError(f"output write failed: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report ChemBlender extension artifact sizes.")
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--wheel-inventory", required=True, type=Path)
    parser.add_argument("--license-copy-list", required=True, type=Path)
    parser.add_argument("--budget", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifact-size.json"))
    args = parser.parse_args(argv)
    try:
        report = build_report(
            args.package, args.wheel_inventory, args.license_copy_list, args.budget
        )
        contents = canonical_json(report)
        _write_atomic(args.output, contents)
    except (OSError, TypeError, ValueError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(contents.decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
