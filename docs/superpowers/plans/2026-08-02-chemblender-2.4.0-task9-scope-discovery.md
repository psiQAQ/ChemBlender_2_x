# ChemBlender 2.4.0 Task 9 Scope Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan task by task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close native Cube core-export remote evidence, select exactly one
evidence-backed next 2.4.0 task, and leave its implementation queued but
unstarted.

**Architecture:** This is a documentation-only state transition. Freeze PR #15
and exact-head CI evidence, compare native Cube export UI, Reader API v1 stable
and 2.4.0 final qualification, then route only Cube UI into one design, plan and
queued cursor. No runtime or public API state changes.

**Tech Stack:** Git, GitHub CLI read-only evidence, Python 3.13 standard-library
`unittest`, Markdown documentation contracts.

## Global Constraints

- Work only on `codex/2.4.0-task9-scope-discovery` from merge commit
  `cd265d95c3cc73cae5355657cc0a5a8f1931d98b`.
- Follow the approved design in
  `docs/superpowers/specs/2026-08-02-chemblender-2.4.0-task9-scope-discovery-design.md`.
- Select exactly one of Cube Export UI, Reader API v1 stable or 2.4.0 Final
  Qualification.
- Do not modify `ChemBlender/`, `worker/`, `.github/`, dependencies, schema,
  manifest, workflows, version, CHANGELOG, tag or Release.
- Do not push, create a PR or otherwise modify remote state.

---

### Task 1: Persist the Task 9 discovery boundary

**Files:**
- Create: `docs/superpowers/plans/2026-08-02-chemblender-2.4.0-task9-scope-discovery.md`
- Create: `.agents/active/2.4.0-task9-scope-discovery.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:** Produce one active recovery cursor; no product interface.

- [x] **Step 1: Write the routing RED**

Set `NEXT_RELEASE_ACTIVE_FILES` to
`("2.4.0-task9-scope-discovery.md",)` and keep the queued set empty. Add a
recoverability test requiring the approved design, this plan, goal
`CB240-TASK9-SCOPE-DISCOVERY`, baseline merge, three candidates and the
no-runtime stop boundary.

- [x] **Step 2: Run RED**

Run the single-active and Task 9 recoverability tests. Expected: failure/error
because the active cursor does not exist.

- [x] **Step 3: Create the active cursor**

Record state `in_progress`, baseline, design/plan paths, candidate set, current
task `Live candidate audit`, resume rule and no-remote stop boundary.

- [x] **Step 4: Run GREEN and commit**

Run the focused documentation tests and `git diff --check`; commit as
`docs: start Task 9 scope discovery`.

### Task 2: Freeze native Cube export remote evidence

**Files:**
- Modify: `.agents/completed/2.4.0-cube-export.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:** Consume PR #15 and exact-head GitHub Actions evidence without
changing the qualified exporter.

- [ ] **Step 1: Write the exact-remote RED**

Require the completed cursor to contain PR URL, feature head
`164a681bb3d9cb788f778eca71f9fe61a0361019`, runs `30747458150` and
`30747458152`, merge commit `cd265d95c3cc73cae5355657cc0a5a8f1931d98b`,
ancestor verification and `Remote CI: Passed`.

- [ ] **Step 2: Run RED**

Run the Cube recoverability test. Expected: failure because the cursor still
records a pending retry.

- [ ] **Step 3: Update final remote evidence**

Preserve local, Blender, package, benchmark and review evidence. Replace only
the pending remote section with the exact successful integration evidence.

- [ ] **Step 4: Run GREEN and commit**

Commit as `docs: record Cube export remote integration`.

### Task 3: Audit and select one candidate

**Files:**
- Create: `docs/quantum-visualization/2.4.0/task9-candidate-intake.md`
- Modify: `.agents/active/2.4.0-task9-scope-discovery.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:** Compare the live capability catalog, export selection flow,
Reader API adoption evidence and release qualification dependency order.

- [ ] **Step 1: Recheck live facts**

Confirm PR #15 exact-head CI, merge and ancestry; Cube
`F5 / core / preview_confirmation`; Reader API `1.0-rc1`; selectable `Grid3D`
Project Browser rows; no visible external reader-manifest adopter.

- [ ] **Step 2: Write candidate-intake RED**

Require all three candidates, explicit selection of
`Task 10 — Native Cube Export UI`, and explicit deferral reasons for Reader API
stable and Final Qualification.

- [ ] **Step 3: Write the evidence record**

Separate confirmed facts, inference and recommendation. Select Cube UI only if
the existing Project Browser operator and core exporter can be reused without
a new module, model, schema or dependency.

- [ ] **Step 4: Run GREEN and commit**

Commit as `docs: select native Cube export UI for Task 10`.

### Task 4: Queue native Cube export UI

**Files:**
- Create: `docs/superpowers/specs/2026-08-02-chemblender-2.4.0-cube-export-ui-design.md`
- Create: `docs/superpowers/plans/2026-08-02-chemblender-2.4.0-cube-export-ui.md`
- Create: `.agents/queued/2.4.0-cube-export-ui.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:** Produce an executable TDD plan for selected-Grid3D projection,
explicit multi-dataset choice, core preview/write dispatch and installed
Project Browser proof. Leave state `not_started`.

- [ ] **Step 1: Write plan/queue RED**

Require the selected design/plan to reuse `.ui.export`,
`preview_cube_export()` and `export_cube()`, forbid a new UI module, and cover
dataset selection, loss confirmation, cancellation, native re-import and
catalog publication. Require queued goal `CB240-CUBE-EXPORT-UI-T10`.

- [ ] **Step 2: Run RED**

Run the Task 9 recoverability test. Expected: error because the selected
design, plan and queued cursor do not exist.

- [ ] **Step 3: Write the implementation design and plan**

Define minimal TDD tasks for `Grid3D` selection, format/filter/preview,
cancellable writer dispatch, capability publication, installed Blender smoke,
qualification, reviews, checkpoint and exact-head remote gate.

- [ ] **Step 4: Create the queued cursor and run GREEN**

Set state `not_started`, baseline to this discovery branch, current task
`Task 1 — Resolve selected Grid3D export context`, and keep Reader API stable
and Final Qualification unstarted. Commit as
`docs: queue native Cube export UI`.

### Task 5: Verify, review and checkpoint

**Files:**
- Delete: `.agents/active/2.4.0-task9-scope-discovery.md`
- Create: `.agents/completed/2.4.0-task9-scope-discovery.md`
- Modify: `docs/superpowers/plans/2026-08-02-chemblender-2.4.0-task9-scope-discovery.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:** Leave no active cursor and exactly one queued implementation.

- [ ] **Step 1: Run documentation qualification**

Run `tests.test_quantum_visualization_docs`,
`tests.test_generated_docs_fresh`, `compileall -q tests`, UTF-8/no-BOM audit
and `git diff --check`. Prove zero diff under protected runtime/release paths.

- [ ] **Step 2: Run two independent reviews**

Review specification compliance and plan/code-quality correctness. Fix every
Critical, Important and task-related Minor finding; rerun affected checks.

- [ ] **Step 3: Write completion RED**

Change routing to no active cursor and one queued Cube UI cursor; require
completed goal `CB240-TASK9-SCOPE-DISCOVERY`. Run the focused test and observe
failure until the completed cursor replaces the active cursor.

- [ ] **Step 4: Checkpoint and commit**

Record all commit SHAs, RED/GREEN evidence, reviews, zero runtime diff and
`Remote CI: Not Run`; mark Tasks 1-5 checked and commit as
`chore: checkpoint Task 9 scope discovery`.

- [ ] **Step 5: Final verification and stop**

Rerun the documentation qualification and confirm a clean worktree. Do not
activate Cube UI, push or create a PR.
