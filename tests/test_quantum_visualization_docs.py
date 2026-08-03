import unittest
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "quantum-visualization"
WAVE_230_QUEUE_FILES = ()
WAVE_230_ACTIVE_FILES = ()
TASK9_SCOPE_ACTIVE_FILE = "2.4.0-task9-scope-discovery.md"
TASK9_SCOPE_COMPLETED_FILE = "2.4.0-task9-scope-discovery.md"
CUBE_EXPORT_UI_CURSOR_FILE = "2.4.0-cube-export-ui.md"
TASK11_SCOPE_ACTIVE_FILE = "2.4.0-task11-scope-discovery.md"
TASK11_SCOPE_COMPLETED_FILE = "2.4.0-task11-scope-discovery.md"
FINAL_QUALIFICATION_CURSOR_FILE = "2.4.0-final-qualification.md"
NEXT_RELEASE_ACTIVE_FILES = ("2.4.0-post-release-cleanup.md",)
NEXT_RELEASE_QUEUED_FILES = ()
NEXT_RELEASE_COMPLETED_FILE = "2.4.0-scope-discovery.md"
MOL2_EXPORT_COMPLETED_FILE = "2.4.0-mol2-export.md"
MOL2_EXPORT_UI_COMPLETED_FILE = "2.4.0-mol2-export-ui.md"
TASK3_SCOPE_COMPLETED_FILE = "2.4.0-task3-scope-discovery.md"
PDB_EXPORT_COMPLETED_FILE = "2.4.0-pdb-export.md"
TASK4_SCOPE_COMPLETED_FILE = "2.4.0-task4-scope-discovery.md"
TASK5_SCOPE_COMPLETED_FILE = "2.4.0-task5-scope-discovery.md"
PQR_EXPORT_COMPLETED_FILE = "2.4.0-pqr-export.md"
PQR_EXPORT_UI_COMPLETED_FILE = "2.4.0-pqr-export-ui.md"
CUBE_EXPORT_QUEUED_FILE = "2.4.0-cube-export.md"
CUBE_EXPORT_COMPLETED_FILE = "2.4.0-cube-export.md"
TASK7_SCOPE_COMPLETED_FILE = "2.4.0-task7-scope-discovery.md"
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

    def test_post_release_documentation_routes_current_and_historical_state(self):
        root = self.read_doc("README.md")
        docs = self.read_doc("docs/README.md")
        agents = self.read_doc(".agents/README.md")
        superpowers = self.read_doc("docs/superpowers/README.md")
        self.assertIn("superpowers/README.md", docs)
        self.assertIn("ChemBlender 2.4.0", root)
        self.assertIn("2.4.0-stable-release.md", agents)
        for term in (".agents/active/", ".agents/queued/", ".agents/completed/"):
            self.assertIn(term, superpowers)
        self.assertIn("historical", superpowers.lower())
        self.assertIn("2.4.0", superpowers)

    def test_user_format_summary_matches_published_240_capabilities(self):
        formats = self.read_doc("docs/user/formats.md")
        self.assertIn("ChemBlender 2.4.0 format scope", formats)
        self.assertNotIn("Base 2.3.0 format scope", formats)
        self.assertIn("Cube export", formats)
        self.assertIn("PQR export", formats)
        self.assertIn("Project Browser", formats)

    def test_240_human_experience_review_is_complete_and_observational(self):
        guide = self.read_doc("docs/user/2.4.0-experience-review.md")
        for index_path in ("README.md", "docs/README.md"):
            self.assertIn("2.4.0-experience-review.md", self.read_doc(index_path))
        for workflow in (
            "Install",
            "First launch",
            "Quick Import",
            "Import Preview",
            "Project Browser",
            "Structure",
            "Volume",
            "Surface",
            "Export",
            "save",
            "reopen",
            "Cancel",
            "recover",
        ):
            self.assertIn(workflow, guide)
        for field in (
            "Environment",
            "Severity",
            "Reproducibility",
            "Expected result",
            "Actual result",
            "Evidence",
        ):
            self.assertIn(field, guide)
        self.assertIn("do not implement", guide.lower())

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
        active_path = ".agents/active/2.4.0-pqr-export.md"
        pqr_completed_path = f".agents/completed/{PQR_EXPORT_COMPLETED_FILE}"
        discovery_queued_path = ".agents/queued/2.4.0-pqr-export.md"
        contract_path = "docs/quantum-visualization/2.4.0/pqr-export-contract.md"
        completed_path = f".agents/completed/{TASK5_SCOPE_COMPLETED_FILE}"
        self.assertFalse((ROOT / active_path).exists(), active_path)
        self.assertTrue((ROOT / pqr_completed_path).is_file(), pqr_completed_path)
        design = self.read_doc(design_path)
        plan = self.read_doc(plan_path)
        intake = self.read_doc(intake_path)
        selected_plan = self.read_doc(selected_plan_path)
        pqr_completed = self.read_doc(pqr_completed_path)
        contract = self.read_doc(contract_path)
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
            discovery_queued_path,
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
            "State: `completed`",
            "Task 6 — Exact-head remote integration gate completed",
            "e713363619faf5d9b2dccbea00c1cce9713b4969",
            "92 Passed",
            "2156 Passed / 26 Skipped / 0 Failed",
            "https://github.com/psiQAQ/ChemBlender_2_x/pull/13",
            "0abb4e32c6269a2a327bccfb0427c626f70084fb",
            "30739236959",
            "30739237004",
            "54dd2364b6f935771f6d6c661452f44b7d4b558a",
            "Remote CI: `Passed`",
            selected_plan_path,
            intake_path,
            "PQR UI is a separate task",
        ):
            self.assertIn(term, pqr_completed)
        for term in (
            "preview_pqr_export",
            "export_pqr",
            "10 whitespace fields",
            "11 whitespace fields",
            "confirm_loss",
            "atomic writer",
        ):
            self.assertIn(term, contract)

    def test_240_pqr_export_ui_is_completed_and_recoverable(self):
        completed_path = (
            f".agents/completed/{PQR_EXPORT_UI_COMPLETED_FILE}"
        )
        design_path = (
            "docs/superpowers/specs/"
            "2026-08-02-chemblender-2.4.0-pqr-export-ui-design.md"
        )
        plan_path = (
            "docs/superpowers/plans/"
            "2026-08-02-chemblender-2.4.0-pqr-export-ui.md"
        )
        completed = self.read_doc(completed_path)
        design = self.read_doc(design_path)
        plan = self.read_doc(plan_path)

        for term in (
            "CB240-PQR-EXPORT-UI-T6",
            "State: `completed`",
            "54dd2364b6f935771f6d6c661452f44b7d4b558a",
            design_path,
            plan_path,
            "pqr-format-choice-and-filter",
            "installed-pqr-export-reimport",
            "Cube export",
            "Reader API v1 stable",
            "https://github.com/psiQAQ/ChemBlender_2_x/pull/14",
            "3bab75429d37276e27dc158ba5bbf69d9085b9bd",
            "30741155445",
            "30741155450",
            "eb3fc4ea6f86e8fc3f9475bd03d379445349db57",
            "Ancestor verification: `Passed`",
            "Remote CI: `Passed`",
        ):
            self.assertIn(term, completed)
        for term in (
            "Reuse `_pdb_entities()` directly",
            "preview_pqr_export",
            "export_pqr",
            "Project Browser",
            "no PQR serializer/readiness/model changes",
        ):
            self.assertIn(term, design)
        for term in (
            "Task 1: Persist activation and exact core integration evidence",
            "Task 2: Add PQR choice and metadata-only preview",
            "Task 3: Dispatch cancellable atomic PQR export",
            "Task 4: Publish and prove the reachable capability",
            "Task 5: Full qualification, reviews and checkpoint",
            "Task 6: Exact-head remote integration gate",
        ):
            self.assertIn(term, plan)

    def test_240_task7_scope_discovery_is_recoverable(self):
        completed_path = f".agents/completed/{TASK7_SCOPE_COMPLETED_FILE}"
        intake_path = (
            "docs/quantum-visualization/2.4.0/task7-candidate-intake.md"
        )
        design_path = (
            "docs/superpowers/specs/"
            "2026-08-02-chemblender-2.4.0-task7-scope-discovery-design.md"
        )
        plan_path = (
            "docs/superpowers/plans/"
            "2026-08-02-chemblender-2.4.0-task7-scope-discovery.md"
        )
        selected_plan_path = (
            "docs/superpowers/plans/"
            "2026-08-02-chemblender-2.4.0-cube-export.md"
        )
        contract_path = (
            "docs/quantum-visualization/2.4.0/cube-export-contract.md"
        )
        cube_completed_path = f".agents/completed/{CUBE_EXPORT_COMPLETED_FILE}"
        completed = self.read_doc(completed_path)
        design = self.read_doc(design_path)
        plan = self.read_doc(plan_path)
        intake = self.read_doc(intake_path)
        selected_plan = self.read_doc(selected_plan_path)
        contract = self.read_doc(contract_path)
        cube_completed = self.read_doc(cube_completed_path)
        self.assertFalse(
            (ROOT / ".agents/active" / CUBE_EXPORT_COMPLETED_FILE).exists()
        )

        for term in (
            "CB240-TASK7-SCOPE-DISCOVERY",
            "State: `completed`",
            "eb3fc4ea6f86e8fc3f9475bd03d379445349db57",
            design_path,
            plan_path,
            "Native Cube export",
            "Reader API v1 stable gate",
            "Cube runtime remains unstarted",
            "Selection: `Native Cube export`",
            "Current task: `Task 7 Scope Discovery checkpoint complete`",
            intake_path,
            selected_plan_path,
            ".agents/queued/2.4.0-cube-export.md",
        ):
            self.assertIn(term, completed)
        for term in (
            "Selected: deterministic native Cube export",
            "Deferred: Reader API v1 stable",
            "PQR Export UI PR #14",
        ):
            self.assertIn(term, design)
        for term in (
            "Task 1: Persist the Task 7 discovery boundary",
            "Task 2: Freeze PQR Export UI remote evidence",
            "Task 3: Audit and select one candidate",
            "Task 4: Queue deterministic native Cube export",
            "Task 5: Verify, review and checkpoint",
        ):
            self.assertIn(term, plan)
        for term in (
            "PQR: F5 / project_browser / preview_confirmation",
            "Cube: F0 / none",
            "Reader API: 1.0-rc1",
            "Task 8 — Deterministic native Cube export",
            "Reader API stable: deferred",
            "writer/readiness",
            "bohr",
            "dataset selection",
            "3bab75429d37276e27dc158ba5bbf69d9085b9bd",
            "30741155445",
            "30741155450",
            "eb3fc4ea6f86e8fc3f9475bd03d379445349db57",
        ):
            self.assertIn(term, intake)
        for term in (
            "preview_cube_export",
            "export_cube",
            "CubeExportReadiness",
            "authoritative lazy snapshots",
            "bohr output",
            "explicit dataset selection",
            "DSET_IDS",
            "positive `NATOMS`",
            "trustworthy source ID",
            "including zero",
            "dataset_id_omitted",
            "positive voxel counts",
            "real numeric arrays",
            "cell/periodic metadata",
            "final pre-publication checkpoint",
            "tests/test_cube_product_flow.py",
            "Semantic native re-import",
            "parse_cube",
            "Task 7: Exact-head remote integration gate",
        ):
            self.assertIn(term, selected_plan)
        for term in (
            "CB240-CUBE-EXPORT-T8",
            "State: `completed`",
            "Task 6 — Full qualification, reviews and checkpoint completed",
            selected_plan_path,
            intake_path,
            "Cube UI remains unstarted",
            "Reader API v1 stable remains unstarted",
            "9fc7e996871b4b6019ca7ef56e7209578c76a641",
            "codex/2.4.0-cube-export",
            contract_path,
            "Completed Commits",
            "Task 1: `c92fe2bffc9997192cb1b659037084973f987289`",
            "Task 2: `e96b20e86f061ea2dad29748a8dd0561be5a9ab1`",
            "Task 3: `fd05baf1d6e3b6beae66a8b61d41b363f17a3d0c`",
            "Task 4: `fd73c872a7227ef4a2384211587b00d3cc83000d`",
            "Task 5 product proof: `613c15076b96a969e0d72b00072b796b46387449`",
            "Task 5 artifact budget: `16e36dc4d79c6afb986ae6cfb81dc2063a239b92`",
            "lazy core facade fix: `de867967671d4724a3ead9133bde8e9af63918ed`",
            "review fixes: `a690f8144e2d63f2174aaeecf419d31be5b5a208`",
            "final artifact budget: `f0c8a393161477ef42606b0011a0b2f40c663a3e`",
            "2186 Passed / 26 Skipped / 0 Failed",
            "Task 7 — Exact-head remote integration gate",
            "https://github.com/psiQAQ/ChemBlender_2_x/pull/15",
            "164a681bb3d9cb788f778eca71f9fe61a0361019",
            "30747458150",
            "30747458152",
            "cd265d95c3cc73cae5355657cc0a5a8f1931d98b",
            "Ancestor verification: `Passed`",
            "Remote CI: `Passed`",
            "59 Passed",
            "66 Passed",
            "71 Passed",
            "41 Passed",
        ):
            self.assertIn(term, cube_completed)
        for term in (
            "cube_export_readiness",
            "MissingSelection",
            "finite real numeric arrays",
            "dataset_index=None",
            "bohr",
            "angstrom",
            "OpenVDB",
        ):
            self.assertIn(term, contract)

    def test_240_task9_scope_discovery_is_recoverable(self):
        active_path = f".agents/active/{TASK9_SCOPE_ACTIVE_FILE}"
        completed_path = f".agents/completed/{TASK9_SCOPE_COMPLETED_FILE}"
        design_path = (
            "docs/superpowers/specs/"
            "2026-08-02-chemblender-2.4.0-task9-scope-discovery-design.md"
        )
        plan_path = (
            "docs/superpowers/plans/"
            "2026-08-02-chemblender-2.4.0-task9-scope-discovery.md"
        )
        intake_path = (
            "docs/quantum-visualization/2.4.0/task9-candidate-intake.md"
        )
        selected_design_path = (
            "docs/superpowers/specs/"
            "2026-08-02-chemblender-2.4.0-cube-export-ui-design.md"
        )
        selected_plan_path = (
            "docs/superpowers/plans/"
            "2026-08-02-chemblender-2.4.0-cube-export-ui.md"
        )
        queued_path = f".agents/queued/{CUBE_EXPORT_UI_CURSOR_FILE}"
        selected_cursor_path = (
            f".agents/completed/{CUBE_EXPORT_UI_CURSOR_FILE}"
        )
        self.assertFalse((ROOT / active_path).exists(), active_path)
        self.assertFalse((ROOT / queued_path).exists(), queued_path)
        completed = self.read_doc(completed_path)
        design = self.read_doc(design_path)
        plan = self.read_doc(plan_path)
        intake = self.read_doc(intake_path)
        selected_design = self.read_doc(selected_design_path)
        selected_plan = self.read_doc(selected_plan_path)
        selected_cursor = self.read_doc(selected_cursor_path)

        for term in (
            "CB240-TASK9-SCOPE-DISCOVERY",
            "State: `completed`",
            "Current task: `Task 9 Scope Discovery checkpoint complete`",
            "cd265d95c3cc73cae5355657cc0a5a8f1931d98b",
            design_path,
            plan_path,
            "Native Cube Export UI",
            "Reader API v1 stable gate",
            "2.4.0 Final Qualification",
            "No runtime implementation",
            "No push",
            "Selection: `Native Cube Export UI`",
            intake_path,
            selected_plan_path,
            queued_path,
            "ceca5e8476dc7773ea3d183075e96685f915affc",
            "30c244602b36ffdcc6c471f95d0456a71f0ff819",
            "09ab20004434262555aa79827866aaf890624e54",
            "2eeaec0568726da70d24c2be71794225b081a339",
            "2f7c525bff7c7fdf59769c1e1610b7e017407968",
            "13a334a345e55f1bc36226639839e4251ff08045",
            "18c7dbffbb509a69f5ea4b0a91e210d9d8fd8f0c",
            "42 Passed",
            "zero runtime diff",
            "Remote CI: `Not Run`",
        ):
            self.assertIn(term, completed)
        for term in (
            "Selected: native Cube export UI",
            "Deferred: Reader API v1 stable gate",
            "Deferred: 2.4.0 final qualification",
            "PR #15",
        ):
            self.assertIn(term, design)
        for term in (
            "Task 1: Persist the Task 9 discovery boundary",
            "Task 2: Freeze native Cube export remote evidence",
            "Task 3: Audit and select one candidate",
            "Task 4: Queue native Cube export UI",
            "Task 5: Verify, review and checkpoint",
        ):
            self.assertIn(term, plan)
        for term in (
            "Cube: F5 / core / preview_confirmation",
            "Reader API: 1.0-rc1",
            "Task 10 — Native Cube Export UI",
            "Reader API stable: deferred",
            "Final Qualification: deferred",
            "Grid3D",
            "resolve_export_selection",
            "164a681bb3d9cb788f778eca71f9fe61a0361019",
            "30747458150",
            "30747458152",
            "cd265d95c3cc73cae5355657cc0a5a8f1931d98b",
        ):
            self.assertIn(term, intake)
        for term in (
            "Reuse `ChemBlender.ui.export`",
            "Grid3D",
            "preview_cube_export",
            "export_cube",
            "explicit dataset index",
            "no Cube-specific operator",
        ):
            self.assertIn(term, selected_design)
        for term in (
            "Task 0: Activate the queued implementation",
            "Task 1: Resolve selected Grid3D export context",
            "Task 2: Add Cube format, dataset choice and preview",
            "Task 3: Dispatch cancellable atomic Cube export",
            "Task 4: Publish and prove the reachable capability",
            "Task 5: Full qualification, reviews and checkpoint",
            "Task 6: Exact-head remote integration gate",
            "tests/test_cube_export_ui_contract.py",
            "preview_cube_export",
            "export_cube",
        ):
            self.assertIn(term, selected_plan)
        for term in (
            "CB240-CUBE-EXPORT-UI-T10",
            "State: `completed`",
            "Task 6 — Exact-head remote integration gate",
            "00e7c6548a555813cfefc97fd00341e6f0ec27d8",
            "codex/2.4.0-cube-export-ui",
            "Task 0 activation: `Passed`",
            "5c558aba0231f36ecc4f3f54cdf0dad3b6e521ad",
            "Task 1 review: `Ready`",
            "076731bd9acd0f2c841cef6db08c6b4926689ff9",
            "05b297161eedd4e1094f587560378db8d5f994ba",
            "Task 2 review: `Ready`",
            "47fa76e312f2568c8a56dacba22d88563a290010",
            "Task 3 review: `Ready`",
            "4d6e97a772b2b5225b81a92be22968539cefa69a",
            "Task 4 review: `Ready`",
            "a2bc97fd26bec51b35df1012695a43b0a08218d5",
            "5fead06f2a3d1643d2fb3fd87706b495aabbe036",
            "3b8ec7b75bbf17854c66310c04b10c6c26834679",
            "2198 Passed / 26 Skipped / 0 Failed",
            "625673281ca42553bfef0dcb24cad2d064dd309e4a82d9452b0ebd6593055255",
            "Task 5 reviews: `Ready`",
            "30754668448",
            "30754668445",
            "PR #17",
            "f63b0a5da47f76dd38f7cf5e79a39e99cf918005",
            "30755106798",
            "30755106795",
            "73e774bb1da93bf009e8dedaa3e67f5860cf6722",
            "Remote CI: `Passed`",
            selected_design_path,
            selected_plan_path,
            intake_path,
            "Reader API v1 stable remains unstarted",
            "Final Qualification remains unstarted",
        ):
            self.assertIn(term, selected_cursor)

    def test_240_task11_scope_discovery_is_recoverable(self):
        active_path = f".agents/active/{TASK11_SCOPE_ACTIVE_FILE}"
        completed_path = f".agents/completed/{TASK11_SCOPE_COMPLETED_FILE}"
        design_path = (
            "docs/superpowers/specs/"
            "2026-08-02-chemblender-2.4.0-task11-scope-discovery-design.md"
        )
        plan_path = (
            "docs/superpowers/plans/"
            "2026-08-02-chemblender-2.4.0-task11-scope-discovery.md"
        )
        intake_path = (
            "docs/quantum-visualization/2.4.0/task11-candidate-intake.md"
        )
        selected_design_path = (
            "docs/superpowers/specs/"
            "2026-08-02-chemblender-2.4.0-final-qualification-design.md"
        )
        selected_plan_path = (
            "docs/superpowers/plans/"
            "2026-08-02-chemblender-2.4.0-final-qualification.md"
        )
        queued_path = f".agents/queued/{FINAL_QUALIFICATION_CURSOR_FILE}"
        qualification_active_path = (
            f".agents/active/{FINAL_QUALIFICATION_CURSOR_FILE}"
        )
        qualification_path = (
            f".agents/completed/{FINAL_QUALIFICATION_CURSOR_FILE}"
        )
        cube_cursor_path = ".agents/completed/2.4.0-cube-export-ui.md"
        self.assertFalse((ROOT / active_path).exists(), active_path)
        self.assertTrue((ROOT / completed_path).is_file(), completed_path)
        self.assertFalse((ROOT / queued_path).exists(), queued_path)
        self.assertFalse(
            (ROOT / qualification_active_path).exists(),
            qualification_active_path,
        )
        self.assertTrue((ROOT / qualification_path).is_file(), qualification_path)
        cursor = self.read_doc(completed_path)
        design = self.read_doc(design_path)
        plan = self.read_doc(plan_path)
        intake = self.read_doc(intake_path)
        selected_design = self.read_doc(selected_design_path)
        selected_plan = self.read_doc(selected_plan_path)
        qualification = self.read_doc(qualification_path)
        cube_cursor = self.read_doc(cube_cursor_path)

        for term in (
            "CB240-TASK11-SCOPE-DISCOVERY",
            "State: `completed`",
            "Current task: `Task 11 Scope Discovery checkpoint complete`",
            "73e774bb1da93bf009e8dedaa3e67f5860cf6722",
            design_path,
            plan_path,
            "Reader API v1 stable gate",
            "2.4.0 Final Qualification",
            "Selection: `2.4.0 Final Qualification`",
            intake_path,
            "Reader API stable: `Deferred`",
            selected_plan_path,
            qualification_active_path,
            "072f5fe108bb70e80c4306e6c84e5a050efe4ffc",
            "2bb6b2a7fc6a0c8f9c8dea56a1c10b246888a298",
            "1bab04155aeeaaed534f3902b8ab336ab96a2e83",
            "85368c86632ac5015ecf0a53a93b62222bb2da20",
            "f540bebb9ef97da3eb458d9ebab4dd91a4f84fce",
            "3e39a85e507d4749b51c3f3eed8c1fa7df7088ea",
            "43 Passed",
            "UTF-8/no-BOM",
            "zero runtime diff",
            "PR #18",
            "30756421957",
            "30756421955",
            "aa6a92978f397011dafb3d79adac29d608262db4",
            "Remote CI: `Passed`",
            "Task 0 activation complete",
            "No runtime implementation",
        ):
            self.assertIn(term, cursor)
        for term in (
            "Selected: 2.4.0 Final Qualification",
            "Deferred: Reader API v1 stable gate",
            "PR #17",
            "f63b0a5da47f76dd38f7cf5e79a39e99cf918005",
            "30755106798",
            "30755106795",
        ):
            self.assertIn(term, design)
        for term in (
            "Task 1: Persist the Task 11 discovery boundary",
            "Task 2: Freeze Native Cube Export UI remote evidence",
            "Task 3: Audit and select one candidate",
            "Task 4: Queue 2.4.0 Final Qualification",
            "Task 5: Verify, review and checkpoint",
        ):
            self.assertIn(term, plan)
        for term in (
            "PR #17",
            "f63b0a5da47f76dd38f7cf5e79a39e99cf918005",
            "30755106798",
            "30755106795",
            "73e774bb1da93bf009e8dedaa3e67f5860cf6722",
            "Remote CI: `Passed`",
            "ancestor",
        ):
            self.assertIn(term, cube_cursor)
        for term in (
            "Task 12 — 2.4.0 Final Qualification",
            "Reader API v1 stable gate",
            "Selected",
            "Deferred",
            "chemblender.reader.json",
            "0 downloads",
            "1.0-rc1",
            "F5 / project_browser / preview_confirmation",
            "do not combine",
            "30755106798",
            "30755106795",
        ):
            self.assertIn(term, intake)
        for term in (
            "Preserve Reader API `1.0-rc1`",
            "No new capability",
            "committed tree",
            "Blender 5.1.2",
            "exact-head CI",
            "ordinary merge commit",
        ):
            self.assertIn(term, selected_design)
        for term in (
            "Task 0: Activate the queued qualification",
            "Task 1: Audit frozen public and scientific boundaries",
            "Task 2: Run complete Python and dependency qualification",
            "Task 3: Rebuild and audit the committed extension artifact",
            "Task 4: Run Blender product qualification",
            "Task 5: Review, checkpoint and exact-head remote gate",
            "1.0-rc1",
            "version",
            "tag",
            "Release",
        ):
            self.assertIn(term, selected_plan)
        for term in (
            "CB240-FINAL-QUALIFICATION-T12",
            "State: `completed`",
            "Current task: `Task 5 — Final Qualification checkpoint complete`",
            "Task 1 frozen-boundary audit",
            "aa6a92978f397011dafb3d79adac29d608262db4",
            "codex/2.4.0-final-qualification",
            "PR #18",
            "30756421957",
            "30756421955",
            selected_design_path,
            selected_plan_path,
            "Independent reviews: `Ready`",
            "Full Python qualification: `2200 Passed / 26 Skipped / 0 Failed`",
            "Remote exact-head gate: `Pending`",
            "Reader API `1.0-rc1`",
            "No version, tag or Release",
        ):
            self.assertIn(term, qualification)

    def test_240_final_qualification_records_frozen_boundaries(self):
        evidence_path = (
            "docs/quantum-visualization/2.4.0/final-qualification.md"
        )
        evidence = self.read_doc(evidence_path)
        for term in (
            "Reader API: `1.0-rc1`",
            "Sidecar manifest: `1.0`",
            "Project schema: `1.0`",
            "Canonical document: `0.1`",
            "ChemBlender.core",
            "ChemBlender.reader_api",
            "rdkit",
            "gemmi",
            "spglib",
            "cclib",
            "iodata",
            "gbasis",
            "ase",
            "pymatgen",
            "14 export-capable reader descriptors",
            "| XYZ | F4 | project_browser | single_structure_coordinates_only |",
            "| Cube | F5 | project_browser | preview_confirmation |",
            "| CJSON | F5 | core | controlled_envelope |",
            "| QCSchema | F5 | core | source_envelope |",
            "Generated document drift: `0 files`",
        ):
            self.assertIn(term, evidence)

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
            "4.716870 s",
            "3.089668",
            "49,279,468 bytes",
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


class ReleasePlanningContractTests(unittest.TestCase):
    def read_doc(self, relative_path: str) -> str:
        path = ROOT / relative_path
        raw = path.read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"), path)
        return raw.decode("utf-8")

    def test_release_planning_is_routed_and_records_exact_evidence(self):
        active = ROOT / ".agents/active/2.4.0-release-planning.md"
        completed = ROOT / ".agents/completed/2.4.0-release-planning.md"
        evidence_path = ROOT / "docs/quantum-visualization/2.4.0/release-planning.md"
        self.assertEqual(1, sum(path.is_file() for path in (active, completed)))
        self.assertTrue(evidence_path.is_file(), evidence_path)
        cursor_path = active if active.is_file() else completed
        cursor = self.read_doc(str(cursor_path.relative_to(ROOT)))
        evidence = self.read_doc(
            str(evidence_path.relative_to(ROOT))
        )
        normalized_cursor = " ".join(cursor.split())
        normalized_evidence = " ".join(evidence.split())

        self.assertIn("CB240-RELEASE-PLANNING", cursor)
        self.assertIn("Reader API: `1.0-rc1`, unchanged", cursor)
        self.assertIn(
            "PR #19: `https://github.com/psiQAQ/ChemBlender_2_x/pull/19`; "
            "- exact feature head: "
            "`98b4da6e13e28fa95c7abdc52494dd4aa7e1e86e`; "
            "- `extension-package` run `30759984026`: `Passed`; "
            "- `optional-qc-core` run `30759984023`: `Passed`; "
            "- ordinary merge: "
            "`9763d2afbb38a68061161a855ec333ce0e970fe4`; "
            "- ancestor verification: `Passed`.",
            normalized_cursor,
        )
        for term in (
            "Prepare `2.4.0-rc.1` before Stable `2.4.0`.",
            "Frozen scope: `MOL2, PDB, PQR, Cube`; Reader API: `1.0-rc1`; "
            "source: PR #19.",
            "`extension-package` run `30759984026`: `Passed` for exact "
            "feature head `98b4da6e13e28fa95c7abdc52494dd4aa7e1e86e`.",
            "`optional-qc-core` run `30759984023`: `Passed` for exact "
            "feature head `98b4da6e13e28fa95c7abdc52494dd4aa7e1e86e`.",
            "Ordinary merge `9763d2afbb38a68061161a855ec333ce0e970fe4`: "
            "`Passed`; exact feature head ancestry: `Passed`.",
            "Release order: exact PR-head CI -> ordinary merge -> exact "
            "merge-SHA CI -> tag authorization -> annotated tag -> exact-tag "
            "CI and installed-runtime evidence -> verification-only release "
            "run -> publication authorization.",
            "CI success is evidence, not merge or publication authority.",
        ):
            self.assertIn(term, normalized_evidence)


if __name__ == "__main__":
    unittest.main()
