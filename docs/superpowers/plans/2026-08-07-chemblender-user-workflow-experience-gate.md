# ChemBlender User Workflow Experience Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify the complete user-workflow documentation, full base-format example corpus, UI-equivalent Blender MCP runner, and tracked manual prerelease experience gate, fix every reproduced in-scope plugin defect, then merge the locally committed result back into local `main` without publishing or pushing.

**Architecture:** `docs/user/workflows/` is the user-facing navigation and release-gate surface; `examples/user-workflows/` owns immutable example inputs, the checked manifest, public-Operator runtime runner, and selected reopenable outputs. Existing generated capability documents remain authoritative, while one standard-library contract test prevents the curated workflow layer from drifting. Blender validation uses the built Extension in `user_default` and calls only public `bpy.ops.chemblender.*` Operators/public RNA for ChemBlender operations.

**Tech Stack:** Markdown, JSON, Python 3.13 standard library `unittest`, Blender 5.1 Python API, Blender Extensions, Blender MCP, existing ChemBlender Reader API and public Operators.

## Global Constraints

- Work only in `D:\workspace\ChemBlender_2_x\.worktrees\user-workflow-experience-gate` on `codex/user-workflow-experience-gate` until final local integration.
- Use local commits only. Do not push, create a PR, tag, publish, alter remotes, or dispatch a Release workflow.
- Keep `docs/user/formats.md`, `docs/user/format-capabilities.json`, and `docs/user/dependencies.json` authoritative; curated workflow prose must not expand their capability boundary.
- Cover XYZ, extXYZ, MOL V2000/V3000, SDF, SMILES, CIF, POSCAR/CONTCAR, MOL2, PDB, PQR, Cube, CJSON, QCSchema, and the explicit 2.1 legacy migration case.
- Prefer copied, already verified repository fixtures; use local generation next; use clearly licensed online sources only if still necessary.
- Each file should remain below 50 MB. Any file above 50 MB requires a checked manifest reason; 100 MB is an absolute failure.
- ChemBlender Agent examples must call public UI-equivalent `bpy.ops.chemblender.*` Operators/public RNA and verify visible product state. They must not import private implementation modules, directly edit `.cbq`, mutate private caches/custom properties, or bypass preview/confirmation.
- General material, light, camera, collection, and render work belongs only in `07-agent-beyond-plugin.md`, uses generic `bpy`, and is labeled outside ChemBlender product scope.
- Before Blender work, run `blender-mcp --help`, query Blender version/executable/Python/system/repos together, require Blender 5.1.0+, and verify `bl_ext.user_default.chemblender` after Extension-native installation.
- If Blender 5.1 crashes or MCP disconnects, verify the exact executable and command line, restart that Blender 5.1 executable, condition-poll MCP, re-query runtime facts, inspect residual state, and rerun the affected case from a clean precondition.
- If a runtime flow exposes a plugin defect, stop that flow, use systematic-debugging and test-driven-development, add one concrete RED/GREEN task to the active cursor, commit the focused fix separately, and rerun the affected plus adjacent workflows.
- Defer any remaining example requiring an unavailable repository, external dependency, or unsafe network material; collect all such cases and ask the user once at the end before preparing them.
- Preserve UTF-8 and existing line endings. Use `apply_patch` for hand-authored files and checked bulk copies for fixture snapshots.

---

### Task 1: Activate the tracked task

**Files:**
- Create: `.agents/active/user-workflow-experience-gate.md`
- Modify: `.agents/README.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Consumes: approved design at `docs/superpowers/specs/2026-08-07-chemblender-user-workflow-experience-gate-design.md`.
- Produces: one active cursor used by every later task.

- [x] **Step 1: Add the active task cursor and route it from `.agents/README.md`**

Create an active document with Goal ID `CB-USER-WORKFLOW-EXPERIENCE-GATE`, state `active`, branch/worktree paths, design/plan paths, explicit no-push/no-release boundary, current task, completed tasks, deferred-external list, Blender runtime evidence section, defect ledger, and next action. Add one `active` row to `.agents/README.md`. Update `NEXT_RELEASE_ACTIVE_FILES` in `tests/test_quantum_visualization_docs.py` to the exact single active filename; restore it to empty when Task 8 archives the cursor.

- [x] **Step 2: Verify the active cursor does not disturb the baseline**

Run:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe' `
  -m unittest tests.test_quantum_visualization_docs tests.test_repository_contract
git diff --check
```

Expected: existing tests PASS and the worktree contains only the active-task documentation changes.

- [x] **Step 3: Commit the task activation**

```powershell
git add -- .agents/README.md .agents/active/user-workflow-experience-gate.md tests/test_quantum_visualization_docs.py docs/superpowers/plans/2026-08-07-chemblender-user-workflow-experience-gate.md
git commit -m "docs: activate user workflow experience gate"
```

---

### Task 2: Create the immutable full-format example corpus — completed

**Files:**
- Create: `examples/user-workflows/README.md`
- Create: `examples/user-workflows/manifest.json`
- Create: `examples/user-workflows/inputs/**`
- Create: `tests/test_user_workflows.py`
- Modify: `.agents/active/user-workflow-experience-gate.md`

**Interfaces:**
- Consumes: `EXPECTED_FAMILIES`, existing `tests/fixtures/**`, `hashlib.sha256`, and JSON.
- Produces: sorted manifest records with keys `path`, `family`, `source`, `provenance`, `sha256`, `bytes`, `runtime`, `expected`, `workflow`, and optional `size_exception_reason`.

- [x] **Step 1: Write the failing manifest contract**

Create `tests/test_user_workflows.py` with the following imports/constants, then add tests that load `manifest.json`, require `schema_version == "1"`, require records ordered by Python `sorted(path)`, require exactly `EXPECTED_FAMILIES`, reject duplicate paths, verify every file/hash/byte count, reject files over 100 MiB, and reject files over 50 MiB without a non-empty `size_exception_reason`.

```python
import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC_ROOT = ROOT / "docs" / "user" / "workflows"
EXAMPLE_ROOT = ROOT / "examples" / "user-workflows"
EXPECTED_FAMILIES = (
    "cif", "cjson", "cube", "extxyz", "legacy", "mol", "mol2",
    "pdb", "poscar", "pqr", "qcschema", "sdf", "smiles", "xyz",
)
```

Use this exact validation core:

```python
    def _manifest(self):
        return json.loads((EXAMPLE_ROOT / "manifest.json").read_text(encoding="utf-8"))

    def test_manifest_inventory_and_hashes(self):
        manifest = self._manifest()
        self.assertEqual(manifest["schema_version"], "1")
        records = manifest["files"]
        paths = [record["path"] for record in records]
        self.assertEqual(paths, sorted(paths))
        self.assertEqual(len(paths), len(set(paths)))
        self.assertEqual(tuple(sorted({record["family"] for record in records})), EXPECTED_FAMILIES)
        for record in records:
            path = EXAMPLE_ROOT / record["path"]
            data = path.read_bytes()
            self.assertEqual(record["bytes"], len(data))
            self.assertEqual(record["sha256"], hashlib.sha256(data).hexdigest())
            self.assertLessEqual(len(data), 100 * 1024 * 1024)
            if len(data) > 50 * 1024 * 1024:
                self.assertTrue(record.get("size_exception_reason"))
```

- [x] **Step 2: Run the manifest tests to verify RED**

Expected: FAIL because `examples/user-workflows/manifest.json` is absent.

- [x] **Step 3: Copy the exact verified fixture snapshots**

Create the directory tree and copy these exact source/destination pairs without modifying bytes:

```text
tests/fixtures/xyz/water.xyz                         -> inputs/xyz/water.xyz
tests/fixtures/extxyz/multiframe-cell.extxyz         -> inputs/extxyz/carbon-trajectory.extxyz
tests/fixtures/mol/water-v2000.mol                   -> inputs/mol/water-v2000.mol
tests/fixtures/mol/water-v3000.mol                   -> inputs/mol/water-v3000.mol
tests/fixtures/sdf/mixed-properties.sdf              -> inputs/sdf/mixed-properties.sdf
tests/fixtures/cif/nacl.cif                          -> inputs/cif/nacl.cif
tests/fixtures/poscar/si.POSCAR                      -> inputs/poscar/si.POSCAR
tests/fixtures/poscar/velocities.CONTCAR             -> inputs/poscar/velocities.CONTCAR
tests/fixtures/mol2/substructure.mol2                -> inputs/mol2/substructure.mol2
tests/fixtures/pdb/multimodel.pdb                    -> inputs/pdb/multimodel.pdb
tests/fixtures/pqr/with-chain.pqr                    -> inputs/pqr/with-chain.pqr
tests/fixtures/cube/two-datasets.cube                -> inputs/cube/two-datasets.cube
tests/fixtures/cjson/water-results.cjson             -> inputs/cjson/water-results.cjson
tests/fixtures/qcschema/atomic_result_v2.json        -> inputs/qcschema/atomic-result.json
tests/fixtures/legacy-blend/chemblender-2.1-molecule.blend -> inputs/legacy/chemblender-2.1-molecule.blend
```

Create `inputs/smiles/ethanol.smi` as UTF-8 without BOM containing exactly `CCO` plus LF.

- [x] **Step 4: Write the checked manifest with observed hashes and provenance**

Measure each copied file with `Path.read_bytes()`, insert the exact observed SHA-256 and size, and sort records with Python `sorted(record["path"])`. Use `repository fixture snapshot` provenance for copies and `locally generated minimal SMILES` for `ethanol.smi`. Do not retain a manifest value that was not measured from the destination file.

- [x] **Step 5: Write the user-readable sample catalog**

`examples/user-workflows/README.md` must explain immutable input versus generated output, path conventions, source/provenance, file-size rules, which workflows use each sample, and that copied examples are independent snapshots rather than imports from `tests/`.

- [x] **Step 6: Add built-in parser checks**

Extend `tests/test_user_workflows.py` to call the public readers for XYZ, extXYZ, POSCAR, MOL2, PDB, PQR, Cube, CJSON, and QCSchema and assert non-empty expected entities. RDKit MOL/SDF/SMILES and Gemmi CIF are required later in installed Blender and must be listed in a separate `test_dependency_backed_samples_are_declared_for_blender_runtime` assertion instead of silently skipped.

- [x] **Step 7: Run GREEN verification and commit**

Run `tests.test_user_workflows`, the corresponding reader modules, and `git diff --check`; then commit:

```powershell
git add -- examples/user-workflows tests/test_user_workflows.py .agents/active/user-workflow-experience-gate.md
git commit -m "test: add user workflow example corpus"
```

---

### Task 3: Write the user-facing workflow center and format boundary

**Files:**
- Create: `docs/user/workflows/README.md`
- Create: `docs/user/workflows/01-import.md`
- Create: `docs/user/workflows/02-process.md`
- Create: `docs/user/workflows/03-visualize.md`
- Create: `docs/user/workflows/04-export.md`
- Create: `docs/user/workflows/05-project-lifecycle.md`
- Create: `docs/user/workflows/formats.md`
- Modify: `README.md`
- Modify: `docs/README.md`
- Modify: `docs/user/2.4.0-experience-review.md`
- Modify: `tests/test_user_workflows.py`
- Modify: `.agents/active/user-workflow-experience-gate.md`

**Interfaces:**
- Consumes: `examples/user-workflows/manifest.json`, existing user guides, generated format/dependency documents, and real UI labels/operators.
- Produces: ordered UI workflows with sample links, success criteria, failure handling, and prompt anchors.

- [ ] **Step 1: Extend the contract test for document structure and links**

Add this exact inventory constant, require every listed file, and require the root entrypoints:

```python
EXPECTED_DOCS = (
    "README.md",
    "01-import.md",
    "02-process.md",
    "03-visualize.md",
    "04-export.md",
    "05-project-lifecycle.md",
    "formats.md",
)
```

For each numbered workflow document require headings `## 操作前检查`, `## UI 操作`, `## 成功判据`, `## Agent 提示词`, and `## 常见问题`. Parse Markdown links with a small regex and assert every repository-relative link resolves under `ROOT`. Require root `README.md`, `docs/README.md`, and the historical 2.4.0 review to link the new index. Task 4 extends `EXPECTED_DOCS` with the two Agent documents; Task 5 extends it with the two review files.

- [ ] **Step 2: Run RED before creating the documents**

Expected: missing document and link failures.

- [ ] **Step 3: Write the overview and import workflow**

The overview must explain the 2.1 direct-object versus current Project boundary, distinguish `基础安装可用` / `需要可选 runtime` / `开发接口或条件能力`, and route users through preparation, import, processing, visualization, export, lifecycle, Agent help, and review evidence. `01-import.md` must cover single/multiple files, drag/drop, SMILES, validation modes, Import Preview decisions, quality/diagnostics, cancel, and the exact sample paths.

- [ ] **Step 4: Write processing and visualization workflows**

`02-process.md` must cover immutable source, Apply Scientific Edits, derived Structure, topology compute/accept/reject/switch, crystal declared/derived symmetry, selective dynamics, biological hierarchy/selection/model playback, and revision validity. `03-visualize.md` must cover Structure, Grid Volume, Signed Surface, property mapping, trajectory/model playback, cache rebuild, and the difference between scientific entities and Blender Views.

- [ ] **Step 5: Write export and project lifecycle workflows**

`04-export.md` must enumerate Project Browser export formats, selection closure, format-specific loss preview, explicit confirmation, cancellation, atomic destination, semantic re-import check, and current no-general-Project-Browser-writer boundary for CJSON/QCSchema. `05-project-lifecycle.md` must cover Save Project, `.blend`/`.cbq` pairing, cold reopen, Verify/Relink/Inspect/Diagnostics/Detach, missing cache reconstruction, revision prompts, and explicit 2.1 legacy preview/migration/backup/reopen.

- [ ] **Step 6: Write the complete curated format reference**

For every base family, include a table row for potential source data, imported ChemBlender data, default/available View, processing, export/maturity, dependency, known loss, and sample link. Cross-check every claim against `docs/user/formats.md` and the generated JSON; do not claim optional runtime availability on the current machine.

- [ ] **Step 7: Add entrypoint links and historical routing**

Add one prominent root README link under Related user guides, add the workflow index first in `docs/README.md` User Guides, and add a short “长期发布前检阅” link to `docs/user/2.4.0-experience-review.md` without rewriting historical 2.4.0 facts.

- [ ] **Step 8: Run doc/link/format verification and commit**

Run `tests.test_user_workflows`, `tests.test_quantum_visualization_docs`, `tests.test_generated_docs_fresh`, and `git diff --check`. Commit:

```powershell
git add -- README.md docs/README.md docs/user .agents/active/user-workflow-experience-gate.md tests/test_user_workflows.py
git commit -m "docs: add user workflow center"
```

---

### Task 4: Add UI-equivalent Agent/MCP prompts and outside-plugin cases

**Files:**
- Create: `docs/user/workflows/06-agent-and-mcp.md`
- Create: `docs/user/workflows/07-agent-beyond-plugin.md`
- Modify: `docs/user/workflows/01-import.md`
- Modify: `docs/user/workflows/02-process.md`
- Modify: `docs/user/workflows/03-visualize.md`
- Modify: `docs/user/workflows/04-export.md`
- Modify: `docs/user/workflows/05-project-lifecycle.md`
- Modify: `tests/test_user_workflows.py`
- Modify: `.agents/active/user-workflow-experience-gate.md`

**Interfaces:**
- Consumes: public Operator names from `ChemBlender/runtime/registration.py` and `ChemBlender/ui/**`.
- Produces: copyable Agent-neutral prompt blocks and a static prompt-safety contract.

- [ ] **Step 1: Add a failing prompt-safety test**

Extend `EXPECTED_DOCS` with `06-agent-and-mcp.md` and `07-agent-beyond-plugin.md`. Require every numbered plugin workflow page to contain a fenced `text` prompt with `Blender MCP`, `bpy.ops.chemblender`, `检查 Operator RNA`, and an explicit “do not import private modules/directly edit .cbq/bypass confirmation” boundary. Reject executable Python lines beginning with `from ChemBlender` or `import ChemBlender`, plus `project.write`, direct `obj["cb_` assignment, and direct writes below a `.cbq` path in `run_ui_workflows.py`; allow the prose guide to name those forbidden patterns while explaining the boundary.

- [ ] **Step 2: Run RED before adding prompts**

Expected: prompt sections are incomplete or missing.

- [ ] **Step 3: Write the Agent/MCP operating guide**

Include connectivity preflight, one-shot runtime query, active file/dirty-state checks, Operator RNA introspection, public Operator execution, visible-state verification, cancellation, failure stop rules, crash recovery, and Codex/Claude Code portability without guessing a specific MCP server tool name.

- [ ] **Step 4: Add one prompt per documented operation**

Each prompt must name the exact sample, ask the Agent to discover the live Operator RNA signature, call the public Operator, wait conditionally, inspect the same state the UI exposes, and return evidence. Prompts must preserve Import Preview, quality decisions, loss confirmation, save/reopen, and migration confirmation.

- [ ] **Step 5: Write outside-plugin examples**

Provide separate generic `bpy` prompts for material styling, world/light/camera setup, collection organization, Eevee/Cycles render setup, and saving a presentation copy. Precede every case with “这不是 ChemBlender 插件能力”; prohibit scientific edits through Object transform/material changes.

- [ ] **Step 6: Run prompt tests and commit**

Run workflow tests plus docs tests and commit:

```powershell
git add -- docs/user/workflows tests/test_user_workflows.py .agents/active/user-workflow-experience-gate.md
git commit -m "docs: add Blender MCP workflow prompts"
```

---

### Task 5: Establish the tracked manual prerelease experience gate

**Files:**
- Create: `docs/user/workflows/reviews/README.md`
- Create: `docs/user/workflows/reviews/template.md`
- Modify: `.agents/reference/dependencies-and-release.md`
- Modify: `docs/development/branch-and-release.md`
- Modify: `tests/test_user_workflows.py`
- Modify: `.agents/active/user-workflow-experience-gate.md`

**Interfaces:**
- Consumes: workflow case IDs, sample manifest, and existing local Extension gates.
- Produces: version-neutral gate `UX-GATE` and tracked `reviews/<version>.md` evidence contract.

- [ ] **Step 1: Add failing release-gate assertions**

Extend `EXPECTED_DOCS` with `reviews/README.md` and `reviews/template.md`. Require both release-policy documents to contain `人工插件使用体验检阅`, `reviews/<version>.md`, and a statement that incomplete/failed required cases block tag/Release. Require the template to include environment, commit/package hashes, every workflow ID, UI result, Agent/MCP result, time, evidence, findings, fix commit, rerun result, file sizes/hashes/reopen state, and final Passed/Failed/Blocked.

- [ ] **Step 2: Run RED**

Expected: release policy and review files absent.

- [ ] **Step 3: Write gate rules and template**

Define required cases with stable IDs `ENV`, `IMP`, `DATA`, `VIEW`, `EXP`, `LIFE`, `MIG`, `AGENT`, and `OUTSIDE`. `OUTSIDE` is required only for evidence that it remains clearly outside product scope; it does not gate scientific correctness. State that automated runner results accompany but never replace manual evidence.

- [ ] **Step 4: Integrate the gate into release policy**

Insert the manual gate after local installed-product validation and before tag/Release authorization. Do not change existing remote authorization rules or imply a current version passed.

- [ ] **Step 5: Verify and commit**

Run workflow/repository/doc tests and commit:

```powershell
git add -- docs/user/workflows/reviews docs/development/branch-and-release.md .agents/reference/dependencies-and-release.md tests/test_user_workflows.py .agents/active/user-workflow-experience-gate.md
git commit -m "docs: add manual plugin experience gate"
```

---

### Task 6: Implement the public-Operator Blender workflow runner

**Files:**
- Create: `examples/user-workflows/scripts/run_ui_workflows.py`
- Modify: `tests/test_user_workflows.py`
- Modify: `examples/user-workflows/README.md`
- Modify: `.agents/active/user-workflow-experience-gate.md`

**Interfaces:**
- Consumes: Blender `bpy`, public `bpy.ops.chemblender.*`, public Scene RNA, example manifest, output root passed after `--`.
- Produces: one JSON report `{schema_version, runtime, cases, deferred}`; each case has `id`, `input`, `operators`, `status`, `evidence`, `outputs`, `elapsed_seconds`, and `error`.

- [ ] **Step 1: Add failing static runner-contract tests**

Parse the runner with `ast`; reject imports whose module starts with `ChemBlender` or `bl_ext`; reject source tokens `cbq.write`, `write_project`, `ProjectSession`, `QCProject`, and assignment to string-keyed `cb_` subscripts. Require calls through `bpy.ops.chemblender` and report schema/case IDs.

- [ ] **Step 2: Run RED because the runner is absent**

- [ ] **Step 3: Implement argument, runtime, and report plumbing**

Use only standard library plus `bpy`. Resolve repository/example/output paths from explicit arguments; never infer the checkout from the installed extension. Record Blender version, executable, Python, runtime system, active file, enabled key, and extension repos. Write the report atomically with `tempfile.NamedTemporaryFile(delete=False, dir=destination.parent)` plus `Path.replace()`.

- [ ] **Step 4: Implement UI-equivalent case helpers**

Helpers may inspect `bpy.types.<Operator>.bl_rna.properties`, set public Scene RNA used by the visible panel, call `bpy.ops.chemblender.*`, inspect `bpy.context.scene`, visible objects and files, and collect Operator return values. They may not import the installed package. Implement cases in this order: ENV, IMP-XYZ, IMP-SMILES, IMP-CANCEL, DATA-TOPOLOGY, DATA-CRYSTAL, DATA-BIOLOGICAL, VIEW-CUBE, EXP-FORMATS, LIFE-SAVE-REOPEN-PREP, MIG-PREVIEW-PREP. Reopen-dependent continuation uses a report/checkpoint argument in a fresh Blender process rather than pretending a single process proves cold reopen.

- [ ] **Step 5: Add safe failure and cleanup behavior**

Each case catches `Exception`, records the exact stage/error, verifies owned staging/temp outputs, and stops cases that depend on the failed state. `MemoryError`, `KeyboardInterrupt`, and process loss are not converted to Passed. The script never deletes an existing user path; it operates only below the explicit empty run directory.

- [ ] **Step 6: Run static tests and commit runner before runtime execution**

Run workflow tests, `compileall` for the script, and `git diff --check`; commit:

```powershell
git add -- examples/user-workflows/scripts examples/user-workflows/README.md tests/test_user_workflows.py .agents/active/user-workflow-experience-gate.md
git commit -m "test: add public operator workflow runner"
```

---

### Task 7: Run Blender MCP build/install workflows and fix reproduced defects

**Files:**
- Modify as evidence requires: `ChemBlender/**`, focused `tests/test_*.py`, `tests/blender_smoke.py`, workflow docs, runner, and active cursor.
- Create after verified run: `examples/user-workflows/results/local-2.4.0.json`
- Create only after cold-reopen qualification: selected `examples/user-workflows/outputs/**`

**Interfaces:**
- Consumes: MCP-discovered Blender paths/runtime, built ZIP, public runner, samples.
- Produces: installed-runtime report, focused defect commits, and selected moderate-size reopenable outputs.

- [ ] **Step 1: Run the mandatory Blender MCP gate**

Run `blender-mcp --help`. Through the available Blender MCP code-execution tool query in one call: `bpy.app.version_string`, `bpy.app.binary_path`, `bpy.app.binary_path_python`, `platform.system()`, extension repos, current file, dirty state, and installed ChemBlender key. Record exact evidence in the active cursor. If no matching Blender 5.1 process/listener exists, start the exact `C:\Program Files\Blender Foundation\Blender 5.1\blender.exe` only after verifying that path, wait conditionally, and repeat the query.

- [ ] **Step 2: Resolve wheels without changing dependency policy**

Check manifest/dependency references and local ignored wheel inventory. Reuse exact hash-matching local files when present. If absent, download only the already pinned RDKit/Gemmi URLs and verify SHA-256; do not add or change dependencies. A network/repository requirement for an additional example goes to the deferred list, not this wheel gate.

- [ ] **Step 3: Validate, build, inspect, and install Extension-native**

Use the MCP-returned Blender/Python paths to run `ChemBlender/scripts/validate_extension.py` and `build_extension.py`; inspect ZIP inventory/CRC/type/size and verify-wheel modes; install into `user_default` with `bpy.ops.extensions.package_install_files`. Verify `bl_ext.user_default.chemblender`, RDKit/Gemmi versions/imports, Panel/Operator/Scene properties, bundled `.blend` assets, and two lifecycle cycles.

- [ ] **Step 4: Run every automated workflow case through MCP**

Create a new empty run directory under ignored `.agents/cache/user-workflows/<run-id>`. Execute the runner through Blender MCP, then use fresh Blender processes for save/reopen and migration continuations. Verify report status and actual output/project/view semantics; do not accept only `FINISHED`, file existence, or listening port.

- [ ] **Step 5: Handle crashes deterministically**

On process loss, inspect exact process path/command line, restart Blender 5.1, condition-poll MCP, re-query runtime, preserve failed evidence, create a new empty case directory, and rerun the failed case from its documented precondition.

- [ ] **Step 6: Insert and execute concrete bug tasks when failures occur**

For each product defect, update the active cursor with reproduction, suspected shared boundary, exact test file/node, and affected adjacent flows. Read all callers, write/run RED, implement one minimal fix, run GREEN plus adjacent tests and installed Blender flow, then commit `fix: <actual defect>`. Documentation or sample defects receive their own focused correction commit. Do not batch unrelated defects.

- [ ] **Step 7: Qualify and copy selected outputs**

From Passed run outputs choose only unique molecular, crystal, Grid3D, and legacy-migration `.blend`/`.cbq` examples that add direct-view value. Before copying into tracked `outputs/`, cold-reopen each with Blender 5.1, verify project link/entities/Views/no missing libraries or images, measure every file, update manifest with observed hash/size/provenance, and omit redundant outputs.

- [ ] **Step 8: Commit runtime evidence and outputs**

Require all non-deferred cases Passed, then commit the checked JSON report, selected outputs, manifest updates, docs corrections, and active cursor as `test: record user workflow runtime evidence`.

---

### Task 8: Final qualification, archive the task, and merge locally to main

**Files:**
- Move: `.agents/active/user-workflow-experience-gate.md` -> `.agents/completed/user-workflow-experience-gate.md`
- Modify: `.agents/README.md`
- Modify as needed: workflow docs, sample manifest, runtime report.

**Interfaces:**
- Consumes: every task commit, Passed runtime report, selected output audits, no unresolved in-scope defect.
- Produces: completed evidence record and local `main` merge commit.

- [ ] **Step 1: Run requirement-by-requirement completion audit**

Build a table in the cursor mapping every design requirement to a current file, command, test output, MCP result, or cold-reopen artifact. Treat missing/indirect evidence as incomplete and return to the relevant task.

- [ ] **Step 2: Run full local qualification**

Use Blender bundled Python for the full standard-library suite, generated docs, compileall, Extension validate/build, ZIP audit, isolated install, installed product smoke, workflow runner, output cold reopen, and `git diff --check`. Record Passed/Failed/Not Run with exact commands/counts; no required item may remain Not Run.

- [ ] **Step 3: Resolve the deferred external list once**

If non-empty, present one consolidated request to the user before preparing those cases. If empty, record `None`. Do not mark the goal complete while a required deferred case remains unresolved.

- [ ] **Step 4: Archive the task and commit completion evidence**

Set state `completed`, list all commits, runtime/build/test evidence, sample/output sizes and hashes, fixed defects, remaining limitations, and the no-remote-write statement. Move the cursor to completed, update `.agents/README.md`, run docs tests and commit `docs: complete user workflow experience gate`.

- [ ] **Step 5: Verify local main integration preconditions**

In the root main worktree fetch no remote state and perform no writes outside Git. Confirm `main` is still `60da41f` or inspect any drift, confirm both worktrees clean, confirm no changed-file conflict with user changes, and verify `main` is an ancestor of the feature head.

- [ ] **Step 6: Merge normally into local main**

From `D:\workspace\ChemBlender_2_x`, run:

```powershell
git merge --no-ff codex/user-workflow-experience-gate -m "Merge user workflow experience gate"
```

Do not push. Re-run the narrow workflow/doc contracts and `git diff --check` on local `main`; verify the feature head is an ancestor and the root worktree is clean.

- [ ] **Step 7: Mark the persistent goal complete only after final evidence passes**

Call `update_goal(status="complete")` only when every explicit objective item has authoritative evidence and no required deferred work remains.
