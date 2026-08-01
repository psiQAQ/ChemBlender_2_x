# ChemBlender 2.4.0 Task 3 Scope Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the merged MOL2 Export UI task with exact remote evidence, select exactly one evidence-backed ChemBlender 2.4.0 Task 3, and leave that implementation queued but unstarted.

**Architecture:** This is a documentation-only state transition. Archive the completed cursor, capture live candidate evidence, and route one bounded task into a queued implementation plan. Do not change the product, package, schema, dependencies, generated capability data, version, workflow, or release state.

**Tech Stack:** Git, GitHub CLI read-only queries, Python 3.13 standard-library `unittest`, Markdown documentation contracts.

## Global Constraints

- Work only in `codex/2.4.0-task3-scope-discovery`, based on merge commit `99548d8aff8bea162651273ff5d723e57be5279c`.
- Use the approved design in `docs/superpowers/specs/2026-08-02-chemblender-2.4.0-task3-scope-discovery-design.md`.
- Preserve exact MOL2 UI integration evidence: feature head `819575f3210d9db92b33b2e5e11cc02590680564`, runs `30708862898` and `30708862900`, ordinary merge `99548d8aff8bea162651273ff5d723e57be5279c`.
- Select at most one of native PDB export, native PQR export, native Cube export, or Reader API v1 stable gate.
- Do not create or modify files under `ChemBlender/`, `worker/`, `.github/`, the manifest, CHANGELOG, or release metadata.
- Do not push, create a PR, modify remote state, tag, or release.

---

### Task 1: Archive the completed MOL2 Export UI integration

**Files:**
- Move: `.agents/active/2.4.0-mol2-export-ui.md`
- Create: `.agents/completed/2.4.0-mol2-export-ui.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Consumes: the merged PR #10 and exact-head GitHub Actions evidence.
- Produces: one immutable completed cursor and no active product task.

- [ ] **Step 1: Add the documentation RED**

Change the 2.4.0 routing constants and MOL2 UI cursor assertions so the contract expects:

```python
NEXT_RELEASE_ACTIVE_FILES = ()
NEXT_RELEASE_QUEUED_FILES = ("2.4.0-pdb-export.md",)
MOL2_EXPORT_UI_COMPLETED_FILE = "2.4.0-mol2-export-ui.md"
TASK3_SCOPE_COMPLETED_FILE = "2.4.0-task3-scope-discovery.md"
```

Require the completed MOL2 UI cursor to contain PR #10, exact head, both run IDs, ordinary merge SHA, ancestor verification, `State: completed`, and no pending remote gate.

- [ ] **Step 2: Run RED**

```powershell
$pythonBin = 'C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe'
& $pythonBin -m unittest tests.test_quantum_visualization_docs.QuantumVisualizationDocsTests.test_single_active_task tests.test_quantum_visualization_docs.QuantumVisualizationDocsTests.test_240_mol2_export_ui_design_is_recoverable -v
```

Expected: the active/queued routing and completed cursor assertions fail because the old cursor is still active and no Task 3 queue exists.

- [ ] **Step 3: Archive the cursor with exact evidence**

Move the active cursor into `.agents/completed/`, set `State: completed`, and record:

- PR `https://github.com/psiQAQ/ChemBlender_2_x/pull/10`;
- exact feature head `819575f3210d9db92b33b2e5e11cc02590680564`;
- `extension-package` run `30708862898`, Passed;
- `optional-qc-core` run `30708862900`, Passed;
- ordinary merge commit `99548d8aff8bea162651273ff5d723e57be5279c`;
- exact head and merge ancestry verified.

Do not alter the existing local RED/GREEN, package, Blender, review, or frozen-boundary evidence.

---

### Task 2: Record live post-MOL2 candidate evidence

**Files:**
- Create: `docs/quantum-visualization/2.4.0/task3-candidate-intake.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Consumes: GitHub live state, generated reader capabilities, frozen PDB/PQR readiness contracts, Cube model/import evidence, and Reader API compatibility policy.
- Produces: one auditable candidate comparison with facts separated from recommendation.

- [ ] **Step 1: Refresh the dynamic evidence**

Read-only checks:

```powershell
git status --short
git rev-parse HEAD
git rev-parse origin/main
gh repo view psiQAQ/ChemBlender_2_x --json defaultBranchRef,hasDiscussionsEnabled,hasIssuesEnabled,pushedAt
gh pr list --repo psiQAQ/ChemBlender_2_x --state open --json number,title,url,headRefOid
gh api repos/psiQAQ/ChemBlender_2_x/releases/tags/v2.3.0
```

Also inspect `docs/user/format-capabilities.json`, `docs/reader-api-v1/compatibility.md`, `docs/quantum-visualization/2.3.0/specs/pdb-pqr-export-p1.md`, PDB/PQR fixtures, Cube tests, and exporter public entries.

- [ ] **Step 2: Add the intake contract and run RED**

Require the new intake to name all four candidates, record PDB/PQR/Cube as F0 and Reader API as `1.0-rc1`, select exactly `Task 3 — Deterministic native PDB export`, and give a distinct deferral reason for PQR, Cube, and Reader API stable.

```powershell
& $pythonBin -m unittest tests.test_quantum_visualization_docs.QuantumVisualizationDocsTests.test_240_task3_scope_discovery_is_recoverable -v
```

Expected: failure because the intake, implementation plan, queued cursor, and completed discovery record do not yet exist.

- [ ] **Step 3: Write the minimal evidence-backed selection**

Select native PDB export because it is an F0 dependency-neutral gap with an existing readiness contract and comprehensive fixed-field/hierarchy fixtures. Its minimum result is a deterministic core writer, explicit loss preview, atomic cancellation, and semantic native re-import.

Defer:

- PQR because it is narrower, requires mandatory charge/radius and dialect decisions, and remains a separate task;
- Cube because no writer/readiness contract is frozen for multi-dataset and native-unit semantics;
- Reader API stable because no external adopter evidence justifies promoting `1.0-rc1`.

---

### Task 3: Queue deterministic native PDB export

**Files:**
- Create: `docs/superpowers/plans/2026-08-02-chemblender-2.4.0-pdb-export.md`
- Create: `.agents/queued/2.4.0-pdb-export.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Consumes: `pdb_export_readiness()`, `Structure`, `BiologicalHierarchy`, `FrameSet`, `AtomicProperty`, shared export reports and atomic writer.
- Produces: an executable TDD plan and a `not_started` recovery cursor; no exporter code.

- [ ] **Step 1: Write a concrete implementation plan**

The plan must define:

- public core signatures `preview_pdb_export(project_entities)` and `export_pdb(...)`;
- deterministic fixed-column `ATOM`/`HETATM`, optional `MODEL`/`ENDMDL`, and terminal `END` records;
- stable serial renumbering and explicit loss entries;
- occupancy/B-factor handling from the existing readiness contract;
- no `CONECT`, crystallographic record synthesis, UI, PQR, dependency, schema, version, or release work;
- atomic cancellation and no partial destination publication;
- semantic re-import comparison through the native PDB parser;
- focused/full/package/Blender verification and independent reviews;
- separate core implementation and later UI boundaries.

- [ ] **Step 2: Create the queued cursor**

The cursor must use goal `CB240-PDB-EXPORT-T3`, state `not_started`, point to the implementation plan and intake evidence, list required subgoals, and state that only a later explicit instruction activates runtime work.

- [ ] **Step 3: Run GREEN**

```powershell
& $pythonBin -m unittest tests.test_quantum_visualization_docs -v
```

Expected: every documentation routing, evidence, UTF-8 and plan-recovery contract passes.

---

### Task 4: Complete scope discovery and prove zero runtime change

**Files:**
- Create: `.agents/completed/2.4.0-task3-scope-discovery.md`
- Modify: `tests/test_quantum_visualization_docs.py`
- Verify: all files from Tasks 1–3 and the approved design.

**Interfaces:**
- Consumes: the archived UI cursor, candidate intake, PDB implementation plan and queued cursor.
- Produces: a completed discovery checkpoint and a clean local branch.

- [ ] **Step 1: Record the completed discovery cursor**

Record baseline, design and planning commits, live evidence date, selected/deferred candidates, documentation RED/GREEN, zero runtime diff, `Remote CI: Not Run`, and stop boundary. State explicitly that PDB exporter runtime implementation has not started.

- [ ] **Step 2: Run focused and static verification**

```powershell
& $pythonBin -m unittest tests.test_quantum_visualization_docs tests.test_generated_docs_fresh -v
& $pythonBin -m compileall -q tests
git diff --check
git diff --name-only origin/main...HEAD -- ChemBlender worker .github ChemBlender/blender_manifest.toml CHANGELOG.md
```

Expected: tests pass, compileall exits `0`, no whitespace errors, and the protected runtime/release diff command prints nothing.

- [ ] **Step 3: Verify encoding and state**

For every added or modified Markdown/Python file, verify UTF-8 decode succeeds and no UTF-8 BOM exists. Confirm exactly zero active cursors, exactly one queued cursor, and the two new completed records.

- [ ] **Step 4: Commit the discovery evidence**

```powershell
git add -- .agents docs tests/test_quantum_visualization_docs.py
git diff --cached --check
git commit -m "docs: select native PDB export for Task 3"
```

- [ ] **Step 5: Final verification**

```powershell
& $pythonBin -m unittest tests.test_quantum_visualization_docs tests.test_generated_docs_fresh -v
& $pythonBin -m compileall -q tests
git diff --check
git status --short
```

Stop with a clean worktree. Do not activate or implement the queued PDB exporter and do not push.
