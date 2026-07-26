#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path


EXPECTED_EXTENSION_ID = "chemblender"
EXPECTED_PLATFORM = "windows-x64"
UNSAFE_VERSION_CHARACTERS = frozenset('<>:"/\\|?*')
_RELEASE_VERSION_PATTERN = re.compile(
    r"(?P<major>0|[1-9]\d*)"
    r"\.(?P<minor>0|[1-9]\d*)"
    r"\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<channel>alpha|beta|rc)\.(?P<channel_number>[1-9]\d*))?"
)


@dataclass(frozen=True, slots=True)
class ParsedReleaseVersion:
    value: str
    major: int
    minor: int
    patch: int
    channel: str | None
    channel_number: int | None
    is_prerelease: bool


@dataclass(frozen=True, slots=True)
class ReleaseMetadata:
    extension_id: str
    version: str
    platform: str
    package_name: str
    checksum_name: str
    artifact_name: str


def parse_release_version(value: str) -> ParsedReleaseVersion:
    if type(value) is not str:
        raise ValueError("release version must be a string")
    match = _RELEASE_VERSION_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError(f"invalid release version: {value!r}")
    channel = match.group("channel")
    channel_number = match.group("channel_number")
    return ParsedReleaseVersion(
        value=value,
        major=int(match.group("major")),
        minor=int(match.group("minor")),
        patch=int(match.group("patch")),
        channel=channel,
        channel_number=int(channel_number) if channel_number is not None else None,
        is_prerelease=channel is not None,
    )


def _required_exact_string(document: dict[str, object], key: str) -> str:
    value = document.get(key)
    if type(value) is not str:
        raise ValueError(f"manifest {key} must be a string")
    return value


def _validate_version(version: str) -> None:
    if not version:
        raise ValueError("manifest version must not be empty")
    if version != version.strip():
        raise ValueError("manifest version must not have surrounding whitespace")
    if not version.isascii():
        raise ValueError("manifest version must be ASCII")
    if any(ord(character) < 32 or ord(character) == 127 for character in version):
        raise ValueError("manifest version must not contain control characters")
    if any(character in UNSAFE_VERSION_CHARACTERS for character in version):
        raise ValueError("manifest version contains a path-unsafe character")
    if version.endswith((".", " ")):
        raise ValueError("manifest version must not end with a dot or space")


def read_release_metadata(extension_root: Path | str) -> ReleaseMetadata:
    root = Path(extension_root)
    manifest_path = root / "blender_manifest.toml"
    document = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    if type(document) is not dict:
        raise ValueError("manifest root must be a table")

    extension_id = _required_exact_string(document, "id")
    version = _required_exact_string(document, "version")
    platforms = document.get("platforms")
    if type(platforms) is not list or any(type(item) is not str for item in platforms):
        raise ValueError("manifest platforms must be an array of strings")
    if extension_id != EXPECTED_EXTENSION_ID:
        raise ValueError(
            f"manifest id must be {EXPECTED_EXTENSION_ID!r}, got {extension_id!r}"
        )
    if platforms != [EXPECTED_PLATFORM]:
        raise ValueError(
            f"manifest platforms must be [{EXPECTED_PLATFORM!r}], got {platforms!r}"
        )
    _validate_version(version)
    parse_release_version(version)

    return ReleaseMetadata(
        extension_id=extension_id,
        version=version,
        platform=platforms[0],
        package_name=f"{extension_id}-{version}.zip",
        checksum_name=f"{extension_id}-{version}.sha256",
        artifact_name=f"{extension_id}-{version}-{platforms[0]}",
    )


def release_metadata_document(metadata: ReleaseMetadata) -> dict[str, str]:
    return {
        "extension_id": metadata.extension_id,
        "version": metadata.version,
        "platform": metadata.platform,
        "package_name": metadata.package_name,
        "checksum_name": metadata.checksum_name,
        "artifact_name": metadata.artifact_name,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read deterministic ChemBlender release metadata."
    )
    parser.add_argument("--extension-root", required=True, type=Path)
    parser.add_argument("--format", choices=("json",), required=True)
    args = parser.parse_args(argv)

    try:
        metadata = read_release_metadata(args.extension_root)
    except (OSError, UnicodeError, ValueError, tomllib.TOMLDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    payload = (
        json.dumps(
            release_metadata_document(metadata),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    )
    sys.stdout.buffer.write(payload.encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
