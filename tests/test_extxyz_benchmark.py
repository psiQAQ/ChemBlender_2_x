import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "ChemBlender"
    / "scripts"
    / "benchmark_extxyz.py"
)


class ExtXYZBenchmarkTests(unittest.TestCase):
    def test_small_profile_reports_required_measurements_and_resilience(self):
        spec = importlib.util.spec_from_file_location(
            "benchmark_extxyz",
            SCRIPT,
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with TemporaryDirectory() as directory:
            report = module.run_benchmark(
                frames=3,
                atoms=2,
                metadata_frames=5,
                repeats=2,
                workspace=Path(directory),
            )

        self.assertEqual(report["benchmark"], "chemblender-extxyz-v1")
        self.assertEqual(
            set(report["measurements"]),
            {
                "first_preview",
                "parse",
                "sidecar_write",
                "single_frame_access",
                "export",
            },
        )
        for measurement in report["measurements"].values():
            self.assertEqual(measurement["sample_count"], 2)
            self.assertGreaterEqual(
                measurement["p95_seconds"],
                measurement["median_seconds"],
            )
        self.assertEqual(
            report["workloads"]["trajectory"],
            {"frames": 3, "atoms": 2},
        )
        self.assertEqual(
            report["workloads"]["metadata_only"],
            {"frames": 5, "atoms": 1},
        )
        self.assertTrue(report["resilience"]["cancellation_cleanup"])
        self.assertTrue(report["resilience"]["publication_rollback"])
        self.assertTrue(report["streaming_arrays"])
        self.assertIn("peak_python_bytes", report)
        self.assertIn("environment", report)
        self.assertIn("budget", report)


if __name__ == "__main__":
    unittest.main()
