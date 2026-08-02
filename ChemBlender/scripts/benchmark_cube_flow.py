#!/usr/bin/env python3
"""Benchmark the generated 128³ Cube-to-Blender product path."""

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
from uuid import uuid4


if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy

from ChemBlender.core import Grid3D, QCProject, export_cube, save_project
from ChemBlender.core.cube import CUBE_READER


def generate_cube(path, *, size):
    path = Path(path)
    voxel_count = size**3
    with path.open("w", encoding="ascii", newline="\n") as stream:
        stream.write(f"ChemBlender {size}-cubed benchmark\n")
        stream.write("Generated scalar field\n")
        stream.write("1 0.0 0.0 0.0\n")
        stream.write(f"{size} 0.1 0.0 0.0\n")
        stream.write(f"{size} 0.0 0.1 0.0\n")
        stream.write(f"{size} 0.0 0.0 0.1\n")
        stream.write("6 6.0 0.0 0.0 0.0\n")
        for start in range(0, voxel_count, 6):
            stop = min(start + 6, voxel_count)
            stream.write(
                " ".join(
                    f"{((index % 257) - 128) / 128.0:.8e}"
                    for index in range(start, stop)
                )
                + "\n"
            )
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


def _grid(batch):
    return next(value for value in batch.datasets if isinstance(value, Grid3D))


def _actual_blender_operations(grid, cache_root):
    import bpy

    from ChemBlender.grid_volume import (
        create_grid_volume,
        ensure_grid_volume_cache,
        volume_cache_path,
    )

    cache_root.mkdir(parents=True, exist_ok=True)
    path = volume_cache_path(cache_root, grid)

    def cache_vdb_cold(_index):
        path.unlink(missing_ok=True)
        ensure_grid_volume_cache(grid, cache_root)

    def cache_vdb_hot(_index):
        ensure_grid_volume_cache(grid, cache_root)

    def view_hot(index):
        obj = create_grid_volume(
            grid,
            cache_root,
            name=f"Cube benchmark {index}",
            collection=bpy.context.scene.collection,
        )
        volume = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if volume.users == 0:
            bpy.data.volumes.remove(volume)

    return {
        "cache_vdb_cold": cache_vdb_cold,
        "cache_vdb_hot": cache_vdb_hot,
        "view_hot": view_hot,
    }


def run_benchmark(
    *,
    size=128,
    repeats=3,
    workspace,
    blender_operations=None,
):
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    source = workspace / "generated.cube"
    generate_cube(source, size=size)

    def parse(_index):
        parsed = CUBE_READER.parse(source)
        if _grid(parsed).grid_shape != (size, size, size):
            raise RuntimeError("parsed Cube shape does not match benchmark")

    batch = CUBE_READER.parse(source)
    grid = _grid(batch)
    project = QCProject(uuid4(), "0.2")
    project.commit(batch)
    export_sizes = []

    def export(index):
        destination = workspace / f"export-{index}.cube"
        export_cube(batch, confirm_loss=True, destination=destination)
        export_sizes.append(destination.stat().st_size)
        destination.unlink()

    def stage_npy(index):
        destination = workspace / f"stage-{index}.npy"
        with destination.open("wb") as stream:
            numpy.save(stream, numpy.asarray(grid.data.values), allow_pickle=False)
            stream.flush()
            os.fsync(stream.fileno())
        destination.unlink()

    def sidecar_save(index):
        destination = workspace / f"project-{index}.cbq"
        save_project(destination, project)
        shutil.rmtree(destination)

    actual_blender = blender_operations is None
    if blender_operations is None:
        blender_operations = _actual_blender_operations(
            grid,
            workspace / "view-cache",
        )
    if set(blender_operations) != {
        "cache_vdb_cold",
        "cache_vdb_hot",
        "view_hot",
    }:
        raise ValueError("blender_operations has the wrong stage inventory")

    operations = {
        "parse": parse,
        "export": export,
        "stage_npy": stage_npy,
        "sidecar_save": sidecar_save,
        **blender_operations,
    }
    stages = {
        name: _measure(operation, repeats)
        for name, operation in operations.items()
    }

    tracemalloc.start()
    CUBE_READER.parse(source)
    _current, peak_python_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    peak_export = workspace / "export-peak.cube"
    tracemalloc.start()
    export_cube(batch, confirm_loss=True, destination=peak_export)
    _current, export_peak_python_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    export_bytes = peak_export.stat().st_size
    peak_export.unlink()
    if not export_sizes or any(value != export_bytes for value in export_sizes):
        raise RuntimeError("Cube export size is not deterministic")

    total_stage_names = (
        "parse",
        "export",
        "stage_npy",
        "sidecar_save",
        "cache_vdb_cold",
        "view_hot",
    )
    total_median_seconds = sum(
        stages[name]["median_seconds"] for name in total_stage_names
    )
    budget = {
        "reference_shape_is_128_cubed": size == 128,
        "real_blender_stages": actual_blender,
        "export_p95_lte_10_seconds": stages["export"]["p95_seconds"] <= 10.0,
        "total_median_lte_10_seconds": total_median_seconds <= 10.0,
    }
    report = {
        "benchmark": "chemblender-cube-flow-v1",
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
            "python_version": platform.python_version(),
            "numpy_version": numpy.__version__,
        },
        "workload": {
            "shape": [size, size, size],
            "voxel_count": size**3,
            "repeats": repeats,
        },
        "source_bytes": source.stat().st_size,
        "export_bytes": export_bytes,
        "cache_state": {
            "parse": "warm OS cache after generated input",
            "cache_vdb_cold": "derived VDB removed before each run",
            "cache_vdb_hot": "validated existing VDB",
            "view_hot": "validated existing VDB before Blender datablock creation",
        },
        "stages": stages,
        "total_stage_names": list(total_stage_names),
        "total_median_seconds": total_median_seconds,
        "peak_python_bytes": peak_python_bytes,
        "export_peak_python_bytes": export_peak_python_bytes,
        "budget": budget,
    }
    report["passed"] = all(budget.values())
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Benchmark the ChemBlender 128-cubed Cube workflow"
    )
    parser.add_argument("--size", type=int, default=128)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.size <= 0 or args.repeats <= 0:
        parser.error("--size and --repeats must be positive")
    with TemporaryDirectory(prefix="chemblender-cube-benchmark-") as directory:
        report = run_benchmark(
            size=args.size,
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
    arguments = (
        sys.argv[sys.argv.index("--") + 1 :]
        if "--" in sys.argv
        else None
    )
    raise SystemExit(main(arguments))
