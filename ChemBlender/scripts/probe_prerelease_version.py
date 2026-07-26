#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path


DEFAULT_PROBE_VERSION = "2.3.0-alpha.1"
_VERSION_ASSIGNMENT = re.compile(
    rb'(?m)^([ \t]*version[ \t]*=[ \t]*)"([^"\r\n]*)"([ \t]*(?:\r?\n|$))'
)
_VERSION_KEY = re.compile(rb"(?m)^[ \t]*version[ \t]*=")
_COPY_IGNORE = shutil.ignore_patterns(
    ".git",
    "__pycache__",
    "wheels",
    "*.zip",
    "*.sha256",
)
_FILE_ATTRIBUTE_REPARSE_POINT = getattr(
    stat,
    "FILE_ATTRIBUTE_REPARSE_POINT",
    0x400,
)


def _source_path_metadata(path: Path, source_root: Path):
    if path.is_symlink():
        relative = path.relative_to(source_root)
        raise ValueError(f"linked probe source path is not allowed: {relative}")
    metadata = path.lstat()
    attributes = getattr(metadata, "st_file_attributes", 0)
    if attributes & _FILE_ATTRIBUTE_REPARSE_POINT:
        relative = path.relative_to(source_root)
        raise ValueError(
            f"reparse-point probe source path is not allowed: {relative}"
        )
    return metadata


def _validate_source_tree(source_root: Path) -> None:
    root_metadata = _source_path_metadata(source_root, source_root)
    if not stat.S_ISDIR(root_metadata.st_mode):
        raise ValueError("extension root must be a directory")

    pending = [source_root]
    while pending:
        directory = pending.pop()
        for path in directory.iterdir():
            metadata = _source_path_metadata(path, source_root)
            if stat.S_ISDIR(metadata.st_mode):
                pending.append(path)


def _manifest_with_version(source: bytes, version: str) -> bytes:
    if type(version) is not str or not version:
        raise ValueError("probe version must be a non-empty string")
    if not version.isascii() or any(
        character in version for character in ('"', "\r", "\n", "\0")
    ):
        raise ValueError("probe version must be safe ASCII TOML text")

    matches = tuple(_VERSION_ASSIGNMENT.finditer(source))
    if len(_VERSION_KEY.findall(source)) != 1 or len(matches) != 1:
        raise ValueError(
            "manifest must contain exactly one quoted root version assignment"
        )
    document = tomllib.loads(source.decode("utf-8"))
    if type(document.get("version")) is not str:
        raise ValueError(
            "manifest must contain exactly one quoted root version assignment"
        )

    match = matches[0]
    replacement = (
        match.group(1)
        + b'"'
        + version.encode("ascii")
        + b'"'
        + match.group(3)
    )
    updated = source[: match.start()] + replacement + source[match.end() :]
    updated_document = tomllib.loads(updated.decode("utf-8"))
    if updated_document.get("version") != version:
        raise ValueError("temporary manifest version assignment was not exact")
    return updated


def probe_prerelease_version(
    extension_root: Path | str,
    blender: Path | str,
    version: str = DEFAULT_PROBE_VERSION,
) -> dict[str, object]:
    source_root = Path(extension_root).absolute()
    _validate_source_tree(source_root)
    manifest_path = source_root / "blender_manifest.toml"
    source_manifest = manifest_path.read_bytes()
    probe_manifest = _manifest_with_version(source_manifest, version)

    command: list[str]
    completed: subprocess.CompletedProcess[str]
    temporary_root_path: Path
    with tempfile.TemporaryDirectory(
        prefix="chemblender-prerelease-probe-"
    ) as temporary_root:
        temporary_root_path = Path(temporary_root)
        temporary_extension = temporary_root_path / source_root.name
        shutil.copytree(
            source_root,
            temporary_extension,
            ignore=_COPY_IGNORE,
        )
        (temporary_extension / "blender_manifest.toml").write_bytes(
            probe_manifest
        )
        command = [
            str(blender),
            "--command",
            "extension",
            "validate",
            str(temporary_extension),
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

    return {
        "command": command,
        "version": version,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "temporary_root": str(temporary_root_path),
        "temporary_root_cleaned": not temporary_root_path.exists(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Probe Blender prerelease extension-version support."
    )
    parser.add_argument("--extension-root", required=True, type=Path)
    parser.add_argument("--blender", required=True)
    parser.add_argument("--version", default=DEFAULT_PROBE_VERSION)
    args = parser.parse_args(argv)

    try:
        result = probe_prerelease_version(
            args.extension_root,
            args.blender,
            args.version,
        )
    except (OSError, UnicodeError, ValueError, tomllib.TOMLDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    payload = (
        json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    )
    sys.stdout.buffer.write(payload.encode("utf-8"))
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
