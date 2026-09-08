import hashlib
import importlib.util
import json
import subprocess
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

import numpy

from ChemBlender.core import (
    AnalysisReportError,
    ArrayData,
    CalculationMetadata,
    CalculationRecord,
    CalculationStatus,
    DensityMatrixLevel,
    DatasetStatus,
    ImportBatch,
    PropertyDataset,
    ProvenanceRecord,
    QCProject,
    RecipeBinding,
    RecipePlan,
    SourceRecord,
    SourceRevision,
    build_analysis_report,
    builtin_recipes,
    describe_report_artifact,
    render_analysis_report_markdown,
    validate_analysis_report,
    write_analysis_report_bundle,
)
from ChemBlender.core.iodata_adapter import adapt_iodata, parse_iodata_wavefunction
from tests.test_iodata_adapter import fake_iodata


PROJECT_ID = UUID("10000000-0000-0000-0000-000000000001")
CALCULATION_ID = UUID("20000000-0000-0000-0000-000000000002")
DATASET_ID = UUID("30000000-0000-0000-0000-000000000003")
PROVENANCE_ID = UUID("40000000-0000-0000-0000-000000000004")
PARENT_PROVENANCE_ID = UUID("50000000-0000-0000-0000-000000000005")
WATER_FCHK = (
    Path(__file__).resolve().parents[1]
    / "submodules/iodata/iodata/test/data/water_sto3g_hf_g03.fchk"
)
HAS_WAVEFUNCTION_STACK = all(
    importlib.util.find_spec(name) is not None for name in ("iodata", "gbasis")
)


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
    def test_scientific_parents_follow_entity_references_without_fabricating_records(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "synthetic.fchk"
            source.write_bytes(b"synthetic wavefunction fixture")
            imported = adapt_iodata(fake_iodata(), source, iodata_version="synthetic")
        parsed = imported.provenance[0]
        charge_record = replace(parsed, id=uuid4(), operation="nuclear_charges")
        calculation_record = replace(parsed, id=uuid4(), operation="calculation")
        unrelated_record = replace(parsed, id=uuid4(), operation="unrelated")
        calculation = replace(project().calculations[CALCULATION_ID],
                              provenance_ids=(calculation_record.id,))
        # Only the basis has the parser provenance: the closure must follow
        # OrbitalSet/DensityMatrix -> BasisSet, not only parent provenance_ids.
        orbitals = replace(imported.orbital_sets[0], provenance_ids=())
        matrix = replace(imported.density_matrices[0], provenance_ids=(),
                         source_calculation=calculation.id)
        charges = replace(imported.datasets[0], provenance_ids=(charge_record.id,))
        derived = replace(parsed, id=PROVENANCE_ID, operation="derived_grid",
                          parent_ids=(matrix.id, charges.id, orbitals.id))

        class UnreadArray:
            shape = ()
            dtype = "float64"

            def __array__(self, *args, **kwargs):
                raise AssertionError("report must not read scientific arrays")

        selected = replace(project().datasets[DATASET_ID], source_calculation=None,
                           data=ArrayData(UnreadArray(), (), "hartree"))
        value = QCProject(PROJECT_ID, "0.1")
        value.commit(ImportBatch(
            structures=imported.structures, basis_sets=imported.basis_sets,
            orbital_sets=(orbitals,), density_matrices=(matrix,),
            calculations=(calculation,), datasets=(charges, selected),
            provenance=(parsed, charge_record, calculation_record, unrelated_record, derived),
        ))
        report = build_analysis_report(value, title="Scientific ancestry", dataset_ids=(selected.id,))
        records = {item["id"]: item for item in report["provenance"]}
        self.assertEqual(set(records), {str(item.id) for item in
                                      (parsed, charge_record, calculation_record, derived)})
        self.assertEqual(records[str(derived.id)]["parent_ids"],
                         sorted(str(item) for item in derived.parent_ids))
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual([item["id"] for item in report["datasets"]], [str(selected.id)])
        self.assertEqual(validate_analysis_report(report), report)
        self.assertEqual(build_analysis_report(value, title="Scientific ancestry",
                                              dataset_ids=(selected.id,)), report)
        # The selected dataset/calculation cycle terminates, but a missing
        # scientific parent or a missing source record remains an error.
        value.orbital_sets.pop(orbitals.id)
        with self.assertRaisesRegex(AnalysisReportError, "missing"):
            build_analysis_report(value, title="Missing parent", dataset_ids=(selected.id,))
        value.orbital_sets[orbitals.id] = orbitals
        value.provenance.pop(parsed.id)
        with self.assertRaisesRegex(AnalysisReportError, "missing"):
            build_analysis_report(value, title="Missing provenance", dataset_ids=(selected.id,))

    def test_selected_dataset_reaches_source_calculation_without_direct_provenance(self):
        value = project()
        value.datasets[DATASET_ID] = replace(value.datasets[DATASET_ID], provenance_ids=())
        report = build_analysis_report(value, title="Calculation source", dataset_ids=(DATASET_ID,))
        self.assertEqual({item["id"] for item in report["provenance"]},
                         {str(PROVENANCE_ID), str(PARENT_PROVENANCE_ID)})

    def test_source_revision_parents_do_not_pull_reverse_ownership_or_parameter_uuids(self):
        original = project()
        source = SourceRecord(uuid4(), "input.log", "file", "2026-09-08T00:00:00Z")
        unrelated = replace(original.provenance[PARENT_PROVENANCE_ID], id=uuid4())
        revision = SourceRevision(
            uuid4(), source.id, "a" * 64, 1, "input.log", "file", "input.log",
            "chemblender.builtin", "fixture", "1", "1.0-rc1", "b" * 64, "c" * 64,
            (*original._all_entity_ids(), unrelated.id), (),
        )
        parent = replace(original.provenance[PARENT_PROVENANCE_ID],
                         parent_ids=(source.id, revision.id),
                         parameters=(("opaque_parameter_uuid", uuid4()),))
        value = QCProject(PROJECT_ID, "0.1")
        value.commit(ImportBatch(
            sources=(source,), source_revisions=(revision,),
            calculations=tuple(original.calculations.values()),
            datasets=tuple(original.datasets.values()),
            provenance=(original.provenance[PROVENANCE_ID], parent, unrelated),
        ))
        report = build_analysis_report(value, title="Source ownership", dataset_ids=(DATASET_ID,))
        self.assertEqual({item["id"] for item in report["provenance"]},
                         {str(PROVENANCE_ID), str(PARENT_PROVENANCE_ID)})
        self.assertEqual(report["provenance"][1]["parent_ids"],
                         sorted((str(source.id), str(revision.id))))

    @unittest.skipUnless(HAS_WAVEFUNCTION_STACK and WATER_FCHK.is_file(),
                         "optional IOData/GBasis and pinned water FCHK fixture are required")
    def test_real_water_fchk_mo_density_and_esp_report_bundle(self):
        from ChemBlender.core.wavefunction_grid import evaluate_molecular_orbital_grid
        from ChemBlender.core.wavefunction_observables import (
            derive_density_matrix_from_orbitals,
            evaluate_density_matrix_grid,
            evaluate_electrostatic_potential_grid,
        )

        digest = hashlib.sha256(WATER_FCHK.read_bytes()).hexdigest()
        self.assertEqual(digest, "aa8dec77849d4f9e1e9dc9357c80f5b4d6ba1efc3bbc17da6c59754bdaed0816")
        imported = parse_iodata_wavefunction(WATER_FCHK)
        value = QCProject(PROJECT_ID, "0.1")
        value.commit(imported)
        structure, basis, orbitals = (imported.structures[0], imported.basis_sets[0],
                                     imported.orbital_sets[0])
        parameters = dict(origin=(-2.1, -1.3, -0.7),
                          step_vectors=((0.8, 0.1, 0), (0, 0.9, 0.1), (0, 0, 0.7)),
                          shape=(3, 3, 3), chunk_size=7)
        mo = evaluate_molecular_orbital_grid(structure, basis, orbitals,
                                             channel="restricted", orbital_index=4, **parameters)
        reconstructed = derive_density_matrix_from_orbitals(
            structure, basis, orbitals, level=DensityMatrixLevel.SCF,
            source_provenance=imported.provenance,
        )
        matrix = reconstructed.density_matrices[0]
        density = evaluate_density_matrix_grid(structure, basis, matrix, **parameters)
        esp = evaluate_electrostatic_potential_grid(structure, basis, matrix,
                                                   imported.datasets[0], **parameters)
        for batch in (mo, reconstructed, density, esp):
            value.commit(batch)
        for batch in (mo, density, esp):
            with self.subTest(role=batch.datasets[0].semantic_role):
                numpy.testing.assert_array_equal(numpy.isfinite(batch.datasets[0].data.values), True)
                report = build_analysis_report(value, title="Water RHF/STO-3G",
                                               dataset_ids=(batch.datasets[0].id,))
                records = {item["id"]: item for item in report["provenance"]}
                self.assertEqual(records[str(imported.provenance[0].id)]["source_hash"], digest)
                self.assertEqual(records[str(imported.provenance[0].id)]["source"], str(WATER_FCHK.resolve()))
                expected = {str(imported.provenance[0].id), str(batch.provenance[0].id)}
                if batch is not mo:
                    expected.add(str(reconstructed.provenance[0].id))
                self.assertEqual(set(records), expected)
                self.assertFalse(report["calculations"])  # The reader did not import a CalculationRecord.
                self.assertEqual(report["schema_version"], 1)
                with TemporaryDirectory() as directory:
                    manifest, markdown = write_analysis_report_bundle(Path(directory) / "report", report)
                    self.assertEqual(json.loads(manifest.read_text(encoding="utf-8")), report)
                    self.assertEqual(validate_analysis_report(report), report)
                    self.assertIn("evaluate_", markdown.read_text(encoding="utf-8"))

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
