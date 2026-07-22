#!/usr/bin/env python3
import argparse
import json
import os
import platform
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter


CASES = (
    ("trajectory", (500, 2000, 3), "float32", (250, slice(None), slice(None))),
    ("grid3d", (160, 160, 160), "float32", (slice(None), slice(None), 80)),
    ("mo_coefficients", (1200, 1200), "float64", (600, slice(None))),
    (
        "projections",
        (2, 64, 96, 16, 9),
        "float32",
        (0, 32, slice(None), slice(None), slice(None)),
    ),
)


def _array(shape, dtype):
    import numpy

    size = int(numpy.prod(shape))
    return (numpy.arange(size, dtype=dtype) % 97).reshape(shape)


def _benchmark_case(directory, name, shape, dtype, selection):
    import numpy

    values = _array(shape, dtype)
    raw_bytes = values.nbytes
    expected = float(values.sum(dtype=numpy.float64))
    expected_slice = float(values[selection].sum(dtype=numpy.float64))
    path = directory / f"{name}.npy"

    started = perf_counter()
    with path.open("wb") as stream:
        numpy.save(stream, values, allow_pickle=False)
        stream.flush()
        os.fsync(stream.fileno())
    write_seconds = perf_counter() - started

    mapped = numpy.load(path, mmap_mode="r", allow_pickle=False)
    started = perf_counter()
    actual = float(mapped.sum(dtype=numpy.float64))
    sequential_seconds = perf_counter() - started

    slice_runs = []
    actual_slice = None
    for _ in range(7):
        started = perf_counter()
        actual_slice = float(mapped[selection].sum(dtype=numpy.float64))
        slice_runs.append(perf_counter() - started)
    slice_seconds = min(slice_runs)
    file_bytes = path.stat().st_size
    memory_map = getattr(mapped, "_mmap", None)
    del mapped
    if memory_map is not None:
        memory_map.close()

    checksum_ok = numpy.isclose(actual, expected) and numpy.isclose(
        actual_slice, expected_slice
    )
    overhead_ratio = (file_bytes - raw_bytes) / raw_bytes
    gates = {
        "checksum": bool(checksum_ok),
        "overhead_lte_1_percent": overhead_ratio <= 0.01,
        "write_lte_5_seconds": write_seconds <= 5.0,
        "sequential_lte_2_seconds": sequential_seconds <= 2.0,
        "slice_lte_0_1_seconds": slice_seconds <= 0.1,
    }
    return {
        "name": name,
        "shape": list(shape),
        "dtype": dtype,
        "raw_bytes": raw_bytes,
        "file_bytes": file_bytes,
        "overhead_ratio": overhead_ratio,
        "write_seconds": write_seconds,
        "sequential_seconds": sequential_seconds,
        "slice_seconds": slice_seconds,
        "gates": gates,
        "passed": all(gates.values()),
    }


def run_benchmark():
    import numpy

    with TemporaryDirectory(prefix="chemblender-sidecar-benchmark-") as directory:
        cases = [
            _benchmark_case(Path(directory), *definition) for definition in CASES
        ]
    return {
        "benchmark": "chemblender-cbq-npy-v1",
        "storage": "numpy-npy-memory-map",
        "cache_state": "warm-os-cache-after-write",
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "numpy_version": numpy.__version__,
        "cases": cases,
        "passed": all(case["passed"] for case in cases),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Benchmark ChemBlender .npy sidecar arrays")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = run_benchmark()
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(encoded, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
