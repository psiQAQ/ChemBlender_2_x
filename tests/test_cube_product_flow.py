import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from ChemBlender.core import (
    DatasetStatus,
    Grid3D,
    QCProject,
    builtin_scene_presets,
    close_project,
    open_project,
    plan_scene_preset,
    resolve_grid_semantics,
    save_project,
    scene_plan_document,
    validate_scene_plan,
)
from ChemBlender.core.cube import CUBE_READER
from ChemBlender.ui.grid import grid_preview_summary


ROOT = Path(__file__).resolve().parents[1]
TWO_DATASETS = ROOT / "tests" / "fixtures" / "cube" / "two-datasets.cube"
BENCHMARK = ROOT / "ChemBlender" / "scripts" / "benchmark_cube_flow.py"


class CubeProductFlowTests(unittest.TestCase):
    def test_multi_dataset_import_resolution_and_signed_plan_survive_roundtrip(self):
        batch = CUBE_READER.parse(TWO_DATASETS)
        raw = next(value for value in batch.datasets if isinstance(value, Grid3D))
        summary = grid_preview_summary(batch)
        self.assertEqual(summary.dataset_count, 2)
        self.assertEqual(summary.source_dataset_ids, ("5", "7"))
        self.assertEqual(summary.quality, "ambiguous")

        project = QCProject(uuid4(), "0.2")
        project.commit(batch)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            raw_sidecar = root / "raw.cbq"
            save_project(raw_sidecar, project)
            loaded = open_project(raw_sidecar)
            try:
                self.assertIs(
                    loaded.datasets[raw.id].status,
                    DatasetStatus.AMBIGUOUS,
                )
                resolution = resolve_grid_semantics(
                    loaded.datasets[raw.id],
                    dataset_index=1,
                    preset_id="molecular_orbital",
                    value_unit="inverse_bohr_to_three_halves",
                )
                resolved = resolution.datasets[0]
                loaded.commit(resolution)
                plan = plan_scene_preset(
                    builtin_scene_presets()["signed_isosurface"],
                    loaded,
                    {"grid": resolved.id},
                    {"dataset_index": 0, "isovalue": 0.2},
                )
                document = scene_plan_document(plan)
                self.assertEqual(
                    document["bindings"],
                    [
                        {
                            "name": "grid",
                            "entity_kind": "dataset",
                            "entity_id": str(resolved.id),
                            "revision": resolved.revision,
                        }
                    ],
                )
                resolved_sidecar = root / "resolved.cbq"
                save_project(resolved_sidecar, loaded)
            finally:
                close_project(loaded)

            reopened = open_project(resolved_sidecar)
            try:
                self.assertIn(raw.id, reopened.datasets)
                self.assertIn(resolved.id, reopened.datasets)
                self.assertEqual(
                    validate_scene_plan(plan, reopened),
                    plan,
                )
                self.assertEqual(
                    reopened.datasets[resolved.id].structure_id,
                    reopened.datasets[raw.id].structure_id,
                )
            finally:
                close_project(reopened)

    def test_small_benchmark_emits_required_stage_contract(self):
        self.assertTrue(BENCHMARK.is_file())
        spec = importlib.util.spec_from_file_location(
            "benchmark_cube_flow",
            BENCHMARK,
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        operations = {
            "cache_vdb_cold": lambda _index: None,
            "cache_vdb_hot": lambda _index: None,
            "view_hot": lambda _index: None,
        }

        with TemporaryDirectory() as directory:
            report = module.run_benchmark(
                size=4,
                repeats=2,
                workspace=Path(directory),
                blender_operations=operations,
            )

        self.assertEqual(report["benchmark"], "chemblender-cube-flow-v1")
        self.assertEqual(
            set(report["stages"]),
            {
                "parse",
                "stage_npy",
                "sidecar_save",
                "cache_vdb_cold",
                "cache_vdb_hot",
                "view_hot",
            },
        )
        for stage in report["stages"].values():
            self.assertEqual(stage["sample_count"], 2)
            self.assertGreaterEqual(
                stage["p95_seconds"],
                stage["median_seconds"],
            )
        self.assertEqual(
            report["workload"],
            {
                "shape": [4, 4, 4],
                "voxel_count": 64,
                "repeats": 2,
            },
        )
        self.assertIn("peak_python_bytes", report)
        self.assertIn("environment", report)
        self.assertIn("budget", report)


if __name__ == "__main__":
    unittest.main()
