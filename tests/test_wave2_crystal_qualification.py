import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = (
    ROOT
    / "docs"
    / "quantum-visualization"
    / "crystal-capability-matrix-v1.json"
)

UNIFIED_CRYSTAL_MODEL = {
    "Structure",
    "PeriodicSiteData",
    "TopologyRecord",
    "SymmetryResult",
}
FORBIDDEN_PARALLEL_MODEL = {
    "CrystalStructure",
    "UnitCell",
    "PeriodicTopology",
}
CAPABILITY_NAMES = {
    "structure",
    "fractional_coordinates",
    "symmetry",
    "periodic_topology",
    "occupancy",
    "adp",
    "selective_dynamics",
    "velocity",
    "export",
}
CAPABILITY_VALUES = {"supported", "partial", "unsupported"}


class Wave2CrystalBoundaryQualificationTests(unittest.TestCase):
    def test_crystal_capability_matrix_freezes_unified_contract(self):
        document = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))

        self.assertEqual(document["schema_name"], "chemblender_crystal_capability_matrix")
        self.assertEqual(document["schema_version"], 1)
        self.assertEqual(set(document["public_model"]), UNIFIED_CRYSTAL_MODEL)
        self.assertEqual(
            set(document["forbidden_parallel_model"]),
            FORBIDDEN_PARALLEL_MODEL,
        )
        self.assertEqual(set(document["formats"]), {"cif", "poscar"})
        for name, capabilities in document["formats"].items():
            with self.subTest(format=name):
                self.assertEqual(set(capabilities), CAPABILITY_NAMES)
                self.assertLessEqual(
                    set(capabilities.values()),
                    CAPABILITY_VALUES,
                )

    def test_public_crystal_surface_uses_unified_model_contract(self):
        import ChemBlender.core as core
        import ChemBlender.reader_api as reader_api

        for module in (core, reader_api):
            public = set(module.__all__)
            with self.subTest(module=module.__name__):
                self.assertLessEqual(UNIFIED_CRYSTAL_MODEL, public)
                self.assertTrue(FORBIDDEN_PARALLEL_MODEL.isdisjoint(public))
                for name in public:
                    owner = getattr(getattr(module, name), "__module__", "")
                    self.assertNotIn(
                        owner.split(".", 1)[0],
                        {"gemmi", "spglib"},
                        name,
                    )

        self.assertLessEqual(
            {
                "unit_cell_parameters",
                "fractional_to_cartesian",
                "cartesian_to_fractional",
                "validate_periodic_coordinate_consistency",
            },
            set(core.__all__),
        )

    def test_core_and_reader_api_cold_imports_do_not_load_crystal_dependencies(self):
        code = """
import sys
import ChemBlender.core
import ChemBlender.reader_api
loaded = sorted({"gemmi", "spglib"}.intersection(sys.modules))
raise SystemExit(f"unexpected optional imports: {loaded}" if loaded else 0)
"""
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(
            completed.returncode,
            0,
            completed.stdout + completed.stderr,
        )

    @unittest.skipUnless(
        importlib.util.find_spec("gemmi") is not None,
        "Gemmi dependency unavailable",
    )
    def test_cif_invocation_loads_gemmi_without_loading_spglib(self):
        code = f"""
import sys
from pathlib import Path
from ChemBlender.core import parse_cif
assert "gemmi" not in sys.modules
assert "spglib" not in sys.modules
parse_cif(Path({str(ROOT / "tests" / "fixtures" / "cif" / "cscl.cif")!r}))
assert "gemmi" in sys.modules
assert "spglib" not in sys.modules
"""
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(
            completed.returncode,
            0,
            completed.stdout + completed.stderr,
        )


if __name__ == "__main__":
    unittest.main()
