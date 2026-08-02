import unittest
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "quantum-visualization"
WAVE_230_QUEUE_FILES = ()
WAVE_230_ACTIVE_FILES = ()
NEXT_RELEASE_ACTIVE_FILES = ()
NEXT_RELEASE_QUEUED_FILES = ("2.4.0-pqr-export.md",)
NEXT_RELEASE_COMPLETED_FILE = "2.4.0-scope-discovery.md"
MOL2_EXPORT_COMPLETED_FILE = "2.4.0-mol2-export.md"
MOL2_EXPORT_UI_COMPLETED_FILE = "2.4.0-mol2-export-ui.md"
TASK3_SCOPE_COMPLETED_FILE = "2.4.0-task3-scope-discovery.md"
PDB_EXPORT_COMPLETED_FILE = "2.4.0-pdb-export.md"
TASK4_SCOPE_COMPLETED_FILE = "2.4.0-task4-scope-discovery.md"
TASK5_SCOPE_COMPLETED_FILE = "2.4.0-task5-scope-discovery.md"
WAVE_230_COMPLETED_FILE = "2.3.0-wave-3-exchange-mol2-pdb-pqr.md"
WAVE_230_FINAL_COMPLETED_FILE = "2.3.0-wave-4-migration-release.md"


class QuantumVisualizationDocsTests(unittest.TestCase):
    def read_doc(self, relative_path: str) -> str:
        path = ROOT / relative_path
        raw = path.read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), path)
        return raw.decode("utf-8")

    def test_roadmap_entrypoints_exist(self):
        index = self.read_doc("docs/quantum-visualization/README.md")
        roadmap = self.read_doc("docs/quantum-visualization/roadmap.md")
        self.assertIn("roadmap.md", index)
        for phase in range(5):
            self.assertIn(f"Phase {phase}", roadmap)

    def test_230_planning_entrypoints_exist_and_are_discoverable(self):
        entrypoints = (
            "docs/quantum-visualization/2.3.0/README.md",
            "docs/quantum-visualization/2.3.0/audits/2026-07-23-main-deep-audit.md",
            "docs/quantum-visualization/crystal-capability-matrix-v1.json",
            "docs/superpowers/specs/2026-07-23-chemblender-2.3.0-native-platform-design.md",
            "docs/superpowers/plans/2026-07-23-chemblender-2.3.0-master-sequencing.md",
        )
        for relative_path in entrypoints:
            self.read_doc(relative_path)

        docs_index = self.read_doc("docs/README.md")
        quantum_index = self.read_doc("docs/quantum-visualization/README.md")
        agent_index = self.read_doc(".agents/README.md")
        for name in (
            "2.3.0/README.md",
            "2026-07-23-main-deep-audit.md",
            "2026-07-23-chemblender-2.3.0-native-platform-design.md",
            "2026-07-23-chemblender-2.3.0-master-sequencing.md",
        ):
            self.assertTrue(
                any(name in index for index in (docs_index, quantum_index)),
                name,
            )
        for name in (
            *WAVE_230_ACTIVE_FILES,
            *WAVE_230_QUEUE_FILES,
            WAVE_230_COMPLETED_FILE,
            WAVE_230_FINAL_COMPLETED_FILE,
        ):
            self.assertIn(name, agent_index)

    def test_wave4_usability_acceptance_is_repeatable_and_measurable(self):
        index = self.read_doc("docs/quantum-visualization/2.3.0/README.md")
        paths = (
            "docs/quantum-visualization/2.3.0/usability-test-script.md",
            "docs/quantum-visualization/2.3.0/usability-results-rc1.md",
        )
        for path in paths:
            self.assertTrue((ROOT / path).is_file(), path)
        script, results = (self.read_doc(path) for path in paths)
        for name in ("usability-test-script.md", "usability-results-rc1.md"):
            self.assertIn(name, index)
        for term in (
            "XYZ",
            "SDF",
            "Cube",
            "CIF",
            "PDB",
            "diagnostics",
            "conformers",
            "save/reopen",
            "revision",
            "scientific edit",
            "export",
            "legacy",
        ):
            self.assertIn(term, script)
        for field in (
            "Completion",
            "Elapsed time",
            "Errors",
            "Help required",
            "Scientific misunderstanding",
        ):
            self.assertIn(field, script)
            self.assertIn(field, results)
        for severity in ("Blocker", "Major", "Minor"):
            self.assertIn(severity, script)
            self.assertIn(severity, results)
        expected_tasks = {f"U{number:02d}" for number in range(1, 13)}
        for document in (script, results):
            self.assertEqual(
                set(
                    re.findall(
                        r"(?m)^\|\s*(U(?:0[1-9]|1[0-2]))(?:\s|\|)",
                        document,
                    )
                ),
                expected_tasks,
            )
        for contract in (
            "fresh profile",
            "refuse reuse",
            "--python-exit-code",
            "$process.ExitCode",
            "PASS:",
        ):
            self.assertIn(contract, script)
        self.assertIn('"--python-exit-code", "1"', script)
        hashes = (
            "0db367c18fd849897bb5ca0189c50c573bda40ea5db35c565a99f882115356ec",
            "36b05c3cacbcc067714615a49df35cf20973bc8122329194ddaecd249df6c3d4",
            "f2995e826762a85bfb6854e314483175c3d39c2cceef109db3f395ab2e83c06a",
            "a6af8e232fe7b934bf850f8e6b24d396596b79cc1fd38e8ff6eb071c50bf8740",
        )
        for digest in hashes:
            self.assertIn(digest, script)
            self.assertIn(digest, results)
        for marker in (
            "PASS: ChemBlender extension lifecycle",
            "PASS: packaged legacy migration and reopen",
        ):
            self.assertIn(marker, script)
            self.assertIn(marker, results)
        self.assertIn("hybrid", script)
        self.assertIn("packaged Extension", script)
        self.assertIn("hybrid", results)
        self.assertIn("packaged Extension", results)
        self.assertIn("Remote CI: Not Run", results)

        legacy_acceptance = ROOT / "tests" / "blender_usability_legacy.py"
        self.assertTrue(legacy_acceptance.is_file(), legacy_acceptance)
        legacy_source = legacy_acceptance.read_text(encoding="utf-8")
        for operation in (
            "bpy.ops.extensions.package_install_files",
            "bl_ext.user_default.chemblender",
            "bpy.ops.chemblender.preview_legacy_migration",
            "bpy.ops.chemblender.migrate_legacy_scene",
            "bpy.ops.wm.save_mainfile",
            "bpy.ops.wm.open_mainfile",
            'cb_legacy_migration_backup") == "v2"',
            "cb_legacy_migration_project_id",
            "cb_legacy_migration_transaction_id",
            "PASS: packaged legacy migration and reopen",
        ):
            self.assertIn(operation, legacy_source)

    def test_user_guides_describe_verified_product_workflows(self):
        import tomllib

        readme = self.read_doc("README.md")
        for term in (
            "result-first",
            "program-neutral",
            "Windows x64",
            "Blender 5.1",
            "XYZ/extXYZ",
            "MOL V2000/V3000",
            "SDF",
            "SMILES",
            "CIF",
            "POSCAR/CONTCAR",
            "MOL2",
            "PDB/PQR",
            "Cube",
            "CJSON",
            "QCSchema",
            ".blend",
            ".cbq",
            "keep them together",
            "optional backends",
        ):
            self.assertIn(term, readme)

        manifest = tomllib.loads(
            self.read_doc("ChemBlender/blender_manifest.toml")
        )
        tagline = manifest["tagline"]
        self.assertEqual(tagline, tagline.strip())
        self.assertNotIn("\n", tagline)
        self.assertLessEqual(len(tagline), 64)
        self.assertTrue(tagline[-1].isalnum())
        self.assertIn("results", tagline.lower())

        index = self.read_doc("docs/README.md")
        contracts = {
            "quick-import.md": (
                "single file",
                "multiple files",
                "drag and drop",
                "Import Preview",
                "Keep Independent",
                "Accept Group",
                "Default View",
                "Cancel",
            ),
            "project-browser.md": (
                "By Source",
                "By Data",
                "Complete",
                "Partial",
                "Ambiguous",
                "Update Selected Views",
                "Comparison View",
                "Keep Current",
            ),
            "project-sidecar.md": (
                ".blend",
                ".cbq",
                "relative",
                "Missing",
                "Mismatch",
                "Incompatible",
                "backup",
                "Clear Derived Cache",
            ),
            "data-quality.md": (
                "Complete",
                "Partial",
                "Ambiguous",
                "Incomplete",
                "Invalid",
                "scientific consequence",
                "suggested action",
            ),
            "scientific-editing.md": (
                "Object transforms",
                "Apply Scientific Edits",
                "source Structure",
                "derived Structure",
                "explicit_file",
                "distance_inferred",
                "revision",
            ),
            "formats.md": (
                "F0–F5",
                "XYZ/extXYZ",
                "MOL V2000/V3000",
                "POSCAR/CONTCAR",
                "PDB/PQR",
                "import",
                "export",
                "loss",
                "RDKit",
                "Gemmi",
                "optional backend",
                "QCSchema",
                "Molecule",
                "AtomicResult",
                "Dependency-free",
                "raw envelope",
                "normalized Project Browser export with semantic round-trip",
                "reader-capability-matrix.json",
            ),
        }
        guide_text = {}
        for name, terms in contracts.items():
            path = f"docs/user/{name}"
            text = self.read_doc(path)
            guide_text[name] = text
            self.assertIn(f"user/{name}", index)
            for term in terms:
                self.assertIn(term, text, path)

        for name in ("quick-import.md", "data-quality.md"):
            compact = " ".join(guide_text[name].split())
            self.assertIn("selected reader", compact, name)
            self.assertIn("reader and format", compact, name)
            self.assertIn("diagnostics", compact, name)
            self.assertNotIn(
                "Maximum keeps more trustworthy partial data",
                compact,
                name,
            )
            self.assertNotIn(
                "Maximum retains more trustworthy partial data",
                compact,
                name,
            )

        scientific_editing = " ".join(
            guide_text["scientific-editing.md"].split()
        )
        self.assertIn(
            "current topology controls do not display the revision",
            scientific_editing,
        )
        self.assertIn("binding", scientific_editing)
        self.assertIn("provenance", scientific_editing)
        self.assertNotIn(
            "topology controls display its source, quality, parameters, "
            "edge count and revision",
            scientific_editing,
        )

        from ChemBlender.core import reader_capability_document

        qcschema = next(
            row
            for row in reader_capability_document()["readers"]
            if row["reader_id"] == "qcschema"
        )
        self.assertEqual(qcschema["execution_mode"], "built_in")
        self.assertEqual(qcschema["availability_contract"], {"kind": "always"})
        self.assertEqual(qcschema["extensions"], [".json"])

    def test_developer_guides_cover_reader_and_release_boundaries(self):
        docs_index = self.read_doc("docs/README.md")
        agent_index = self.read_doc(".agents/README.md")
        guides = {
            "import-pipeline.md": (
                "ReaderDescriptor",
                "ReaderRuntimeDescriptor",
                "ReaderPluginManifest",
                "PublicImportBatch",
                "ImportDiagnostic",
                "ImportCommitDecisions",
                "commit_import_preview()",
                "generate_format_docs.py --check",
                "tests.test_reader_conformance_v1",
            ),
            "source-revisions.md": (
                "SourceRecord",
                "SourceRevision",
                "parse_identity",
                "created_entity_ids",
                "immutable",
                "derived Structure",
                "entity_id",
                "revision",
            ),
            "testing-fixtures.md": (
                "SHA-256",
                "provenance",
                "license",
                ".gitattributes",
                "hash-locked",
                "tests/fixtures/legacy-blend/README.md",
            ),
            "release-2.3.md": (
                "release_metadata.py",
                "generate_format_docs.py --check",
                "artifact_size_report.py",
                "verify_release_artifact.py",
                "exact HEAD",
                "exact tag",
                "explicit authorization",
                "Remote CI: Not Run",
            ),
        }
        for name, terms in guides.items():
            relative = f"docs/development/{name}"
            text = self.read_doc(relative)
            self.assertIn(f"development/{name}", docs_index)
            self.assertIn(name, agent_index)
            for term in terms:
                self.assertIn(term, text, relative)

            path = ROOT / relative
            for destination in re.findall(r"\[[^]]+\]\(([^)]+)\)", text):
                destination = destination.strip("<>").split("#", 1)[0]
                if not destination or destination.startswith(("http://", "https://")):
                    continue
                self.assertTrue(
                    (path.parent / destination).resolve().exists(),
                    f"{relative}: {destination}",
                )

        reader_index = self.read_doc("docs/reader-api-v1/README.md")
        self.assertIn("../development/import-pipeline.md", reader_index)
        self.assertIn("../../examples/reader-extension/README.md", reader_index)
        worker = self.read_doc("docs/reader-api-v1/worker-api.md")
        for term in (
            "WorkerHandle.wait(timeout=...)",
            "request_cancel()",
            "terminate()",
            "reader.parse@0.1",
            "worker exited with code",
        ):
            self.assertIn(term, worker)

        architecture = self.read_doc(
            ".agents/reference/code-architecture-guide.md"
        )
        self.assertIn("Reader API v1 RC 门面", architecture)
        self.assertNotIn("Reader API alpha 门面", architecture)

    def test_release_and_worker_guides_fail_closed_at_real_dependency_boundaries(self):
        release = self.read_doc("docs/development/release-2.3.md")
        for term in (
            "dependency_inventory.py",
            "--no-index",
            "--no-deps",
            "--target $dependencySite",
            "version('rdkit') == '2026.3.3'",
            "gemmi.__version__ == '0.7.5'",
            "Blender global site-packages",
            "不得联网下载",
            "cb23-qualification-",
            "$qualificationRootOwned = $false",
            "$createdRoot = New-Item -ItemType Directory -Path $qualificationRoot",
            "$createdPath = [IO.Path]::GetFullPath($createdRoot.FullName)",
            "$qualificationRootOwned = $true",
            "if ($qualificationRootOwned -and (Test-Path -LiteralPath $qualificationRoot))",
            "$cleanupRoot = (Resolve-Path -LiteralPath $qualificationRoot).Path",
            "-not $cleanupRoot.StartsWith(",
            "Remove-Item -LiteralPath $cleanupRoot -Recurse -Force",
            "throw 'Qualification temp cleanup failed'",
            "throw 'Release metadata probe failed'",
            "throw 'Generated documentation check failed'",
            "throw 'git diff --check failed'",
            "throw 'Extension validation failed'",
            "throw 'Extension build failed'",
        ):
            self.assertIn(term, release)
        self.assertNotIn(
            "extensions/.local/lib/python3.13/site-packages",
            release,
        )
        self.assertLess(
            release.index("try {"),
            release.index("Remove-Item -LiteralPath $cleanupRoot -Recurse -Force"),
        )
        self.assertLess(
            release.index("throw 'Refusing to reuse a qualification temp root'"),
            release.index(
                "$createdRoot = New-Item -ItemType Directory -Path $qualificationRoot"
            ),
        )
        self.assertLess(
            release.index("$createdPath = [IO.Path]::GetFullPath($createdRoot.FullName)"),
            release.index("$qualificationRootOwned = $true"),
        )
        self.assertLess(
            release.index("$qualificationRootOwned = $true"),
            release.index("New-Item -ItemType Directory -Path $dependencySite"),
        )
        self.assertLess(
            release.index("dependency_inventory.py"),
            release.index("$env:PYTHONPATH = $dependencySite"),
        )
        self.assertLess(
            release.index("$env:PYTHONPATH = $dependencySite"),
            release.index("-m unittest discover"),
        )

        worker = self.read_doc("docs/reader-api-v1/worker-api.md")
        for term in (
            "request_id",
            "SourceRevision.id",
            "bundle graph",
            "固定受信 worker",
            "不独立重算",
            "runtime hardening",
        ):
            self.assertIn(term, worker)
        self.assertNotIn(
            "content hash 与 source revision identity",
            worker,
        )

    def test_230_wave_4_and_wave_3_are_completed(self):
        queued = sorted(
            path.name
            for path in (ROOT / ".agents" / "queued").glob("2.3.0-wave-*.md")
        )
        self.assertEqual(queued, sorted(WAVE_230_QUEUE_FILES))
        self.assertTrue(
            (ROOT / ".agents" / "completed" / WAVE_230_COMPLETED_FILE).is_file()
        )
        self.assertTrue(
            (
                ROOT
                / ".agents"
                / "completed"
                / WAVE_230_FINAL_COMPLETED_FILE
            ).is_file()
        )

    def test_230_markdown_is_utf8_without_bom(self):
        paths = [
            *(ROOT / ".agents" / "decisions").glob("00[234][0-9]-*.md"),
            *(ROOT / ".agents" / "active").glob("2.3.0-wave-*.md"),
            *(ROOT / ".agents" / "completed").glob("2.3.0-wave-*.md"),
            *(ROOT / ".agents" / "queued").glob("2.3.0-wave-*.md"),
            *(ROOT / "docs" / "quantum-visualization" / "2.3.0").rglob("*.md"),
            *(ROOT / "docs" / "user").rglob("*.md"),
            *(ROOT / "docs" / "superpowers" / "plans").glob(
                "2026-07-23-chemblender-2.3.0-*.md"
            ),
            *(ROOT / "docs" / "superpowers" / "specs").glob(
                "2026-07-23-chemblender-2.3.0-*.md"
            ),
        ]
        for path in paths:
            self.read_doc(str(path.relative_to(ROOT)))

    def test_adr_numbers_are_unique(self):
        numbers = [
            path.name.split("-", 1)[0]
            for path in (ROOT / ".agents" / "decisions").glob("[0-9][0-9][0-9][0-9]-*.md")
        ]
        self.assertEqual(len(numbers), len(set(numbers)))

    def test_topic_plans_have_required_sections(self):
        required = (
            "## 范围",
            "## 非目标",
            "## 优先级",
            "## 依赖关系",
            "## 交付物",
            "## 验收标准",
            "## 参考仓库触发条件",
        )
        for relative_path in (
            "docs/quantum-visualization/plans/semantic-core.md",
            "docs/quantum-visualization/plans/readers-and-formats.md",
            "docs/quantum-visualization/plans/wavefunction-and-grids.md",
            "docs/quantum-visualization/plans/blender-visualization.md",
            "docs/quantum-visualization/plans/periodic-electronic-structure.md",
            "docs/quantum-visualization/plans/storage-and-workers.md",
            "docs/quantum-visualization/plans/workflows-and-connectors.md",
        ):
            text = self.read_doc(relative_path)
            for heading in required:
                self.assertIn(heading, text, relative_path)

    def test_data_boundary_lists_five_decisions(self):
        text = self.read_doc(
            "docs/quantum-visualization/architecture/data-boundary.md"
        )
        for decision in (
            "量子化学语义模型",
            "Grid3D 数据约定",
            "单位约定",
            "reader capability contract",
            "Blender 与边车数据的职责边界",
        ):
            self.assertIn(decision, text)

    def test_reference_catalog_and_pinned_submodule(self):
        references = self.read_doc("docs/quantum-visualization/references.md")
        placeholder = self.read_doc("submodules/README.md")
        for project in (
            "xyzrender",
            "quantum-chem-skills",
            "Molecular Blender",
            "Beautiful Atoms",
            "Molecular Nodes",
            "cclib",
            "IOData",
            "Gemmi",
            "spglib",
            "pymatgen",
            "phonopy",
        ):
            self.assertIn(project, references)
        self.assertIn("git submodule add", placeholder)
        gitmodules = self.read_doc(".gitmodules")
        self.assertIn("submodules/cclib", gitmodules)
        self.assertIn("submodules/iodata", gitmodules)
        self.assertIn("submodules/gbasis", gitmodules)
        self.assertIn("submodules/gemmi", gitmodules)
        self.assertIn("submodules/spglib", gitmodules)
        self.assertIn("submodules/ase", gitmodules)
        self.assertIn("submodules/pymatgen-core", gitmodules)
        self.assertIn("submodules/phonopy", gitmodules)
        self.assertIn("submodules/pyprocar", gitmodules)
        self.assertIn("submodules/quantum-chem-skills", gitmodules)
        self.assertIn("submodules/critic2", gitmodules)
        self.assertIn("submodules/qcelemental", gitmodules)
        self.assertIn("submodules/avogadrolibs", gitmodules)
        self.assertIn("submodules/qcengine", gitmodules)
        children = {path.name for path in (ROOT / "submodules").iterdir()}
        self.assertEqual(
            children,
            {
                "README.md",
                "ase",
                "avogadrolibs",
                "cclib",
                "critic2",
                "gbasis",
                "gemmi",
                "iodata",
                "pymatgen-core",
                "phonopy",
                "pyprocar",
                "quantum-chem-skills",
                "qcelemental",
                "qcengine",
                "spglib",
            },
        )
        self.assertIn("07260dd0394cb1a2381d4d897746d727a12ad6ce", placeholder)
        self.assertIn("adab5813713ba64641565eb2a8c11803a4e9bba6", placeholder)
        self.assertIn("6440c84f3fcf8d42cbd9b5de53ae8d70bed4cd4f", placeholder)
        self.assertIn("5cc1c23c6007e0e6cbd69289c6f7c0bff50e943e", placeholder)
        self.assertIn("12355c77fb7c505a55f52cae36341d73b781a065", placeholder)
        self.assertIn("f27c0005ae6a67ea419f996e728668865bfc1f86", placeholder)
        self.assertIn("488ad74cc5ecaba5d24c1726e2762fb47f31f5ef", placeholder)
        self.assertIn("2df40f4865d477f44d3b5d1ebcafc0b4af878e35", placeholder)
        self.assertIn("4a2ec9049af78fdd35b6214eef68fe40e5f356ed", placeholder)
        self.assertIn("fbfb3c23f94dff29f8db64a3b49c8dc6c840a154", placeholder)
        self.assertIn("4b5dec9131c3a035af1b421d68a227c47fd641db", placeholder)
        self.assertIn("46034a0587e2e74426cb1ae2d4d7f66ad5cf6090", placeholder)
        self.assertIn("5d5d11f4a9ca716f7fb9653eb92424f1714b68ac", placeholder)
        self.assertIn("d1842c4dd2c1e61eb9075a0d32ffefc7c4d5b318", placeholder)

    def test_wave3_exchange_boundary_is_frozen_before_readers(self):
        adr = self.read_doc(
            ".agents/decisions/0043-wave3-exchange-data-boundary.md"
        )
        for term in (
            "ChemicalAnnotation",
            "ExternalReference",
            "BiologicalHierarchy",
            "PropertyDataset",
            "CJSONEnvelope",
            "Reader API `1.0-rc1`",
        ):
            self.assertIn(term, adr)

        plans = {
            "mol2": self.read_doc(
                "docs/superpowers/plans/"
                "2026-07-23-chemblender-2.3.0-wave-3-mol2.md"
            ),
            "pdb": self.read_doc(
                "docs/superpowers/plans/"
                "2026-07-23-chemblender-2.3.0-wave-3-pdb-pqr.md"
            ),
            "cjson": self.read_doc(
                "docs/superpowers/plans/"
                "2026-07-23-chemblender-2.3.0-wave-3-cjson-reader-plugin-v1.md"
            ),
        }
        for text in plans.values():
            self.assertIn("ADR 0043", text)
        self.assertIn("ChemicalAnnotation", plans["mol2"])
        self.assertIn("BiologicalHierarchy", plans["pdb"])
        self.assertIn("whitelist", plans["cjson"].lower())

    def test_single_active_task(self):
        active = sorted((ROOT / ".agents" / "active").glob("*.md"))
        self.assertEqual(
            [path.name for path in active],
            list(NEXT_RELEASE_ACTIVE_FILES),
        )
        queued = sorted((ROOT / ".agents" / "queued").glob("*.md"))
        self.assertEqual(
            [path.name for path in queued],
            list(NEXT_RELEASE_QUEUED_FILES),
        )

    def test_240_candidate_intake_records_completed_selected_task(self):
        intake_path = (
            "docs/quantum-visualization/2.4.0/candidate-intake.md"
        )
        plan_path = (
            "docs/superpowers/plans/"
            "2026-08-01-chemblender-2.4.0-mol2-export.md"
        )
        cursor_path = f".agents/completed/{MOL2_EXPORT_COMPLETED_FILE}"
        contract_path = (
            "docs/quantum-visualization/2.4.0/mol2-export-contract.md"
        )
        for relative_path in (intake_path, plan_path, cursor_path, contract_path):
            self.assertTrue((ROOT / relative_path).is_file(), relative_path)
        intake = self.read_doc(intake_path)
        plan = self.read_doc(plan_path)
        cursor = self.read_doc(cursor_path)
        contract = self.read_doc(contract_path)

        for term in (
            "GitHub Issues: disabled",
            "2.3.1",
            "2.4.0",
            "MOL2",
            "F0",
        ):
            self.assertIn(term, intake)
        for term in (
            "export_mol2",
            "mol2_export_readiness",
            "No UI",
        ):
            self.assertIn(term, plan)
        for term in (
            "CB240-MOL2-EXPORT-T1",
            "State: `completed`",
            "fed930d21fef0aaa4dc334c5a0db1e550ab2e0a2",
            plan_path,
            "Current task:",
            "2086 Passed",
            "Blender 5.1.2 package verification",
            "No push",
        ):
            self.assertIn(term, cursor)
        for term in (
            "NO_CHARGES",
            "source_atom_ids_renumbered",
            "confirm_loss=True",
            "Semantic round-trip",
        ):
            self.assertIn(term, contract)

    def test_240_mol2_export_ui_design_is_recoverable(self):
        intake_path = (
            "docs/quantum-visualization/2.4.0/mol2-export-ui-intake.md"
        )
        design_path = (
            "docs/superpowers/specs/"
            "2026-08-01-chemblender-2.4.0-mol2-export-ui-design.md"
        )
        cursor_path = (
            f".agents/completed/{MOL2_EXPORT_UI_COMPLETED_FILE}"
        )
        intake = self.read_doc(intake_path)
        design = self.read_doc(design_path)
        cursor = self.read_doc(cursor_path)

        for term in (
            "Task 2 — MOL2 Export UI Workflow",
            "63f6043bdfe1a15fa411662f2bd418de6ebee85e",
            "extension-package",
        ):
            self.assertIn(term, intake)
        for term in (
            "CHEMBLENDER_OT_export_project_entity",
            "preview_mol2_export",
            "export_mol2",
            "ConformerSet-to-MOL2 is rejected",
            "atomic destination replacement",
        ):
            self.assertIn(term, design)
        for term in (
            "CB240-MOL2-EXPORT-UI-T2",
            "State: `completed`",
            "Approved by user on 2026-08-01",
            "https://github.com/psiQAQ/ChemBlender_2_x/pull/10",
            "819575f3210d9db92b33b2e5e11cc02590680564",
            "30708862898",
            "30708862900",
            "99548d8aff8bea162651273ff5d723e57be5279c",
            "Ancestor verification: `Passed`",
            design_path,
        ):
            self.assertIn(term, cursor)

        plan_path = (
            "docs/superpowers/plans/"
            "2026-08-01-chemblender-2.4.0-mol2-export-ui.md"
        )
        plan = self.read_doc(plan_path)
        self.assertIn("Task 7: Remote integration gate", plan)
        self.assertIn("exact pushed head", plan)
        self.assertIn(plan_path, cursor)

    def test_240_task3_scope_discovery_is_recoverable(self):
        intake_path = (
            "docs/quantum-visualization/2.4.0/task3-candidate-intake.md"
        )
        design_path = (
            "docs/superpowers/specs/"
            "2026-08-02-chemblender-2.4.0-task3-scope-discovery-design.md"
        )
        discovery_plan_path = (
            "docs/superpowers/plans/"
            "2026-08-02-chemblender-2.4.0-task3-scope-discovery.md"
        )
        selected_plan_path = (
            "docs/superpowers/plans/"
            "2026-08-02-chemblender-2.4.0-pdb-export.md"
        )
        completed_path = (
            f".agents/completed/{TASK3_SCOPE_COMPLETED_FILE}"
        )
        pdb_export_path = f".agents/completed/{PDB_EXPORT_COMPLETED_FILE}"
        documents = {
            path: self.read_doc(path)
            for path in (
                intake_path,
                design_path,
                discovery_plan_path,
                selected_plan_path,
                completed_path,
                pdb_export_path,
            )
        }

        intake = documents[intake_path]
        for term in (
            "Native PDB export",
            "Native PQR export",
            "Native Cube export",
            "Reader API v1 stable gate",
            "F0",
            "1.0-rc1",
            "Task 3 — Deterministic native PDB export",
            "PQR: deferred",
            "Cube: deferred",
            "Reader API stable: deferred",
        ):
            self.assertIn(term, intake)

        selected_plan = documents[selected_plan_path]
        for term in (
            "preview_pdb_export",
            "export_pdb",
            "Semantic native re-import",
            "No CONECT",
            "No UI",
        ):
            self.assertIn(term, selected_plan)

        pdb_export = documents[pdb_export_path]
        for term in (
            "CB240-PDB-EXPORT-T3",
            "State: `completed`",
            selected_plan_path,
            intake_path,
            "Task 1 — Freeze native PDB export contract",
            "2114 Passed / 26 Skipped / 0 Failed",
            "PASS: installed native PDB export and re-import",
            "`TER` segment omission is reported as `source_records_omitted`",
            "29,964,601",
            "2,616,399",
            "2d5854788a602ffad8c64d8adebd40727f9bcda6266cc6d59d27cbb83758a025",
            "30724509726",
            "30724509723",
            "a6c1cbb71ef5269cfe864fb924749f000fa060d5",
        ):
            self.assertIn(term, pdb_export)

        completed = documents[completed_path]
        for term in (
            "CB240-TASK3-SCOPE-DISCOVERY",
            "State: `completed`",
            "Native PDB export",
            "zero runtime diff",
            "Remote CI: `Not Run`",
            "PDB exporter runtime implementation has not started",
            design_path,
            discovery_plan_path,
            selected_plan_path,
            ".agents/queued/2.4.0-pdb-export.md",
        ):
            self.assertIn(term, completed)

    def test_240_task4_scope_discovery_is_recoverable(self):
        intake_path = (
            "docs/quantum-visualization/2.4.0/task4-candidate-intake.md"
        )
        design_path = (
            "docs/superpowers/specs/"
            "2026-08-02-chemblender-2.4.0-task4-scope-discovery-design.md"
        )
        plan_path = (
            "docs/superpowers/plans/"
            "2026-08-02-chemblender-2.4.0-task4-scope-discovery.md"
        )
        selected_plan_path = (
            "docs/superpowers/plans/"
            "2026-08-02-chemblender-2.4.0-pdb-export-ui.md"
        )
        cursor_path = ".agents/completed/2.4.0-task4-scope-discovery.md"
        queued_record_path = ".agents/queued/2.4.0-pdb-export-ui.md"
        active_path = ".agents/completed/2.4.0-pdb-export-ui.md"
        intake = self.read_doc(intake_path)
        design = self.read_doc(design_path)
        plan = self.read_doc(plan_path)
        selected_plan = self.read_doc(selected_plan_path)
        cursor = self.read_doc(cursor_path)
        completed = self.read_doc(active_path)

        for term in (
            "PDB Export UI",
            "Native PQR export",
            "Native Cube export",
            "Reader API v1 stable gate",
            "zero runtime diff",
        ):
            self.assertIn(term, design)
        for term in (
            "Task 1: Persist the Task 4 discovery boundary",
            "Task 2: Audit and select one candidate",
            "Task 3: Queue the selected implementation",
            "Task 4: Verify and checkpoint",
        ):
            self.assertIn(term, plan)
        for term in (
            "PDB: F5 / core / preview_confirmation",
            "PDB UI: absent",
            "PQR: F0",
            "Cube: F0",
            "Reader API: 1.0-rc1",
            "Task 4 — PDB Export UI",
            "PQR: deferred",
            "Cube: deferred",
            "Reader API stable: deferred",
        ):
            self.assertIn(term, intake)
        for term in (
            "_pdb_entities",
            "selection.frame_set",
            "all `MODEL` blocks",
            "no duplicate base frame",
            "preview_pdb_export",
            "export_pdb",
            "No new operator",
            "Task 7: Remote integration gate",
        ):
            self.assertIn(term, selected_plan)
        for term in (
            "CB240-TASK4-SCOPE-DISCOVERY",
            "State: `completed`",
            "79a93f52053fdf809c28c24800366010577a1984",
            "2995386744768b424e8276db7cd72a90154edf25",
            "30724971581",
            "30724971598",
            "c613edfdbf4b299a7c44d3d288c8484c0545f6e6",
            design_path,
            plan_path,
            intake_path,
            selected_plan_path,
            queued_record_path,
            "Selection: `PDB Export UI`",
            "zero runtime diff",
            "Remote CI: `Not Run`",
            "PDB UI runtime implementation remains unstarted",
        ):
            self.assertIn(term, cursor)
        for term in (
            "CB240-PDB-EXPORT-UI-T4",
            "State: `completed`",
            selected_plan_path,
            "Task 4 — PDB Export UI",
            "https://github.com/psiQAQ/ChemBlender_2_x/pull/12",
            "5756532077d8aca8cebc54becf411133af7f96d8",
            "30728969782",
            "30728969751",
            "d5028aa5d8568a44181b822293fbe62462d9a496",
            "Ancestor verification: `Passed`",
        ):
            self.assertIn(term, completed)

    def test_240_task5_scope_discovery_is_recoverable(self):
        design_path = (
            "docs/superpowers/specs/"
            "2026-08-02-chemblender-2.4.0-task5-scope-discovery-design.md"
        )
        plan_path = (
            "docs/superpowers/plans/"
            "2026-08-02-chemblender-2.4.0-task5-scope-discovery.md"
        )
        intake_path = (
            "docs/quantum-visualization/2.4.0/task5-candidate-intake.md"
        )
        selected_plan_path = (
            "docs/superpowers/plans/"
            "2026-08-02-chemblender-2.4.0-pqr-export.md"
        )
        queued_path = ".agents/queued/2.4.0-pqr-export.md"
        completed_path = f".agents/completed/{TASK5_SCOPE_COMPLETED_FILE}"
        design = self.read_doc(design_path)
        plan = self.read_doc(plan_path)
        intake = self.read_doc(intake_path)
        selected_plan = self.read_doc(selected_plan_path)
        queued = self.read_doc(queued_path)
        completed = self.read_doc(completed_path)

        for term in (
            "Native PQR export",
            "Native Cube export",
            "Reader API v1 stable gate",
            "zero runtime diff",
        ):
            self.assertIn(term, design)
        for term in (
            "Task 1: Persist the Task 5 discovery boundary",
            "Task 2: Archive PDB Export UI integration",
            "Task 3: Audit and select one candidate",
            "Task 4: Queue deterministic native PQR export",
            "Task 5: Verify and checkpoint",
        ):
            self.assertIn(term, plan)
        for term in (
            "CB240-TASK5-SCOPE-DISCOVERY",
            "State: `completed`",
            "d5028aa5d8568a44181b822293fbe62462d9a496",
            design_path,
            plan_path,
            intake_path,
            selected_plan_path,
            queued_path,
            "Native PQR export",
            "Native Cube export",
            "Reader API v1 stable gate",
            "Selection: `Native PQR export`",
            "zero runtime diff",
            "Remote CI: `Not Run`",
            "PQR runtime implementation has not started",
        ):
            self.assertIn(term, completed)
        for term in (
            "PDB: F5 / project_browser / preview_confirmation",
            "PQR: F0 / none",
            "Cube: F0 / none",
            "Reader API: 1.0-rc1",
            "Task 5 — Deterministic native PQR export",
            "Cube: deferred",
            "Reader API stable: deferred",
            "5756532077d8aca8cebc54becf411133af7f96d8",
            "30728969782",
            "30728969751",
            "d5028aa5d8568a44181b822293fbe62462d9a496",
        ):
            self.assertIn(term, intake)
        for term in (
            "pqr_export_readiness",
            "preview_pqr_export",
            "export_pqr",
            "10/11-field",
            "Semantic native re-import",
            "No UI",
            "parse_pqr",
        ):
            self.assertIn(term, selected_plan)
        for term in (
            "CB240-PQR-EXPORT-T5",
            "State: `not_started`",
            "Task 1 — Freeze native PQR export contract",
            selected_plan_path,
            intake_path,
            "PQR UI remains unstarted",
        ):
            self.assertIn(term, queued)

    def test_240_scope_discovery_entrypoints_exist(self):
        design_path = (
            "docs/superpowers/specs/"
            "2026-08-01-chemblender-2.4.0-scope-discovery-design.md"
        )
        plan_path = (
            "docs/superpowers/plans/"
            "2026-08-01-chemblender-2.4.0-scope-discovery.md"
        )
        cursor_path = f".agents/completed/{NEXT_RELEASE_COMPLETED_FILE}"
        design = self.read_doc(design_path)
        plan = self.read_doc(plan_path)
        self.assertTrue((ROOT / cursor_path).is_file(), cursor_path)
        self.read_doc(cursor_path)

        for term in ("2.4.0 Scope Discovery", "2.3.1"):
            self.assertTrue(
                any(term in document for document in (design, plan)),
                term,
            )

    def test_240_scope_discovery_cursor_is_recoverable(self):
        design_path = (
            "docs/superpowers/specs/"
            "2026-08-01-chemblender-2.4.0-scope-discovery-design.md"
        )
        plan_path = (
            "docs/superpowers/plans/"
            "2026-08-01-chemblender-2.4.0-scope-discovery.md"
        )
        cursor_path = f".agents/completed/{NEXT_RELEASE_COMPLETED_FILE}"
        self.assertTrue((ROOT / cursor_path).is_file(), cursor_path)
        cursor = self.read_doc(cursor_path)

        for term in (
            "CB240-SCOPE-DISCOVERY",
            "State: `completed`",
            "Evidence-backed candidate intake",
            "224155fa6986a4a51deaae3f9cf3d5f87ea0941a",
            "89090a0c698cf87cd1f42ba14a206aa0637e5b5d",
            design_path,
            plan_path,
            ".agents/completed/2.3.0-release-readiness.md",
            "docs/superpowers/plans/2026-08-01-chemblender-2.4.0-mol2-export.md",
            ".agents/queued/2.4.0-mol2-export.md",
            "No product implementation was started",
            "No push",
        ):
            self.assertIn(term, cursor)

    def test_code_architecture_guide_tracks_source_files(self):
        import re

        guide = self.read_doc(".agents/reference/code-architecture-guide.md")
        expected = {
            path.relative_to(ROOT).as_posix()
            for root in (ROOT / "ChemBlender", ROOT / "worker")
            for path in root.rglob("*.py")
        }
        documented = set(
            re.findall(r"`((?:ChemBlender|worker)/[^`]+\.py)`", guide)
        )
        self.assertIn(
            "ChemBlender/core/storage/atomic_paths.py",
            documented,
        )
        self.assertIn("ChemBlender/ui/view_cache.py", documented)
        self.assertIn("ChemBlender/ui/export.py", documented)
        self.assertIn("ChemBlender/scripts/benchmark_cube_flow.py", documented)
        self.assertIn("ChemBlender/scripts/benchmark_extxyz.py", documented)
        self.assertIn("ChemBlender/scripts/release_metadata.py", documented)
        self.assertIn(
            "ChemBlender/scripts/probe_prerelease_version.py",
            documented,
        )
        self.assertEqual(documented, expected)

        readme = self.read_doc("README.md")
        agents = self.read_doc("AGENTS.md")
        index = self.read_doc(".agents/README.md")
        reference = ".agents/reference/code-architecture-guide.md"
        self.assertIn(reference, readme)
        self.assertIn(reference, agents)
        self.assertIn("code-architecture-guide.md", index)
        self.assertIn("Every architecture change", agents)

    def test_cube_flow_baseline_records_real_budget_evidence(self):
        baseline = self.read_doc(
            "docs/quantum-visualization/2.3.0/benchmarks/"
            "cube-flow-baseline.md"
        )
        for value in (
            "128 × 128 × 128",
            "1.679902 s",
            "Blender 5.1.2",
            "cold VDB cache",
            "Remote CI: Not Run",
        ):
            self.assertIn(value, baseline)

    def test_extxyz_flow_baseline_records_reference_budget_evidence(self):
        baseline = self.read_doc(
            "docs/quantum-visualization/2.3.0/benchmarks/"
            "extxyz-flow-baseline.md"
        )
        for value in (
            "1,000 frames × 1,000 atoms",
            "0.448/0.457 s",
            "99.702 s",
            "bounded 64 KiB source-read",
            "Remote CI: Not Run",
        ):
            self.assertIn(value, baseline)

    def test_quantum_model_is_a_package(self):
        import importlib

        self.assertFalse((ROOT / "ChemBlender" / "core" / "model.py").exists())
        self.assertTrue((ROOT / "ChemBlender" / "core" / "model" / "__init__.py").exists())
        model = importlib.import_module("ChemBlender.core.model")
        self.assertIsNotNone(model.__spec__.submodule_search_locations)

    def test_extxyz_plan_records_preimplementation_contracts(self):
        plan = self.read_doc(
            "docs/superpowers/plans/"
            "2026-07-23-chemblender-2.3.0-wave-1-extxyz.md"
        )
        sections = {}
        for task_number in range(1, 6):
            marker = f"### Task {task_number}:"
            start = plan.index(marker)
            next_marker = f"### Task {task_number + 1}:"
            end = plan.find(next_marker, start)
            sections[task_number] = plan[start : end if end != -1 else None]

        required_by_task = {
            1: (
                '`FrameProperty` validity mask prefix `("frame",)`',
                '`AtomFrameProperty` validity mask prefix `("frame", "atom")`',
                '`CellFrameProperty` validity mask prefix `("frame",)`',
                "`mask.dims == required_prefix`",
                "`mask.values.shape == data.values.shape[:len(required_prefix)]`",
                "`mask.values.dtype == numpy.bool_`",
                '`mask.unit == "dimensionless"`',
                "Numeric and logical Partial properties use that boolean mask.",
                "integer codes",
                "unique categories",
                "explicit missing code",
                "does not add a redundant validity mask",
            ),
            2: (
                "Create: `ChemBlender/core/formats/__init__.py`",
                "string, integer, real, logical, 1-D array and 2-D array",
                "raw lexeme and diagnostic",
                "bounded one-frame iterator",
                "libAtoms, ASE and OVITO",
                "ASE remains fixture provenance only, not a runtime dependency",
            ),
            3: (
                "`ax ay az bx by bz cx cy cz`",
                "no `Lattice` and no `pbc`: `(False, False, False)`",
                "`Lattice` and no `pbc`: `(True, True, True)`",
                "explicit `pbc` overrides",
                "staged memmap/NPY owner",
                "Cancellation cleanup",
                "must not construct a nested Python tuple containing all frames",
                "sidecar publication failure rolls back",
            ),
            4: (
                "deterministic typed metadata serialization",
                "scalar, 1-D and 2-D typed metadata",
                "metadata type, shape and value",
                "unsafe raw lexeme and diagnostic",
                "loss preview",
            ),
            5: (
                "Modify: `ChemBlender/runtime/registration.py`",
                "Modify: `tests/test_registration_contract.py`",
                "Modify: `.agents/reference/code-architecture-guide.md`",
                "Modify: `tests/test_quantum_visualization_docs.py`",
                "`ChemBlender/ui/export.py` is an explicit registration root",
            ),
        }
        for task_number, contracts in required_by_task.items():
            for contract in contracts:
                self.assertIn(contract, sections[task_number], contract)

    def test_local_markdown_links_resolve(self):
        import re

        paths = [
            ROOT / "README.md",
            ROOT / "AGENTS.md",
            ROOT / ".agents" / "README.md",
            *(ROOT / ".agents" / "active").glob("*.md"),
            *(ROOT / ".agents" / "completed").glob("2.3.0-wave-*.md"),
            *(ROOT / ".agents" / "decisions").glob("00[234][0-9]-*.md"),
            *(ROOT / ".agents" / "queued").glob("2.3.0-wave-*.md"),
            ROOT / "docs" / "README.md",
            *DOCS.rglob("*.md"),
            *(ROOT / "docs" / "user").rglob("*.md"),
            *(ROOT / "docs" / "superpowers" / "plans").glob(
                "2026-07-23-chemblender-2.3.0-*.md"
            ),
            *(ROOT / "docs" / "superpowers" / "specs").glob(
                "2026-07-23-chemblender-2.3.0-*.md"
            ),
        ]
        for path in paths:
            text = self.read_doc(str(path.relative_to(ROOT)))
            for destination in re.findall(r"\[[^]]+\]\(([^)]+)\)", text):
                destination = destination.strip("<>").split("#", 1)[0]
                if not destination or destination.startswith(("http://", "https://")):
                    continue
                target = (path.parent / destination).resolve()
                self.assertTrue(target.exists(), f"{path}: {destination}")


if __name__ == "__main__":
    unittest.main()
