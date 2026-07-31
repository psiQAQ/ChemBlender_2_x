import importlib.util
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ChemBlender" / "scripts" / "benchmark_230.py"


def load_harness():
    spec = importlib.util.spec_from_file_location("benchmark_230", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BenchmarkDatasetTests(unittest.TestCase):
    def test_scale_catalog_and_small_streaming_fixtures_are_deterministic(self):
        from ChemBlender.benchmarks.datasets import (
            BENCHMARK_SCALES,
            generate_grid_npy,
            generate_sdf_fixture,
            generate_structure_xyz,
            generate_trajectory_npy,
        )
        from ChemBlender.core.formats.sdf import iter_sdf_file_records

        self.assertEqual(BENCHMARK_SCALES["interactive"].structure_atoms, 50_000)
        self.assertEqual(BENCHMARK_SCALES["lazy"].structure_atoms, 250_000)
        self.assertEqual(BENCHMARK_SCALES["interactive"].trajectory_frames, 1_000)
        self.assertEqual(BENCHMARK_SCALES["lazy"].trajectory_frames, 100_000)
        self.assertEqual(BENCHMARK_SCALES["interactive"].grid_shape, (128, 128, 128))
        self.assertEqual(BENCHMARK_SCALES["lazy"].grid_shape, (256, 256, 256))
        self.assertEqual(BENCHMARK_SCALES["interactive"].sdf_records, 10_000)
        self.assertEqual(BENCHMARK_SCALES["lazy"].sdf_records, 100_000)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            first = generate_structure_xyz(root / "first.xyz", atom_count=3)
            second = generate_structure_xyz(root / "second.xyz", atom_count=3)
            self.assertEqual(first.sha256, second.sha256)

            trajectory = generate_trajectory_npy(
                root / "trajectory.npy", frames=3, atoms=2
            )
            self.assertEqual(trajectory.shape, (3, 2, 3))
            self.assertFalse(trajectory.array.loaded)
            self.assertEqual(tuple(trajectory.array[1].shape), (2, 3))
            self.assertTrue(trajectory.array.loaded)
            trajectory.array.close()

            grid = generate_grid_npy(root / "grid.npy", shape=(2, 2, 2))
            self.assertEqual(grid.shape, (2, 2, 2))
            self.assertEqual(len(grid.sha256), 64)

            sdf = generate_sdf_fixture(root / "records.sdf", record_count=3)
            self.assertEqual(sdf.record_count, 3)
            self.assertEqual(sdf.sha256, generate_sdf_fixture(root / "copy.sdf", record_count=3).sha256)
            self.assertEqual(len(tuple(iter_sdf_file_records(sdf.path))), 3)


class BenchmarkHarnessTests(unittest.TestCase):
    def test_registry_covers_plan_stages_and_blender_cases_are_boundaries(self):
        harness = load_harness()

        self.assertEqual(
            set(harness.CASE_REGISTRY),
            {
                "extension_enable",
                "preflight_feedback",
                "parse",
                "project_commit",
                "sidecar_save_open",
                "vdb_cache",
                "default_view",
                "trajectory_frame",
                "browser_projection_filter",
                "cancel_cleanup",
            },
        )
        for name in ("extension_enable", "vdb_cache", "default_view"):
            self.assertEqual(harness.CASE_REGISTRY[name].execution, "blender")
            self.assertIn("Blender", harness.CASE_REGISTRY[name].boundary)
        self.assertNotIn("import bpy", SCRIPT.read_text(encoding="utf-8"))

    def test_builtin_core_runners_can_use_a_tiny_overridden_scale(self):
        from ChemBlender.benchmarks.datasets import BenchmarkScale

        harness = load_harness()
        harness.BENCHMARK_SCALES["test"] = BenchmarkScale(
            "test", 3, 3, (2, 2, 2), 3
        )
        try:
            report = harness.run_benchmark(
                case_names=tuple(harness.BUILTIN_RUNNERS),
                scale="test",
                warmup_count=0,
                sample_count=1,
            )
        finally:
            del harness.BENCHMARK_SCALES["test"]
        self.assertTrue(report["passed"])

    def test_measurement_report_is_canonical_and_complete(self):
        harness = load_harness()
        clock_values = iter((0.0, 0.1, 1.0, 1.4, 2.0, 2.2, 3.0, 3.5))
        report = harness.run_benchmark(
            case_names=("parse",),
            scale="interactive",
            warmup_count=1,
            sample_count=3,
            runners={"parse": lambda _scale, _workspace: None},
            clock=lambda: next(clock_values),
        )

        self.assertTrue(report["passed"])
        self.assertEqual(report["warmup_count"], 1)
        self.assertEqual(report["sample_count"], 3)
        self.assertEqual(report["failure_count"], 0)
        case, = report["cases"]
        self.assertEqual(case["status"], "Passed")
        self.assertAlmostEqual(case["cold_seconds"], 0.4)
        self.assertAlmostEqual(case["hot_seconds"], 0.35)
        self.assertAlmostEqual(case["minimum_seconds"], 0.2)
        self.assertAlmostEqual(case["median_seconds"], 0.4)
        self.assertAlmostEqual(case["p95_seconds"], 0.5)
        self.assertAlmostEqual(case["maximum_seconds"], 0.5)
        self.assertEqual(
            harness.canonical_json(report),
            harness.canonical_json(json.loads(harness.canonical_json(report))),
        )

    def test_failed_or_nonfinite_case_is_not_qualified(self):
        harness = load_harness()
        failed = harness.run_benchmark(
            case_names=("parse",),
            scale="interactive",
            warmup_count=0,
            sample_count=1,
            runners={"parse": lambda _scale, _workspace: (_ for _ in ()).throw(RuntimeError("boom"))},
        )
        self.assertFalse(failed["passed"])
        self.assertEqual(failed["failure_count"], 1)
        with self.assertRaises(ValueError):
            harness.validate_qualified_report(failed)

        nonfinite = {"value": math.nan}
        with self.assertRaises(ValueError):
            harness.canonical_json(nonfinite)

    def test_not_run_or_missing_fields_are_rejected_for_qualification(self):
        harness = load_harness()
        not_run = harness.run_benchmark(
            case_names=("extension_enable",),
            scale="interactive",
            warmup_count=0,
            sample_count=1,
        )
        self.assertFalse(not_run["passed"])
        self.assertEqual(not_run["cases"][0]["status"], "Not Run")

        complete = harness.run_benchmark(
            case_names=("parse",),
            scale="interactive",
            warmup_count=0,
            sample_count=1,
            runners={"parse": lambda _scale, _workspace: None},
        )
        incomplete = dict(complete)
        del incomplete["sample_count"]
        with self.assertRaises(ValueError):
            harness.validate_qualified_report(incomplete)

    def test_atomic_json_output_uses_utf8_lf(self):
        harness = load_harness()
        with TemporaryDirectory() as directory:
            output = Path(directory) / "nested" / "benchmark.json"
            harness.write_canonical_json(output, {"text": "化学", "value": 1})
            raw = output.read_bytes()
            self.assertEqual(raw, b'{"text":"\xe5\x8c\x96\xe5\xad\xa6","value":1}\n')
            self.assertFalse(list(output.parent.glob("*.tmp")))


if __name__ == "__main__":
    unittest.main()
