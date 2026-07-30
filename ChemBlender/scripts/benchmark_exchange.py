#!/usr/bin/env python3
"""Reproducible Wave 3 native exchange-format benchmark."""

import argparse
from ctypes import Structure as CStructure, byref, c_ulong, c_ulonglong, sizeof
from math import ceil
import gc
import json
import os
from pathlib import Path
import platform
from statistics import median
import sys
from tempfile import TemporaryDirectory
from time import perf_counter
import tracemalloc


if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy

from ChemBlender.core.cjson_adapter import parse_cjson
from ChemBlender.core.formats.mol2 import parse_mol2
from ChemBlender.core.formats.pdb import parse_pdb
from ChemBlender.core.formats.pqr import parse_pqr
from ChemBlender.core.import_pipeline.request import (
    ImportRequest,
    ImportSource,
    ReaderOverride,
)
from ChemBlender.core.import_pipeline.staging import StagedImportSession
from ChemBlender.reader_api.import_pipeline_bridge import preflight_reader_plugins
from ChemBlender.reader_api.registry import builtin_reader_plugin_registry


class _MemoryStatus(CStructure):
    _fields_ = (
        ("length", c_ulong),
        ("memory_load", c_ulong),
        ("total_physical", c_ulonglong),
        ("available_physical", c_ulonglong),
        ("total_page_file", c_ulonglong),
        ("available_page_file", c_ulonglong),
        ("total_virtual", c_ulonglong),
        ("available_virtual", c_ulonglong),
        ("available_extended_virtual", c_ulonglong),
    )


def _total_memory_bytes():
    if platform.system() != "Windows":
        return None
    from ctypes import windll

    status = _MemoryStatus()
    status.length = sizeof(status)
    return (
        int(status.total_physical)
        if windll.kernel32.GlobalMemoryStatusEx(byref(status))
        else None
    )


def _write(path, writer):
    with Path(path).open("w", encoding="ascii", newline="\n") as stream:
        writer(stream)
        stream.flush()
        os.fsync(stream.fileno())


def _generate_mol2(path, atom_count):
    def write(stream):
        stream.write(
            "@<TRIPOS>MOLECULE\nbenchmark\n"
            f"{atom_count} 0 0 0 0\nSMALL\nNO_CHARGES\n"
            "@<TRIPOS>ATOM\n"
        )
        for index in range(atom_count):
            stream.write(
                f"{index + 1} C{index + 1} "
                f"{index % 1000 * 0.01:.4f} 0.0000 0.0000 C.3\n"
            )

    _write(path, write)


def _generate_pdb(path, atom_count):
    def write(stream):
        for index in range(atom_count):
            serial = index + 1
            residue = index % 9999 + 1
            x = index % 1000 * 0.01
            stream.write(
                f"ATOM  {serial:5d}  C   GLY A{residue:4d}    "
                f"{x:8.3f}{0.0:8.3f}{0.0:8.3f}"
                "  1.00  0.00           C  \n"
            )

    _write(path, write)


def _generate_pqr(path, atom_count):
    def write(stream):
        for index in range(atom_count):
            stream.write(
                f"ATOM {index + 1} C GLY A {index % 9999 + 1} "
                f"{index % 1000 * 0.01:.4f} 0.0000 0.0000 0.0000 1.7000\n"
            )

    _write(path, write)


def _generate_cjson(path, atom_count):
    def write(stream):
        stream.write('{"chemicalJson":1,"atoms":{"elements":{"number":[')
        for index in range(atom_count):
            stream.write(("" if index == 0 else ",") + "6")
        stream.write(']},"coords":{"3d":[')
        for index in range(atom_count):
            stream.write(
                ("" if index == 0 else ",")
                + f"{index % 1000 * 0.01:.4f},0.0,0.0"
            )
        stream.write("]}}}\n")

    _write(path, write)


def _timed(operation):
    started = perf_counter()
    operation()
    return perf_counter() - started


def _peak_bytes(operation):
    gc.collect()
    tracemalloc.start()
    try:
        operation()
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def _measure(operation, *, samples, source, atom_count, path):
    cold = _timed(operation)
    operation()
    elapsed = [_timed(operation) for _index in range(samples)]
    ordered = sorted(elapsed)
    peak = _peak_bytes(operation)
    source_bytes = Path(source).stat().st_size
    return {
        "status": "Passed",
        "sample_count": samples,
        "cold_seconds": cold,
        "median_seconds": median(elapsed),
        "p95_seconds": ordered[max(0, ceil(samples * 0.95) - 1)],
        "peak_bytes": peak,
        "source_bytes": source_bytes,
        "peak_to_source_ratio": peak / source_bytes,
        "atom_count": atom_count,
        "draw_path": False,
        "path": path,
    }


def benchmark_exchange(*, atom_count=50_000, preview_atom_count=20, samples=5):
    for name, value in (
        ("atom_count", atom_count),
        ("preview_atom_count", preview_atom_count),
        ("samples", samples),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{name} must be a positive integer")
    if samples < 5:
        raise ValueError("samples must be at least five")

    with TemporaryDirectory(prefix="chemblender-wave3-exchange-") as directory:
        workspace = Path(directory)
        sources = {
            "mol2": workspace / "benchmark.mol2",
            "pdb": workspace / "benchmark.pdb",
            "pqr": workspace / "benchmark.pqr",
            "cjson": workspace / "benchmark.cjson",
        }
        for name, generator in (
            ("mol2", _generate_mol2),
            ("pdb", _generate_pdb),
            ("pqr", _generate_pqr),
            ("cjson", _generate_cjson),
        ):
            generator(sources[name], atom_count)
        preview_source = workspace / "preview.mol2"
        _generate_mol2(preview_source, preview_atom_count)

        def parser_operation(parser, source, expected):
            def parse():
                batch = parser(source)
                if (
                    len(batch.structures) != 1
                    or len(batch.structures[0].atomic_numbers) != expected
                ):
                    raise RuntimeError("parser produced an unexpected atom count")

            return parse

        metrics = {}
        for name, parser in (
            ("mol2", parse_mol2),
            ("pdb", parse_pdb),
            ("pqr", parse_pqr),
            ("cjson", parse_cjson),
        ):
            metrics[f"{name}_parse"] = _measure(
                parser_operation(parser, sources[name], atom_count),
                samples=samples,
                source=sources[name],
                atom_count=atom_count,
                path=f"native {name.upper()} parser; outside Blender draw",
            )

        registry = builtin_reader_plugin_registry()

        def preview_projection():
            session = StagedImportSession.create(temp_parent=workspace)
            source = ImportSource(preview_source)
            try:
                result = preflight_reader_plugins(
                    ImportRequest(
                        sources=(source,),
                        reader_overrides=(ReaderOverride(source.id, "mol2"),),
                    ),
                    registry,
                    session,
                )
                source_preview, = result.source_previews
                batch_id, = source_preview.staged_batch_ids
                batch = session.result(batch_id)
                summary = (
                    len(result.source_previews),
                    source_preview.selected_reader_id,
                    len(batch.structures[0].atomic_numbers),
                )
                if summary != (1, "mol2", preview_atom_count):
                    raise RuntimeError("preview projection did not match workload")
            finally:
                session.discard()
            if session.root.exists():
                raise RuntimeError("preview projection left staging data behind")

        preview_metric = _measure(
            preview_projection,
            samples=samples,
            source=preview_source,
            atom_count=preview_atom_count,
            path=(
                "Reader API preflight, staged ImportBatch and bpy-free "
                "selected-reader summary"
            ),
        )
        preview_metric["blender_rna_projection"] = "Not Run"
        metrics["preview_projection"] = preview_metric

    memory_bounded = all(
        metric["peak_bytes"]
        <= max(64 * 1024 * 1024, metric["source_bytes"] * 32)
        for metric in metrics.values()
    )
    qualification = {
        "quick_feedback_within_0_5_seconds": (
            metrics["preview_projection"]["median_seconds"] <= 0.5
        ),
        "peak_python_memory_bounded": memory_bounded,
        "over_one_second_work_outside_draw_path": all(
            metric["median_seconds"] <= 1.0 or not metric["draw_path"]
            for metric in metrics.values()
        ),
    }
    return {
        "benchmark": "chemblender-wave3-exchange-v1",
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
            "total_memory_bytes": _total_memory_bytes(),
            "python_executable": sys.executable,
            "python_version": platform.python_version(),
            "numpy_version": numpy.__version__,
        },
        "warmup_count": 1,
        "workload": {
            "reference_atom_count": atom_count,
            "preview_atom_count": preview_atom_count,
        },
        "metrics": metrics,
        "qualification": qualification,
        "passed": all(qualification.values()),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Benchmark ChemBlender Wave 3 exchange formats"
    )
    parser.add_argument("--atoms", type=int, default=50_000)
    parser.add_argument("--preview-atoms", type=int, default=20)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.atoms <= 0 or args.preview_atoms <= 0 or args.samples < 5:
        parser.error("--atoms/--preview-atoms must be positive and --samples >= 5")
    report = benchmark_exchange(
        atom_count=args.atoms,
        preview_atom_count=args.preview_atoms,
        samples=args.samples,
    )
    encoded = json.dumps(
        report,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ) + "\n"
    if args.output is None:
        sys.stdout.buffer.write(encoded.encode("utf-8"))
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8", newline="\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
