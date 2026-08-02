# ChemBlender 2.4.0 Final Qualification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Qualify and ordinarily integrate the complete committed ChemBlender 2.4.0 product surface without adding features or publishing a release.

**Architecture:** Treat qualification as an evidence pipeline over the committed tree: frozen-boundary audit, complete Python/dependency verification, deterministic package audit, real Blender product smoke, independent reviews and exact-head CI. Focused fixes restart the affected evidence chain.

**Tech Stack:** Python 3.13, standard-library `unittest`, Blender 5.1.2 Extensions, GitHub Actions, existing pinned optional dependencies.

## Global Constraints

- Follow `docs/superpowers/specs/2026-08-02-chemblender-2.4.0-final-qualification-design.md`.
- Activate only after Task 11 is ordinarily merged and its exact head is an ancestor of live `origin/main`.
- Preserve Reader API `1.0-rc1`, sidecar schema, canonical schema and all public model contracts.
- Do not add a capability, dependency or workflow and do not change the manifest version or CHANGELOG.
- Any product fix requires a focused regression test and fresh affected qualification.
- No force-push, rebase, squash merge, branch deletion, tag or Release.

---

### Task 0: Activate the queued qualification

**Files:**
- Delete: `.agents/queued/2.4.0-final-qualification.md`
- Create: `.agents/active/2.4.0-final-qualification.md`
- Modify: `.agents/completed/2.4.0-task11-scope-discovery.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Consumes: completed Task 11 cursor and its exact remote integration evidence.
- Produces: isolated branch `codex/2.4.0-final-qualification` from live `origin/main` and the sole active goal `CB240-FINAL-QUALIFICATION-T12`.

- [x] **Step 1: Integrate the Task 11 discovery gate**

Require a clean discovery worktree and query existing PRs for the exact head
before any remote write. If it is already merged, verify exact-head runs and
ancestry and do not create a duplicate PR. Otherwise use ordinary push and one
ready PR, wait for `extension-package` and `optional-qc-core` to pass the exact
discovery head, merge with `--merge --delete-branch=false`, fetch and prove
ancestry.

- [x] **Step 2: Create an isolated qualification worktree**

Run:

```powershell
$commonDir = git rev-parse --path-format=absolute --git-common-dir
$repositoryRoot = Split-Path -Parent $commonDir
$qualificationPath = Join-Path $repositoryRoot ".worktrees/2.4.0-final-qualification"
git -C $repositoryRoot fetch origin --prune
git -C $repositoryRoot worktree add $qualificationPath `
  -b codex/2.4.0-final-qualification origin/main
```

Record the actual full baseline SHA; do not reuse the discovery branch.

- [x] **Step 3: Move queued to active with routing RED/GREEN**

Update the routing contract to one active qualification cursor and no queued
cursor. Preserve goal, selected design/plan and Reader API stop boundary.

- [x] **Step 4: Verify and commit activation**

Run focused documentation routing tests and `git diff --check`. Commit as
`docs: activate 2.4.0 final qualification`.

### Task 1: Audit frozen public and scientific boundaries

**Files:**
- Create: `docs/quantum-visualization/2.4.0/final-qualification.md`
- Modify: `.agents/active/2.4.0-final-qualification.md`
- Modify: `tests/test_quantum_visualization_docs.py`
- Modify only finding-related source/tests when a confirmed defect exists

**Interfaces:**
- Consumes: current public core/model, Reader API, schema, catalog and generated-document contracts.
- Produces: a versioned evidence matrix with no public-surface enlargement.

- [x] **Step 1: Write the evidence-record RED**

Require the evidence document to record Reader API `1.0-rc1`, sidecar and
canonical schema versions, public import audits, every F4/F5 exporter execution
mode, optional dependency isolation and zero unexplained generated-doc drift.

- [x] **Step 2: Run focused boundary tests**

Run:

```powershell
& $pythonBin -m unittest `
  tests.test_reader_api_v1_rc `
  tests.test_reader_plugin_manifest `
  tests.test_reader_conformance_v1 `
  tests.test_sidecar_v1_schema `
  tests.test_sidecar_storage `
  tests.test_reader_canonical_document `
  tests.test_generated_docs_fresh `
  tests.test_quantum_visualization_docs -v
```

Record exact counts and failures; do not weaken assertions or add skips.

- [x] **Step 3: Write the evidence matrix and focused fixes**

Populate only observed facts. For each confirmed defect, add one failing
contract test, implement the smallest shared-boundary fix, and rerun the
affected module set.

- [x] **Step 4: Commit the frozen-boundary audit**

Run focused GREEN and `git diff --check`. Commit as
`test: qualify 2.4.0 public boundaries`.

### Task 2: Run complete Python and dependency qualification

**Files:**
- Modify: `docs/quantum-visualization/2.4.0/final-qualification.md`
- Modify: `.agents/active/2.4.0-final-qualification.md`
- Modify only finding-related source/tests when a confirmed defect exists

**Interfaces:**
- Consumes: Blender bundled Python, pinned wheels/constraints and existing test discovery.
- Produces: complete pass/skip/fail counts plus optional integration evidence.

- [x] **Step 1: Run full Python qualification**

Run:

```powershell
& $pythonBin -m unittest discover -s tests -p "test_*.py" -v
& $pythonBin -m compileall -q ChemBlender worker tests
& $pythonBin ChemBlender/scripts/generate_format_docs.py --check
git diff --check
```

- [x] **Step 2: Run import isolation**

In fresh subprocesses import `ChemBlender.core` and `ChemBlender.reader_api`;
assert `rdkit`, `gemmi`, `spglib`, `cclib`, `iodata`, `gbasis`, `ase` and
`pymatgen` are absent from `sys.modules` until their adapter is called.

- [x] **Step 3: Run existing optional integrations**

With the workflow-pinned environments and fixtures active, run the exact
integration module set:

```powershell
& $pythonBin -m unittest `
  tests.test_cclib_adapter `
  tests.test_iodata_adapter `
  tests.test_wavefunction_grid `
  tests.test_wavefunction_observables -v
```

Record package versions and fixture SHAs from
`.github/workflows/optional-qc-core.yml`. A skipped module is not local
integration proof; the exact-head `cclib`, `iodata` and `gbasis` jobs in Task 5
remain mandatory. Do not install into Blender global site-packages.

- [x] **Step 4: Fix, rerun and commit only if needed**

If no defect is found, update evidence/cursor only. Otherwise add focused RED,
apply the smallest fix and rerun full discovery. Commit as
`test: qualify 2.4.0 Python integrations`.

### Task 3: Rebuild and audit the committed extension artifact

**Files:**
- Modify: `docs/quantum-visualization/2.4.0/final-qualification.md`
- Modify: `.agents/active/2.4.0-final-qualification.md`
- Modify only finding-related packaging tests/config when a confirmed defect exists

**Interfaces:**
- Consumes: clean committed tree, Blender 5.1.2 and pinned RDKit/Gemmi wheels.
- Produces: validated ZIP, checksum, inventory, artifact-size and release-metadata evidence.

- [x] **Step 1: Verify dependency inputs**

Resolve exact wheel filenames and SHA-256 values from
`ChemBlender/dependencies.toml`; reject missing, extra or mismatched wheels.

- [x] **Step 2: Validate and build**

Run:

```powershell
& $pythonBin ChemBlender/scripts/build_extension.py `
  --python $pythonBin --blender $blenderBin
```

Require native validate/build success and the exact package name from
`release_metadata.py`.

- [x] **Step 3: Audit the artifact**

Run `dependency_inventory.py`, `artifact_size_report.py` and
`verify_release_artifact.py --metadata-mode package-ci` with the exact
arguments used by `extension-package.yml`. Inspect all ZIP paths and CRCs;
record package hash, member count, packed/unpacked/section sizes and budget
result.

- [x] **Step 4: Commit evidence or a focused fix**

Rebuild from a clean committed tree after any change. Commit as
`test: qualify 2.4.0 extension artifact`.

### Task 4: Run Blender product qualification

**Files:**
- Modify: `docs/quantum-visualization/2.4.0/final-qualification.md`
- Modify: `.agents/active/2.4.0-final-qualification.md`
- Modify only finding-related Blender/product tests when a confirmed defect exists

**Interfaces:**
- Consumes: exact ZIP from Task 3.
- Produces: isolated Blender 5.1.2 install, lifecycle and representative product-flow evidence.

- [x] **Step 1: Run isolated install and lifecycle**

Set a fresh temporary `BLENDER_USER_RESOURCES`; execute
`tests/blender_smoke.py -- <exact-package>` with `--factory-startup` and
`--python-exit-code 1`. Require install, enable, register/unregister/reload
twice and final cleanup to exit zero.

- [x] **Step 2: Run representative export workflows**

Through the installed Project Browser, import, preview, confirm, export and
native-reimport one MOL2, PDB, PQR and multi-dataset Cube fixture. Compare
scientific semantics and confirm cancellation preserves an existing
destination.

- [x] **Step 3: Run save/reopen and resource checks**

Save, close and reopen a representative molecular and Grid3D project; verify
sidecar links, derived cache reconstruction and no duplicate registration or
object creation.

- [x] **Step 4: Commit evidence or a focused fix**

Rerun affected Blender and full Python checks after any change. Commit as
`test: qualify 2.4.0 Blender workflows`.

### Task 5: Review, checkpoint and exact-head remote gate

**Files:**
- Delete: `.agents/active/2.4.0-final-qualification.md`
- Create: `.agents/completed/2.4.0-final-qualification.md`
- Modify: `docs/superpowers/plans/2026-08-02-chemblender-2.4.0-final-qualification.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Consumes: all qualification evidence and findings.
- Produces: one clean final feature head, exact-head CI and ordinary merge ancestry.

- [ ] **Step 1: Run two independent reviews**

Require specification-compliance and code-quality/security/scientific-
correctness verdicts. Fix all Critical, Important and task-related Minor
findings, then rerun every affected gate.

- [ ] **Step 2: Run final local qualification**

Freshly rerun full unittest discovery, compileall, generated docs, optional
import audit, committed-tree artifact build/audit, Blender installed smoke and
`git diff --check`. Move the cursor to completed and commit as
`chore: checkpoint 2.4.0 final qualification`.

- [ ] **Step 3: Push and require exact-head CI**

Ordinarily push `codex/2.4.0-final-qualification`, create a ready PR to
`main`, and require:

```text
extension-package: native-core, package
optional-qc-core: cclib, iodata, gbasis
```

Every job must finish success with `headSha` equal to the checkpoint head.

- [ ] **Step 4: Merge ordinarily and verify ancestry**

Merge using `gh pr merge --merge --delete-branch=false`, then run:

```powershell
$checkpointHead = git rev-parse HEAD
git fetch origin --prune
git merge-base --is-ancestor $checkpointHead origin/main
if ($LASTEXITCODE -ne 0) { throw "Qualification head is not in origin/main" }
```

Do not squash, rebase, delete the branch, tag or publish a Release.

## Stop Boundary

Stop after Final Qualification is merged and ancestry is verified. Reader API
stable, manifest version, CHANGELOG release entry, release planning, tag and
Release remain unstarted.
