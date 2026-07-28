#!/usr/bin/env python3
"""Reproducible extXYZ streaming and persistence benchmark."""

import argparse
from math import ceil
import json
import os
from pathlib import Path
import platform
import shutil
import sys
from tempfile import TemporaryDirectory
from time import perf_counter
import tracemalloc
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5


if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy

from ChemBlender.core import (
    QCProject,
    close_session,
    create_session,
    save_project,
)
from ChemBlender.core.exporters import export_extxyz
from ChemBlender.core.formats.extxyz import (
    ExtXYZCancelled,
    iter_extxyz_frames,
    parse_extxyz,
)
from ChemBlender.core.import_pipeline.request import (
    ImportRequest,
    ImportSource,
    ValidationMode,
)
from ChemBlender.core.import_pipeline.staging import StagedImportSession
from ChemBlender.core.import_pipeline.transaction import (
    ImportCommitDecisions,
    commit_import_preview,
)
from ChemBlender.reader_api.import_pipeline_bridge import (
    preflight_reader_plugins,
)
from ChemBlender.reader_api.registry import builtin_reader_plugin_registry
from ChemBlender.ui.extxyz_preview import extxyz_preview_summary


def generate_extxyz(path, *, frames, atoms, metadata_only=False):
    path = Path(path)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for frame in range(frames):
            stream.write(f"{atoms}\n")
            properties = (
                "species:S:1:pos:R:3"
                if metadata_only
                else "species:S:1:pos:R:3:force:R:3"
            )
            stream.write(
                'Lattice="20 0 0 0 20 0 0 0 20" '
                f"Properties={properties} pbc=\"T T T\" "
                f"step={frame} temperature={300 + frame % 7}\n"
            )
            for atom in range(atoms):
                x = (atom % 100) * 0.1 + frame * 0.0001
                y = ((atom // 100) % 100) * 0.1
                z = (atom // 10_000) * 0.1
                suffix = (
                    ""
                    if metadata_only
                    else f" {atom % 5 - 2} {(atom + 1) % 5 - 2} 0"
                )
                stream.write(f"C {x:.8f} {y:.8f} {z:.8f}{suffix}\n")
        stream.flush()
        os.fsync(stream.fileno())


def _summary(samples):
    samples = sorted(samples)
    return {
        "sample_count": len(samples),
        "median_seconds": samples[len(samples) // 2],
        "p95_seconds": samples[max(0, ceil(len(samples) * 0.95) - 1)],
        "samples_seconds": samples,
    }


def _measure(operation, repeats):
    samples = []
    for index in range(repeats):
        started = perf_counter()
        operation(index)
        samples.append(perf_counter() - started)
    return _summary(samples)


def _close_array(value):
    mmap = getattr(value, "_mmap", None)
    if mmap is not None:
        mmap.close()


def _close_batch_arrays(batch):
    for dataset in batch.datasets:
        data = dataset.data
        _close_array(getattr(data, "values", None))
        _close_array(getattr(getattr(data, "codes", None), "values", None))
        _close_array(
            getattr(getattr(dataset, "validity_mask", None), "values", None)
        )


def _parsed(source, staging_root):
    batch = parse_extxyz(source, staging_root=staging_root)
    frame_set = next(
        dataset
        for dataset in batch.datasets
        if dataset.semantic_role == "coordinates"
    )
    return batch, frame_set


def _cleanup_parse(batch, root):
    _close_batch_arrays(batch)
    shutil.rmtree(root, ignore_errors=True)


def _cancellation_cleanup(source, root):
    staging = root / "cancel-staging"
    checks = 0

    def cancelled():
        nonlocal checks
        checks += 1
        return checks > 1

    try:
        parse_extxyz(
            source,
            staging_root=staging,
            is_cancelled=cancelled,
        )
    except ExtXYZCancelled:
        return staging.is_dir() and not tuple(staging.iterdir())
    return False


def _publication_rollback(source, root):
    project_session = create_session(temp_parent=root)
    staged = StagedImportSession.create(temp_parent=root)
    try:
        preview = preflight_reader_plugins(
            ImportRequest(
                sources=(ImportSource(source),),
                validation_mode=ValidationMode.BALANCED,
            ),
            builtin_reader_plugin_registry(),
            staged,
        )
        previous = project_session.project
        from ChemBlender.core.import_pipeline import transaction

        with patch.object(
            transaction,
            "solidify_session",
            side_effect=OSError("benchmark publication failure"),
        ):
            try:
                commit_import_preview(
                    project_session,
                    staged,
                    preview,
                    ImportCommitDecisions(),
                )
            except OSError:
                return (
                    project_session.project is previous
                    and project_session.sidecar_path is None
                    and staged.root.exists()
                )
        return False
    finally:
        staged.discard()
        close_session(project_session)


def run_benchmark(
    *,
    frames=1_000,
    atoms=1_000,
    metadata_frames=10_000,
    repeats=3,
    workspace,
):
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    source = workspace / "trajectory.extxyz"
    metadata_source = workspace / "metadata-only.extxyz"
    generate_extxyz(source, frames=frames, atoms=atoms)
    generate_extxyz(
        metadata_source,
        frames=metadata_frames,
        atoms=1,
        metadata_only=True,
    )

    def first_frame_decode(_index):
        iterator = iter_extxyz_frames(source)
        try:
            next(iterator)
        finally:
            iterator.close()

    registry = builtin_reader_plugin_registry()

    def preview_ready(_index):
        staged = StagedImportSession.create(temp_parent=workspace)
        try:
            preview = preflight_reader_plugins(
                ImportRequest(
                    sources=(ImportSource(source),),
                    validation_mode=ValidationMode.BALANCED,
                ),
                registry,
                staged,
            )
            staged_source, = preview.source_previews
            batch_id, = staged_source.staged_batch_ids
            summary = extxyz_preview_summary(staged.result(batch_id))
            if summary.frame_count != frames:
                raise RuntimeError("preview frame count does not match workload")
        finally:
            staged.discard()

    parse_counter = 0

    def parse_once(_index, parse_source=source):
        nonlocal parse_counter
        parse_counter += 1
        root = workspace / f"parse-{parse_counter}"
        batch = parse_extxyz(parse_source, staging_root=root)
        _cleanup_parse(batch, root)

    measurements = {
        "first_frame_decode": _measure(first_frame_decode, repeats),
        "preview_ready": _measure(preview_ready, repeats),
        "parse": _measure(parse_once, repeats),
    }
    metadata_parse = _measure(
        lambda index: parse_once(index, metadata_source),
        repeats,
    )

    active_root = workspace / "active-staging"
    batch, frame_set = _parsed(source, active_root)
    properties = tuple(
        dataset for dataset in batch.datasets if dataset is not frame_set
    )
    structure, = batch.structures
    project = QCProject(
        uuid5(NAMESPACE_URL, f"chemblender:extxyz-benchmark:{frames}:{atoms}"),
        "0.2",
    )
    project.commit(batch)

    def sidecar_write(index):
        destination = workspace / f"sidecar-{index}.cbq"
        save_project(destination, project)
        shutil.rmtree(destination)

    def frame_access(index):
        values = numpy.asarray(
            frame_set.data.values[index % frame_set.data.shape[0]]
        )
        if not numpy.isfinite(values).all():
            raise RuntimeError("benchmark frame contains non-finite values")

    def export(index):
        destination = workspace / f"export-{index}.extxyz"
        report = export_extxyz(
            destination,
            structure,
            frame_set=frame_set,
            properties=properties,
            confirm_loss=True,
        )
        if not report.written:
            raise RuntimeError("benchmark export was not written")
        destination.unlink()

    measurements["sidecar_write"] = _measure(sidecar_write, repeats)
    measurements["single_frame_access"] = _measure(frame_access, repeats)
    measurements["export"] = _measure(export, repeats)
    streaming_arrays = all(
        not isinstance(getattr(dataset.data, "values", None), tuple)
        for dataset in batch.datasets
    )

    peak_root = workspace / "peak-staging"
    tracemalloc.start()
    peak_batch = parse_extxyz(source, staging_root=peak_root)
    _current, peak_python_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    _cleanup_parse(peak_batch, peak_root)

    resilience = {
        "cancellation_cleanup": _cancellation_cleanup(source, workspace),
        "publication_rollback": _publication_rollback(source, workspace),
    }
    raw_bytes = frames * atoms * 6 * 8
    budget = {
        "reference_scale_met": frames >= 1_000 and atoms >= 1_000,
        "metadata_scale_met": metadata_frames > frames,
        "preview_ready_lte_0_5_seconds": (
            measurements["preview_ready"]["median_seconds"] <= 0.5
        ),
        "frame_access_p95_lte_0_1_seconds": (
            measurements["single_frame_access"]["p95_seconds"] <= 0.1
        ),
        "peak_python_memory_bounded": (
            peak_python_bytes <= max(64 * 1024 * 1024, raw_bytes * 2)
        ),
    }
    result = {
        "benchmark": "chemblender-extxyz-v1",
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
            "python_version": platform.python_version(),
            "numpy_version": numpy.__version__,
        },
        "cache_state": "warm OS cache (inputs generated immediately before measurement)",
        "workloads": {
            "trajectory": {"frames": frames, "atoms": atoms},
            "metadata_only": {"frames": metadata_frames, "atoms": 1},
        },
        "measurements": measurements,
        "metadata_only_parse": metadata_parse,
        "peak_python_bytes": peak_python_bytes,
        "streaming_arrays": streaming_arrays,
        "resilience": resilience,
        "budget": budget,
    }
    result["passed"] = (
        all(resilience.values())
        and streaming_arrays
        and all(budget.values())
    )
    _cleanup_parse(batch, active_root)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Benchmark ChemBlender extXYZ streaming workflow"
    )
    parser.add_argument("--frames", type=int, default=1_000)
    parser.add_argument("--atoms", type=int, default=1_000)
    parser.add_argument("--metadata-frames", type=int, default=10_000)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if min(args.frames, args.atoms, args.metadata_frames, args.repeats) <= 0:
        parser.error("benchmark sizes and repeats must be positive")
    with TemporaryDirectory(prefix="chemblender-extxyz-benchmark-") as directory:
        report = run_benchmark(
            frames=args.frames,
            atoms=args.atoms,
            metadata_frames=args.metadata_frames,
            repeats=args.repeats,
            workspace=Path(directory),
        )
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(encoded, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
