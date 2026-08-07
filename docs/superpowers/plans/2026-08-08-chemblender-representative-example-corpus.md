# ChemBlender Representative Example Corpus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a provenance-locked, specification-backed representative corpus for every ChemBlender base format, document every contract and representative input, and prove the representative workflows in Blender 5.1 through public Operators.

**Architecture:** Keep the existing tiny files as fast `contract` fixtures and add one bounded `representative` path per format family where scale adds meaningful coverage. `manifest.json` schema 2 is the source of truth for role, provenance, license, derivation, exact bytes, metrics, specifications and adjacent documentation; one standard-library preparation script reproduces downloaded/derived inputs without adding a dependency or submodule. Reuse the existing workflow runner and public `bpy.ops.chemblender.*` boundary for runtime proof.

**Tech Stack:** Python 3.13 standard library, Blender 5.1 bundled NumPy, existing extension RDKit 2026.3.3 and Gemmi 0.7.5, `unittest`, Blender Extensions CLI, Blender MCP, Markdown and JSON.

## Global Constraints

- Preserve every existing contract input path and exact byte/hash behavior.
- Use only HTTPS sources from an official platform, DOI record or official project repository pinned to an exact commit.
- Do not commit material without an explicit redistribution basis; record policy caveats instead of inventing an SPDX license.
- Do not add or change project dependencies, install packages, or add a Git submodule.
- Each committed file should remain below 50 MiB and may never exceed 100 MiB.
- Use Blender 5.1.0 or newer and only public `bpy.ops.chemblender.*` / public RNA for product validation.
- Store retained `.blend` and `.cbq` evidence under `examples/user-workflows/outputs/representative/`.
- Work only on `codex/representative-example-corpus`; commit locally, then merge locally into `main`; do not push, tag, publish, release, create a PR or alter remotes.
- Treat a package build, manifest parse or simulated import as insufficient without real Blender output and cold reopen evidence.

---

## File map

- `examples/user-workflows/manifest.json`: schema 2 inventory and exact-byte contract for inputs and retained outputs.
- `examples/user-workflows/scripts/prepare_representative_inputs.py`: pinned downloads plus deterministic derivations; no runtime import or UI behavior.
- `tests/test_representative_examples.py`: provenance, size, documentation and format-semantic checks.
- `examples/user-workflows/scripts/run_ui_workflows.py`: existing Blender Operator runner, extended only with representative cases.
- `examples/user-workflows/inputs/<family>/<stem>.md`: user-facing adjacent documentation for one data file.
- `docs/user/workflows/formats.md` and workflow chapters: corpus routing, scale guidance and copyable public-Operator prompts.
- `examples/user-workflows/results/local-representative-2.4.0.json`: checked runtime result from the exact local package.
- `examples/user-workflows/outputs/representative/`: bounded saved scene/sidecar evidence.

### Task 1: Lock manifest schema 2 and the corpus contract

**Files:**
- Create: `tests/test_representative_examples.py`
- Modify: `examples/user-workflows/manifest.json`
- Modify: `tests/test_user_workflows.py`

**Interfaces:**
- Consumes: existing schema 1 records and `examples/user-workflows/inputs/` paths.
- Produces: schema 2 records with `role`, `source_platform`, `source_id`, `source_url`, `retrieved_at`, `license`, `license_url`, `derivation`, `source_sha256`, `sha256`, `bytes`, `metrics`, `specifications`, and `documentation`.

- [x] **Step 1: Write the failing schema and exact-byte tests**

```python
REQUIRED_KEYS = {
    "path", "family", "role", "source_platform", "source_id", "source_url",
    "retrieved_at", "license", "license_url", "derivation", "source_sha256",
    "sha256", "bytes", "runtime", "expected", "workflow", "metrics",
    "specifications", "documentation",
}

def test_manifest_schema_two_is_complete(self):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    self.assertEqual(manifest["schema_version"], "2")
    for record in manifest["files"]:
        self.assertEqual(set(record), REQUIRED_KEYS)
        self.assertIn(record["role"], {"contract", "representative"})
        self.assertTrue(record["source_url"].startswith("https://") or record["source_url"].startswith("repository:"))
        self.assertTrue(record["documentation"].endswith(".md"))

def test_manifest_exact_bytes_and_limits(self):
    for record in self.records:
        path = EXAMPLE_ROOT / record["path"]
        payload = path.read_bytes()
        self.assertEqual(len(payload), record["bytes"])
        self.assertEqual(hashlib.sha256(payload).hexdigest(), record["sha256"])
        self.assertLess(len(payload), 50 * 1024 * 1024)
        self.assertLessEqual(len(payload), 100 * 1024 * 1024)
```

- [x] **Step 2: Run the focused tests and confirm RED**

Run:

```powershell
$pythonBin = 'C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe'
& $pythonBin -m unittest tests.test_representative_examples tests.test_user_workflows -v
```

Expected: FAIL because the manifest is schema 1 and adjacent documentation does not yet exist.

- [x] **Step 3: Upgrade existing records without changing their data bytes**

For every existing record, set `role` to `contract`, preserve the current `sha256` and `bytes`, use the repository fixture path as `source_id`, set `source_sha256` equal to `sha256`, identify the repository license, and add format-specific metrics plus one or more HTTPS specification records. Change the old schema assertion in `tests/test_user_workflows.py` from `"1"` to `"2"`; do not weaken its family, sort or byte checks.

- [x] **Step 4: Run focused schema and byte tests**

Run the Step 2 command. Expected: schema, keys, sort and byte checks PASS. Adjacent-document existence is introduced with its implementation in Task 4, so every intermediate commit remains green.

- [x] **Step 5: Commit the schema boundary**

```powershell
git add tests/test_representative_examples.py tests/test_user_workflows.py examples/user-workflows/manifest.json
git commit -m "test: define representative corpus contract"
```

### Task 2: Acquire and pin authoritative source bytes

**Files:**
- Create: `examples/user-workflows/scripts/prepare_representative_inputs.py`
- Create: `examples/user-workflows/inputs/cif/cod-4503272-caffeine-cocrystal.cif`
- Create: `examples/user-workflows/inputs/cjson/avogadro-phthalocyanine.cjson`
- Create: `examples/user-workflows/inputs/mol2/openbabel-5sun-protein.mol2`
- Create: `examples/user-workflows/inputs/pdb/1d3z-ubiquitin-nmr.pdb`
- Create: `examples/user-workflows/inputs/pqr/apbs-protein-rna-nb.pqr`
- Create: `examples/user-workflows/inputs/qcschema/molssi-water-gradient-hf.json`
- Modify: `examples/user-workflows/manifest.json`

**Interfaces:**
- Consumes: official URLs and a caller-supplied `.agents/cache/representative-examples/` directory.
- Produces: `download(url: str, destination: Path) -> tuple[str, int]`, returning SHA-256 and byte length; exact direct-source records in the manifest.

- [x] **Step 1: Add a failing acquisition-script contract**

```python
def test_preparation_script_pins_only_https_sources(self):
    module = load_preparation_module()
    self.assertTrue(module.SOURCES)
    for source in module.SOURCES.values():
        self.assertTrue(source["url"].startswith("https://"))
        self.assertTrue(source["license_url"].startswith("https://"))
        self.assertTrue(source["source_id"])
```

- [x] **Step 2: Run the one test and confirm RED**

Run: `& $pythonBin -m unittest tests.test_representative_examples.RepresentativeExampleTests.test_preparation_script_pins_only_https_sources -v`

Expected: FAIL because `prepare_representative_inputs.py` does not exist.

- [x] **Step 3: Implement the minimal source table and atomic downloader**

Pin these exact upstream identities in `SOURCES`: wwPDB CCD `AIN`, `CFF`, `TA1`; PDB entry `1D3Z`; COD `4503272` and `9012293`; rMD17 DOI `10.6084/m9.figshare.12672038.v3`; Open Babel commit `0e94434fa75c9f61095023e3c12e0d5f2ac035ff`; APBS commit `4613d0d547c3c71df8815dcb85e9e19abf61822c`; Avogadro commit `e32739bed4b9d79db080a32a0026947e15b240d9`; QCSchema commit `5390e6f11d21847e4e7ca2ad14a97594f957cb2d`. Use `urllib.request`, a descriptive User-Agent, a temporary file followed by `Path.replace`, and `hashlib.sha256`. The Figshare endpoint proved range-only and the first proxy stream was truncated, so the implemented standard-library reader retries only the failed 64 MiB range and validates every `Content-Range`; no retry framework or network dependency was added.

- [x] **Step 4: Download only the selected source files and record exact evidence**

Run:

```powershell
& $pythonBin examples/user-workflows/scripts/prepare_representative_inputs.py `
  --cache .agents/cache/representative-examples `
  --output-root examples/user-workflows/inputs `
  --stage download
```

Expected: selected files are fetched and source SHA-256 plus bytes are printed as JSON. The full 1,066,301,513-byte rMD17 container is never stored; only its 153,601,803-byte aspirin NPZ is retained in ignored `.agents/cache` for derivation. No cached source is committed, and every committed direct source remains below 50 MiB.

- [x] **Step 5: Verify upstream licenses before copying bytes**

Record: PDB archive and CCD as CC0; COD as CC0; rMD17 as CC0; Avogadro as BSD-3-Clause; QCSchema as BSD-3-Clause; APBS using its pinned three-clause redistribution text; Open Babel using the pinned repository `COPYING`. Reject the file if the pinned source does not cover it.

- [x] **Step 6: Add direct-source manifest records and run tests**

Run: `& $pythonBin -m unittest tests.test_representative_examples -v`

Expected: source identity, HTTPS, exact bytes and size checks PASS for direct-source files; derived-file and documentation checks remain pending.

- [x] **Step 7: Commit authoritative source bytes**

```powershell
git add examples/user-workflows/scripts/prepare_representative_inputs.py examples/user-workflows/inputs examples/user-workflows/manifest.json tests/test_representative_examples.py
git commit -m "data: add pinned representative source files"
```

### Task 3: Build deterministic derived formats

**Files:**
- Modify: `examples/user-workflows/scripts/prepare_representative_inputs.py`
- Create: `examples/user-workflows/inputs/xyz/ta1-paclitaxel-ccd.xyz`
- Create: `examples/user-workflows/inputs/extxyz/aspirin-rmd17-32.extxyz`
- Create: `examples/user-workflows/inputs/mol/ain-aspirin-v2000.mol`
- Create: `examples/user-workflows/inputs/mol/ta1-paclitaxel-v3000.mol`
- Create: `examples/user-workflows/inputs/sdf/ccd-3d-showcase.sdf`
- Create: `examples/user-workflows/inputs/smiles/ta1-paclitaxel-isomeric.smi`
- Create: `examples/user-workflows/inputs/poscar/cod-9012293-diamond.POSCAR`
- Create: `examples/user-workflows/inputs/poscar/cod-9012293-diamond-2x2x2.CONTCAR`
- Create: `examples/user-workflows/inputs/cube/h2-lcao-1s-density-64.cube`
- Modify: `examples/user-workflows/manifest.json`

**Interfaces:**
- Consumes: cached wwPDB CCD SDFs, COD `9012293`, and rMD17 aspirin NPZ.
- Produces: `derive(cache: Path, output_root: Path) -> dict[str, dict[str, object]]`, with one metrics/hash record per derived path.

- [x] **Step 1: Write failing semantic thresholds**

```python
MINIMUMS = {
    "inputs/extxyz/aspirin-rmd17-32.extxyz": {"frames": 32, "atoms_per_frame": 21},
    "inputs/pdb/1d3z-ubiquitin-nmr.pdb": {"frames": 10},
    "inputs/mol2/openbabel-5sun-protein.mol2": {"atoms": 6185, "substructures": 390},
    "inputs/cube/h2-lcao-1s-density-64.cube": {"grid": [64, 64, 64]},
    "inputs/sdf/ccd-3d-showcase.sdf": {"records": 3},
    "inputs/poscar/cod-9012293-diamond-2x2x2.CONTCAR": {"sites": 64},
}

def test_representative_metrics_meet_format_thresholds(self):
    by_path = {record["path"]: record for record in self.records}
    for path, expected in MINIMUMS.items():
        self.assertEqual(by_path[path]["role"], "representative")
        for key, value in expected.items():
            self.assertEqual(by_path[path]["metrics"][key], value)
```

- [x] **Step 2: Run the threshold test and confirm RED**

Run: `& $pythonBin -m unittest tests.test_representative_examples.RepresentativeExampleTests.test_representative_metrics_meet_format_thresholds -v`

Expected: FAIL because derived paths are absent.

- [x] **Step 3: Implement CCD molecular derivations with existing RDKit**

Load `AIN`, `CFF`, and `TA1` ideal SDF records with RDKit 2026.3.3. Write `AIN` as V2000, force `TA1` as V3000, concatenate the three valid SDF records in the order `AIN`, `CFF`, `TA1`, write one canonical isomeric `TA1` SMILES record because the public ChemBlender reader intentionally accepts one non-empty line, and write `TA1` elements plus coordinates as XYZ. Preserve explicit hydrogens where the target format represents them and record RDKit version, source hashes and ordering in `derivation`.

- [x] **Step 4: Implement the fixed rMD17 subset**

Read NPZ with `numpy.load(..., allow_pickle=False)`, choose array rows `0, 100, ..., 3100`, and write 32 extXYZ frames using `Properties=species:S:1:pos:R:3:forces:R:3` plus the original `old_indices` value as `source_index`. Convert rMD17 kcal/mol and kcal/mol/angstrom values to the reader's declared electron-volt units instead of silently relabelling them. Do not present this time-series subset as statistically independent training data.

- [x] **Step 5: Implement crystal and grid derivations**

Parse COD `9012293` through existing Gemmi-backed `parse_cif`, export its periodic structure with existing `export_poscar`, then generate the `2 × 2 × 2` direct-coordinate supercell with 64 sites and a zero ion-velocity block. Generate the Cube on a `64 × 64 × 64` grid spanning `[-6, 6]` bohr around H nuclei separated by 1.4 bohr, using the normalized two-electron bonding density `rho=(phi_A+phi_B)^2/(1+S)` where `phi=exp(-r)/sqrt(pi)` and `S=exp(-R)*(1+R+R^2/3)`; label it an analytic LCAO model, not HF/DFT.

- [x] **Step 6: Run derivation twice and prove byte determinism**

Run:

```powershell
& $pythonBin examples/user-workflows/scripts/prepare_representative_inputs.py --cache .agents/cache/representative-examples --output-root examples/user-workflows/inputs --stage derive
& $pythonBin examples/user-workflows/scripts/prepare_representative_inputs.py --cache .agents/cache/representative-examples --output-root examples/user-workflows/inputs --stage verify
```

Expected: the second run reports no byte/hash drift and all outputs stay below 50 MiB.

- [x] **Step 7: Parse derived files and compare representable semantics**

Use ChemBlender readers to assert atom/frame/record/site/grid counts, finite coordinates and fields, `source_index` preservation, and non-zero Cube range. Compare CCD-derived molecular outputs by atomic number, bond topology, formal charge and stereochemistry; do not require formats to preserve fields they cannot represent.

- [x] **Step 8: Commit derived inputs**

```powershell
git add examples/user-workflows/scripts/prepare_representative_inputs.py examples/user-workflows/inputs examples/user-workflows/manifest.json tests/test_representative_examples.py
git commit -m "data: derive representative format corpus"
```

### Task 4: Document every input beside its data

**Files:**
- Create: `examples/user-workflows/inputs/cif/nacl.md`
- Create: `examples/user-workflows/inputs/cif/cod-4503272-caffeine-cocrystal.md`
- Create: `examples/user-workflows/inputs/cjson/water-results.md`
- Create: `examples/user-workflows/inputs/cjson/avogadro-phthalocyanine.md`
- Create: `examples/user-workflows/inputs/cube/two-datasets.md`
- Create: `examples/user-workflows/inputs/cube/h2-lcao-1s-density-64.md`
- Create: `examples/user-workflows/inputs/extxyz/carbon-trajectory.md`
- Create: `examples/user-workflows/inputs/extxyz/aspirin-rmd17-32.md`
- Create: `examples/user-workflows/inputs/legacy/chemblender-2.1-molecule.md`
- Create: `examples/user-workflows/inputs/mol/water-v2000.md`
- Create: `examples/user-workflows/inputs/mol/water-v3000.md`
- Create: `examples/user-workflows/inputs/mol/ain-aspirin-v2000.md`
- Create: `examples/user-workflows/inputs/mol/ta1-paclitaxel-v3000.md`
- Create: `examples/user-workflows/inputs/mol2/substructure.md`
- Create: `examples/user-workflows/inputs/mol2/openbabel-5sun-protein.md`
- Create: `examples/user-workflows/inputs/pdb/model-trajectory.md`
- Create: `examples/user-workflows/inputs/pdb/multimodel.md`
- Create: `examples/user-workflows/inputs/pdb/1d3z-ubiquitin-nmr.md`
- Create: `examples/user-workflows/inputs/poscar/si.md`
- Create: `examples/user-workflows/inputs/poscar/velocities.md`
- Create: `examples/user-workflows/inputs/poscar/cod-9012293-diamond.md`
- Create: `examples/user-workflows/inputs/poscar/cod-9012293-diamond-2x2x2.md`
- Create: `examples/user-workflows/inputs/pqr/with-chain.md`
- Create: `examples/user-workflows/inputs/pqr/apbs-protein-rna-nb.md`
- Create: `examples/user-workflows/inputs/qcschema/atomic-result.md`
- Create: `examples/user-workflows/inputs/qcschema/molssi-water-gradient-hf.md`
- Create: `examples/user-workflows/inputs/sdf/mixed-properties.md`
- Create: `examples/user-workflows/inputs/sdf/ccd-3d-showcase.md`
- Create: `examples/user-workflows/inputs/smiles/ethanol.md`
- Create: `examples/user-workflows/inputs/smiles/ta1-paclitaxel-isomeric.md`
- Create: `examples/user-workflows/inputs/xyz/water.md`
- Create: `examples/user-workflows/inputs/xyz/ta1-paclitaxel-ccd.md`
- Modify: `examples/user-workflows/manifest.json`

**Interfaces:**
- Consumes: final manifest records and parser/runtime evidence.
- Produces: one same-stem Markdown path per data file, referenced by `record["documentation"]`.

- [x] **Step 1: Add a failing adjacent-document content test**

```python
REQUIRED_HEADINGS = (
    "## 用途与选择理由", "## 来源与许可", "## 规模与分辨率",
    "## 字段说明", "## ChemBlender 支持边界", "## 操作流程",
    "## Agent 提示词", "## 完整性与验证", "## 参考资料",
)

def test_each_input_has_user_facing_adjacent_documentation(self):
    for record in self.records:
        text = (EXAMPLE_ROOT / record["documentation"]).read_text(encoding="utf-8")
        for heading in REQUIRED_HEADINGS:
            self.assertIn(heading, text, (record["path"], heading))
        self.assertIn(record["sha256"], text)
        self.assertIn(str(record["bytes"]), text)
        self.assertIn("Blender MCP", text)
        self.assertIn("bpy.ops.chemblender", text)
```

- [x] **Step 2: Run the documentation test and confirm RED**

Run: `& $pythonBin -m unittest tests.test_representative_examples.RepresentativeExampleTests.test_each_input_has_user_facing_adjacent_documentation -v`

Expected: FAIL at the first missing document.

- [x] **Step 3: Write each document from actual file content**

Use the nine required headings. Explain each field with an actual value/range from that file; distinguish format capacity from ChemBlender 2.4.0 support; state whether size measures atom count, frames, grid points or only text encoding; include source ID, source URL, retrieval date, license, derivation, bytes and SHA-256. Mark contract fixtures as synthetic/repository fixtures and never present them as experimental data.

- [x] **Step 4: Add one copyable public-Operator prompt per file**

Each fenced `text` prompt must tell the Agent to connect through Blender MCP, use UI-equivalent `bpy.ops.chemblender.*` and Operator RNA, avoid private modules, report import diagnostics and project entities, request confirmation for lossy export, keep `.cbq` beside `.blend`, and stop rather than bypass a confirmation/cancellation boundary.

- [x] **Step 5: Review Chinese prose with `humanizer-zh`**

Remove promotional wording, repetitive transition phrases and unsupported claims. Keep exact identifiers, field names, units, warnings and citations unchanged.

- [x] **Step 6: Run adjacent-document tests and expose the Task 5 link gap**

Run: `& $pythonBin -m unittest tests.test_representative_examples tests.test_user_workflows -v`

Result: all 9 representative-example tests PASS. The existing workflow suite has 21 PASS
and the one expected RED link-inventory test for the 15 new representative paths; Task 5
owns those workflow-document links.

- [x] **Step 7: Commit adjacent documentation**

```powershell
git add examples/user-workflows/inputs examples/user-workflows/manifest.json tests/test_representative_examples.py
git commit -m "docs: explain every workflow input"
```

### Task 5: Route users through the representative corpus

**Files:**
- Modify: `README.md`
- Modify: `docs/README.md`
- Modify: `docs/user/workflows/README.md`
- Modify: `docs/user/workflows/01-import.md`
- Modify: `docs/user/workflows/02-process.md`
- Modify: `docs/user/workflows/03-visualize.md`
- Modify: `docs/user/workflows/04-export.md`
- Modify: `docs/user/workflows/05-project-lifecycle.md`
- Modify: `docs/user/workflows/06-agent-and-mcp.md`
- Modify: `docs/user/workflows/formats.md`
- Modify: `examples/user-workflows/README.md`
- Modify: `tests/test_user_workflows.py`

**Interfaces:**
- Consumes: schema 2 manifest and adjacent documents.
- Produces: user routes for import, process, visualize, export, lifecycle and Agent-assisted execution.

- [x] **Step 1: Extend the failing link inventory**

Update the existing test so every data path, adjacent Markdown path and retained output bundle must be linked from the workflow documentation. Add assertions for the terms `contract`, `representative`, `分辨率`, `来源`, `许可证`, and `人工插件使用体验检阅`.

- [x] **Step 2: Run workflow tests and confirm RED**

Run: `& $pythonBin -m unittest tests.test_user_workflows -v`

Expected: FAIL because new adjacent documents and representative paths are not routed.

- [x] **Step 3: Update the overview and format matrix**

Add a concise “快速合同样本 / 代表性样本” explanation, a format-to-sample matrix, what “resolution” means for coordinate/trajectory/grid/crystal/hierarchy data, download/reproduction boundaries, and links to every adjacent file document. Preserve the existing distinction between plugin capabilities and Agent-only scene/material work.

- [x] **Step 4: Update each workflow chapter and prompts**

Use representative examples where scale matters: rMD17 for trajectory; 1D3Z and APBS PQR for hierarchy; COD for crystals; H2 Cube for volumes/surfaces; RCSB CCD for molecular conversion; Open Babel 5SUN for MOL2. Keep loss preview/confirmation explicit and do not expose private APIs.

- [x] **Step 5: Run all documentation contracts**

Run:

```powershell
& $pythonBin -m unittest tests.test_user_workflows tests.test_quantum_visualization_docs tests.test_representative_examples -v
```

Expected: PASS.

- [x] **Step 6: Commit user routing**

```powershell
git add README.md docs examples/user-workflows/README.md tests/test_user_workflows.py
git commit -m "docs: route representative user workflows"
```

### Task 6: Exercise representative semantics in code

**Files:**
- Modify: `tests/test_representative_examples.py`
- Modify only if a real defect is reproduced: the narrowest affected file under `ChemBlender/core/` or `ChemBlender/ui/`
- Modify with any public entrypoint/responsibility change: `.agents/reference/code-architecture-guide.md`

**Interfaces:**
- Consumes: every representative input through its registered reader.
- Produces: semantic assertions over structures, topology, records, trajectories, hierarchy, charge/radius, periodic data, Grid3D, CJSON and QCSchema.

- [ ] **Step 1: Add parser-level assertions for every representative path**

Assert `TA1=113 atoms/119 bonds`, `rMD17=32 frames/21 atoms with energy and force`, `SDF=3 records`, `1D3Z=10 MODEL frames with chain/residue hierarchy`, `5SUN MOL2=6185 atoms/6248 bonds/390 substructures`, APBS PQR charge/radius completeness, COD cell/symmetry/occupancy, POSCAR/CONTCAR site and velocity counts, Cube dimensions/value range, and successful CJSON/QCSchema envelope recovery.

- [ ] **Step 2: Run the smallest failing parser test first**

Run one `unittest` node for each family. Expected: PASS for supported semantics; any failure must reproduce a reader defect or correct an inaccurate fixture expectation before broader work.

- [ ] **Step 3: Fix only confirmed defects with systematic debugging and TDD**

Trace all callers of the failing shared parser/exporter, add one focused regression test that fails for the root cause, implement the smallest shared fix, and rerun sibling reader/exporter tests. Do not broaden ChemBlender capability merely to consume an unsupported optional field; document preserved raw fields and diagnostics instead.

- [ ] **Step 4: Run the static and reader suites**

Run:

```powershell
& $pythonBin -m unittest tests.test_representative_examples tests.test_user_workflows -v
& $pythonBin -m unittest discover -s tests -p 'test_*.py'
```

Expected: PASS with optional-dependency skips reported separately; no representative format remains unparsed.

- [ ] **Step 5: Commit semantic coverage and any root-cause fixes**

```powershell
git add tests/test_representative_examples.py ChemBlender .agents/reference/code-architecture-guide.md
git commit -m "test: verify representative format semantics"
```

Omit unchanged paths from `git add`; if no product defect exists, the commit contains tests only.

### Task 7: Exercise public UI workflows in Blender 5.1

**Files:**
- Modify: `examples/user-workflows/scripts/run_ui_workflows.py`
- Modify: `tests/test_user_workflows.py`
- Create: `examples/user-workflows/results/local-representative-2.4.0.json`
- Create: `examples/user-workflows/outputs/representative/molecular/molecular.blend`
- Create: `examples/user-workflows/outputs/representative/trajectory/trajectory.blend`
- Create: `examples/user-workflows/outputs/representative/biological/biological.blend`
- Create: `examples/user-workflows/outputs/representative/crystal/crystal.blend`
- Create: `examples/user-workflows/outputs/representative/grid/grid.blend`
- Create as generated companions: matching `.cbq/` sidecars below each representative output directory.
- Modify only for reproduced defects: narrow files under `ChemBlender/`, matching tests and architecture docs.

**Interfaces:**
- Consumes: public Operator RNA, schema 2 manifest and representative inputs.
- Produces: runner cases `REP-MOLECULAR`, `REP-TRAJECTORY`, `REP-BIOLOGICAL`, `REP-CRYSTAL`, `REP-GRID`, `REP-SAVE-REOPEN-PREP` plus cold-reopen evidence.

- [ ] **Step 1: Write failing runner inventory assertions**

Require the six representative case IDs, their exact input paths, public Operator names and retained outputs. Reject executable imports from `ChemBlender` private modules in the runner.

- [ ] **Step 2: Run runner-contract tests and confirm RED**

Run: `& $pythonBin -m unittest tests.test_user_workflows -v`

Expected: FAIL because representative case IDs do not exist.

- [ ] **Step 3: Extend the existing runner without a second framework**

Reuse `RunContext`, `_operator`, `_project_rows`, `_run_case`, save/checkpoint and cold-reopen helpers. Each case imports via `bpy.ops.chemblender.*`, inspects only public Scene RNA, records diagnostics/counts/timing, and saves only the five bounded evidence bundles. Do not call private core parsers to make an Operator failure look successful.

- [ ] **Step 4: Query and recover the Blender MCP runtime**

Run `blender-mcp --help`, then query Blender version, exact executable, bundled Python, runtime system and extension repositories together. Require Blender 5.1.0+; if the exact Blender 5.1 process is absent, start that executable, wait for the listener and repeat the live query.

- [ ] **Step 5: Build and install the exact extension package**

Run repository contracts, Blender native extension validation/build, inspect ZIP contents, install to a temporary profile, then install and enable `bl_ext.user_default.chemblender` in `user_default`. Record Git commit and package SHA-256 in the result JSON.

- [ ] **Step 6: Run all representative cases through Blender MCP**

Execute `REP-MOLECULAR`, `REP-TRAJECTORY`, `REP-BIOLOGICAL`, `REP-CRYSTAL`, `REP-GRID`, then `REP-SAVE-REOPEN-PREP`. Confirm loss dialogs rather than bypassing them; verify trajectory playback, hierarchy, periodic view, volume/surface, saved project rows and sidecar-local paths.

- [ ] **Step 7: Cold reopen each retained `.blend`**

Start a fresh Blender process/profile for reopen, verify linked entities/views, missing external files equals zero, frame counts/grid identity survive, and every `.blend`, `.cbq` member and VDB remains below 50 MiB and never above 100 MiB.

- [ ] **Step 8: Debug and fix any Blender defect at its root cause**

For each failure, preserve the runner report, reproduce with the smallest public Operator case, use systematic debugging, add a regression test, implement the narrow fix and rerun that case plus siblings. A Blender crash triggers restart of Blender 5.1 and resumption from the last completed case.

- [ ] **Step 9: Commit runtime evidence**

```powershell
git add examples/user-workflows/scripts/run_ui_workflows.py examples/user-workflows/results/local-representative-2.4.0.json examples/user-workflows/outputs/representative examples/user-workflows/manifest.json tests ChemBlender .agents/reference/code-architecture-guide.md
git commit -m "test: verify representative Blender workflows"
```

Omit unchanged product/architecture paths from `git add`.

### Task 8: Close the local release gate and integrate locally

**Files:**
- Modify: `.agents/active/representative-example-corpus.md`
- Move when all gates pass: `.agents/active/representative-example-corpus.md` to `.agents/completed/representative-example-corpus.md`
- Modify: `.agents/README.md`
- Modify: `docs/user/workflows/reviews/template.md`
- Create: `docs/user/workflows/reviews/local-2.4.0-representative-corpus.md`

**Interfaces:**
- Consumes: all static, parser, package, Blender runtime and cold-reopen evidence.
- Produces: an explicit `人工插件使用体验检阅` checklist for the user and a clean local merge into `main`.

- [ ] **Step 1: Add representative cases to the manual review template**

Add user-executable rows for every representative family and five saved bundles. Leave manual status `Not Run`; automation may prefill evidence references but must not claim the human review passed.

- [ ] **Step 2: Run final verification from the branch HEAD**

Run:

```powershell
& $pythonBin -m unittest discover -s tests -p 'test_*.py'
git diff --check
git status --short --branch
git ls-files examples/user-workflows/inputs | ForEach-Object { if ((Get-Item $_).Length -gt 100MB) { throw "oversize: $_" } }
```

Also repeat Blender extension validate/build, exact ZIP audit, enabled-key check and one cold reopen from the final commit. Expected: all Passed, no unexplained warning promoted to success, and worktree clean after final records are committed.

- [ ] **Step 3: Archive the active task with evidence**

Record source IDs/commits, hashes and sizes; test counts; Blender 5.1 version/executable; package hash; representative case results; cold reopen results; defects fixed; remaining human review status. Move the active cursor to completed and update `.agents/README.md` in the same commit.

- [ ] **Step 4: Commit the completion record**

```powershell
git add .agents docs/user/workflows/reviews
git commit -m "docs: record representative corpus verification"
```

- [ ] **Step 5: Verify local `main` has not drifted and merge**

In `D:\workspace\ChemBlender_2_x`, require a clean `main`, verify its current HEAD is an ancestor of `codex/representative-example-corpus`, then merge non-interactively. If main changed incompatibly or has user edits, stop and report rather than rebasing or overwriting.

```powershell
git -C D:\workspace\ChemBlender_2_x status --short --branch
git -C D:\workspace\ChemBlender_2_x merge --no-ff codex/representative-example-corpus -m "merge: representative example corpus"
```

- [ ] **Step 6: Verify the merged local main**

Rerun focused corpus/workflow tests, `git diff --check`, and `git status --short --branch` from local `main`. Do not push or publish.

## Self-review result

- Spec coverage: two-layer corpus, authoritative sources, license gate, per-file documentation, format semantics, Agent prompts, file limits, Blender public Operators, retained outputs, cold reopen, bug-fix loop, manual review gate and local-only merge each map to a task above.
- Placeholder scan: no deferred implementation marker is used; source identities, filenames, thresholds, formulas, commands and success conditions are explicit.
- Interface consistency: schema-2 field names and six `REP-*` case IDs are identical wherever consumed; preparation stages are `download`, `derive`, and `verify`; file stems match their adjacent Markdown paths.
