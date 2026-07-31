#!/usr/bin/env python3
"""Qualify the six ChemBlender 2.3.0 product performance budgets.

The normal mode is a stdlib orchestrator.  For each sample it installs the
exact ZIP in a short isolated profile, exits, then measures from a second cold
Blender process.  Every command/stdout/stderr/timing record is retained.
``worker`` mode runs only inside Blender and imports product code from
``bl_ext.user_default``.
"""

import argparse
from collections import namedtuple
from datetime import datetime, timezone
import hashlib
import importlib
import json
from math import ceil, isfinite
import os
from pathlib import Path
import platform
import re
import shutil
from statistics import median
import subprocess
import sys
from time import perf_counter
from uuid import uuid4


ProductCase = namedtuple(
    "ProductCase", "name execution boundary cache_state measurement"
)

PRODUCT_CASES = {
    "extension_enable": ProductCase(
        "extension_enable",
        "blender",
        "fresh-profile Blender Extension enable",
        "cold",
        "cold_p95",
    ),
    "preflight_feedback": ProductCase(
        "preflight_feedback",
        "blender",
        "50k-atom reader preflight plus Import Preview projection",
        "cold",
        "cold_p95",
    ),
    "default_view": ProductCase(
        "default_view",
        "blender",
        "50k-atom automatic Structure scene preset",
        "cold",
        "cold_p95",
    ),
    "vdb_cache": ProductCase(
        "vdb_cache",
        "blender",
        "128-cubed Grid3D to OpenVDB Volume cache",
        "cold",
        "cold_p95",
    ),
    "trajectory_frame": ProductCase(
        "trajectory_frame",
        "blender",
        "cached 1000-atom frame through TrajectoryFrameManager and Blender mesh update",
        "hot",
        "hot_p95",
    ),
    "browser_projection_filter": ProductCase(
        "browser_projection_filter",
        "blender",
        "cold Project Browser projection/filter over 10k SDF records",
        "cold",
        "cold_p95",
    ),
}

WORKER_MARKER = "CHEMBLENDER_PRODUCT_BENCHMARK="
_MODULE_KEY = "bl_ext.user_default.chemblender"
_PREPARED_PROFILE_MARKER = "chemblender-product-package.json"
_MINIMUM_SAMPLES = 5
_TRAJECTORY_ATOMS = 1_000
_WORKER_FIELDS = {
    "assertions",
    "blender_version",
    "case",
    "elapsed_seconds",
    "gemmi_version",
    "installed_origin",
    "package_sha256",
    "python_executable",
    "python_implementation",
    "python_version",
    "rdkit_version",
    "sample_index",
}


def _base_harness():
    if not __package__:
        root = Path(__file__).resolve().parents[2]
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
    return importlib.import_module("ChemBlender.scripts.benchmark_230")


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_bytes(document):
    return (
        json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _write_bytes(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _is_relative_to(path, parent):
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def sample_profile(root, case_name, sample_index):
    if (
        not isinstance(case_name, str)
        or not re.fullmatch(r"[a-z][a-z0-9_]*", case_name)
        or isinstance(sample_index, bool)
        or not isinstance(sample_index, int)
        or sample_index < 0
    ):
        raise ValueError("sample profile identity is invalid")
    return Path(root) / case_name / f"sample-{sample_index:03d}"


def write_prepared_profile_marker(
    profile, *, package_sha256, installed_origin
):
    profile = Path(profile).resolve(strict=True)
    origin = Path(installed_origin).resolve(strict=True)
    if (
        not re.fullmatch(r"[0-9a-f]{64}", package_sha256)
        or not _is_relative_to(origin, profile)
    ):
        raise ValueError("prepared profile identity is invalid")
    _write_bytes(
        profile / _PREPARED_PROFILE_MARKER,
        _canonical_bytes(
            {
                "installed_origin": str(origin),
                "package_sha256": package_sha256,
            }
        ),
    )


def verify_prepared_profile(profile, *, package_sha256):
    profile = Path(profile).resolve(strict=True)
    marker = profile / _PREPARED_PROFILE_MARKER
    try:
        document = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("prepared profile marker is invalid") from error
    if (
        type(document) is not dict
        or set(document) != {"installed_origin", "package_sha256"}
        or document["package_sha256"] != package_sha256
    ):
        raise ValueError("prepared profile package hash does not match")
    origin = Path(document["installed_origin"]).resolve(strict=True)
    if not _is_relative_to(origin, profile):
        raise ValueError("prepared profile installed origin is invalid")
    return origin


def worker_command(
    blender,
    script,
    *,
    case_name,
    package,
    package_sha256,
    profile,
    workspace,
    sample_index,
):
    return [
        str(Path(blender)),
        "--background",
        "--factory-startup",
        "--python-exit-code",
        "1",
        "--python",
        str(Path(script)),
        "--",
        "worker",
        "--case",
        case_name,
        "--package",
        str(Path(package)),
        "--package-sha256",
        package_sha256,
        "--profile",
        str(Path(profile)),
        "--workspace",
        str(Path(workspace)),
        "--sample-index",
        str(sample_index),
    ]


def parse_worker_output(
    stdout,
    *,
    expected_case,
    expected_sample_index,
    expected_package_sha256,
    profile,
    checkout_root,
):
    marker_lines = [
        line.removeprefix(WORKER_MARKER)
        for line in stdout.splitlines()
        if line.startswith(WORKER_MARKER)
    ]
    if len(marker_lines) != 1:
        raise ValueError("worker output must contain one product benchmark marker")
    try:
        document = json.loads(marker_lines[0])
    except json.JSONDecodeError as error:
        raise ValueError("worker marker is not valid JSON") from error
    if type(document) is not dict or set(document) != _WORKER_FIELDS:
        raise ValueError("worker marker has missing or unexpected fields")
    if document["case"] != expected_case:
        raise ValueError("worker case does not match the command")
    if document["sample_index"] != expected_sample_index:
        raise ValueError("worker sample index does not match the command")
    if document["package_sha256"] != expected_package_sha256:
        raise ValueError("worker package hash does not match the command")
    elapsed = document["elapsed_seconds"]
    if (
        isinstance(elapsed, bool)
        or not isinstance(elapsed, (int, float))
        or not isfinite(elapsed)
        or elapsed < 0
    ):
        raise ValueError("worker elapsed_seconds is invalid")
    assertions = document["assertions"]
    if (
        type(assertions) is not dict
        or not assertions
        or any(value is not True for value in assertions.values())
    ):
        raise ValueError("worker product assertions did not all pass")
    for name in (
        "blender_version",
        "gemmi_version",
        "python_executable",
        "python_implementation",
        "python_version",
        "rdkit_version",
    ):
        if not isinstance(document[name], str) or not document[name]:
            raise ValueError(f"worker runtime field is invalid: {name}")
    origin = Path(document["installed_origin"]).resolve()
    profile = Path(profile).resolve()
    checkout_root = Path(checkout_root).resolve()
    if not _is_relative_to(origin, profile) or _is_relative_to(
        origin, checkout_root
    ):
        raise ValueError("worker installed origin is not inside its isolated profile")
    return document


def case_result(case_name, samples):
    try:
        case = PRODUCT_CASES[case_name]
    except KeyError as error:
        raise ValueError(f"unknown product case: {case_name}") from error
    values = list(samples)
    if len(values) < _MINIMUM_SAMPLES:
        raise ValueError("product qualification requires at least five samples")
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or value < 0
        for value in values
    ):
        raise ValueError("product samples must be finite non-negative numbers")
    ordered = sorted(values)
    summary = {
        "maximum_seconds": ordered[-1],
        "median_seconds": median(ordered),
        "minimum_seconds": ordered[0],
        "p95_seconds": ordered[max(0, ceil(len(ordered) * 0.95) - 1)],
    }
    return {
        "boundary": case.boundary,
        "cache_state": case.cache_state,
        "cold_seconds": values[0],
        "execution": case.execution,
        "failure_count": 0,
        "failures": [],
        "hot_seconds": median(values),
        **summary,
        "measurement": case.measurement,
        "name": case.name,
        "sample_seconds": values,
        "status": "Passed",
    }


def _runtime_environment(runtime):
    required = {
        "blender_version",
        "gemmi_version",
        "python_executable",
        "python_implementation",
        "python_version",
        "rdkit_version",
    }
    if type(runtime) is not dict or set(runtime) != required or any(
        not isinstance(value, str) or not value for value in runtime.values()
    ):
        raise ValueError("runtime identity is incomplete")
    return {
        "cpu_count": os.cpu_count(),
        "machine": platform.machine(),
        "platform": platform.platform(),
        "processor": platform.processor()
        or os.environ.get("PROCESSOR_IDENTIFIER", ""),
        **runtime,
    }


def build_report(
    samples_by_case,
    *,
    runtime,
    source_commit,
    source_dirty,
):
    if (
        not isinstance(source_commit, str)
        or not re.fullmatch(r"[0-9a-f]{40}", source_commit)
        or source_dirty is not False
    ):
        raise ValueError("product qualification requires one clean source commit")
    if type(samples_by_case) is not dict or set(samples_by_case) != set(
        PRODUCT_CASES
    ):
        raise ValueError("product samples must cover the six approved cases")
    sample_counts = {len(tuple(values)) for values in samples_by_case.values()}
    if len(sample_counts) != 1:
        raise ValueError("product cases must use one sample count")
    sample_count, = sample_counts
    if sample_count < _MINIMUM_SAMPLES:
        raise ValueError("product qualification requires at least five samples")
    cases = [
        case_result(name, samples_by_case[name]) for name in PRODUCT_CASES
    ]
    report = {
        "benchmark": "chemblender-2.3.0-v2",
        "cases": cases,
        "environment": _runtime_environment(runtime),
        "failure_count": 0,
        "passed": True,
        "sample_count": sample_count,
        "scale": "interactive",
        "source_commit": source_commit,
        "source_dirty": False,
        "warmup_count": 0,
    }
    _base_harness().validate_qualified_report(report)
    return report


def write_process_evidence(
    evidence_root,
    *,
    label,
    command,
    environment,
    returncode,
    stdout,
    stderr,
    duration_seconds,
):
    if not isinstance(label, str) or not re.fullmatch(
        r"[a-z0-9][a-z0-9.-]*", label
    ):
        raise ValueError("evidence label is invalid")
    if (
        isinstance(duration_seconds, bool)
        or not isinstance(duration_seconds, (int, float))
        or not isfinite(duration_seconds)
        or duration_seconds < 0
    ):
        raise ValueError("evidence duration is invalid")
    root = Path(evidence_root)
    root.mkdir(parents=True, exist_ok=True)
    stdout_path = root / f"{label}.stdout.log"
    stderr_path = root / f"{label}.stderr.log"
    _write_bytes(stdout_path, stdout.encode("utf-8"))
    _write_bytes(stderr_path, stderr.encode("utf-8"))
    return {
        "command": list(command),
        "duration_seconds": duration_seconds,
        "environment": dict(sorted(environment.items())),
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "returncode": returncode,
        "stderr_path": stderr_path.name,
        "stdout_path": stdout_path.name,
    }


def _git_source_state(root):
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        check=False,
        text=True,
        timeout=20,
    )
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=root,
        capture_output=True,
        check=False,
        text=True,
        timeout=20,
    )
    source_commit = commit.stdout.strip()
    if (
        commit.returncode
        or status.returncode
        or not re.fullmatch(r"[0-9a-f]{40}", source_commit)
    ):
        raise RuntimeError("cannot resolve benchmark source state")
    return source_commit, bool(status.stdout)


def _runtime_identity(document):
    return {
        name: document[name]
        for name in (
            "blender_version",
            "gemmi_version",
            "python_executable",
            "python_implementation",
            "python_version",
            "rdkit_version",
        )
    }


def _run_worker_process(
    *,
    blender,
    script,
    case_name,
    package,
    package_sha256,
    profile,
    workspace,
    sample_index,
    checkout_root,
    raw_root,
    timeout_seconds,
    evidence_label=None,
):
    profile.mkdir(parents=True)
    temp = profile / "temp"
    temp.mkdir()
    environment = os.environ.copy()
    selected_environment = {
        "BLENDER_USER_RESOURCES": str(profile),
        "TEMP": str(temp),
        "TMP": str(temp),
    }
    environment.update(selected_environment)
    command = worker_command(
        blender,
        script,
        case_name=case_name,
        package=package,
        package_sha256=package_sha256,
        profile=profile,
        workspace=workspace,
        sample_index=sample_index,
    )
    started = perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=workspace,
            env=environment,
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
        duration = perf_counter() - started
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout or ""
        stderr = error.stderr or ""
        label = evidence_label or (
            f"{case_name.replace('_', '-')}-{max(sample_index, 0):03d}"
        )
        write_process_evidence(
            raw_root,
            label=label,
            command=command,
            environment=selected_environment,
            returncode=124,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=perf_counter() - started,
        )
        raise RuntimeError(f"Blender worker timed out: {case_name}") from error
    label_index = 0 if sample_index < 0 else sample_index
    label = evidence_label or (
        f"{case_name.replace('_', '-')}-{label_index:03d}"
    )
    record = write_process_evidence(
        raw_root,
        label=label,
        command=command,
        environment=selected_environment,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        duration_seconds=duration,
    )
    if completed.returncode:
        raise RuntimeError(
            f"Blender worker failed ({case_name}, exit {completed.returncode}); "
            f"see {record['stdout_path']} and {record['stderr_path']}"
        )
    document = parse_worker_output(
        completed.stdout,
        expected_case=case_name,
        expected_sample_index=sample_index,
        expected_package_sha256=package_sha256,
        profile=profile,
        checkout_root=checkout_root,
    )
    return document, record


def _fixture_manifest(workspace):
    from ChemBlender.benchmarks.datasets import (
        BENCHMARK_SCALES,
        generate_grid_npy,
        generate_sdf_fixture,
        generate_structure_xyz,
        generate_trajectory_npy,
    )

    scale = BENCHMARK_SCALES["interactive"]
    structure = generate_structure_xyz(
        workspace / "structure.xyz", atom_count=scale.structure_atoms
    )
    grid = generate_grid_npy(workspace / "grid.npy", shape=scale.grid_shape)
    trajectory = generate_trajectory_npy(
        workspace / "trajectory.npy",
        frames=scale.trajectory_frames,
        atoms=_TRAJECTORY_ATOMS,
    )
    trajectory.array.close()
    sdf = generate_sdf_fixture(
        workspace / "records.sdf", record_count=scale.sdf_records
    )
    return {
        "grid": {"path": str(grid.path), "sha256": grid.sha256, "shape": list(grid.shape)},
        "sdf": {
            "path": str(sdf.path),
            "record_count": sdf.record_count,
            "sha256": sdf.sha256,
        },
        "structure": {
            "atom_count": structure.record_count,
            "path": str(structure.path),
            "sha256": structure.sha256,
        },
        "trajectory": {
            "path": str(trajectory.path),
            "sha256": trajectory.sha256,
            "shape": list(trajectory.shape),
        },
    }


def _markdown_report(report, budget, comparison, *, package, package_sha256):
    lines = [
        "# ChemBlender 2.3.0-rc.1 Product Performance Reference",
        "",
        f"- Source commit: `{report['source_commit']}`",
        "- Source dirty: `false`",
        f"- Package: `{Path(package).name}`",
        f"- Package SHA-256: `{package_sha256}`",
        f"- Blender: `{report['environment']['blender_version']}`",
        f"- Python: `{report['environment']['python_version']}`",
        f"- RDKit: `{report['environment']['rdkit_version']}`",
        f"- Gemmi: `{report['environment']['gemmi_version']}`",
        f"- Samples per case: `{report['sample_count']}`",
        f"- Budget comparison: `{'Passed' if comparison['passed'] else 'Failed'}`",
        "",
        "| Case | Boundary | Cache | Measurement | Median (s) | p95 (s) | Limit (s) | Result |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for case in report["cases"]:
        limit = budget["cases"][case["name"]]["hard_limit_seconds"]
        result = "Passed" if case["p95_seconds"] <= limit else "Failed"
        lines.append(
            f"| `{case['name']}` | {case['boundary']} | `{case['cache_state']}` | "
            f"`{case['measurement']}` | {case['median_seconds']:.6f} | "
            f"{case['p95_seconds']:.6f} | {limit:.6f} | {result} |"
        )
    lines.extend(
        [
            "",
            "Each sample used an isolated `BLENDER_USER_RESOURCES`; one "
            "process installed and byte-compiled the exact ZIP, then exited "
            "before a separate cold measurement process. The "
            "trajectory case primed the selected frame through the real "
            "`TrajectoryFrameManager` before timing the Blender mesh update.",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def run_product_qualification(args):
    checkout_root = args.checkout_root.resolve(strict=True)
    source_commit, source_dirty = _git_source_state(checkout_root)
    if source_dirty:
        raise RuntimeError("product qualification must start from a clean worktree")
    package = args.package.resolve(strict=True)
    if not package.is_file() or package.name != "chemblender-2.3.0-rc.1.zip":
        raise ValueError("package must be the exact 2.3.0-rc.1 ZIP")
    package_sha256 = _sha256(package)
    if package_sha256 != args.package_sha256:
        raise ValueError("package SHA-256 does not match --package-sha256")
    blender = args.blender.resolve(strict=True)
    if not blender.is_file():
        raise ValueError("--blender must be an executable file")
    evidence_root = args.evidence_dir.resolve()
    if evidence_root.exists() and any(evidence_root.iterdir()):
        raise ValueError("evidence directory must be absent or empty")
    evidence_root.mkdir(parents=True, exist_ok=True)
    workspace = evidence_root / "inputs"
    raw_root = evidence_root / "raw"
    profiles_root = args.profile_root.resolve()
    if profiles_root.exists() and any(profiles_root.iterdir()):
        raise ValueError("profile root must be absent or empty")
    profiles_root.mkdir(parents=True, exist_ok=True)
    workspace.mkdir()
    raw_root.mkdir()
    script = Path(__file__).resolve()
    fixture_manifest = _fixture_manifest(workspace)
    command_records = []

    preparation_profile = sample_profile(
        profiles_root, "prepare_browser", 0
    )
    prepared, record = _run_worker_process(
        blender=blender,
        script=script,
        case_name="prepare_profile",
        package=package,
        package_sha256=package_sha256,
        profile=preparation_profile,
        workspace=workspace,
        sample_index=0,
        checkout_root=checkout_root,
        raw_root=raw_root,
        timeout_seconds=600,
        evidence_label="prepare-browser-profile-000",
    )
    command_records.append(record)
    preparation, record = _run_worker_process(
        blender=blender,
        script=script,
        case_name="prepare_browser",
        package=package,
        package_sha256=package_sha256,
        profile=preparation_profile,
        workspace=workspace,
        sample_index=-1,
        checkout_root=checkout_root,
        raw_root=raw_root,
        timeout_seconds=1_200,
        evidence_label="prepare-browser-project-000",
    )
    command_records.append(record)
    if not (workspace / "browser.cbq").is_dir():
        raise RuntimeError("browser preparation did not create a sidecar")
    if _runtime_identity(prepared) != _runtime_identity(preparation):
        raise RuntimeError("browser profile preparation runtime identity changed")
    shutil.rmtree(preparation_profile)

    samples = {name: [] for name in PRODUCT_CASES}
    runtime = None
    for case_name in PRODUCT_CASES:
        for sample_index in range(args.samples):
            profile = sample_profile(
                profiles_root, case_name, sample_index
            )
            prepared, record = _run_worker_process(
                blender=blender,
                script=script,
                case_name="prepare_profile",
                package=package,
                package_sha256=package_sha256,
                profile=profile,
                workspace=workspace,
                sample_index=sample_index,
                checkout_root=checkout_root,
                raw_root=raw_root,
                timeout_seconds=600,
                evidence_label=(
                    f"prepare-{case_name.replace('_', '-')}-{sample_index:03d}"
                ),
            )
            command_records.append(record)
            document, record = _run_worker_process(
                blender=blender,
                script=script,
                case_name=case_name,
                package=package,
                package_sha256=package_sha256,
                profile=profile,
                workspace=workspace,
                sample_index=sample_index,
                checkout_root=checkout_root,
                raw_root=raw_root,
                timeout_seconds=600,
            )
            command_records.append(record)
            identity = _runtime_identity(document)
            if runtime is None:
                runtime = identity
            elif identity != runtime:
                raise RuntimeError("Blender worker runtime identity changed")
            if _runtime_identity(prepared) != identity:
                raise RuntimeError("profile preparation runtime identity changed")
            samples[case_name].append(document["elapsed_seconds"])
            shutil.rmtree(profile)
    if _runtime_identity(preparation) != runtime:
        raise RuntimeError("browser preparation runtime identity changed")

    report = build_report(
        samples,
        runtime=runtime,
        source_commit=source_commit,
        source_dirty=False,
    )
    base = _base_harness()
    budget = base.load_performance_budget(args.budget)
    comparison = base.compare_performance_report(report, budget)
    evidence_manifest = {
        "commands": command_records,
        "fixture_manifest": fixture_manifest,
        "package": str(package),
        "package_sha256": package_sha256,
        "passed": comparison["passed"],
        "performance_comparison": comparison,
        "source_commit": source_commit,
        "source_dirty": False,
    }
    _write_bytes(
        evidence_root / "evidence-manifest.json",
        _canonical_bytes(evidence_manifest),
    )
    _write_bytes(args.output, _canonical_bytes(report))
    _write_bytes(
        args.markdown_output,
        _markdown_report(
            report,
            budget,
            comparison,
            package=package,
            package_sha256=package_sha256,
        ),
    )
    if not comparison["passed"]:
        raise RuntimeError(f"product performance budget failed: {comparison}")
    return report


def _product_module(suffix):
    return importlib.import_module(f"{_MODULE_KEY}.{suffix}")


def _install_product(bpy, package, *, enable):
    result = bpy.ops.extensions.package_install_files(
        filepath=str(package),
        repo="user_default",
        enable_on_install=enable,
        overwrite=True,
    )
    if result != {"FINISHED"}:
        raise RuntimeError(f"extension package install failed: {result}")


def _installed_origin():
    module = importlib.import_module(_MODULE_KEY)
    origin = Path(module.__file__).resolve(strict=True)
    profile = Path(os.environ["BLENDER_USER_RESOURCES"]).resolve(strict=True)
    if not _is_relative_to(origin, profile):
        raise RuntimeError("product import did not originate in the isolated profile")
    return origin


def _prepare_product_profile(bpy, package, package_sha256):
    started = perf_counter()
    _install_product(bpy, package, enable=False)
    enabled = bpy.ops.preferences.addon_enable(module=_MODULE_KEY)
    origin = _installed_origin()
    elapsed = perf_counter() - started
    if enabled != {"FINISHED"}:
        raise RuntimeError("prepared profile enable did not finish")
    write_prepared_profile_marker(
        os.environ["BLENDER_USER_RESOURCES"],
        package_sha256=package_sha256,
        installed_origin=origin,
    )
    return elapsed, {
        "bytecode_prepared": True,
        "preparation_process_exits_before_cold_launch": True,
        "product_boundary": True,
    }


def _measure_extension_enable(bpy, _workspace, _sample_index):
    started = perf_counter()
    result = bpy.ops.preferences.addon_enable(module=_MODULE_KEY)
    elapsed = perf_counter() - started
    if result != {"FINISHED"} or _MODULE_KEY not in {
        addon.module for addon in bpy.context.preferences.addons
    }:
        raise RuntimeError("extension enable did not finish")
    return elapsed, {"enabled": True, "product_boundary": True}


def _measure_preflight(_bpy, workspace, _sample_index):
    core = _product_module("core")
    request_model = _product_module("core.import_pipeline.request")
    bridge = _product_module("reader_api.import_pipeline_bridge")
    registry_module = _product_module("reader_api.registry")
    properties = _product_module("ui.properties")
    preview_ui = _product_module("ui.import_preview")
    session_root = workspace / f"preflight-session-{uuid4().hex}"
    session_root.mkdir()
    session = core.create_session(temp_parent=session_root)
    staging = properties.create_quick_import_staging(session)
    registry = registry_module.builtin_reader_plugin_registry()
    request = request_model.ImportRequest(
        sources=(request_model.ImportSource(workspace / "structure.xyz"),)
    )
    try:
        started = perf_counter()
        preview = bridge.preflight_reader_plugins(
            request,
            registry,
            staging,
            progress=lambda *_args: None,
            is_cancelled=lambda: False,
        )
        properties.store_quick_import_preview(session, staging, preview)
        rows = preview_ui.project_import_preview(
            session,
            properties.get_quick_import_state(session),
            registry,
        )
        elapsed = perf_counter() - started
        if (
            len(preview.staged_batch_ids) != 1
            or len(rows) != 1
            or rows[0].reader_id != "xyz"
        ):
            raise RuntimeError("preflight product projection is incomplete")
        batch = staging.result(preview.staged_batch_ids[0])
        if len(batch.structures[0].atomic_numbers) != 50_000:
            raise RuntimeError("preflight did not retain the 50k structure")
        return elapsed, {
            "fifty_thousand_atoms": True,
            "product_boundary": True,
            "staged_preview": True,
        }
    finally:
        try:
            properties.clear_quick_import_state(session)
        finally:
            core.close_session(session)
            shutil.rmtree(session_root, ignore_errors=True)


def _measure_default_view(bpy, workspace, _sample_index):
    core = _product_module("core")
    default_views = _product_module("ui.default_views")
    scene_view = _product_module("scene_preset_view")
    batch = core.parse_xyz(workspace / "structure.xyz")
    project = core.QCProject(uuid4(), "1.0")
    project.commit(batch)
    revision, = batch.source_revisions
    started = perf_counter()
    default = default_views.plan_default_view(
        revision, project.structures, project.datasets
    )
    if default is None:
        raise RuntimeError("automatic default view planner returned no plan")
    preset = core.builtin_scene_presets()[default.preset_id]
    plan = core.plan_scene_preset(
        preset,
        project,
        dict(default.bindings),
        dict(default.settings),
    )
    created = scene_view.apply_scene_preset(plan, project)
    bpy.context.view_layer.update()
    elapsed = perf_counter() - started
    try:
        if (
            len(created) != 1
            or created[0].type != "MESH"
            or len(created[0].data.vertices) != 50_000
        ):
            raise RuntimeError("default Structure view is incomplete")
        return elapsed, {
            "fifty_thousand_atoms": True,
            "product_boundary": True,
            "structure_scene_preset": True,
        }
    finally:
        for obj in tuple(created):
            if obj.name in bpy.data.objects:
                scene_view._remove_objects((obj,))


def _measure_vdb_cache(bpy, workspace, _sample_index):
    import numpy

    core = _product_module("core")
    grid_volume = _product_module("grid_volume")
    values = numpy.load(workspace / "grid.npy", mmap_mode="r", allow_pickle=False)
    grid = core.Grid3D(
        id=uuid4(),
        revision="product-performance-grid-r1",
        semantic_role="electron_density",
        domain="grid",
        data=core.ArrayData(values, ("x", "y", "z"), "dimensionless"),
        status=core.DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(),
        origin=(0.0, 0.0, 0.0),
        step_vectors=((0.1, 0.0, 0.0), (0.0, 0.1, 0.0), (0.0, 0.0, 0.1)),
        coordinate_unit="angstrom",
    )
    cache = workspace / f"vdb-{uuid4().hex}"
    cache.mkdir()
    obj = None
    try:
        started = perf_counter()
        obj = grid_volume.create_grid_volume(grid, cache)
        bpy.context.view_layer.update()
        elapsed = perf_counter() - started
        cache_path = Path(obj["cb_cache_path"])
        if (
            obj.type != "VOLUME"
            or not cache_path.is_file()
            or obj.data.grids["density"] is None
            or grid.grid_shape != (128, 128, 128)
        ):
            raise RuntimeError("OpenVDB product cache is incomplete")
        return elapsed, {
            "grid_128_cubed": True,
            "openvdb_loaded": True,
            "product_boundary": True,
        }
    finally:
        if obj is not None and obj.name in bpy.data.objects:
            volume = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if volume.users == 0:
                bpy.data.volumes.remove(volume)
        mmap = getattr(values, "_mmap", None)
        if mmap is not None:
            mmap.close()
        shutil.rmtree(cache, ignore_errors=True)


def _measure_trajectory(bpy, workspace, sample_index):
    import numpy

    core = _product_module("core")
    trajectory_view = _product_module("trajectory_view")
    values = numpy.load(
        workspace / "trajectory.npy", mmap_mode="r", allow_pickle=False
    )
    structure_id = uuid4()
    frames = core.FrameSet(
        id=uuid4(),
        revision="product-performance-trajectory-r1",
        semantic_role="coordinates",
        domain="frame",
        data=core.ArrayData(
            values, ("frame", "atom", "xyz"), "angstrom"
        ),
        status=core.DatasetStatus.COMPLETE,
        source_calculation=None,
        provenance_ids=(),
        structure_id=structure_id,
        comments=("",) * values.shape[0],
    )
    mesh = bpy.data.meshes.new("Product Performance Trajectory")
    mesh.from_pydata(numpy.asarray(values[0]).tolist(), [], [])
    obj = bpy.data.objects.new(mesh.name, mesh)
    bpy.context.collection.objects.link(obj)
    obj["cb_structure_id"] = str(structure_id)
    target = sample_index + 2
    try:
        trajectory_view.configure_trajectory_view(
            obj, frames, cache_size=8, prefetch_ahead=0
        )
        binding = trajectory_view._BINDINGS[obj.as_pointer()]
        binding.manager.frame(target)
        hits_before = binding.manager.cache_info().hits
        started = perf_counter()
        bpy.context.scene.frame_set(target + 1)
        bpy.context.view_layer.update()
        elapsed = perf_counter() - started
        hits_after = binding.manager.cache_info().hits
        if (
            obj["cb_trajectory_frame_index"] != target
            or hits_after <= hits_before
            or len(obj.data.vertices) != _TRAJECTORY_ATOMS
        ):
            raise RuntimeError("cached trajectory product update is incomplete")
        return elapsed, {
            "blender_mesh_update": True,
            "cached_manager_hit": True,
            "product_boundary": True,
            "trajectory_1000_by_1000": True,
        }
    finally:
        if obj.name in bpy.data.objects:
            trajectory_view.clear_trajectory_view(obj)
            bpy.data.objects.remove(obj, do_unlink=True)
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
        mmap = getattr(values, "_mmap", None)
        if mmap is not None and not mmap.closed:
            mmap.close()


def _prepare_browser_project(_bpy, workspace, _sample_index):
    core = _product_module("core")
    destination = workspace / "browser.cbq"
    started = perf_counter()
    batch = core.parse_sdf(workspace / "records.sdf")
    project = core.QCProject(uuid4(), "1.0")
    project.commit(batch)
    core.save_project(destination, project)
    elapsed = perf_counter() - started
    if len(project.molecular_records) != 10_000 or not destination.is_dir():
        raise RuntimeError("10k SDF browser preparation is incomplete")
    return elapsed, {
        "product_boundary": True,
        "sidecar_written": True,
        "ten_thousand_sdf_records": True,
    }


def _measure_browser(_bpy, workspace, _sample_index):
    core = _product_module("core")
    browser = _product_module("ui.project_browser.model")
    project = core.open_project(workspace / "browser.cbq")
    try:
        browser.clear_browser_caches()
        started = perf_counter()
        rows = browser.build_browser_rows(
            project,
            session_id=uuid4(),
            browser_revision=0,
            search="benchmark-42",
            page_size=1_000,
        )
        elapsed = perf_counter() - started
        if (
            len(project.molecular_records) != 10_000
            or not any(row.kind == "molecular_record" for row in rows)
        ):
            raise RuntimeError("10k browser product filter is incomplete")
        return elapsed, {
            "cold_projection_cache": True,
            "product_boundary": True,
            "ten_thousand_sdf_records": True,
        }
    finally:
        core.close_project(project)


_WORKER_CASES = {
    "extension_enable": _measure_extension_enable,
    "preflight_feedback": _measure_preflight,
    "default_view": _measure_default_view,
    "vdb_cache": _measure_vdb_cache,
    "trajectory_frame": _measure_trajectory,
    "browser_projection_filter": _measure_browser,
    "prepare_browser": _prepare_browser_project,
    "prepare_profile": None,
}


def worker_main(argv):
    import bpy

    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=tuple(_WORKER_CASES), required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--package-sha256", required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--sample-index", type=int, required=True)
    args = parser.parse_args(argv)
    package = args.package.resolve(strict=True)
    workspace = args.workspace.resolve(strict=True)
    profile = args.profile.resolve(strict=True)
    if Path(os.environ["BLENDER_USER_RESOURCES"]).resolve(strict=True) != profile:
        raise RuntimeError("worker profile does not match BLENDER_USER_RESOURCES")
    actual_hash = _sha256(package)
    if actual_hash != args.package_sha256:
        raise RuntimeError("worker package hash mismatch")
    if args.case == "prepare_profile":
        elapsed, assertions = _prepare_product_profile(
            bpy, package, actual_hash
        )
    else:
        verify_prepared_profile(profile, package_sha256=actual_hash)
        if args.case != "extension_enable":
            enabled = bpy.ops.preferences.addon_enable(module=_MODULE_KEY)
            if enabled != {"FINISHED"}:
                raise RuntimeError("prepared product enable did not finish")
    if args.case == "extension_enable":
        elapsed, assertions = _WORKER_CASES[args.case](
            bpy, workspace, args.sample_index
        )
    elif args.case != "prepare_profile":
        _installed_origin()
        elapsed, assertions = _WORKER_CASES[args.case](
            bpy, workspace, args.sample_index
        )
    origin = _installed_origin()
    import gemmi
    from rdkit import rdBase

    document = {
        "assertions": {"installed_package": True, **assertions},
        "blender_version": bpy.app.version_string,
        "case": args.case,
        "elapsed_seconds": elapsed,
        "gemmi_version": gemmi.__version__,
        "installed_origin": str(origin),
        "package_sha256": actual_hash,
        "python_executable": sys.executable,
        "python_implementation": platform.python_implementation(),
        "python_version": platform.python_version(),
        "rdkit_version": rdBase.rdkitVersion,
        "sample_index": args.sample_index,
    }
    print(WORKER_MARKER + _canonical_bytes(document).decode("utf-8").strip())
    return 0


def main(argv=None):
    if argv is None and "--" in sys.argv:
        argv = sys.argv[sys.argv.index("--") + 1 :]
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "worker":
        return worker_main(argv[1:])
    parser = argparse.ArgumentParser(
        description="Run exact-ZIP ChemBlender 2.3.0 product performance qualification"
    )
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--package-sha256", required=True)
    parser.add_argument("--checkout-root", type=Path, required=True)
    parser.add_argument("--budget", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument(
        "--profile-root",
        type=Path,
        required=True,
        help="Short, empty root for disposable isolated Blender profiles",
    )
    parser.add_argument("--samples", type=int, default=5)
    args = parser.parse_args(argv)
    if args.samples < _MINIMUM_SAMPLES:
        parser.error("--samples must be at least 5")
    if not re.fullmatch(r"[0-9a-f]{64}", args.package_sha256):
        parser.error("--package-sha256 must be lowercase SHA-256 hex")
    run_product_qualification(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
