import copy
import importlib.util
import math
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "ChemBlender" / "scripts" / "benchmark_230.py"
BUDGET = ROOT / "ChemBlender" / "benchmarks" / "budget.json"


def load_harness():
    spec = importlib.util.spec_from_file_location("benchmark_230", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def qualified_report(harness, values, *, environment=None, scale="interactive"):
    cases = []
    for name, seconds in values.items():
        definition = harness.CASE_REGISTRY[name]
        cases.append(
            {
                "boundary": definition.boundary,
                "cache_state": definition.cache_state,
                "cold_seconds": seconds,
                "execution": definition.execution,
                "failure_count": 0,
                "failures": [],
                "hot_seconds": seconds,
                "maximum_seconds": seconds,
                "median_seconds": seconds,
                "minimum_seconds": seconds,
                "name": name,
                "p95_seconds": seconds,
                "sample_seconds": [seconds, seconds],
                "status": "Passed",
            }
        )
    return {
        "benchmark": "chemblender-2.3.0-v1",
        "cases": cases,
        "environment": environment or harness.benchmark_environment(),
        "failure_count": 0,
        "passed": True,
        "sample_count": 2,
        "scale": scale,
        "warmup_count": 0,
    }


class PerformanceBudgetTests(unittest.TestCase):
    def test_budget_maps_approved_p95_limits(self):
        harness = load_harness()

        budget = harness.load_performance_budget(BUDGET)

        self.assertEqual(budget["hard_local_metric"], "p95_seconds")
        self.assertEqual(budget["trend_metric"], "p95_seconds")
        self.assertEqual(budget["trend_max_regression_percent"], 15)
        self.assertEqual(
            {
                name: definition["hard_limit_seconds"]
                for name, definition in budget["cases"].items()
            },
            {
                "extension_enable": 2.0,
                "preflight_feedback": 0.5,
                "default_view": 3.0,
                "vdb_cache": 10.0,
                "trajectory_frame": 0.1,
                "browser_projection_filter": 0.2,
            },
        )

    def test_hard_local_p95_over_budget_fails(self):
        harness = load_harness()
        budget = harness.load_performance_budget(BUDGET)
        values = {
            name: definition["hard_limit_seconds"]
            for name, definition in budget["cases"].items()
        }
        report = qualified_report(harness, values)

        self.assertTrue(harness.compare_performance_report(report, budget)["passed"])

        over_budget = copy.deepcopy(report)
        next(
            case for case in over_budget["cases"]
            if case["name"] == "preflight_feedback"
        )["p95_seconds"] = 0.500001
        result = harness.compare_performance_report(over_budget, budget)
        self.assertFalse(result["passed"])
        self.assertEqual(result["hard_local_failures"], ["preflight_feedback"])

    def test_trend_compares_only_matching_reference_context(self):
        harness = load_harness()
        budget = harness.load_performance_budget(BUDGET)
        baseline_values = {
            name: definition["hard_limit_seconds"] / 2
            for name, definition in budget["cases"].items()
        }
        baseline = qualified_report(harness, baseline_values)
        candidate = qualified_report(
            harness,
            {
                name: seconds * 1.15
                for name, seconds in baseline_values.items()
            },
        )

        self.assertTrue(
            harness.compare_performance_report(
                candidate, budget, baseline_report=baseline
            )["passed"]
        )

        too_slow = copy.deepcopy(candidate)
        next(
            case for case in too_slow["cases"]
            if case["name"] == "browser_projection_filter"
        )["p95_seconds"] = baseline_values["browser_projection_filter"] * 1.150001
        result = harness.compare_performance_report(
            too_slow, budget, baseline_report=baseline
        )
        self.assertFalse(result["passed"])
        self.assertEqual(result["trend_failures"], ["browser_projection_filter"])

        mismatch = copy.deepcopy(candidate)
        mismatch["scale"] = "lazy"
        with self.assertRaisesRegex(ValueError, "scale"):
            harness.compare_performance_report(
                mismatch, budget, baseline_report=baseline
            )
        mismatch = copy.deepcopy(candidate)
        next(
            case for case in mismatch["cases"]
            if case["name"] == "trajectory_frame"
        )["cache_state"] = "cold"
        with self.assertRaisesRegex(ValueError, "cache_state"):
            harness.compare_performance_report(
                mismatch, budget, baseline_report=baseline
            )
        mismatch = copy.deepcopy(candidate)
        mismatch["environment"]["python_version"] = "0"
        with self.assertRaisesRegex(ValueError, "environment"):
            harness.compare_performance_report(
                mismatch, budget, baseline_report=baseline
            )

    def test_missing_or_nonfinite_required_measurement_is_rejected(self):
        harness = load_harness()
        budget = harness.load_performance_budget(BUDGET)
        report = qualified_report(
            harness,
            {
                name: definition["hard_limit_seconds"] / 2
                for name, definition in budget["cases"].items()
            },
        )

        missing = copy.deepcopy(report)
        missing["cases"].pop()
        with self.assertRaisesRegex(ValueError, "missing"):
            harness.compare_performance_report(missing, budget)
        nonfinite = copy.deepcopy(report)
        next(iter(nonfinite["cases"]))["p95_seconds"] = math.nan
        with self.assertRaisesRegex(ValueError, "finite"):
            harness.compare_performance_report(nonfinite, budget)


if __name__ == "__main__":
    unittest.main()
