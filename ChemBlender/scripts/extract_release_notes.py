#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Sequence


VERSION_PATTERN = re.compile(r"\d+\.\d+\.\d+")
SECTION_PATTERN = re.compile(r"^## \[[^\]]+\](?: - \d{4}-\d{2}-\d{2})?\s*$", re.MULTILINE)
REFERENCE_PATTERN = re.compile(r"^\[[^\]]+\]:\s+\S+.*$", re.MULTILINE)


def extract_release_notes(changelog: str, version: str) -> str:
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError(f"invalid release version: {version}")

    entry_pattern = re.compile(
        rf"^## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}\s*$",
        re.MULTILINE,
    )
    entries = list(entry_pattern.finditer(changelog))
    if len(entries) != 1:
        raise ValueError(
            f"expected exactly one dated entry for version {version}, found {len(entries)}"
        )

    entry = entries[0]
    next_section = SECTION_PATTERN.search(changelog, entry.end())
    next_reference = REFERENCE_PATTERN.search(changelog, entry.end())
    boundaries = [
        match.start() for match in (next_section, next_reference) if match is not None
    ]
    end = min(boundaries, default=len(changelog))
    notes = changelog[entry.end() : end].strip()
    if not notes:
        raise ValueError(f"release notes are empty for version {version}")
    return notes + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract one version from CHANGELOG.md.")
    parser.add_argument("--changelog", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    try:
        notes = extract_release_notes(
            args.changelog.read_text(encoding="utf-8"), args.version
        )
        if args.output:
            args.output.write_text(notes, encoding="utf-8", newline="\n")
        else:
            print(notes, end="")
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
