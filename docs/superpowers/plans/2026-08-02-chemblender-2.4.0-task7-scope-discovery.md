# ChemBlender 2.4.0 Task 7 Scope Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close PQR Export UI remote evidence, select exactly one evidence-backed
Task 7, and leave its implementation queued but unstarted.

**Architecture:** This is a documentation-only state transition. Record the
already-merged PQR UI gate, compare native Cube export with Reader API v1 stable,
then route only Cube core export into one implementation plan and queued cursor.
No runtime or public API state changes.

**Tech Stack:** Git, GitHub CLI read-only evidence, Python 3.13 standard-library
`unittest`, Markdown documentation contracts.

## Global Constraints

- Work only on `codex/2.4.0-task7-scope-discovery` from merge commit
  `eb3fc4ea6f86e8fc3f9475bd03d379445349db57`.
- Use the approved design in
  `docs/superpowers/specs/2026-08-02-chemblender-2.4.0-task7-scope-discovery-design.md`.
- Select at most one of deterministic native Cube export or Reader API v1
  stable promotion.
- Do not modify `ChemBlender/`, `worker/`, `.github/`, dependencies, schema,
  manifest, workflows, version, CHANGELOG, tags or Releases.
- Do not push, create a PR or otherwise modify remote state.

---

### Task 1: Persist the Task 7 discovery boundary

**Files:**
- Create: `docs/superpowers/plans/2026-08-02-chemblender-2.4.0-task7-scope-discovery.md`
- Create: `.agents/active/2.4.0-task7-scope-discovery.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:** Produce one active recovery cursor; no product interface.

- [ ] **Step 1: Write the routing RED**

Set `NEXT_RELEASE_ACTIVE_FILES` to
`("2.4.0-task7-scope-discovery.md",)` and keep
`NEXT_RELEASE_QUEUED_FILES = ()`. Add
`test_240_task7_scope_discovery_is_recoverable()` requiring the design, this
plan, goal `CB240-TASK7-SCOPE-DISCOVERY`, baseline merge, both candidates and
the no-runtime stop boundary.

- [ ] **Step 2: Run the routing RED**

Run:

```powershell
& $pythonBin -m unittest `
  tests.test_quantum_visualization_docs.QuantumVisualizationDocsTests.test_single_active_task `
  tests.test_quantum_visualization_docs.QuantumVisualizationDocsTests.test_240_task7_scope_discovery_is_recoverable -v
```

Expected: failure/error because the active cursor does not exist.

- [ ] **Step 3: Create the active cursor**

Create the sole active cursor with state `in_progress`, current task
`Live candidate audit`, baseline `eb3fc4e...`, the design/plan paths,
candidates `Native Cube export` and `Reader API v1 stable gate`, and a stop
boundary that forbids Cube runtime and API-token changes.

- [ ] **Step 4: Run GREEN and commit**

Run the two focused tests and `git diff --check`, then commit:

```powershell
git add -- `
  .agents/active/2.4.0-task7-scope-discovery.md `
  docs/superpowers/plans/2026-08-02-chemblender-2.4.0-task7-scope-discovery.md `
  tests/test_quantum_visualization_docs.py
git commit -m "docs: start Task 7 scope discovery"
```

### Task 2: Freeze PQR Export UI remote evidence

**Files:**
- Modify: `.agents/completed/2.4.0-pqr-export-ui.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:** Consume PR #14 and exact-head GitHub Actions evidence; update
the completed cursor without changing product code.

- [ ] **Step 1: Write the exact-remote RED**

Require the completed cursor to contain:

```text
https://github.com/psiQAQ/ChemBlender_2_x/pull/14
3bab75429d37276e27dc158ba5bbf69d9085b9bd
30741155445
30741155450
eb3fc4ea6f86e8fc3f9475bd03d379445349db57
Ancestor verification: `Passed`
Remote CI: `Passed`
```

- [ ] **Step 2: Run RED**

Run the PQR UI recoverability test. Expected: failure because the cursor still
records `Remote CI: Not Run`.

- [ ] **Step 3: Update only final remote evidence**

Preserve local, Blender, package and review evidence. Replace the pending
remote section with the exact feature head, both matching runs, ordinary merge
commit and ancestor result.

- [ ] **Step 4: Run GREEN and commit**

Commit as `docs: record PQR UI remote integration`.

### Task 3: Audit and select one candidate

**Files:**
- Create: `docs/quantum-visualization/2.4.0/task7-candidate-intake.md`
- Modify: `.agents/active/2.4.0-task7-scope-discovery.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:** Consume live GitHub state, Cube reader/model/fixtures, ADR 0041,
artifact capabilities and Reader API compatibility policy. Produce one
auditable selection.

- [ ] **Step 1: Recheck live facts**

Confirm PR #14, exact feature head, runs, merge and ancestry. Confirm Cube is
`F0 / none`, PQR is `F5 / project_browser / preview_confirmation`, Reader API
is `1.0-rc1`, and no external `chemblender.reader.json` adopter is visible.

- [ ] **Step 2: Write candidate-intake RED**

Require the intake to contain both candidates, current capability facts,
`Task 8 — Deterministic native Cube export`, explicit Reader API deferral, and
the unit/multi-dataset/readiness boundaries.

- [ ] **Step 3: Write the evidence record**

Separate confirmed facts, inference and recommendation. Select Cube only if
the reader, Grid3D, nuclear-charge, sidecar, cache and fixture evidence remains
valid and no writer already exists.

- [ ] **Step 4: Run GREEN and commit**

Commit the intake and updated cursor as
`docs: select native Cube export for Task 8`.

### Task 4: Queue deterministic native Cube export

**Files:**
- Create: `docs/superpowers/plans/2026-08-02-chemblender-2.4.0-cube-export.md`
- Create: `.agents/queued/2.4.0-cube-export.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:** Produce an executable TDD plan for
`preview_cube_export(project_entities, *, dataset_index=None)` and
`export_cube(project_entities, *, dataset_index=None, confirm_loss=False,
destination=None, is_cancelled=None)`. Leave state `not_started`.

- [ ] **Step 1: Write plan/queue RED**

Require the selected plan to cover readiness, authoritative lazy snapshots,
bohr output conversion, explicit dataset selection, dataset IDs, stable loss
preview, atomic cancellation and semantic native `parse_cube()` re-import.
Require queued goal `CB240-CUBE-EXPORT-T8` and stop boundaries for UI and
Reader API stable.

- [ ] **Step 2: Run RED**

Run the Task 7 recoverability test. Expected: error because the selected plan
and queued cursor do not exist.

- [ ] **Step 3: Write the Cube implementation plan**

Define independent TDD tasks for readiness, writer, unit/dataset semantics,
semantic re-import/resource ownership, capability publication, complete local
and Blender qualification, two reviews, checkpoint and exact-head remote gate.
Use the existing `ExportReport`, short-sibling atomic writer, `Grid3D`,
`AtomicProperty` and native parser. Add no model or dependency.

- [ ] **Step 4: Create the queued cursor and run GREEN**

Set `State: not_started`, baseline to this discovery branch, current task
`Task 1 — Freeze Cube export readiness`, and keep Cube UI and Reader API stable
unstarted. Run the documentation tests and commit as
`docs: queue deterministic native Cube export`.

### Task 5: Verify, review and checkpoint

**Files:**
- Delete: `.agents/active/2.4.0-task7-scope-discovery.md`
- Create: `.agents/completed/2.4.0-task7-scope-discovery.md`
- Modify: `docs/superpowers/plans/2026-08-02-chemblender-2.4.0-task7-scope-discovery.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:** Leave no active cursor and exactly one queued implementation.

- [ ] **Step 1: Run documentation/static qualification**

Run:

```powershell
& $pythonBin -m unittest `
  tests.test_quantum_visualization_docs `
  tests.test_generated_docs_fresh -v
& $pythonBin -m compileall -q tests
git diff --check
```

Prove zero diff under `ChemBlender/`, `worker/`, `.github/`, manifest and
CHANGELOG.

- [ ] **Step 2: Run two independent reviews**

Review specification compliance and plan/code-quality correctness. Fix every
Critical, Important and task-related Minor finding; rerun affected checks.

- [ ] **Step 3: Write completion RED**

Change routing to no active cursor, queued Cube only, and require completed
goal `CB240-TASK7-SCOPE-DISCOVERY`. Run the focused tests; expect failure/error
until the completed cursor replaces the active cursor.

- [ ] **Step 4: Checkpoint and commit**

Record design/planning/selection/queue commits, RED/GREEN evidence, reviews,
zero runtime diff and `Remote CI: Not Run`. Mark Tasks 1–5 checked and commit:

```powershell
git add -- `
  .agents/active/2.4.0-task7-scope-discovery.md `
  .agents/completed/2.4.0-task7-scope-discovery.md `
  .agents/queued/2.4.0-cube-export.md `
  docs/superpowers/plans/2026-08-02-chemblender-2.4.0-task7-scope-discovery.md `
  tests/test_quantum_visualization_docs.py
git commit -m "chore: checkpoint Task 7 scope discovery"
```

- [ ] **Step 5: Final verification and stop**

Rerun the full documentation/static qualification and confirm a clean
worktree. Do not activate or implement Cube export and do not push.
