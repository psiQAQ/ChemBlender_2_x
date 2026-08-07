import ast
import hashlib
import json
import re
import unittest
from pathlib import Path

from ChemBlender.core import FrameSet
from ChemBlender.core.cjson_adapter import parse_cjson
from ChemBlender.core.cube import parse_cube
from ChemBlender.core.formats.extxyz import parse_extxyz
from ChemBlender.core.formats.mol2 import parse_mol2
from ChemBlender.core.formats.pdb import parse_pdb
from ChemBlender.core.formats.poscar import parse_poscar
from ChemBlender.core.formats.pqr import parse_pqr
from ChemBlender.core.qcschema_adapter import parse_qcschema
from ChemBlender.core.xyz import parse_xyz


ROOT = Path(__file__).resolve().parents[1]
DOC_ROOT = ROOT / "docs" / "user" / "workflows"
EXAMPLE_ROOT = ROOT / "examples" / "user-workflows"
RUNNER = EXAMPLE_ROOT / "scripts" / "run_ui_workflows.py"
RUNTIME_RESULT = EXAMPLE_ROOT / "results" / "local-2.4.0.json"
EXPECTED_FAMILIES = (
    "cif",
    "cjson",
    "cube",
    "extxyz",
    "legacy",
    "mol",
    "mol2",
    "pdb",
    "poscar",
    "pqr",
    "qcschema",
    "sdf",
    "smiles",
    "xyz",
)
EXPECTED_OUTPUT_BUNDLES = ("legacy-migration", "workflow-project")
EXPECTED_DOCS = (
    "README.md",
    "01-import.md",
    "02-process.md",
    "03-visualize.md",
    "04-export.md",
    "05-project-lifecycle.md",
    "06-agent-and-mcp.md",
    "07-agent-beyond-plugin.md",
    "formats.md",
    "reviews/README.md",
    "reviews/template.md",
)
REQUIRED_RECORD_KEYS = {
    "path",
    "family",
    "role",
    "source_platform",
    "source_id",
    "source_url",
    "retrieved_at",
    "license",
    "license_url",
    "derivation",
    "source_sha256",
    "sha256",
    "bytes",
    "runtime",
    "expected",
    "workflow",
    "metrics",
    "specifications",
    "documentation",
}
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")
TEXT_FENCE = re.compile(r"```text\s+(.*?)```", re.DOTALL)
PLUGIN_WORKFLOW_DOCS = (
    "01-import.md",
    "02-process.md",
    "03-visualize.md",
    "04-export.md",
    "05-project-lifecycle.md",
    "06-agent-and-mcp.md",
)
REVIEW_CASE_IDS = (
    "ENV",
    "IMP",
    "DATA",
    "VIEW",
    "EXP",
    "LIFE",
    "MIG",
    "AGENT",
    "OUTSIDE",
)
RUNNER_CASE_IDS = (
    "ENV",
    "IMP-XYZ",
    "IMP-SMILES",
    "IMP-CANCEL",
    "DATA-TOPOLOGY",
    "DATA-CRYSTAL",
    "DATA-BIOLOGICAL",
    "VIEW-CUBE",
    "EXP-FORMATS",
    "LIFE-SAVE-REOPEN-PREP",
    "MIG-PREVIEW-PREP",
)
REPRESENTATIVE_CASE_IDS = (
    "REP-MOLECULAR",
    "REP-TRAJECTORY",
    "REP-BIOLOGICAL",
    "REP-CRYSTAL",
    "REP-GRID",
    "REP-SAVE-REOPEN-PREP",
)
REPRESENTATIVE_CASE_INPUTS = {
    "REP-MOLECULAR": (
        "inputs/cjson/avogadro-phthalocyanine.cjson",
        "inputs/mol/ain-aspirin-v2000.mol",
        "inputs/mol/ta1-paclitaxel-v3000.mol",
        "inputs/mol2/openbabel-5sun-protein.mol2",
        "inputs/qcschema/molssi-water-gradient-hf.json",
        "inputs/sdf/ccd-3d-showcase.sdf",
        "inputs/smiles/ta1-paclitaxel-isomeric.smi",
        "inputs/xyz/ta1-paclitaxel-ccd.xyz",
    ),
    "REP-TRAJECTORY": ("inputs/extxyz/aspirin-rmd17-32.extxyz",),
    "REP-BIOLOGICAL": (
        "inputs/pdb/1d3z-ubiquitin-nmr.pdb",
        "inputs/pqr/apbs-protein-rna-nb.pqr",
    ),
    "REP-CRYSTAL": (
        "inputs/cif/cod-4503272-caffeine-cocrystal.cif",
        "inputs/poscar/cod-9012293-diamond-2x2x2.CONTCAR",
        "inputs/poscar/cod-9012293-diamond.POSCAR",
    ),
    "REP-GRID": ("inputs/cube/h2-lcao-1s-density-64.cube",),
    "REP-SAVE-REOPEN-PREP": (),
}
REPRESENTATIVE_OUTPUTS = (
    "outputs/representative/molecular/molecular.blend",
    "outputs/representative/trajectory/trajectory.blend",
    "outputs/representative/biological/biological.blend",
    "outputs/representative/crystal/crystal.blend",
    "outputs/representative/grid/grid.blend",
)


class UserWorkflowContractTests(unittest.TestCase):
    def runner_tree(self):
        self.assertTrue(RUNNER.is_file(), RUNNER)
        return ast.parse(RUNNER.read_text(encoding="utf-8"), filename=str(RUNNER))

    def manifest(self):
        path = EXAMPLE_ROOT / "manifest.json"
        self.assertTrue(path.is_file(), path)
        return json.loads(path.read_text(encoding="utf-8"))

    def local_link_targets(self, path):
        targets = set()
        for raw_target in MARKDOWN_LINK.findall(path.read_text(encoding="utf-8")):
            raw_target = raw_target.strip().strip("<>").split("#", 1)[0]
            if not raw_target or raw_target.startswith(("http://", "https://", "mailto:")):
                continue
            target = (path.parent / raw_target).resolve()
            self.assertTrue(target.is_relative_to(ROOT.resolve()), (path, raw_target))
            self.assertTrue(target.exists(), (path, raw_target))
            targets.add(target)
        return targets

    def test_workflow_document_inventory_and_links(self):
        paths = tuple(DOC_ROOT / name for name in EXPECTED_DOCS)
        for path in paths:
            self.assertTrue(path.is_file(), path)
        for path in paths:
            self.local_link_targets(path)

    def test_repository_entrypoints_link_to_workflow_index(self):
        index = (DOC_ROOT / "README.md").resolve()
        for path in (
            ROOT / "README.md",
            ROOT / "docs" / "README.md",
            ROOT / "docs" / "user" / "2.4.0-experience-review.md",
        ):
            self.assertIn(index, self.local_link_targets(path), path)
        self.assertIn(
            (EXAMPLE_ROOT / "README.md").resolve(),
            self.local_link_targets(ROOT / "README.md"),
        )

    def test_every_sample_is_linked_from_the_workflow_documents(self):
        linked = set()
        for name in EXPECTED_DOCS:
            path = DOC_ROOT / name
            if path.is_file():
                linked.update(self.local_link_targets(path))
        expected = {
            (EXAMPLE_ROOT / record["path"]).resolve()
            for record in self.manifest()["files"]
        }
        expected.update(
            (EXAMPLE_ROOT / record["documentation"]).resolve()
            for record in self.manifest()["files"]
        )
        expected.update(
            (EXAMPLE_ROOT / bundle["blend"]).resolve()
            for bundle in self.manifest()["output_bundles"]
        )
        expected.update(
            (EXAMPLE_ROOT / bundle["sidecar"] / "manifest.json").resolve()
            for bundle in self.manifest()["output_bundles"]
        )
        self.assertEqual(expected - linked, set())

    def test_workflow_overview_explains_representative_corpus_boundary(self):
        document = "\n".join(
            (DOC_ROOT / name).read_text(encoding="utf-8")
            for name in EXPECTED_DOCS
            if (DOC_ROOT / name).is_file()
        )
        for term in (
            "contract",
            "representative",
            "分辨率",
            "来源",
            "许可证",
            "人工插件使用体验检阅",
        ):
            self.assertIn(term, document)

    def test_plugin_workflow_prompts_keep_the_public_ui_boundary(self):
        for name in PLUGIN_WORKFLOW_DOCS:
            path = DOC_ROOT / name
            self.assertTrue(path.is_file(), path)
            prompts = TEXT_FENCE.findall(path.read_text(encoding="utf-8"))
            self.assertTrue(prompts, path)
            contract = "\n".join(prompts)
            for term in (
                "Blender MCP",
                "bpy.ops.chemblender",
                "Operator RNA",
                "private modules",
                ".cbq",
                "confirmation",
            ):
                self.assertIn(term, contract, (path, term))

    def test_guides_do_not_contain_executable_private_imports(self):
        forbidden = re.compile(r"^\s*(?:from|import)\s+ChemBlender\b", re.MULTILINE)
        for name in EXPECTED_DOCS:
            path = DOC_ROOT / name
            if path.is_file():
                self.assertIsNone(forbidden.search(path.read_text(encoding="utf-8")), path)

    def test_outside_plugin_examples_are_explicitly_scoped(self):
        path = DOC_ROOT / "07-agent-beyond-plugin.md"
        self.assertTrue(path.is_file(), path)
        document = path.read_text(encoding="utf-8")
        self.assertGreaterEqual(document.count("这不是 ChemBlender 插件能力"), 5)
        self.assertNotIn("bpy.ops.chemblender", document)
        for term in ("evaluated geometry", "没有材质", "空白、全黑、严重裁切"):
            self.assertIn(term, document)

    def test_manual_experience_gate_blocks_release_when_incomplete(self):
        policy_paths = (
            ROOT / ".agents" / "reference" / "dependencies-and-release.md",
            ROOT / "docs" / "development" / "branch-and-release.md",
        )
        for path in policy_paths:
            document = path.read_text(encoding="utf-8")
            for term in (
                "人工插件使用体验检阅",
                "reviews/<version>.md",
                "Incomplete",
                "Failed",
                "Blocked",
                "tag/Release",
            ):
                self.assertIn(term, document, (path, term))

        dependency_policy = policy_paths[0].read_text(encoding="utf-8")
        self.assertLess(
            dependency_policy.index("## Local Extension Gates"),
            dependency_policy.index("## 人工插件使用体验检阅"),
        )
        self.assertLess(
            dependency_policy.index("## 人工插件使用体验检阅"),
            dependency_policy.index("## Release Gates"),
        )

        branch_policy = policy_paths[1].read_text(encoding="utf-8")
        self.assertLess(
            branch_policy.index("Run all local gates"),
            branch_policy.index("人工插件使用体验检阅"),
        )
        self.assertLess(
            branch_policy.index("人工插件使用体验检阅"),
            branch_policy.index("Create and push one annotated tag"),
        )

    def test_manual_review_template_has_required_cases_and_evidence(self):
        path = DOC_ROOT / "reviews" / "template.md"
        self.assertTrue(path.is_file(), path)
        template = path.read_text(encoding="utf-8")
        for case_id in REVIEW_CASE_IDS:
            self.assertIn(f"| {case_id} |", template)
        for term in (
            "Environment",
            "Git commit",
            "Package SHA-256",
            "UI result",
            "Agent/MCP result",
            "Duration",
            "Evidence",
            "Findings",
            "Fix commit",
            "Rerun result",
            "File size",
            "File SHA-256",
            "Reopen state",
            "Passed / Failed / Blocked",
        ):
            self.assertIn(term, template)

    def test_runner_uses_only_public_blender_boundaries(self):
        tree = self.runner_tree()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules = (node.module or "",)
            else:
                modules = ()
            self.assertFalse(
                any(name.startswith(("ChemBlender", "bl_ext")) for name in modules),
                (RUNNER, getattr(node, "lineno", None), modules),
            )
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = (
                    node.targets
                    if isinstance(node, ast.Assign)
                    else (node.target,)
                )
                for target in targets:
                    for child in ast.walk(target):
                        if isinstance(child, ast.Subscript) and isinstance(
                            child.slice, ast.Constant
                        ):
                            key = child.slice.value
                            self.assertFalse(
                                isinstance(key, str) and key.startswith("cb_"),
                                (RUNNER, getattr(node, "lineno", None), key),
                            )

        source = RUNNER.read_text(encoding="utf-8")
        for token in (
            "cbq.write",
            "write_project",
            "ProjectSession",
            "QCProject",
        ):
            self.assertNotIn(token, source)
        self.assertIn("bpy.ops.chemblender", source)

    def test_runner_declares_cases_and_atomic_report_contract(self):
        tree = self.runner_tree()
        constants = {
            value.value
            for value in ast.walk(tree)
            if isinstance(value, ast.Constant) and isinstance(value.value, str)
        }
        self.assertTrue(set(RUNNER_CASE_IDS) <= constants)
        self.assertTrue(
            {
                "schema_version",
                "runtime",
                "cases",
                "deferred",
                "operators",
                "evidence",
                "outputs",
                "elapsed_seconds",
                "error",
            }
            <= constants
        )

    def test_runner_declares_representative_inputs_operators_and_outputs(self):
        tree = self.runner_tree()

        def literal(name):
            node = next(
                item
                for item in tree.body
                if isinstance(item, ast.Assign)
                and any(
                    isinstance(target, ast.Name) and target.id == name
                    for target in item.targets
                )
            )
            return ast.literal_eval(node.value)

        case_ids = literal("CASE_IDS")
        case_inputs = literal("CASE_INPUTS")
        self.assertEqual(case_ids[-len(REPRESENTATIVE_CASE_IDS) :], REPRESENTATIVE_CASE_IDS)
        self.assertEqual(
            {
                case_id: tuple(case_inputs[case_id])
                for case_id in REPRESENTATIVE_CASE_IDS
            },
            REPRESENTATIVE_CASE_INPUTS,
        )
        constants = {
            value.value
            for value in ast.walk(tree)
            if isinstance(value, ast.Constant) and isinstance(value.value, str)
        }
        for value in REPRESENTATIVE_OUTPUTS:
            self.assertIn(value, constants)
        for operator in (
            "quick_import",
            "confirm_import",
            "derive_crystal_symmetry",
            "create_biological_view",
            "play_biological_models",
            "select_biological_atoms",
            "resolve_grid_semantics",
            "create_grid_view",
            "project_link_recovery",
            "save_as_mainfile",
            "save_mainfile",
        ):
            self.assertIn(operator, constants)

    def test_runtime_result_is_sanitized_and_complete(self):
        self.assertTrue(RUNTIME_RESULT.is_file(), RUNTIME_RESULT)
        report = json.loads(RUNTIME_RESULT.read_text(encoding="utf-8"))
        self.assertEqual(report["schema_version"], "1")
        self.assertEqual(report["product_version"], "2.4.0")
        self.assertRegex(report["runner_commit"], r"^[0-9a-f]{40}$")
        self.assertEqual(
            report["package"]["sha256"],
            "079b00b8a47dba56298eb9635b5a5dff76bcb1c4983aeefe5dfe360cc149c79d",
        )
        cases = {case["id"]: case for case in report["cases"]}
        self.assertEqual(tuple(cases), RUNNER_CASE_IDS)
        self.assertEqual({case["status"] for case in cases.values()}, {"passed"})
        self.assertEqual(report["deferred"], [])
        self.assertIn(
            "bpy.ops.wm.save_mainfile",
            cases["LIFE-SAVE-REOPEN-PREP"]["operator_ids"],
        )
        self.assertIn(
            "bpy.ops.chemblender.migrate_legacy_scene",
            cases["MIG-PREVIEW-PREP"]["operator_ids"],
        )
        self.assertEqual(
            tuple(bundle["id"] for bundle in report["tracked_outputs"]),
            EXPECTED_OUTPUT_BUNDLES,
        )
        self.assertEqual(report["outside_plugin"]["status"], "passed")
        self.assertTrue(all(report["outside_plugin"]["scientific_state_unchanged"].values()))
        serialized = json.dumps(report, ensure_ascii=False)
        self.assertNotIn(str(ROOT), serialized)
        self.assertNotIn(".agents/cache", serialized.replace("\\", "/"))
        source = RUNNER.read_text(encoding="utf-8")
        self.assertIn("NamedTemporaryFile", source)
        self.assertIn(".replace(", source)

    def test_runner_activates_matching_structure_view_for_context_operator(self):
        source = RUNNER.read_text(encoding="utf-8")
        activation = 'context.activate_structure_view(structure["entity_id"])'
        toggle = 'context.call_chem("toggle_selective_constraints")'
        self.assertIn(activation, source)
        self.assertLess(source.index(activation), source.index(toggle))
        for token in (
            'obj.get("cb_structure_id")',
            "obj.select_set(True)",
            "bpy.context.view_layer.objects.active = obj",
        ):
            self.assertIn(token, source)

    def test_biological_playback_sample_has_compatible_model_frames(self):
        path = EXAMPLE_ROOT / "inputs" / "pdb" / "model-trajectory.pdb"
        batch = parse_pdb(path)
        frames = tuple(
            dataset for dataset in batch.datasets if isinstance(dataset, FrameSet)
        )
        self.assertEqual(len(batch.structures), 1)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].data.shape, (2, 2, 3))

    def test_runner_handles_the_expected_export_confirmation_rejection(self):
        source = RUNNER.read_text(encoding="utf-8")
        for token in (
            'details["error"] = f"{type(error).__name__}: {error}"',
            "except RuntimeError as error:",
            "Loss/Partial/Ambiguous export requires explicit confirmation",
        ):
            self.assertIn(token, source)

    def test_runner_resume_preserves_operator_and_elapsed_evidence(self):
        source = RUNNER.read_text(encoding="utf-8")
        for token in (
            'list(previous["operators"]) if previous else []',
            'dict(previous["evidence"]) if previous else {}',
            'list(previous["outputs"]) if previous else []',
            'float(previous["elapsed_seconds"]) if previous else 0.0',
            "previous_elapsed + time.perf_counter() - started",
        ):
            self.assertIn(token, source)

    def test_first_project_save_documents_and_runs_the_second_save_step(self):
        source = RUNNER.read_text(encoding="utf-8")
        self.assertIn('context.call_wm("save_as_mainfile"', source)
        self.assertIn('context.call_wm("save_mainfile")', source)
        lifecycle = (DOC_ROOT / "05-project-lifecycle.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("再次选择 `Save Project`", lifecycle)

    def test_manifest_covers_each_base_format_family(self):
        manifest = self.manifest()
        self.assertEqual(manifest["schema_version"], "2")
        families = tuple(
            sorted({record["family"] for record in manifest["files"]})
        )
        self.assertEqual(families, EXPECTED_FAMILIES)

    def test_manifest_paths_are_unique_and_ordinally_sorted(self):
        records = self.manifest()["files"]
        paths = [record["path"] for record in records]
        self.assertEqual(paths, sorted(paths))
        self.assertEqual(len(paths), len(set(paths)))
        for record in records:
            self.assertTrue(REQUIRED_RECORD_KEYS <= record.keys())

    def test_manifest_matches_tracked_file_bytes(self):
        for record in self.manifest()["files"]:
            path = EXAMPLE_ROOT / record["path"]
            data = path.read_bytes()
            self.assertEqual(record["bytes"], len(data), path)
            self.assertEqual(
                record["sha256"], hashlib.sha256(data).hexdigest(), path
            )
            self.assertLessEqual(len(data), 100 * 1024 * 1024, path)
            if len(data) > 50 * 1024 * 1024:
                self.assertTrue(record.get("size_exception_reason"), path)

    def test_output_bundles_match_every_tracked_file(self):
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
        self.assertIn("examples/user-workflows/outputs/** -text", attributes)
        bundles = self.manifest()["output_bundles"]
        self.assertEqual(tuple(bundle["id"] for bundle in bundles), EXPECTED_OUTPUT_BUNDLES)
        records = [record for bundle in bundles for record in bundle["files"]]
        paths = [record["path"] for record in records]
        tracked = sorted(
            path.relative_to(EXAMPLE_ROOT).as_posix()
            for path in (EXAMPLE_ROOT / "outputs").rglob("*")
            if path.is_file()
        )
        self.assertEqual(paths, tracked)
        self.assertEqual(len(paths), len(set(paths)))
        for bundle in bundles:
            self.assertEqual(bundle["cold_reopen"], "passed")
            self.assertTrue((EXAMPLE_ROOT / bundle["blend"]).is_file())
            self.assertTrue((EXAMPLE_ROOT / bundle["sidecar"]).is_dir())
            self.assertTrue(bundle["covers"])
        for record in records:
            path = EXAMPLE_ROOT / record["path"]
            data = path.read_bytes()
            self.assertEqual(record["bytes"], len(data), path)
            self.assertEqual(record["sha256"], hashlib.sha256(data).hexdigest(), path)
            self.assertLess(len(data), 50 * 1024 * 1024, path)

    def test_builtin_samples_parse_to_expected_entities(self):
        cases = (
            (
                "inputs/cjson/water-results.cjson",
                parse_cjson,
                ("structures", "cjson_envelopes"),
            ),
            (
                "inputs/cube/two-datasets.cube",
                parse_cube,
                ("structures", "datasets"),
            ),
            (
                "inputs/extxyz/carbon-trajectory.extxyz",
                parse_extxyz,
                ("structures",),
            ),
            (
                "inputs/mol2/substructure.mol2",
                parse_mol2,
                ("structures", "topologies"),
            ),
            (
                "inputs/pdb/model-trajectory.pdb",
                parse_pdb,
                ("structures", "biological_hierarchies", "datasets"),
            ),
            ("inputs/pdb/multimodel.pdb", parse_pdb, ("structures",)),
            ("inputs/poscar/si.POSCAR", parse_poscar, ("structures",)),
            ("inputs/poscar/velocities.CONTCAR", parse_poscar, ("structures",)),
            (
                "inputs/pqr/with-chain.pqr",
                parse_pqr,
                ("structures", "biological_hierarchies", "datasets"),
            ),
            (
                "inputs/qcschema/atomic-result.json",
                parse_qcschema,
                ("structures", "qcschema_envelopes"),
            ),
            ("inputs/xyz/water.xyz", parse_xyz, ("structures",)),
        )
        for relative, parser, attributes in cases:
            with self.subTest(path=relative):
                batch = parser(EXAMPLE_ROOT / relative)
                for attribute in attributes:
                    self.assertTrue(getattr(batch, attribute), attribute)

    def test_dependency_backed_samples_are_declared_for_blender_runtime(self):
        records = self.manifest()["files"]
        declared = {
            (record["family"], record["runtime"])
            for record in records
            if record["runtime"] in {"gemmi", "rdkit"}
        }
        self.assertEqual(
            declared,
            {
                ("cif", "gemmi"),
                ("mol", "rdkit"),
                ("sdf", "rdkit"),
                ("smiles", "rdkit"),
            },
        )


if __name__ == "__main__":
    unittest.main()
