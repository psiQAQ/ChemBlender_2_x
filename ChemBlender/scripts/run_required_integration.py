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
            "expected_failure": [],
            "failed": [],
            "passed": [],
            "skipped": [],
            "unexpected_success": [],
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

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            category = (
                "failed" if issubclass(err[0], test.failureException) else "error"
            )
            self.test_ids[category].append(subtest.id())

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self.test_ids["expected_failure"].append(test.id())

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self.test_ids["unexpected_success"].append(test.id())


def _version_requirements(specifications: list[str]):
    required_versions = {}
    versions = {}
    errors = []
    for specification in sorted(specifications):
        name, separator, expected = specification.partition("==")
        if (
            not separator
            or not name
            or not expected
            or "==" in expected
            or any(character.isspace() for character in specification)
        ):
            raise ValueError(
                "--require-version must use the exact distribution==version form"
            )
        if name in required_versions and required_versions[name] != expected:
            raise ValueError(f"conflicting required versions for {name}")
        required_versions[name] = expected
    for name, expected in required_versions.items():
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            actual = "missing"
        versions[name] = actual
        if actual != expected:
            errors.append(f"{name}: expected {expected}, found {actual}")
    return required_versions, versions, errors


def _version_specs_from_files(paths: list[Path]):
    specifications = []
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise ValueError("--require-version-file must name a regular file")
        for line in path.read_text(encoding="utf-8").splitlines():
            specification = line.strip()
            if specification and not specification.startswith("#"):
                specifications.append(specification)
    return specifications


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
    required_versions, versions, version_errors = _version_requirements(version_specs)
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
        "expected_failure": len(test_ids["expected_failure"]),
        "failed": len(test_ids["failed"]),
        "load_error": len(load_errors),
        "passed": len(test_ids["passed"]),
        "skipped": len(test_ids["skipped"]),
        "total": result.testsRun,
        "unexpected_success": len(test_ids["unexpected_success"]),
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
        "required_versions": required_versions,
        "test_ids": test_ids,
        "version_errors": version_errors,
        "versions": versions,
        "zero_discovered": zero_discovered,
    }
    failed = (
        bool(fixture_errors)
        or bool(version_errors)
        or bool(load_errors)
        or bool(zero_discovered)
        or not result.wasSuccessful()
        or counts["passed"] != counts["total"]
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
    parser.add_argument(
        "--require-version-file", action="append", default=[], type=Path
    )
    namespace = parser.parse_args(arguments)
    try:
        version_specs = [
            *namespace.require_version,
            *_version_specs_from_files(namespace.require_version_file),
        ]
        summary, failed = run_required_modules(
            namespace.module, namespace.fixture, version_specs
        )
        _write_summary(namespace.summary, summary)
    except ValueError as error:
        parser.error(str(error))
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
