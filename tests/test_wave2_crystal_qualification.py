import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

import numpy


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
CIF_FIXTURES = ROOT / "tests" / "fixtures" / "cif"
POSCAR_FIXTURES = ROOT / "tests" / "fixtures" / "poscar"
CIF_QUALIFICATION_CASES = (
    "quartz.cif",
    "nacl.cif",
    "partial-disorder.cif",
    "multi-block.cif",
)
POSCAR_QUALIFICATION_CASES = (
    "si.POSCAR",
    "fe-bcc.POSCAR",
    "cscl-selective.vasp",
    "velocities.CONTCAR",
)


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


class Wave2CrystalRoundTripQualificationTests(unittest.TestCase):
    def assert_optional_array_equal(self, left, right):
        self.assertEqual(left is None, right is None)
        if left is not None:
            self.assertEqual(left.dims, right.dims)
            self.assertEqual(left.unit, right.unit)
            numpy.testing.assert_allclose(
                left.values,
                right.values,
                rtol=0.0,
                atol=1.0e-10,
                equal_nan=True,
            )

    def assert_periodic_structure_equal(self, left, right):
        self.assertEqual(left.atomic_numbers, right.atomic_numbers)
        self.assertEqual(left.cell.unit, right.cell.unit)
        numpy.testing.assert_allclose(
            left.cell.values,
            right.cell.values,
            rtol=0.0,
            atol=1.0e-9,
        )
        self.assertEqual(left.periodic.pbc, right.periodic.pbc)
        delta = numpy.abs(
            numpy.mod(
                numpy.asarray(left.periodic.fractional_coordinates.values)
                - numpy.asarray(right.periodic.fractional_coordinates.values),
                1.0,
            )
        )
        numpy.testing.assert_allclose(
            numpy.minimum(delta, 1.0 - delta),
            0.0,
            rtol=0.0,
            atol=1.0e-9,
        )
        self.assertEqual(
            left.periodic.site_labels,
            right.periodic.site_labels,
        )
        numpy.testing.assert_allclose(
            left.periodic.occupancies.values,
            right.periodic.occupancies.values,
            rtol=0.0,
            atol=1.0e-10,
            equal_nan=True,
        )
        self.assertEqual(left.periodic.adp_types, right.periodic.adp_types)
        self.assertEqual(
            left.periodic.disorder_groups,
            right.periodic.disorder_groups,
        )
        self.assertEqual(
            left.periodic.disorder_assemblies,
            right.periodic.disorder_assemblies,
        )
        self.assertEqual(
            left.periodic.declared_symmetry,
            right.periodic.declared_symmetry,
        )
        self.assert_optional_array_equal(
            left.periodic.isotropic_displacements,
            right.periodic.isotropic_displacements,
        )
        self.assert_optional_array_equal(
            left.periodic.anisotropic_displacements,
            right.periodic.anisotropic_displacements,
        )

    @unittest.skipUnless(
        importlib.util.find_spec("gemmi") is not None,
        "Gemmi dependency unavailable",
    )
    def test_fixed_cif_inventory_survives_sidecar_and_export_roundtrip(self):
        from ChemBlender.core import (
            QCProject,
            close_project,
            open_project,
            parse_cif,
            save_project,
        )
        from ChemBlender.core.exporters import export_cif

        for name in CIF_QUALIFICATION_CASES:
            source = CIF_FIXTURES / name
            with self.subTest(fixture=name):
                self.assertTrue(source.is_file(), source)
                batch = parse_cif(source)
                project = QCProject(uuid4(), "1.0")
                project.commit(batch)
                with TemporaryDirectory() as directory:
                    directory = Path(directory)
                    sidecar = save_project(
                        directory / f"{source.stem}.cbq",
                        project,
                    )
                    restored = open_project(sidecar)
                    try:
                        self.assertEqual(restored.schema_version, "1.0")
                        original = batch.structures[0]
                        reopened = restored.structures[original.id]
                        self.assert_periodic_structure_equal(
                            original,
                            reopened,
                        )
                        envelope = restored.cif_envelopes[
                            reopened.periodic.cif_envelope_id
                        ]
                        exported = directory / f"{source.stem}-exported.cif"
                        export_cif(
                            exported,
                            reopened,
                            envelope=envelope,
                            mode="preserve",
                        )
                        reparsed = parse_cif(exported)
                        exported_structure = next(
                            structure
                            for structure in reparsed.structures
                            if structure.periodic.cif_block_name
                            == reopened.periodic.cif_block_name
                        )
                        self.assert_periodic_structure_equal(
                            reopened,
                            exported_structure,
                        )
                    finally:
                        close_project(restored)

    def test_fixed_poscar_inventory_survives_sidecar_and_export_roundtrip(self):
        from ChemBlender.core import (
            ImportBatch,
            QCProject,
            close_project,
            open_project,
            parse_poscar,
            save_project,
        )
        from ChemBlender.core.exporters import (
            PoscarExportSettings,
            export_poscar,
            semantic_poscar_differences,
        )
        from ChemBlender.core.formats.poscar import (
            PoscarLatticeVelocityBlock,
            parse_poscar_document,
        )

        for name in POSCAR_QUALIFICATION_CASES:
            source = POSCAR_FIXTURES / name
            with self.subTest(fixture=name):
                self.assertTrue(source.is_file(), source)
                batch = parse_poscar(source)
                project = QCProject(uuid4(), "1.0")
                project.commit(batch)
                with TemporaryDirectory() as directory:
                    directory = Path(directory)
                    sidecar = save_project(
                        directory / f"{source.stem}.cbq",
                        project,
                    )
                    restored = open_project(sidecar)
                    try:
                        self.assertEqual(restored.schema_version, "1.0")
                        original = batch.structures[0]
                        reopened = restored.structures[original.id]
                        self.assert_periodic_structure_equal(
                            original,
                            reopened,
                        )
                        datasets = tuple(restored.datasets.values())
                        by_role = {
                            dataset.semantic_role: dataset
                            for dataset in datasets
                        }
                        provenance = next(
                            value
                            for value in restored.provenance.values()
                            if value.producer
                            == "ChemBlender POSCAR adapter"
                        )
                        parameters = dict(provenance.parameters)
                        lattice = None
                        if "lattice_velocity" in by_role:
                            lattice = PoscarLatticeVelocityBlock(
                                float(
                                    parameters[
                                        "lattice_velocity_initialization_state"
                                    ]
                                ),
                                tuple(
                                    tuple(map(float, row))
                                    for row in by_role[
                                        "lattice_velocity"
                                    ].data.values
                                ),
                                tuple(
                                    tuple(map(float, row))
                                    for row in parameters[
                                        "lattice_velocity_vectors"
                                    ]
                                ),
                            )
                        exported = directory / "CONTCAR"
                        export_poscar(
                            exported,
                            reopened,
                            PoscarExportSettings(
                                coordinate_mode="direct",
                                velocity_mode="cartesian",
                            ),
                            selective_dynamics=by_role.get(
                                "selective_dynamics"
                            ),
                            velocities=by_role.get("atomic_velocity"),
                            lattice_velocities=lattice,
                        )
                        reparsed = parse_poscar(exported)
                        self.assertEqual(
                            semantic_poscar_differences(batch, reparsed),
                            (),
                        )
                        if lattice is not None:
                            exported_document = parse_poscar_document(
                                exported.read_bytes()
                            )
                            self.assertEqual(
                                exported_document.lattice_velocities,
                                lattice,
                            )
                        reopened_batch = ImportBatch(
                            structures=(reopened,),
                            datasets=datasets,
                        )
                        self.assertEqual(
                            semantic_poscar_differences(
                                batch,
                                reopened_batch,
                            ),
                            (),
                        )
                    finally:
                        close_project(restored)


class Wave2CrystalPerformanceQualificationTests(unittest.TestCase):
    @unittest.skipUnless(
        importlib.util.find_spec("gemmi") is not None,
        "Gemmi dependency unavailable",
    )
    def test_benchmark_reports_measured_metrics_and_explicit_view_skip(self):
        from ChemBlender.scripts.benchmark_crystal import benchmark_crystal

        result = benchmark_crystal(
            samples=2,
            cif_atom_count=10,
            supercell=(2, 2, 2),
            include_blender_view=False,
        )

        self.assertIn("environment", result)
        self.assertEqual(
            set(result["metrics"]),
            {
                "cif_preview",
                "symmetry_expansion",
                "supercell_10x10x10",
                "poscar_import",
                "crystal_view_creation",
            },
        )
        self.assertGreater(
            result["metrics"]["symmetry_expansion"]["workload"][
                "operation_count"
            ],
            1,
        )
        for name, metric in result["metrics"].items():
            with self.subTest(metric=name):
                self.assertIn("status", metric)
                self.assertIn("workload", metric)
                if name == "crystal_view_creation":
                    self.assertEqual(metric["status"], "Not Run")
                    self.assertEqual(
                        metric["reason"],
                        "requires Blender runtime",
                    )
                    continue
                self.assertEqual(metric["status"], "Passed")
                self.assertEqual(metric["samples"], 2)
                self.assertGreaterEqual(metric["median_seconds"], 0.0)
                self.assertGreaterEqual(
                    metric["p95_seconds"],
                    metric["median_seconds"],
                )
                self.assertGreater(metric["peak_bytes"], 0)


if __name__ == "__main__":
    unittest.main()
