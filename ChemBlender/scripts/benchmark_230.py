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


def _call_timed(runner, scale, workspace, clock):
    started = clock()
    runner(scale, workspace)
    elapsed = clock() - started
    if not isfinite(elapsed) or elapsed < 0:
        raise ValueError("benchmark timer must return a finite non-negative duration")
    return elapsed


def _measure_case(case, runner, scale, workspace, warmup_count, sample_count, clock):
    failures = []
    try:
        for _index in range(warmup_count):
            _call_timed(runner, scale, workspace, clock)
        samples = [
            _call_timed(runner, scale, workspace, clock)
            for _index in range(sample_count)
        ]
    except Exception as error:
        failures.append({"type": type(error).__name__, "message": str(error)})
        samples = []
    result = {
        "boundary": case.boundary,
        "cold_seconds": None if not samples else samples[0],
        "execution": case.execution,
        "failure_count": len(failures),
        "failures": failures,
        "hot_seconds": None if len(samples) < 2 else median(samples[1:]),
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


def _source_path(workspace, scale):
    return generate_structure_xyz(
        Path(workspace) / f"{scale.name}-structure.xyz",
        atom_count=scale.structure_atoms,
    ).path


def _preflight_feedback(scale, workspace):
    from ChemBlender.core.import_pipeline.request import ImportRequest, ImportSource
    from ChemBlender.core.import_pipeline.staging import StagedImportSession
    from ChemBlender.reader_api.import_pipeline_bridge import preflight_reader_plugins
    from ChemBlender.reader_api.registry import builtin_reader_plugin_registry

    session = StagedImportSession.create(temp_parent=Path(workspace))
    try:
        result = preflight_reader_plugins(
            ImportRequest(sources=(ImportSource(_source_path(workspace, scale)),)),
            builtin_reader_plugin_registry(),
            session,
        )
        if len(result.staged_batch_ids) != 1:
            raise RuntimeError("preflight did not stage one batch")
    finally:
        session.discard()


def _parse(scale, workspace):
    from ChemBlender.core.xyz import parse_xyz

    batch = parse_xyz(_source_path(workspace, scale))
    if len(batch.structures[0].atomic_numbers) != scale.structure_atoms:
        raise RuntimeError("XYZ parser returned the wrong atom count")


def _project_commit(scale, workspace):
    from ChemBlender.core import QCProject
    from ChemBlender.core.xyz import parse_xyz

    project = QCProject(uuid4(), "0.2")
    project.commit(parse_xyz(_source_path(workspace, scale)))
    if len(project.structures) != 1:
        raise RuntimeError("project commit did not retain the parsed structure")


def _sidecar_save_open(scale, workspace):
    from ChemBlender.core import QCProject, close_project, open_project, save_project
    from ChemBlender.core.xyz import parse_xyz

    destination = Path(workspace) / "benchmark.cbq"
    project = QCProject(uuid4(), "0.2")
    project.commit(parse_xyz(_source_path(workspace, scale)))
    save_project(destination, project)
    reopened = open_project(destination)
    try:
        if len(reopened.structures) != 1:
            raise RuntimeError("sidecar reopen did not retain the structure")
    finally:
        close_project(reopened)
        shutil.rmtree(destination)


def _trajectory_frame(scale, workspace):
    fixture = generate_trajectory_npy(
        Path(workspace) / f"{scale.name}-trajectory.npy",
        frames=scale.trajectory_frames,
    )
    try:
        frame = fixture.array[scale.trajectory_frames - 1]
        if not frame.shape == (1, 3):
            raise RuntimeError("lazy trajectory frame has the wrong shape")
    finally:
        fixture.array.close()


def _browser_projection_filter(scale, workspace):
    from ChemBlender.core import QCProject
    from ChemBlender.core.xyz import parse_xyz
    from ChemBlender.ui.project_browser import build_browser_rows

    project = QCProject(uuid4(), "0.2")
    project.commit(parse_xyz(_source_path(workspace, scale)))
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
    ) or sample_count == 0:
        raise ValueError("warmup_count must be non-negative and sample_count positive")
    names = tuple(case_names)
    if not names or len(set(names)) != len(names) or any(
        name not in CASE_REGISTRY for name in names
    ):
        raise ValueError("case_names must be distinct registered benchmark cases")
    active_runners = dict(BUILTIN_RUNNERS if runners is None else runners)
    results = []
    with TemporaryDirectory(prefix="chemblender-230-benchmark-") as directory:
        workspace = Path(directory)
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
                        BENCHMARK_SCALES[scale],
                        workspace,
                        warmup_count,
                        sample_count,
                        clock,
                    )
                )
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
    if not report.get("passed") or report.get("failure_count"):
        raise ValueError("benchmark report contains failed cases")
    for case in report.get("cases", ()):
        if set(case) != required_case:
            raise ValueError("benchmark case has missing or unexpected fields")
        if case["status"] != "Passed":
            raise ValueError("benchmark qualification requires every selected case")
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
