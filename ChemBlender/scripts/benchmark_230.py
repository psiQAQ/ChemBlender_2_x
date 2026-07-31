#!/usr/bin/env python3
"""Unified, dependency-free benchmark result harness for ChemBlender 2.3.0."""

import argparse
from collections import namedtuple
import json
from math import ceil, isfinite
import os
from pathlib import Path
import platform
import shutil
from statistics import median
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
    "BenchmarkCase", "name execution boundary"
)
PreparedFixtures = namedtuple(
    "PreparedFixtures", "workspace scale source trajectory batch"
)

CASE_REGISTRY = {
    "extension_enable": BenchmarkCase(
        "extension_enable", "blender", "requires a separate Blender launch"
    ),
    "preflight_feedback": BenchmarkCase("preflight_feedback", "core", ""),
    "parse": BenchmarkCase("parse", "core", ""),
    "project_commit": BenchmarkCase("project_commit", "core", ""),
    "sidecar_save_open": BenchmarkCase("sidecar_save_open", "core", ""),
    "vdb_cache": BenchmarkCase(
        "vdb_cache", "blender", "requires Blender and OpenVDB runtime"
    ),
    "default_view": BenchmarkCase(
        "default_view", "blender", "requires Blender scene datablocks"
    ),
    "trajectory_frame": BenchmarkCase("trajectory_frame", "core", ""),
    "browser_projection_filter": BenchmarkCase(
        "browser_projection_filter", "core", ""
    ),
    "cancel_cleanup": BenchmarkCase(
        "cancel_cleanup",
        "future",
        "requires the Wave 4 cancellable task state machine",
    ),
}


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
    return {
        "cpu_count": os.cpu_count(),
        "machine": platform.machine(),
        "platform": platform.platform(),
        "processor": platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER", ""),
        "python_executable": sys.executable,
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
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
        "cold_seconds": cold_seconds,
        "execution": case.execution,
        "failure_count": len(failures),
        "failures": failures,
        "hot_seconds": None if not samples else median(samples),
        "maximum_seconds": None,
        "median_seconds": None,
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
        "cold_seconds": None,
        "execution": case.execution,
        "failure_count": 0,
        "failures": [],
        "hot_seconds": None,
        "maximum_seconds": None,
        "median_seconds": None,
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
    report = {
        "benchmark": "chemblender-2.3.0-v1",
        "cases": results,
        "environment": benchmark_environment(),
        "failure_count": sum(case["failure_count"] for case in results),
        "passed": all(case["status"] == "Passed" for case in results),
        "sample_count": sample_count,
        "scale": scale,
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
        "warmup_count",
    }
    required_environment = set(benchmark_environment())
    required_case = {
        "boundary",
        "cold_seconds",
        "execution",
        "failure_count",
        "failures",
        "hot_seconds",
        "maximum_seconds",
        "median_seconds",
        "minimum_seconds",
        "name",
        "p95_seconds",
        "sample_seconds",
        "status",
    }
    if not isinstance(report, dict) or set(report) != required_report:
        raise ValueError("benchmark report has missing or unexpected fields")
    if set(report.get("environment", ())) != required_environment:
        raise ValueError("benchmark environment is incomplete")
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
