import importlib.util
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "ChemBlender"
    / "scripts"
    / "benchmark_sidecar.py"
)


class SidecarBenchmarkContractTests(unittest.TestCase):
    def test_cases_cover_phase_one_and_two_array_families(self):
        spec = importlib.util.spec_from_file_location("benchmark_sidecar", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        names = {case[0] for case in module.CASES}
        self.assertEqual(
            names,
            {"trajectory", "grid3d", "mo_coefficients", "projections"},
        )
        self.assertNotIn("zarr", SCRIPT.read_text(encoding="utf-8").lower())
        self.assertNotIn("h5py", SCRIPT.read_text(encoding="utf-8").lower())


if __name__ == "__main__":
    unittest.main()
