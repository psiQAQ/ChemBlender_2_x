#!/usr/bin/env python3
"""Benchmark the Wave 2 CIF, POSCAR and periodic-view product paths."""

import argparse
from ctypes import Structure as CStructure, byref, c_ulong, c_ulonglong, sizeof
from math import ceil, prod
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

import gemmi
import numpy

from ChemBlender.core import parse_cif, parse_poscar
from ChemBlender.core.import_pipeline.request import (
    ImportRequest,
    ImportSource,
    ReaderOverride,
)
from ChemBlender.core.import_pipeline.staging import StagedImportSession
from ChemBlender.reader_api.import_pipeline_bridge import (
    preflight_reader_plugins,
)
from ChemBlender.reader_api.registry import builtin_reader_plugin_registry
from ChemBlender.views.periodic import (
    PeriodicViewSettings,
    _derived_periodic_sites,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"


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
    if not windll.kernel32.GlobalMemoryStatusEx(byref(status)):
        return None
    return int(status.total_physical)


def _generate_cif(path, atom_count):
    edge = max(10.0, atom_count ** (1.0 / 3.0) * 2.0)
    with Path(path).open("w", encoding="ascii", newline="\n") as stream:
        stream.write("data_benchmark\n")
        for name, value in (
            ("a", edge),
            ("b", edge),
            ("c", edge),
        ):
            stream.write(f"_cell_length_{name} {value:.9f}\n")
        for name in ("alpha", "beta", "gamma"):
            stream.write(f"_cell_angle_{name} 90\n")
        stream.write(
            """_space_group_name_H-M_alt 'P 1'
_space_group_IT_number 1
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
_atom_site_occupancy
"""
        )
        side = max(1, ceil(atom_count ** (1.0 / 3.0)))
        for index in range(atom_count):
            x = index % side
            y = (index // side) % side
            z = index // (side * side)
            stream.write(
                f"H{index + 1} H "
                f"{(x + 0.25) / side:.12f} "
                f"{(y + 0.25) / side:.12f} "
                f"{(z + 0.25) / side:.12f} 1.0\n"
            )


def _measure(operation, samples):
    def timed_sample():
        tracemalloc.start()
        started = perf_counter()
        try:
            operation()
        finally:
            duration = perf_counter() - started
            _current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        return duration, peak

    cold_elapsed, cold_peak = timed_sample()
    elapsed = []
    peaks = []
    for _index in range(samples):
        duration, peak = timed_sample()
        elapsed.append(duration)
        peaks.append(peak)
    ordered = sorted(elapsed)
    return {
        "status": "Passed",
        "samples": samples,
        "cold_seconds": cold_elapsed,
        "cold_peak_bytes": cold_peak,
        "median_seconds": median(elapsed),
        "p95_seconds": ordered[max(0, ceil(samples * 0.95) - 1)],
        "peak_bytes": max(peaks),
        "samples_seconds": elapsed,
        "cache_state": "cold first sample; hot samples after cold warmup",
    }


def _view_operation(structure):
    import bpy

    from ChemBlender.views.periodic import create_periodic_structure_view
    from ChemBlender.views.structure import remove_structure_view

    settings = PeriodicViewSettings(representation="source_sites")

    def create_view():
        before = set(bpy.data.objects)
        obj = create_periodic_structure_view(
            structure,
            settings=settings,
            name="Wave 2 qualification benchmark",
            collection=bpy.context.scene.collection,
        )
        try:
            if len(obj.data.vertices) != len(structure.atomic_numbers):
                raise RuntimeError(
                    "crystal view produced an unexpected atom count"
                )
        finally:
            remove_structure_view(obj)
        if set(bpy.data.objects) != before:
            raise RuntimeError("crystal view cleanup left objects behind")

    return create_view


def benchmark_crystal(
    *,
    samples=5,
    cif_atom_count=1000,
    supercell=(10, 10, 10),
    include_blender_view=False,
):
    if isinstance(samples, bool) or not isinstance(samples, int) or samples <= 0:
        raise ValueError("samples must be a positive integer")
    if (
        isinstance(cif_atom_count, bool)
        or not isinstance(cif_atom_count, int)
        or cif_atom_count <= 0
    ):
        raise ValueError("cif_atom_count must be a positive integer")
    if (
        type(supercell) is not tuple
        or len(supercell) != 3
        or any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or value <= 0
            for value in supercell
        )
    ):
        raise ValueError("supercell must contain three positive integers")
    if type(include_blender_view) is not bool:
        raise TypeError("include_blender_view must be a bool")

    with TemporaryDirectory(prefix="chemblender-crystal-benchmark-") as directory:
        workspace = Path(directory)
        cif_path = workspace / "thousand-sites.cif"
        _generate_cif(cif_path, cif_atom_count)
        source = ImportSource(cif_path)
        request = ImportRequest(
            sources=(source,),
            reader_overrides=(ReaderOverride(source.id, "cif"),),
        )
        registry = builtin_reader_plugin_registry()

        def preview():
            session = StagedImportSession.create(temp_parent=workspace)
            try:
                result = preflight_reader_plugins(
                    request,
                    registry,
                    session,
                )
                if len(result.staged_batch_ids) != 1:
                    raise RuntimeError("CIF preview did not stage one batch")
                batch = session.result(result.staged_batch_ids[0])
                if (
                    len(batch.structures) != 1
                    or len(batch.structures[0].atomic_numbers)
                    != cif_atom_count
                ):
                    raise RuntimeError(
                        "CIF preview produced an unexpected atom count"
                    )
                if include_blender_view:
                    from ChemBlender.ui.import_preview import _cif_summary

                    summary = _cif_summary(batch)
                    if (
                        summary is None
                        or summary["block_count"] != 1
                        or summary["valid_block_count"] != 1
                        or summary["site_summary"]
                        != f"{cif_atom_count} sites across 1 structure(s)"
                    ):
                        raise RuntimeError(
                            "CIF preview summary did not match the workload"
                        )
            finally:
                session.discard()
            if session.root.exists():
                raise RuntimeError("CIF preview left staging data behind")

        preview_metric = {
            **_measure(preview, samples),
            "workload": {
                "atom_count": cif_atom_count,
                "reader": "cif",
                "path": (
                    "Reader API preflight, staged ImportBatch and "
                    "Import Preview CIF summary"
                    if include_blender_view
                    else "Reader API preflight and staged ImportBatch"
                ),
                "summary_projection": (
                    "Passed" if include_blender_view else "Not Run"
                ),
            },
        }
        large_structure = parse_cif(cif_path).structures[0]
        quartz = parse_cif(FIXTURES / "cif" / "quartz.cif").structures[0]
        expanded_settings = PeriodicViewSettings(
            representation="expanded_cell",
        )
        supercell_settings = PeriodicViewSettings(
            representation="supercell",
            supercell=supercell,
        )
        expanded_site_count = 7
        full_cell_site_count = 9
        supercell_site_count = (
            full_cell_site_count * prod(supercell) - len(quartz.atomic_numbers)
        )

        def require_derived_count(derived, expected, operation):
            counts = {
                len(derived["coordinates"]),
                len(derived["source_atom_ids"]),
                len(derived["rotations"]),
            }
            if counts != {expected}:
                raise RuntimeError(
                    f"{operation} produced unexpected site counts: "
                    f"{sorted(counts)}"
                )

        def expand_symmetry():
            require_derived_count(
                _derived_periodic_sites(quartz, expanded_settings),
                expanded_site_count,
                "symmetry expansion",
            )

        def derive_supercell():
            require_derived_count(
                _derived_periodic_sites(quartz, supercell_settings),
                supercell_site_count,
                "supercell derivation",
            )

        def import_poscar():
            batch = parse_poscar(FIXTURES / "poscar" / "si.POSCAR")
            if (
                len(batch.structures) != 1
                or len(batch.structures[0].atomic_numbers) != 2
            ):
                raise RuntimeError(
                    "POSCAR import produced an unexpected atom count"
                )

        metrics = {
            "cif_preview": preview_metric,
            "symmetry_expansion": {
                **_measure(expand_symmetry, samples),
                "workload": {
                    "source_atom_count": len(quartz.atomic_numbers),
                    "operation_count": len(
                        quartz.periodic.symmetry_operations
                    ),
                    "representation": "expanded_cell",
                },
            },
            "supercell": {
                **_measure(derive_supercell, samples),
                "workload": {
                    "source_atom_count": len(quartz.atomic_numbers),
                    "supercell": list(supercell),
                },
            },
            "poscar_import": {
                **_measure(import_poscar, samples),
                "workload": {
                    "fixture": "si.POSCAR",
                    "atom_count": 2,
                },
            },
        }
        if include_blender_view:
            metrics["crystal_view_creation"] = {
                **_measure(_view_operation(large_structure), samples),
                "workload": {
                    "atom_count": cif_atom_count,
                    "representation": "source_sites",
                    "cache_state": "hot after measured cold sample",
                },
            }
        else:
            metrics["crystal_view_creation"] = {
                "status": "Not Run",
                "reason": "requires Blender runtime",
                "workload": {
                    "atom_count": cif_atom_count,
                    "representation": "source_sites",
                },
            }

    return {
        "benchmark": "chemblender-wave2-crystal-v1",
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor()
            or os.environ.get("PROCESSOR_IDENTIFIER", ""),
            "cpu_count": os.cpu_count(),
            "total_memory_bytes": _total_memory_bytes(),
            "python_version": platform.python_version(),
            "numpy_version": numpy.__version__,
            "gemmi_version": gemmi.__version__,
            "blender_version": (
                __import__("bpy").app.version_string
                if include_blender_view
                else None
            ),
        },
        "metrics": metrics,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Benchmark ChemBlender Wave 2 crystal workflows"
    )
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--cif-atom-count", type=int, default=1000)
    parser.add_argument("--supercell", type=int, default=10)
    parser.add_argument("--include-blender-view", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = benchmark_crystal(
            samples=args.samples,
            cif_atom_count=args.cif_atom_count,
            supercell=(args.supercell,) * 3,
            include_blender_view=args.include_blender_view,
        )
    except (TypeError, ValueError) as error:
        parser.error(str(error))
    encoded = json.dumps(
        report,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    if args.output is None:
        print(encoded, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    arguments = (
        sys.argv[sys.argv.index("--") + 1 :]
        if "--" in sys.argv
        else None
    )
    raise SystemExit(main(arguments))
