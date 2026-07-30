from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


class RecordingResult(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.test_ids = {
            "error": [],
            "failed": [],
            "passed": [],
            "skipped": [],
        }

    def addSuccess(self, test):
        super().addSuccess(test)
        self.test_ids["passed"].append(test.id())

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.test_ids["failed"].append(test.id())

    def addError(self, test, err):
        super().addError(test, err)
        self.test_ids["error"].append(test.id())

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.test_ids["skipped"].append(test.id())


def _version_requirements(specifications: list[str]):
    versions = {}
    errors = []
    for specification in sorted(specifications):
        name, separator, expected = specification.partition("==")
        if not separator or not name or not expected:
            raise ValueError(
                "--require-version must use the exact distribution==version form"
            )
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            actual = "missing"
        versions[name] = actual
        if actual != expected:
            errors.append(f"{name}: expected {expected}, found {actual}")
    return versions, errors


def _fixture_hashes(specifications: list[str]):
    root = Path.cwd().resolve()
    hashes = {}
    errors = []
    for specification in sorted(specifications):
        name, separator, expected = specification.rpartition("=")
        if not separator or not name or len(expected) != 64 or any(
            character not in "0123456789abcdefABCDEF" for character in expected
        ):
            raise ValueError(
                "--fixture must use the relative-path=64-character-sha256 form"
            )
        declared = Path(name)
        candidate = (root / declared).resolve()
        if declared.is_absolute() or not candidate.is_relative_to(root):
            errors.append(f"{name}: outside working directory")
            continue
        if not candidate.is_file():
            errors.append(f"{name}: missing")
            continue
        actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
        hashes[declared.as_posix()] = actual
        if actual != expected.lower():
            errors.append(f"{name}: sha256 mismatch")
    return hashes, errors


def _load_modules(module_names: list[str]):
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    load_errors = []
    zero_discovered = []
    for module_name in module_names:
        error_count = len(loader.errors)
        loaded = loader.loadTestsFromName(module_name)
        if len(loader.errors) != error_count:
            load_errors.append(module_name)
            continue
        if loaded.countTestCases() == 0:
            zero_discovered.append(module_name)
            continue
        suite.addTest(loaded)
    return suite, sorted(load_errors), sorted(zero_discovered)


def _write_summary(path: Path, summary: dict):
    if path.is_symlink():
        raise ValueError("summary path must not be a symlink")
    parent = path.parent.resolve()
    if not parent.is_dir():
        raise ValueError("summary parent directory does not exist")
    payload = json.dumps(summary, sort_keys=True, separators=(",", ":")) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        dir=parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def run_required_modules(
    module_names: list[str], fixture_specs: list[str], version_specs: list[str]
):
    fixture_hashes, fixture_errors = _fixture_hashes(fixture_specs)
    versions, version_errors = _version_requirements(version_specs)
    if fixture_errors or version_errors:
        suite = unittest.TestSuite()
        load_errors = []
        zero_discovered = []
    else:
        suite, load_errors, zero_discovered = _load_modules(module_names)
    result = RecordingResult()
    suite.run(result)
    test_ids = {
        **{name: sorted(ids) for name, ids in result.test_ids.items()},
        "load_error": load_errors,
    }
    counts = {
        "error": len(test_ids["error"]),
        "failed": len(test_ids["failed"]),
        "load_error": len(load_errors),
        "passed": len(test_ids["passed"]),
        "skipped": len(test_ids["skipped"]),
        "total": result.testsRun,
    }
    summary = {
        "counts": counts,
        "fixture_errors": fixture_errors,
        "fixture_hashes": fixture_hashes,
        "modules": sorted(module_names),
        "python": {
            "implementation": sys.implementation.name,
            "version": sys.version.split()[0],
        },
        "test_ids": test_ids,
        "version_errors": version_errors,
        "versions": versions,
        "zero_discovered": zero_discovered,
    }
    failed = any(
        (
            counts["error"],
            counts["failed"],
            counts["load_error"],
            counts["skipped"],
            bool(fixture_errors),
            bool(version_errors),
            bool(zero_discovered),
        )
    )
    return summary, failed


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run required unittest integrations and reject skipped coverage."
    )
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--module", action="append", required=True)
    parser.add_argument("--fixture", action="append", default=[])
    parser.add_argument("--require-version", action="append", default=[])
    namespace = parser.parse_args(arguments)
    try:
        summary, failed = run_required_modules(
            namespace.module, namespace.fixture, namespace.require_version
        )
        _write_summary(namespace.summary, summary)
    except ValueError as error:
        parser.error(str(error))
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
