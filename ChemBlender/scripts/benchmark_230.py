#!/usr/bin/env python3
"""Unified, dependency-free benchmark result harness for ChemBlender 2.3.0."""

import argparse
from collections import namedtuple
from functools import lru_cache
import json
from math import ceil, isclose, isfinite
import os
from pathlib import Path
import platform
import re
import shutil
from statistics import median
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import perf_counter
from uuid import uuid4


if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ChemBlender.benchmarks.datasets import (
    BENCHMARK_SCALES,
    generate_structure_xyz,
    generate_trajectory_npy,
)


BenchmarkCase = namedtuple(
    "BenchmarkCase", "name execution boundary cache_state measurement"
)
PreparedFixtures = namedtuple(
    "PreparedFixtures", "workspace scale source trajectory batch"
)

CASE_REGISTRY = {
    "extension_enable": BenchmarkCase(
        "extension_enable", "blender", "requires a separate Blender launch", "cold", "diagnostic"
    ),
    "preflight_feedback": BenchmarkCase("preflight_feedback", "core", "", "cold", "diagnostic"),
    "parse": BenchmarkCase("parse", "core", "", "cold", "diagnostic"),
    "project_commit": BenchmarkCase("project_commit", "core", "", "cold", "diagnostic"),
    "sidecar_save_open": BenchmarkCase("sidecar_save_open", "core", "", "cold", "diagnostic"),
    "vdb_cache": BenchmarkCase(
        "vdb_cache", "blender", "requires Blender and OpenVDB runtime", "cold", "diagnostic"
    ),
    "default_view": BenchmarkCase(
        "default_view", "blender", "requires Blender scene datablocks", "cold", "diagnostic"
    ),
    "trajectory_frame": BenchmarkCase("trajectory_frame", "core", "", "hot", "diagnostic"),
    "browser_projection_filter": BenchmarkCase(
        "browser_projection_filter", "core", "", "cold", "diagnostic"
    ),
    "cancel_cleanup": BenchmarkCase(
        "cancel_cleanup",
        "future",
        "requires the Wave 4 cancellable task state machine",
        "cold",
        "diagnostic",
    ),
}

_BUDGET_SCHEMA_VERSION = "2.0"
_REQUIRED_BUDGET_CASES = frozenset(
    {
        "extension_enable",
        "preflight_feedback",
        "default_view",
        "vdb_cache",
        "trajectory_frame",
        "browser_projection_filter",
    }
)
_TREND_ENVIRONMENT_FIELDS = (
    "cpu_count",
    "machine",
    "platform",
    "processor",
    "python_implementation",
    "python_version",
    "blender_version",
    "rdkit_version",
    "gemmi_version",
)
_PRODUCT_MEASUREMENTS = frozenset({"cold_p95", "hot_p95"})


def _blender_executable():
    candidates = []
    configured = os.environ.get("BLENDER_BINARY")
    if configured:
        candidates.append(Path(configured))
    candidates.extend(parent / "blender.exe" for parent in Path(sys.executable).resolve().parents[:4])
    for candidate in candidates:
        if not candidate.is_file():
            continue
        return candidate
    return None


@lru_cache(maxsize=1)
def _blender_runtime_versions():
    empty = {"blender_version": None, "gemmi_version": None, "rdkit_version": None}
    executable = _blender_executable()
    if executable is None:
        return empty
    code = (
        "bpy=__import__('bpy');gemmi=__import__('gemmi');json=__import__('json');rdkit=__import__('rdkit');"
        "print('CHEMBLENDER_RUNTIME=' + json.dumps({'blender_version': bpy.app.version_string, "
        "'gemmi_version': gemmi.__version__, 'rdkit_version': rdkit.__version__}, sort_keys=True))"
    )
    try:
        result = subprocess.run(
            [
                str(executable),
                "--background",
                "--factory-startup",
                "--python-expr",
                code,
                "--python-exit-code",
                "1",
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return empty
    for line in result.stdout.splitlines():
        if not line.startswith("CHEMBLENDER_RUNTIME="):
            continue
        try:
            versions = json.loads(line.removeprefix("CHEMBLENDER_RUNTIME="))
        except json.JSONDecodeError:
            return empty
        if (
            result.returncode == 0
            and type(versions) is dict
            and set(versions) == set(empty)
            and all(isinstance(value, str) and value for value in versions.values())
        ):
            return versions
    return empty


def benchmark_source_state():
    root = Path(__file__).resolve().parents[2]
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=root,
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except OSError:
        return None, None
    source_commit = commit.stdout.strip()
    if commit.returncode or dirty.returncode or not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        return None, None
    return source_commit, bool(dirty.stdout)


def canonical_json(document):
    """Encode compact, sorted UTF-8 JSON and reject non-finite values."""
    try:
        return json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ) + "\n"
    except (TypeError, ValueError) as error:
        raise ValueError("benchmark JSON must be finite and serializable") from error


def write_canonical_json(path, document):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json(document).encode("utf-8")
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def benchmark_environment():
    runtime = _blender_runtime_versions()
    return {
        "cpu_count": os.cpu_count(),
        "machine": platform.machine(),
        "platform": platform.platform(),
        "processor": platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER", ""),
        "python_executable": sys.executable,
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        **runtime,
    }


def load_performance_budget(path):
    """Load the versioned local-SLA and CI trend policy."""
    try:
        budget = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("performance budget is not valid JSON") from error
    required = {
        "cases",
        "hard_local_metric",
        "schema_version",
        "trend_max_regression_percent",
        "trend_metric",
    }
    if type(budget) is not dict or set(budget) != required:
        raise ValueError("performance budget has missing or unexpected fields")
    if budget["schema_version"] != _BUDGET_SCHEMA_VERSION:
        raise ValueError("performance budget schema version is unsupported")
    if budget["hard_local_metric"] != "p95_seconds" or budget["trend_metric"] != "p95_seconds":
        raise ValueError("performance budget must use p95_seconds")
    percent = budget["trend_max_regression_percent"]
    if (
        isinstance(percent, bool)
        or not isinstance(percent, (int, float))
        or not isfinite(percent)
        or not 0 <= percent <= 100
    ):
        raise ValueError("performance budget trend percentage is invalid")
    cases = budget["cases"]
    if type(cases) is not dict or set(cases) != _REQUIRED_BUDGET_CASES:
        raise ValueError("performance budget cases are incomplete")
    for name, definition in cases.items():
        if type(definition) is not dict or set(definition) != {
            "cache_state",
            "hard_limit_seconds",
            "measurement",
            "scale",
        }:
            raise ValueError(f"performance budget case is invalid: {name}")
        limit = definition["hard_limit_seconds"]
        if (
            isinstance(limit, bool)
            or not isinstance(limit, (int, float))
            or not isfinite(limit)
            or limit <= 0
        ):
            raise ValueError(f"performance budget limit is invalid: {name}")
        if definition["scale"] not in BENCHMARK_SCALES:
            raise ValueError(f"performance budget scale is invalid: {name}")
        if definition["cache_state"] not in {"cold", "hot"}:
            raise ValueError(f"performance budget cache_state is invalid: {name}")
        if definition["measurement"] != f"{definition['cache_state']}_p95":
            raise ValueError(f"performance budget measurement is invalid: {name}")
        if CASE_REGISTRY[name].cache_state != definition["cache_state"]:
            raise ValueError(f"performance budget cache_state disagrees: {name}")
    return budget


def _required_budget_cases(report, budget):
    validate_qualified_report(report)
    cases = {}
    for case in report["cases"]:
        name = case["name"]
        if name in cases or name not in CASE_REGISTRY:
            raise ValueError("benchmark report has duplicate or unknown case")
        cases[name] = case
    missing = set(budget["cases"]) - set(cases)
    if missing:
        raise ValueError(f"benchmark report is missing required cases: {sorted(missing)}")
    for name, definition in budget["cases"].items():
        case = cases[name]
        if report["scale"] != definition["scale"]:
            raise ValueError(f"benchmark report scale disagrees: {name}")
        if case["cache_state"] != definition["cache_state"]:
            raise ValueError(f"benchmark report cache_state disagrees: {name}")
        if case["measurement"] == "diagnostic":
            raise ValueError(f"benchmark report diagnostic-only case: {name}")
        if case["measurement"] != definition["measurement"]:
            raise ValueError(f"benchmark report measurement disagrees: {name}")
        if not isfinite(case["p95_seconds"]):
            raise ValueError(f"benchmark report p95_seconds is not finite: {name}")
    return cases


def _matching_trend_environment(candidate, baseline):
    for name in _TREND_ENVIRONMENT_FIELDS:
        if candidate["environment"][name] != baseline["environment"][name]:
            raise ValueError(f"benchmark environment mismatch: {name}")


def compare_performance_report(report, budget, *, baseline_report=None):
    """Fail closed for incomplete data; return failed hard/trend budget checks."""
    cases = _required_budget_cases(report, budget)
    hard_failures = [
        name
        for name, definition in budget["cases"].items()
        if cases[name][budget["hard_local_metric"]] > definition["hard_limit_seconds"]
    ]
    trend_failures = []
    if baseline_report is not None:
        baseline_cases = _required_budget_cases(baseline_report, budget)
        if report["scale"] != baseline_report["scale"]:
            raise ValueError("benchmark scale mismatch")
        _matching_trend_environment(report, baseline_report)
        for name in budget["cases"]:
            if cases[name]["cache_state"] != baseline_cases[name]["cache_state"]:
                raise ValueError(f"benchmark cache_state mismatch: {name}")
            baseline_p95 = baseline_cases[name][budget["trend_metric"]]
            if baseline_p95 <= 0:
                raise ValueError(f"benchmark baseline p95_seconds must be positive: {name}")
            candidate_p95 = cases[name][budget["trend_metric"]]
            limit = baseline_p95 * (1 + budget["trend_max_regression_percent"] / 100)
            if candidate_p95 > limit and not isclose(candidate_p95, limit, rel_tol=1e-12, abs_tol=1e-12):
                trend_failures.append(name)
    return {
        "hard_local_failures": hard_failures,
        "passed": not hard_failures and not trend_failures,
        "trend_failures": trend_failures,
    }


def _summary(samples):
    ordered = sorted(samples)
    return {
        "minimum_seconds": ordered[0],
        "median_seconds": median(ordered),
        "p95_seconds": ordered[max(0, ceil(len(ordered) * 0.95) - 1)],
        "maximum_seconds": ordered[-1],
    }


def _call_timed(case_name, runner, fixtures, clock, *, builtin):
    sample = _prepare_sample(case_name, fixtures) if builtin else None
    try:
        started = clock()
        runner(fixtures, sample)
        elapsed = clock() - started
        if not isfinite(elapsed) or elapsed < 0:
            raise ValueError("benchmark timer must return a finite non-negative duration")
        return elapsed
    finally:
        if builtin:
            _cleanup_sample(case_name, sample)


def _measure_case(case, runner, fixtures, warmup_count, sample_count, clock, *, builtin):
    failures = []
    cold_seconds = None
    try:
        cold_seconds = _call_timed(
            case.name, runner, fixtures, clock, builtin=builtin
        )
        for _index in range(warmup_count):
            _call_timed(case.name, runner, fixtures, clock, builtin=builtin)
        samples = [
            _call_timed(case.name, runner, fixtures, clock, builtin=builtin)
            for _index in range(sample_count)
        ]
    except Exception as error:
        failures.append({"type": type(error).__name__, "message": str(error)})
        samples = []
    result = {
        "boundary": case.boundary,
        "cache_state": case.cache_state,
        "cold_seconds": cold_seconds,
        "execution": case.execution,
        "failure_count": len(failures),
        "failures": failures,
        "hot_seconds": None if not samples else median(samples),
        "maximum_seconds": None,
        "median_seconds": None,
        "measurement": case.measurement,
        "minimum_seconds": None,
        "name": case.name,
        "p95_seconds": None,
        "sample_seconds": samples,
        "status": "Failed" if failures else "Passed",
    }
    if samples:
        result.update(_summary(samples))
    return result


def _not_run_case(case):
    return {
        "boundary": case.boundary,
        "cache_state": case.cache_state,
        "cold_seconds": None,
        "execution": case.execution,
        "failure_count": 0,
        "failures": [],
        "hot_seconds": None,
        "maximum_seconds": None,
        "median_seconds": None,
        "measurement": case.measurement,
        "minimum_seconds": None,
        "name": case.name,
        "p95_seconds": None,
        "sample_seconds": [],
        "status": "Not Run",
    }


_SOURCE_CASES = frozenset(
    {
        "preflight_feedback",
        "parse",
        "project_commit",
        "sidecar_save_open",
        "browser_projection_filter",
    }
)
_BATCH_CASES = frozenset(
    {"project_commit", "sidecar_save_open", "browser_projection_filter"}
)


def _prepare_fixtures(case_names, scale, workspace):
    source = None
    trajectory = None
    batch = None
    try:
        if _SOURCE_CASES.intersection(case_names):
            source = generate_structure_xyz(
                Path(workspace) / f"{scale.name}-structure.xyz",
                atom_count=scale.structure_atoms,
            )
        if "trajectory_frame" in case_names:
            trajectory = generate_trajectory_npy(
                Path(workspace) / f"{scale.name}-trajectory.npy",
                frames=scale.trajectory_frames,
            )
        if _BATCH_CASES.intersection(case_names):
            from ChemBlender.core.xyz import parse_xyz

            batch = parse_xyz(source.path)
        return PreparedFixtures(Path(workspace), scale, source, trajectory, batch)
    except BaseException as error:
        if trajectory is not None:
            try:
                trajectory.array.close()
            except BaseException as cleanup_error:
                error.add_note(f"benchmark fixture cleanup failed: {cleanup_error}")
        raise


def _cleanup_fixtures(fixtures):
    if fixtures.trajectory is not None:
        fixtures.trajectory.array.close()


def _prepare_sample(case_name, fixtures):
    if case_name == "preflight_feedback":
        from ChemBlender.core.import_pipeline.staging import StagedImportSession

        return StagedImportSession.create(temp_parent=fixtures.workspace)
    if case_name == "project_commit":
        from ChemBlender.core import QCProject

        return QCProject(uuid4(), "0.2")
    if case_name == "sidecar_save_open":
        from ChemBlender.core import QCProject

        project = QCProject(uuid4(), "0.2")
        project.commit(fixtures.batch)
        return {
            "destination": fixtures.workspace / f"sidecar-{uuid4().hex}.cbq",
            "project": project,
            "reopened": None,
        }
    if case_name == "browser_projection_filter":
        from ChemBlender.core import QCProject

        project = QCProject(uuid4(), "0.2")
        project.commit(fixtures.batch)
        return project
    return None


def _cleanup_sample(case_name, sample):
    if case_name == "preflight_feedback" and sample is not None:
        sample.discard()
    elif case_name == "sidecar_save_open" and sample is not None:
        if sample["reopened"] is not None:
            from ChemBlender.core import close_project

            close_project(sample["reopened"])
        if sample["destination"].exists():
            shutil.rmtree(sample["destination"])


def _preflight_feedback(fixtures, session):
    from ChemBlender.core.import_pipeline.request import ImportRequest, ImportSource
    from ChemBlender.reader_api.import_pipeline_bridge import preflight_reader_plugins
    from ChemBlender.reader_api.registry import builtin_reader_plugin_registry

    result = preflight_reader_plugins(
        ImportRequest(sources=(ImportSource(fixtures.source.path),)),
        builtin_reader_plugin_registry(),
        session,
    )
    if len(result.staged_batch_ids) != 1:
        raise RuntimeError("preflight did not stage one batch")


def _parse(fixtures, _sample):
    from ChemBlender.core.xyz import parse_xyz

    batch = parse_xyz(fixtures.source.path)
    if len(batch.structures[0].atomic_numbers) != fixtures.scale.structure_atoms:
        raise RuntimeError("XYZ parser returned the wrong atom count")


def _project_commit(fixtures, project):
    project.commit(fixtures.batch)
    if len(project.structures) != 1:
        raise RuntimeError("project commit did not retain the parsed structure")


def _sidecar_save_open(_fixtures, sample):
    from ChemBlender.core import open_project, save_project

    save_project(sample["destination"], sample["project"])
    sample["reopened"] = open_project(sample["destination"])
    if len(sample["reopened"].structures) != 1:
        raise RuntimeError("sidecar reopen did not retain the structure")


def _trajectory_frame(fixtures, _sample):
    frame = fixtures.trajectory.array[fixtures.scale.trajectory_frames - 1]
    if not frame.shape == (1, 3):
        raise RuntimeError("lazy trajectory frame has the wrong shape")


def _browser_projection_filter(_fixtures, project):
    from ChemBlender.ui.project_browser import build_browser_rows

    if not build_browser_rows(project, search="benchmark"):
        raise RuntimeError("browser projection did not retain the benchmark source")


BUILTIN_RUNNERS = {
    "preflight_feedback": _preflight_feedback,
    "parse": _parse,
    "project_commit": _project_commit,
    "sidecar_save_open": _sidecar_save_open,
    "trajectory_frame": _trajectory_frame,
    "browser_projection_filter": _browser_projection_filter,
}


def run_benchmark(
    *,
    case_names,
    scale="interactive",
    warmup_count=1,
    sample_count=5,
    runners=None,
    clock=perf_counter,
):
    if scale not in BENCHMARK_SCALES:
        raise ValueError(f"unknown benchmark scale: {scale}")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in (warmup_count, sample_count)
    ) or sample_count < 2:
        raise ValueError("warmup_count must be non-negative and sample_count at least two")
    names = tuple(case_names)
    if not names or len(set(names)) != len(names) or any(
        name not in CASE_REGISTRY for name in names
    ):
        raise ValueError("case_names must be distinct registered benchmark cases")
    builtin = runners is None
    active_runners = dict(BUILTIN_RUNNERS if builtin else runners)
    results = []
    with TemporaryDirectory(prefix="chemblender-230-benchmark-") as directory:
        workspace = Path(directory)
        fixtures = (
            _prepare_fixtures(names, BENCHMARK_SCALES[scale], workspace)
            if builtin
            else PreparedFixtures(workspace, BENCHMARK_SCALES[scale], None, None, None)
        )
        try:
            for name in names:
                case = CASE_REGISTRY[name]
                runner = active_runners.get(name)
                if runner is None:
                    results.append(_not_run_case(case))
                else:
                    results.append(
                        _measure_case(
                            case,
                            runner,
                            fixtures,
                            warmup_count,
                            sample_count,
                            clock,
                            builtin=builtin,
                        )
                    )
        finally:
            if builtin:
                _cleanup_fixtures(fixtures)
    source_commit, source_dirty = benchmark_source_state()
    report = {
        "benchmark": "chemblender-2.3.0-v2",
        "cases": results,
        "environment": benchmark_environment(),
        "failure_count": sum(case["failure_count"] for case in results),
        "passed": all(case["status"] == "Passed" for case in results),
        "sample_count": sample_count,
        "scale": scale,
        "source_commit": source_commit,
        "source_dirty": source_dirty,
        "warmup_count": warmup_count,
    }
    return report


def validate_qualified_report(report):
    required_report = {
        "benchmark",
        "cases",
        "environment",
        "failure_count",
        "passed",
        "sample_count",
        "scale",
        "source_commit",
        "source_dirty",
        "warmup_count",
    }
    required_environment = set(benchmark_environment())
    required_case = {
        "boundary",
        "cache_state",
        "cold_seconds",
        "execution",
        "failure_count",
        "failures",
        "hot_seconds",
        "maximum_seconds",
        "median_seconds",
        "measurement",
        "minimum_seconds",
        "name",
        "p95_seconds",
        "sample_seconds",
        "status",
    }
    if not isinstance(report, dict) or set(report) != required_report:
        raise ValueError("benchmark report has missing or unexpected fields")
    if report["benchmark"] != "chemblender-2.3.0-v2":
        raise ValueError("benchmark report schema version is unsupported")
    if not isinstance(report["source_commit"], str) or not re.fullmatch(
        r"[0-9a-f]{40}", report["source_commit"]
    ):
        raise ValueError("benchmark report source_commit is invalid")
    if report["source_dirty"] is not False:
        raise ValueError("benchmark report source_dirty must be false")
    if set(report.get("environment", ())) != required_environment:
        raise ValueError("benchmark environment is incomplete")
    for name in ("blender_version", "rdkit_version", "gemmi_version"):
        if not isinstance(report["environment"][name], str) or not report["environment"][name]:
            raise ValueError(f"benchmark environment {name} is invalid")
    if (
        isinstance(report["sample_count"], bool)
        or not isinstance(report["sample_count"], int)
        or report["sample_count"] < 2
    ):
        raise ValueError("benchmark qualification requires at least two samples")
    if not report.get("passed") or report.get("failure_count"):
        raise ValueError("benchmark report contains failed cases")
    for case in report.get("cases", ()):
        if set(case) != required_case:
            raise ValueError("benchmark case has missing or unexpected fields")
        if case["status"] != "Passed":
            raise ValueError("benchmark qualification requires every selected case")
        if case["cache_state"] not in {"cold", "hot"}:
            raise ValueError("benchmark case cache_state is invalid")
        if case["measurement"] not in _PRODUCT_MEASUREMENTS | {"diagnostic"}:
            raise ValueError("benchmark case measurement is invalid")
        if len(case["sample_seconds"]) != report["sample_count"]:
            raise ValueError("benchmark case sample count does not match report")
        for name in (
            "cold_seconds",
            "hot_seconds",
            "minimum_seconds",
            "median_seconds",
            "p95_seconds",
            "maximum_seconds",
        ):
            if not isfinite(case[name]):
                raise ValueError("benchmark timing must be finite")
    canonical_json(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run ChemBlender 2.3.0 benchmark cases")
    parser.add_argument("--case", action="append", choices=tuple(CASE_REGISTRY) + ("all",))
    parser.add_argument("--scale", choices=tuple(BENCHMARK_SCALES), default="interactive")
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.samples < 2:
        parser.error("--samples must be at least 2")
    case_names = tuple(CASE_REGISTRY) if not args.case or "all" in args.case else tuple(args.case)
    report = run_benchmark(
        case_names=case_names,
        scale=args.scale,
        warmup_count=args.warmups,
        sample_count=args.samples,
    )
    encoded = canonical_json(report)
    if args.output is None:
        sys.stdout.buffer.write(encoded.encode("utf-8"))
    else:
        write_canonical_json(args.output, report)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
