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
    r"(?P<major>0|[1-9][0-9]*)"
    r"\.(?P<minor>0|[1-9][0-9]*)"
    r"\.(?P<patch>0|[1-9][0-9]*)"
    r"(?:-(?P<channel>alpha|beta|rc)\.(?P<channel_number>[1-9][0-9]*))?"
)
_GIT_COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}")


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


def release_channel_document(version: str) -> dict[str, str | bool]:
    parsed = parse_release_version(version)
    return {
        "channel": parsed.channel or "final",
        "is_prerelease": parsed.is_prerelease,
    }


def _required_positive_int(document: dict[str, object], key: str) -> int:
    value = document.get(key)
    if type(value) is not int or value <= 0:
        raise ValueError(f"{key} must be a positive integer")
    return value


def _required_string(document: dict[str, object], key: str) -> str:
    value = document.get(key)
    if type(value) is not str:
        raise ValueError(f"{key} must be a string")
    return value


def select_exact_package_run(
    records: object,
    *,
    tag: str,
    tag_commit: str,
) -> int:
    """Return the sole successful package run for one exact tag commit."""
    if type(records) is not list:
        raise ValueError("run records must be a list")
    if type(tag) is not str or not tag:
        raise ValueError("tag must be a non-empty string")
    if type(tag_commit) is not str or _GIT_COMMIT_PATTERN.fullmatch(tag_commit) is None:
        raise ValueError("tag commit must be a 40-character lowercase SHA-1")

    matching_ids: list[int] = []
    for record in records:
        if type(record) is not dict:
            raise ValueError("run record must be an object")
        run_id = _required_positive_int(record, "id")
        head_sha = _required_string(record, "head_sha")
        head_branch = _required_string(record, "head_branch")
        event = _required_string(record, "event")
        conclusion = _required_string(record, "conclusion")
        if (
            head_sha == tag_commit
            and head_branch == tag
            and event == "push"
            and conclusion == "success"
        ):
            matching_ids.append(run_id)

    if len(matching_ids) != 1:
        raise ValueError(
            "expected exactly one successful exact package run, "
            f"found {len(matching_ids)}"
        )
    return matching_ids[0]


def workflow_run_records_from_pages(pages: object) -> list[dict[str, object]]:
    """Flatten every paginated workflow-runs response without truncating it."""
    if type(pages) is not list:
        raise ValueError("workflow run pages must be a list")
    records: list[dict[str, object]] = []
    for page in pages:
        if type(page) is not dict:
            raise ValueError("workflow run page must be an object")
        workflow_runs = page.get("workflow_runs")
        if type(workflow_runs) is not list:
            raise ValueError("workflow_runs must be a list")
        records.extend(workflow_runs)
    return records


def select_exact_package_artifact(document: object, *, artifact_name: str) -> int:
    """Return the sole unexpired artifact with the metadata-derived name."""
    if type(document) is not dict:
        raise ValueError("artifact document must be an object")
    if type(artifact_name) is not str or not artifact_name:
        raise ValueError("artifact name must be a non-empty string")
    artifacts = document.get("artifacts")
    if type(artifacts) is not list:
        raise ValueError("artifacts must be a list")

    matching_ids: list[int] = []
    for artifact in artifacts:
        if type(artifact) is not dict:
            raise ValueError("artifact must be an object")
        artifact_id = _required_positive_int(artifact, "id")
        name = _required_string(artifact, "name")
        expired = artifact.get("expired")
        if type(expired) is not bool:
            raise ValueError("expired must be a boolean")
        if name == artifact_name and not expired:
            matching_ids.append(artifact_id)

    if len(matching_ids) != 1:
        raise ValueError(
            "expected exactly one unexpired exact artifact, "
            f"found {len(matching_ids)}"
        )
    return matching_ids[0]


def _selection_payload(key: str, value: int) -> bytes:
    return (json.dumps({key: value}, separators=(",", ":")) + "\n").encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read deterministic ChemBlender release metadata."
    )
    parser.add_argument("--extension-root", type=Path)
    parser.add_argument("--format", choices=("json",))
    parser.add_argument("--include-channel", action="store_true")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--select-package-run", action="store_true")
    selection.add_argument("--select-package-artifact", action="store_true")
    parser.add_argument("--tag")
    parser.add_argument("--tag-commit")
    parser.add_argument("--artifact-name")
    args = parser.parse_args(argv)

    try:
        if args.select_package_run:
            if args.tag is None or args.tag_commit is None:
                parser.error("--select-package-run requires --tag and --tag-commit")
            selected = select_exact_package_run(
                workflow_run_records_from_pages(json.load(sys.stdin)),
                tag=args.tag,
                tag_commit=args.tag_commit,
            )
            sys.stdout.buffer.write(_selection_payload("run_id", selected))
            return 0
        if args.select_package_artifact:
            if args.artifact_name is None:
                parser.error("--select-package-artifact requires --artifact-name")
            selected = select_exact_package_artifact(
                json.load(sys.stdin),
                artifact_name=args.artifact_name,
            )
            sys.stdout.buffer.write(_selection_payload("artifact_id", selected))
            return 0
        if args.extension_root is None or args.format is None:
            parser.error("--extension-root and --format are required for metadata")
        metadata = read_release_metadata(args.extension_root)
    except (
        OSError,
        UnicodeError,
        ValueError,
        json.JSONDecodeError,
        tomllib.TOMLDecodeError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    document: dict[str, str | bool] = release_metadata_document(metadata)
    if args.include_channel:
        document.update(release_channel_document(metadata.version))
    payload = (
        json.dumps(
            document,
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
