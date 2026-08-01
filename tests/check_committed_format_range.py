from __future__ import annotations

import argparse
import re
import subprocess
import sys


EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
SHA256 = re.compile(r"^[0-9a-fA-F]{40}$")


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", *args),
        check=False,
        capture_output=True,
        encoding="utf-8",
    )


def _write_result(result: subprocess.CompletedProcess[str]) -> None:
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)


def _has_commit(revision: str) -> bool:
    return _git("cat-file", "-e", f"{revision}^{{commit}}").returncode == 0


def _event_base(arguments: argparse.Namespace) -> str:
    if arguments.event_name == "pull_request":
        return arguments.pull_request_base
    if arguments.event_name == "push":
        return arguments.push_before
    return ""


def _resolve_event_base(base: str) -> tuple[str | None, int]:
    if not base or base == "0" * 40:
        return None, 0
    if not SHA256.fullmatch(base):
        print("event base must be a nonzero 40-hex commit SHA", file=sys.stderr)
        return None, 2
    if _has_commit(base):
        return base, 0
    fetched = _git("fetch", "--no-tags", "--depth=1", "origin", base)
    if fetched.returncode:
        _write_result(fetched)
        print("event base is unavailable after fetch", file=sys.stderr)
        return None, fetched.returncode
    if _has_commit(base):
        return base, 0
    print("event base is unavailable after fetch", file=sys.stderr)
    return None, 1


def _full_branch_base(default_branch: str) -> str:
    if not default_branch or default_branch.startswith("-") or any(
        character.isspace() for character in default_branch
    ):
        return EMPTY_TREE
    remote_ref = f"refs/remotes/origin/{default_branch}"
    if _git("show-ref", "--verify", "--quiet", remote_ref).returncode:
        _git(
            "fetch",
            "--no-tags",
            "--depth=1",
            "origin",
            f"+refs/heads/{default_branch}:{remote_ref}",
        )
    merged = _git("merge-base", remote_ref, "HEAD")
    if merged.returncode == 0:
        base = merged.stdout.strip()
        if SHA256.fullmatch(base):
            return base
    return EMPTY_TREE


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--pull-request-base", default="")
    parser.add_argument("--push-before", default="")
    parser.add_argument("--default-branch", required=True)
    arguments = parser.parse_args(argv)

    base, status = _resolve_event_base(_event_base(arguments))
    if status:
        return status
    if base is None:
        base = _full_branch_base(arguments.default_branch)
    checked = _git("diff", "--check", base, "HEAD")
    _write_result(checked)
    return checked.returncode


if __name__ == "__main__":
    raise SystemExit(main())
