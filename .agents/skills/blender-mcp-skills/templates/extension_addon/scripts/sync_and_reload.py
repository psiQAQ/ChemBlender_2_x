#!/usr/bin/env python3
"""Incrementally sync extension files and print Blender reload commands."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_EXTENSIONS = {".py", ".toml", ".json"}


@dataclass
class SyncResult:
    copied: int = 0
    skipped: int = 0


@dataclass
class CopyDecision:
    should_copy: bool
    reason: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Incrementally sync changed/new extension files from source to target "
            "and print Blender reload commands."
        )
    )
    parser.add_argument("--source", required=True, help="Source directory (extension workspace)")
    parser.add_argument("--target", required=True, help="Target directory (installed extension repo path)")
    parser.add_argument("--module", required=True, help="Blender add-on module name, for example: my_addon")
    parser.add_argument("--dry-run", action="store_true", help="Preview copy operations without writing files")
    parser.add_argument(
        "--allow-legacy-target",
        action="store_true",
        help="Allow syncing to legacy scripts/addons paths. Disabled by default for extension-only workflow.",
    )
    parser.add_argument(
        "--delete-stale",
        action="store_true",
        help="Delete supported files from target when they no longer exist in source.",
    )
    return parser.parse_args()


def validate_module(module: str) -> None:
    pattern = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
    if not pattern.fullmatch(module):
        raise ValueError(
            "Invalid --module format. Use Blender module names like: my_addon or package.submodule"
        )


def _is_path_writable(path: Path) -> bool:
    return os.access(path, os.W_OK)


def _looks_like_legacy_addons_path(path: Path) -> bool:
    parts = [p.lower() for p in path.parts]
    for i in range(len(parts) - 1):
        if parts[i] == "scripts" and parts[i + 1] in {"addons", "addons_core"}:
            return True
    return False


def _compute_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def validate_paths(source: Path, target: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(f"source does not exist: {source}")
    if not source.is_dir():
        raise NotADirectoryError(f"source is not a directory: {source}")

    if not target.exists():
        raise FileNotFoundError(
            f"target does not exist: {target}. Confirm the Blender extension directory is created first."
        )
    if not target.is_dir():
        raise NotADirectoryError(f"target is not a directory: {target}")
    if not _is_path_writable(target):
        raise PermissionError(
            f"target is not writable: {target}. Check permissions or cross-system path mapping (for example WSL /mnt/c/...)."
        )


def decide_copy(src: Path, dst: Path) -> CopyDecision:
    if not dst.exists():
        return CopyDecision(True, "destination file missing")

    src_stat = src.stat()
    dst_stat = dst.stat()

    if src_stat.st_size != dst_stat.st_size:
        return CopyDecision(True, "different file size")

    if src_stat.st_mtime > dst_stat.st_mtime:
        return CopyDecision(True, "source is newer (mtime)")

    if src_stat.st_mtime == dst_stat.st_mtime:
        src_hash = _compute_sha256(src)
        dst_hash = _compute_sha256(dst)
        if src_hash != dst_hash:
            return CopyDecision(True, "same mtime but different content (hash mismatch)")
        return CopyDecision(False, "same mtime and same content")

    return CopyDecision(False, "destination is newer (mtime)")


def sync_incremental(source: Path, target: Path, dry_run: bool) -> SyncResult:
    result = SyncResult()

    for src_file in source.rglob("*"):
        if not src_file.is_file():
            continue
        if src_file.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        rel_path = src_file.relative_to(source)
        dst_file = target / rel_path

        decision = decide_copy(src_file, dst_file)

        if decision.should_copy:
            action = "[DRY-RUN] COPY" if dry_run else "COPY"
            print(f"{action} {src_file} -> {dst_file} ({decision.reason})")
            if not dry_run:
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
            result.copied += 1
        else:
            print(f"SKIP {src_file} ({decision.reason})")
            result.skipped += 1

    return result


def delete_stale_files(source: Path, target: Path, dry_run: bool) -> int:
    deleted = 0

    for dst_file in target.rglob("*"):
        if not dst_file.is_file():
            continue
        if dst_file.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        rel_path = dst_file.relative_to(target)
        src_file = source / rel_path

        if src_file.exists():
            continue

        action = "[DRY-RUN] DELETE" if dry_run else "DELETE"
        print(f"{action} {dst_file} (missing from source)")

        if not dry_run:
            dst_file.unlink()

        deleted += 1

    return deleted


def print_reload_hint(module: str) -> None:
    print("\nRun the following in Blender Python Console:")
    print(f'bpy.ops.preferences.addon_disable(module="{module}")')
    print(f'bpy.ops.preferences.addon_enable(module="{module}")')


def main() -> int:
    args = parse_args()

    source = Path(args.source).expanduser().resolve()
    target = Path(args.target).expanduser().resolve()

    try:
        validate_module(args.module)
        validate_paths(source, target)
        if _looks_like_legacy_addons_path(target) and not args.allow_legacy_target:
            print(
                "Error: target looks like a legacy scripts/addons path. "
                "For extension-only workflow, target an installed extension repo path instead. "
                "Use --allow-legacy-target only when intentionally developing a legacy add-on.",
                file=sys.stderr,
            )
            return 1
        result = sync_incremental(source, target, args.dry_run)
        deleted = delete_stale_files(source, target, args.dry_run) if args.delete_stale else 0
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    mode = "DRY-RUN" if args.dry_run else "APPLY"
    print(f"\nSync complete [{mode}]: copied {result.copied}, skipped {result.skipped}, deleted {deleted}")
    print_reload_hint(args.module)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
