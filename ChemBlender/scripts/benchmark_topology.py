#!/usr/bin/env python3
import argparse
from math import ceil
import json
from pathlib import Path
import platform
import sys
from time import perf_counter
from uuid import NAMESPACE_URL, uuid5


if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy

from ChemBlender.core import ArrayData, Structure
from ChemBlender.core.topology.infer import infer_distance_topology


def _structure(atom_count):
    indices = numpy.arange(atom_count)
    coordinates = numpy.column_stack(
        (
            indices % 100,
            (indices // 100) % 100,
            indices // 10_000,
        )
    ).astype(float)
    coordinates *= 4.0
    return Structure(
        id=uuid5(NAMESPACE_URL, f"chemblender:topology-benchmark:{atom_count}"),
        revision=f"generated-{atom_count}",
        atomic_numbers=(6,) * atom_count,
        coordinates=ArrayData(coordinates, ("atom", "xyz"), "angstrom"),
    )


def _samples(atom_count, repeats):
    reference = _structure(atom_count)
    samples = []
    for _ in range(repeats):
        started = perf_counter()
        batch = infer_distance_topology(reference)
        samples.append(perf_counter() - started)
        if batch.topologies[0].bond_indices.shape != (0, 2):
            raise RuntimeError("sparse benchmark unexpectedly produced bonds")
    return sorted(samples)


def _summary(samples):
    return {
        "median_seconds": samples[len(samples) // 2],
        "p95_seconds": samples[max(0, ceil(len(samples) * 0.95) - 1)],
        "samples_seconds": samples,
    }


def run_benchmark(atom_count=50_000, repeats=3):
    smaller_count = max(1, atom_count // 2)
    smaller = _summary(_samples(smaller_count, repeats))
    target = _summary(_samples(atom_count, repeats))
    scaling_ratio = target["median_seconds"] / max(
        smaller["median_seconds"],
        sys.float_info.epsilon,
    )
    gates = {
        "target_is_50000_atoms": atom_count >= 50_000,
        "median_lte_3_seconds": target["median_seconds"] <= 3.0,
        "doubling_ratio_lt_3": scaling_ratio < 3.0,
    }
    return {
        "benchmark": "chemblender-nonperiodic-topology-v1",
        "algorithm": "spatial-cell-list-27-neighbors",
        "atom_count": atom_count,
        "repeats": repeats,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "numpy_version": numpy.__version__,
        "smaller": {"atom_count": smaller_count, **smaller},
        "target": target,
        "scaling_ratio": scaling_ratio,
        "gates": gates,
        "passed": all(gates.values()),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Benchmark ChemBlender nonperiodic topology inference"
    )
    parser.add_argument("--atoms", type=int, default=50_000)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.atoms <= 0 or args.repeats <= 0:
        parser.error("--atoms and --repeats must be positive")
    report = run_benchmark(args.atoms, args.repeats)
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(encoded, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
