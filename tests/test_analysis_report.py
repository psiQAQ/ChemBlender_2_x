import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

import numpy

from ChemBlender.core import (
    AnalysisReportError,
    ArrayData,
    CalculationMetadata,
    CalculationRecord,
    CalculationStatus,
    DatasetStatus,
    ImportBatch,
    PropertyDataset,
    ProvenanceRecord,
    QCProject,
    RecipeBinding,
    RecipePlan,
    build_analysis_report,
    builtin_recipes,
    describe_report_artifact,
    render_analysis_report_markdown,
    validate_analysis_report,
    write_analysis_report_bundle,
)


PROJECT_ID = UUID("10000000-0000-0000-0000-000000000001")
CALCULATION_ID = UUID("20000000-0000-0000-0000-000000000002")
DATASET_ID = UUID("30000000-0000-0000-0000-000000000003")
PROVENANCE_ID = UUID("40000000-0000-0000-0000-000000000004")
PARENT_PROVENANCE_ID = UUID("50000000-0000-0000-0000-000000000005")


def project(*, calculation_status=CalculationStatus.SUCCESS, dataset_status=DatasetStatus.COMPLETE):
    parent = ProvenanceRecord(
        PARENT_PROVENANCE_ID,
        "parent-r1",
        "source-program",
        "1.0",
        "input.log",
        "a" * 64,
        (),
        "parse",
        (("format", "fixture"),),
    )
    provenance = ProvenanceRecord(
        PROVENANCE_ID,
        "provenance-r1",
        "analysis-program",
        "2.0",
        "result.json",
        "b" * 64,
        (PARENT_PROVENANCE_ID,),
        "derive",
        (("threshold", 0.1),),
    )
    unit = "hartree" if dataset_status is not DatasetStatus.AMBIGUOUS else "unknown"
    dataset = PropertyDataset(
        DATASET_ID,
        "dataset-r1",
        "return_energy",
        "global",
        ArrayData(numpy.asarray(-1.1), (), unit),
        dataset_status,
        CALCULATION_ID,
        (PROVENANCE_ID,),
    )
    metadata = CalculationMetadata(
        "energy", "HF", "sto-3g", 0, 1, "fixture-engine", "1.2.3"
    )
    calculation = CalculationRecord(
        CALCULATION_ID,
        "calculation-r1",
        calculation_status,
        (),
        (),
        (DATASET_ID,),
        (PROVENANCE_ID,),
        metadata,
    )
    result = QCProject(PROJECT_ID, "0.1")
    result.commit(
        ImportBatch(
            calculations=(calculation,),
            datasets=(dataset,),
            provenance=(parent, provenance),
        )
    )
    return result


def recipe_and_plan():
    recipe = builtin_recipes()["tddft_uvvis"]
    plan = RecipePlan(
        recipe.recipe_id,
        recipe.version,
        (RecipeBinding("states", "dataset", DATASET_ID, "dataset-r1"),),
        (("fwhm", 10.0), ("profile", "stick")),
        "c" * 64,
    )
    return recipe, plan


class AnalysisReportTests(unittest.TestCase):
    def test_manifest_collects_linked_dataset_provenance_recipe_and_citations(self):
        recipe, plan = recipe_and_plan()
        report = build_analysis_report(
            project(),
            title="H2 analysis",
            calculation_ids=(CALCULATION_ID,),
            recipe=recipe,
            recipe_plan=plan,
        )

        self.assertEqual(report["schema_name"], "chemblender_analysis_report")
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["status"], "complete")
        self.assertEqual([item["id"] for item in report["datasets"]], [str(DATASET_ID)])
        self.assertEqual(
            [item["id"] for item in report["provenance"]],
            sorted((str(PROVENANCE_ID), str(PARENT_PROVENANCE_ID))),
        )
        self.assertEqual(report["recipe"]["derivation_key"], "c" * 64)
        self.assertEqual(report["recipe"]["citations"][0]["key"], "cclib")
        self.assertEqual(
            report["calculations"][0]["metadata"]["unit_convention"],
            "ChemBlender normalized units",
        )

    def test_order_and_rendering_are_deterministic(self):
        recipe, plan = recipe_and_plan()
        first = build_analysis_report(
            project(),
            title="H2 | deterministic\nreport",
            calculation_ids=(CALCULATION_ID,),
            dataset_ids=(DATASET_ID,),
            recipe=recipe,
            recipe_plan=plan,
        )
        second = build_analysis_report(
            project(),
            title="H2 | deterministic\nreport",
            dataset_ids=(DATASET_ID,),
            calculation_ids=(CALCULATION_ID,),
            recipe_plan=plan,
            recipe=recipe,
        )

        first_json = json.dumps(first, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        second_json = json.dumps(second, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.assertEqual(first_json, second_json)
        self.assertEqual(
            render_analysis_report_markdown(first),
            render_analysis_report_markdown(second),
        )
        self.assertIn("H2 \\| deterministic report", render_analysis_report_markdown(first))

    def test_failed_and_ambiguous_inputs_are_not_reported_as_valid_conclusions(self):
        report = build_analysis_report(
            project(
                calculation_status=CalculationStatus.FAILED,
                dataset_status=DatasetStatus.AMBIGUOUS,
            ),
            title="Failed analysis",
            calculation_ids=(CALCULATION_ID,),
        )

        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["datasets"][0]["status"], "ambiguous")
        self.assertGreaterEqual(len(report["warnings"]), 2)
        markdown = render_analysis_report_markdown(report)
        self.assertIn("不能作为有效计算结论", markdown)
        self.assertIn("ambiguous", markdown)

    def test_artifacts_must_exist_inside_root_and_bundle_is_atomic_and_stable(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            artifact_path = root / "figures" / "density.png"
            artifact_path.parent.mkdir()
            artifact_path.write_bytes(b"image")
            artifact = describe_report_artifact(
                root, "figures/density.png", role="density_surface", media_type="image/png"
            )
            self.assertEqual(artifact["path"], "figures/density.png")
            self.assertEqual(len(artifact["sha256"]), 64)

            report = build_analysis_report(
                project(),
                title="Artifact report",
                dataset_ids=(DATASET_ID,),
                artifacts=(artifact,),
            )
            manifest_path, markdown_path = write_analysis_report_bundle(
                root / "report", report
            )
            self.assertTrue(manifest_path.is_file())
            self.assertTrue(markdown_path.is_file())
            before = manifest_path.read_bytes()
            with self.assertRaises(AnalysisReportError):
                write_analysis_report_bundle(root / "report", report)
            self.assertEqual(manifest_path.read_bytes(), before)

            with self.assertRaises(AnalysisReportError):
                describe_report_artifact(
                    root, "../escape.png", role="bad", media_type="image/png"
                )
            with self.assertRaises(AnalysisReportError):
                describe_report_artifact(
                    root, "missing.png", role="bad", media_type="image/png"
                )

    def test_unknown_selection_and_stale_recipe_binding_are_rejected(self):
        with self.assertRaises(AnalysisReportError):
            build_analysis_report(
                project(), title="Unknown", dataset_ids=(UUID(int=99),)
            )

        recipe, plan = recipe_and_plan()
        stale = RecipePlan(
            plan.recipe_id,
            plan.recipe_version,
            (RecipeBinding("states", "dataset", DATASET_ID, "stale"),),
            plan.parameters,
            plan.derivation_key,
        )
        with self.assertRaises(AnalysisReportError):
            build_analysis_report(
                project(),
                title="Stale",
                dataset_ids=(DATASET_ID,),
                recipe=recipe,
                recipe_plan=stale,
            )

    def test_manifest_validation_is_strict_and_core_import_remains_blender_free(self):
        report = build_analysis_report(
            project(), title="Strict", dataset_ids=(DATASET_ID,)
        )
        report["datasets"][0]["unexpected"] = True
        with self.assertRaises(AnalysisReportError):
            validate_analysis_report(report)

        subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; from ChemBlender.core import build_analysis_report; "
                "assert 'bpy' not in sys.modules",
            ],
            check=True,
            cwd=Path(__file__).resolve().parents[1],
        )


if __name__ == "__main__":
    unittest.main()
