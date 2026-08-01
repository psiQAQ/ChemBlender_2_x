#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import tempfile
import tomllib
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


SCHEMA_VERSION = "1"
TEXT_FIELDS = (
    "distribution",
    "version",
    "filename",
    "platform",
    "python_abi",
    "url",
    "sha256",
    "spdx_license",
    "license_source",
)
DEPENDENCY_FIELDS = frozenset(
    (*TEXT_FIELDS, "required", "max_compressed_bytes", "max_unpacked_bytes")
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _schema_error(reason: str) -> ValueError:
    return ValueError(f"invalid dependency inventory schema: {reason}")


def _safe_text(value: Any) -> bool:
    return (
        type(value) is str
        and bool(value)
        and value == value.strip()
        and value.isascii()
        and all(" " <= char <= "~" for char in value)
    )


def _member_path(name: str, *, is_directory: bool) -> str:
    if "\0" in name:
        raise ValueError(f"unsafe wheel member path: {name!r}")
    normalized = name.replace("\\", "/")
    if is_directory:
        normalized = normalized.removesuffix("/")
    parts = normalized.split("/")
    if (
        not normalized
        or normalized.startswith("/")
        or (len(normalized) >= 2 and normalized[0].isalpha() and normalized[1] == ":")
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise ValueError(f"unsafe wheel member path: {name!r}")
    return "/".join(parts)


def _wheel_filename(value: str) -> bool:
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    return (
        value.endswith(".whl")
        and value not in {".", ".."}
        and "/" not in value
        and "\\" not in value
        and not posix.is_absolute()
        and not windows.is_absolute()
        and not windows.drive
    )


def _license_target(dependency: dict[str, Any]) -> str:
    return (
        f"licenses/{dependency['distribution']}-{dependency['version']}-"
        f"{PurePosixPath(dependency['license_source']).name}"
    )


def _validate_schema(config: Any) -> list[dict[str, Any]]:
    if type(config) is not dict or set(config) != {"schema_version", "dependency"}:
        raise _schema_error("root keys must be schema_version and dependency")
    if type(config["schema_version"]) is not str or config["schema_version"] != SCHEMA_VERSION:
        raise _schema_error(f"schema_version must be {SCHEMA_VERSION!r}")
    dependencies = config["dependency"]
    if type(dependencies) is not list or not dependencies:
        raise _schema_error("dependency must be a non-empty array of tables")

    distributions: set[str] = set()
    filenames: set[str] = set()
    targets: set[str] = set()
    for index, dependency in enumerate(dependencies):
        if type(dependency) is not dict or set(dependency) != DEPENDENCY_FIELDS:
            raise _schema_error(f"dependency[{index}] has unexpected fields")
        for field in TEXT_FIELDS:
            if not _safe_text(dependency[field]):
                raise _schema_error(f"dependency[{index}].{field} must be non-empty ASCII text")
        if type(dependency["required"]) is not bool:
            raise _schema_error(f"dependency[{index}].required must be bool")
        for field in ("max_compressed_bytes", "max_unpacked_bytes"):
            if type(dependency[field]) is not int or dependency[field] <= 0:
                raise _schema_error(f"dependency[{index}].{field} must be a positive int")
        if not _wheel_filename(dependency["filename"]):
            raise _schema_error(f"dependency[{index}].filename must be a .whl basename")
        try:
            _member_path(dependency["license_source"], is_directory=False)
        except ValueError as exc:
            raise _schema_error(f"dependency[{index}].license_source is unsafe") from exc
        if "/" in dependency["distribution"] or "\\" in dependency["distribution"]:
            raise _schema_error(f"dependency[{index}].distribution is unsafe")
        if "/" in dependency["version"] or "\\" in dependency["version"]:
            raise _schema_error(f"dependency[{index}].version is unsafe")
        target = _license_target(dependency)
        if dependency["distribution"] in distributions:
            raise _schema_error(f"duplicate distribution: {dependency['distribution']}")
        if dependency["filename"] in filenames:
            raise _schema_error(f"duplicate filename: {dependency['filename']}")
        if target in targets:
            raise _schema_error(f"duplicate license target: {target}")
        distributions.add(dependency["distribution"])
        filenames.add(dependency["filename"])
        targets.add(target)
    return dependencies


def _wheel_path(wheel_dir: Path, filename: str) -> Path:
    try:
        root = wheel_dir.resolve()
        candidate = wheel_dir / filename
        resolved = candidate.resolve()
        resolved.relative_to(root)
        if candidate.is_symlink() or not stat.S_ISREG(resolved.stat().st_mode):
            raise ValueError
    except (OSError, ValueError) as exc:
        raise ValueError("wheel path must be an ordinary file within wheel directory") from exc
    return resolved


def _safe_members(archive: zipfile.ZipFile) -> dict[str, tuple[zipfile.ZipInfo, bool, int]]:
    members: dict[str, tuple[zipfile.ZipInfo, bool, int]] = {}
    for member in archive.infolist():
        original = member.orig_filename
        named_directory = original.endswith("/")
        name = _member_path(original, is_directory=named_directory)
        mode = (member.external_attr >> 16) & 0xFFFF
        file_type = stat.S_IFMT(mode)
        if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
            raise ValueError(f"unsafe wheel member type: {original!r}")
        if named_directory and file_type == stat.S_IFREG:
            raise ValueError(f"unsafe wheel member type: {original!r}")
        is_directory = named_directory or file_type == stat.S_IFDIR
        if name in members:
            raise ValueError(f"duplicate wheel member path: {original!r}")
        members[name] = (member, is_directory, file_type)
    return members


def inventory(
    inventory_path: Path, wheel_dir: Path, manifest_path: Path | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    with inventory_path.open("rb") as handle:
        dependencies = _validate_schema(tomllib.load(handle))
    if manifest_path is not None:
        with manifest_path.open("rb") as handle:
            manifest = tomllib.load(handle)
        expected_wheels = [
            f"./wheels/{dependency['filename']}"
            for dependency in dependencies
            if dependency["required"] is True
        ]
        if manifest.get("wheels") != expected_wheels:
            raise ValueError("manifest wheel paths must equal required inventory")

    wheels: list[dict[str, Any]] = []
    licenses: list[dict[str, str]] = []
    for dependency in dependencies:
        if dependency["required"] is not True:
            continue
        wheel = _wheel_path(wheel_dir, dependency["filename"])
        actual_sha256 = _sha256(wheel)
        if actual_sha256 != dependency["sha256"]:
            raise ValueError(f"wheel hash mismatch: {wheel.name}")
        with zipfile.ZipFile(wheel) as archive:
            members = _safe_members(archive)
            source = _member_path(dependency["license_source"], is_directory=False)
            license_member = members.get(source)
            if license_member is None:
                raise ValueError(f"license source missing: {dependency['license_source']}")
            _, is_directory, file_type = license_member
            if is_directory or file_type not in {0, stat.S_IFREG}:
                raise ValueError("license source must be a regular wheel member")
            unpacked_bytes = sum(member.file_size for member, _, _ in members.values())
        compressed_bytes = wheel.stat().st_size
        if compressed_bytes > dependency["max_compressed_bytes"]:
            raise ValueError(f"compressed size exceeds budget: {wheel.name}")
        if unpacked_bytes > dependency["max_unpacked_bytes"]:
            raise ValueError(f"unpacked size exceeds budget: {wheel.name}")
        item = dict(dependency)
        item["compressed_bytes"] = compressed_bytes
        item["unpacked_bytes"] = unpacked_bytes
        wheels.append(item)
        licenses.append(
            {
                "distribution": dependency["distribution"],
                "filename": dependency["filename"],
                "source": dependency["license_source"],
                "target": _license_target(dependency),
                "version": dependency["version"],
            }
        )
    wheels.sort(key=lambda item: item["filename"])
    licenses.sort(key=lambda item: item["filename"])
    return {"wheels": wheels}, {"licenses": licenses}


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _write_bytes(path: Path, contents: bytes) -> None:
    with path.open("wb") as handle:
        handle.write(contents)
        handle.flush()
        os.fsync(handle.fileno())


def _transaction_file(parent: Path, suffix: str) -> Path:
    descriptor, filename = tempfile.mkstemp(dir=parent, prefix=".cbi-", suffix=suffix)
    path = Path(filename)
    try:
        os.close(descriptor)
    except OSError:
        _cleanup([path])
        raise
    return path


def _write_transaction_file(parent: Path, suffix: str, contents: bytes) -> Path:
    path = _transaction_file(parent, suffix)
    try:
        _write_bytes(path, contents)
    except OSError:
        _cleanup([path])
        raise
    return path


def _cleanup(paths: list[Path | None]) -> None:
    for path in paths:
        if path is not None:
            try:
                mode = stat.S_IMODE(path.stat().st_mode)
                if not mode & stat.S_IWUSR:
                    path.chmod(mode | stat.S_IWUSR)
                path.unlink()
            except OSError:
                pass


def _preflight_output_paths(output: Path, license_copy_list: Path) -> None:
    if output.resolve() == license_copy_list.resolve():
        raise ValueError("output paths must be distinct")
    if output.exists() and license_copy_list.exists():
        try:
            same_file = os.path.samefile(output, license_copy_list)
        except OSError as exc:
            raise ValueError(f"could not compare output paths: {exc}") from exc
        if same_file:
            raise ValueError("output paths must be distinct")
    for path in (output, license_copy_list):
        if not path.parent.is_dir():
            raise ValueError(f"output parent does not exist: {path.parent}")


def _backup_output(path: Path) -> Path | None:
    if not path.exists():
        return None
    backup = _transaction_file(path.parent, ".bak")
    try:
        shutil.copy2(path, backup)
        mode = stat.S_IMODE(backup.stat().st_mode)
        if not mode & stat.S_IWUSR:
            backup.chmod(mode | stat.S_IWUSR)
        try:
            with backup.open("r+b") as handle:
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            if not mode & stat.S_IWUSR:
                backup.chmod(mode)
    except OSError:
        _cleanup([backup])
        raise
    return backup


def _restore_outputs(
    paths: tuple[Path, Path], backups: list[Path | None], replaced: list[bool]
) -> list[tuple[int, OSError]]:
    errors: list[tuple[int, OSError]] = []
    for index in reversed(range(len(paths))):
        if not replaced[index]:
            continue
        path = paths[index]
        backup = backups[index]
        try:
            if backup is None:
                path.unlink()
            else:
                os.replace(backup, path)
                backups[index] = None
        except OSError as exc:
            errors.append((index, exc))
    return errors


def _write_outputs(
    output: Path, license_copy_list: Path, wheel_inventory: dict[str, Any], licenses: dict[str, Any]
) -> str:
    _preflight_output_paths(output, license_copy_list)
    output_text = _json_text(wheel_inventory)
    license_text = _json_text(licenses)
    paths = (output, license_copy_list)
    temporary: list[Path | None] = []
    try:
        for path, text in zip(paths, (output_text, license_text), strict=True):
            temporary.append(
                _write_transaction_file(path.parent, ".tmp", text.encode("utf-8") + b"\n")
            )
    except OSError as exc:
        _cleanup(temporary)
        raise ValueError(f"output write failed: {exc}") from exc
    backups: list[Path | None] = []
    try:
        for path in paths:
            backups.append(_backup_output(path))
    except OSError as exc:
        _cleanup(backups)
        _cleanup(temporary)
        raise ValueError(f"output backup failed: {exc}") from exc
    replaced = [False, False]
    try:
        for index, path in enumerate(paths):
            os.replace(temporary[index], path)
            temporary[index] = None
            replaced[index] = True
    except OSError as exc:
        recovery_errors = _restore_outputs(paths, backups, replaced)
        failed_indices = {index for index, _ in recovery_errors}
        _cleanup(
            [backup for index, backup in enumerate(backups) if index not in failed_indices]
        )
        if recovery_errors:
            retained_backups = [
                str(backups[index].absolute())
                for index, _ in recovery_errors
                if backups[index] is not None
            ]
            backup_detail = ", ".join(retained_backups) or "none"
            recovery_detail = "; ".join(
                f"{paths[index]}: {recovery_error}"
                for index, recovery_error in recovery_errors
            )
            raise ValueError(
                f"output replace failed: {exc}; recovery failed: {recovery_detail}; "
                f"recoverable backups: {backup_detail}"
            ) from exc
        raise ValueError(f"output replace failed: {exc}") from exc
    finally:
        _cleanup(temporary)
    _cleanup(backups)
    return output_text


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
        output = _write_outputs(
            args.output, args.license_copy_list, wheel_inventory, license_copy_list
        )
    except (OSError, TypeError, ValueError, zipfile.BadZipFile, tomllib.TOMLDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
