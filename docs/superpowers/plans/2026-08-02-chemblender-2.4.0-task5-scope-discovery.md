# ChemBlender 2.4.0 Task 5 Scope Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` task by task.

**Goal:** Close PDB Export UI remote integration evidence, select exactly one
evidence-backed Task 5, and leave its runtime implementation queued but
unstarted.

**Architecture:** This is a documentation-only state transition. Archive the
merged PDB UI cursor, compare the three remaining bounded candidates, and route
one selected slice into an implementation plan and queued cursor. Product and
runtime state remain read-only.

**Tech Stack:** Git, GitHub CLI read-only evidence, Python 3.13 standard-library
`unittest`, Markdown documentation contracts.

## Global Constraints

- Work only on `codex/2.4.0-task5-scope-discovery` from merge commit
  `d5028aa5d8568a44181b822293fbe62462d9a496`.
- Use the approved design in
  `docs/superpowers/specs/2026-08-02-chemblender-2.4.0-task5-scope-discovery-design.md`.
- Select at most one of native PQR export, native Cube export or Reader API v1
  stable gate.
- Do not modify runtime, dependencies, schema, manifest, workflows, version,
  CHANGELOG, tags or Releases.
- Do not push, create a PR or otherwise modify remote state.

### Task 1: Persist the Task 5 discovery boundary

**Files:**
- Create: `docs/superpowers/plans/2026-08-02-chemblender-2.4.0-task5-scope-discovery.md`
- Create: `.agents/active/2.4.0-task5-scope-discovery.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:** Produce one active recovery cursor; no product interface.

- [ ] Change the routing contract to expect only
  `.agents/active/2.4.0-task5-scope-discovery.md` and no queued task.
- [ ] Add a recoverability contract for the design, plan, goal, baseline,
  selection candidates, stop boundary and pending implementation state.
- [ ] Run the focused contract before creating the active cursor; expect failure
  because the merged PDB UI cursor is still active and the Task 5 cursor is
  absent.
- [ ] Create the active cursor with goal `CB240-TASK5-SCOPE-DISCOVERY`, baseline
  `d5028aa5d8568a44181b822293fbe62462d9a496`, the approved design and this plan.
- [ ] Run the focused documentation GREEN and `git diff --check`.
- [ ] Commit as `docs: start Task 5 scope discovery`.

### Task 2: Archive PDB Export UI integration

**Files:**
- Move: `.agents/active/2.4.0-pdb-export-ui.md`
- Create: `.agents/completed/2.4.0-pdb-export-ui.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:** Consume PR #12 and exact-head GitHub Actions evidence; produce
one immutable completed cursor.

- [ ] Require the completed cursor to record PR #12, exact feature head
  `5756532077d8aca8cebc54becf411133af7f96d8`, runs `30728969782` and
  `30728969751`, ordinary merge `d5028aa5d8568a44181b822293fbe62462d9a496`
  and passed ancestry verification.
- [ ] Run the focused test and record RED because the cursor still contains the
  pre-merge attempt state and remains active.
- [ ] Move the cursor to completed, preserve its local RED/GREEN, package,
  Blender and review evidence, and replace the pending remote gate with the
  final exact-head evidence.
- [ ] Run the focused test GREEN.

### Task 3: Audit and select one candidate

**Files:**
- Create: `docs/quantum-visualization/2.4.0/task5-candidate-intake.md`
- Modify: `.agents/active/2.4.0-task5-scope-discovery.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:** Consume live GitHub state, generated capabilities, PQR
readiness/reader fixtures, Cube contracts and Reader API policy. Produce one
auditable selection.

- [ ] Confirm PR #12, exact feature head, two exact-head runs, merge commit and
  ancestry live.
- [ ] Confirm PDB is `F5 / project_browser`, PQR and Cube are F0, and Reader API
  is `1.0-rc1`.
- [ ] Add a documentation RED requiring all three candidates, exact facts,
  `Task 5 — Deterministic native PQR export` and distinct Cube/Reader API
  deferral reasons.
- [ ] Write the minimum evidence-backed intake. Select PQR only if the live
  audit still proves its readiness/reader boundary and absent writer.
- [ ] Run the focused test GREEN.

### Task 4: Queue deterministic native PQR export

**Files:**
- Create: `docs/superpowers/plans/2026-08-02-chemblender-2.4.0-pqr-export.md`
- Create: `.agents/queued/2.4.0-pqr-export.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:** Consume `pqr_export_readiness()`, `Structure`,
`BiologicalHierarchy`, charge/radius datasets, shared export reports and the
short sibling atomic writer. Produce an executable TDD plan and a
`not_started` cursor; no exporter code.

- [ ] Add a RED requiring public `preview_pqr_export(project_entities)` and
  `export_pqr(project_entities, ...)` boundaries, deterministic 10/11-field
  whitespace records, explicit loss confirmation, cancellation cleanup and
  native semantic re-import.
- [ ] Write the implementation plan with core contract, writer, semantic
  round-trip, capability docs, package/Blender verification, two independent
  reviews, commits, exact-head remote gate and stop boundary.
- [ ] Create queued goal `CB240-PQR-EXPORT-T5` with `State: not_started` and
  keep PQR UI, Cube and Reader API stable unstarted.
- [ ] Run the documentation routing GREEN.

### Task 5: Verify and checkpoint

**Files:**
- Move: `.agents/active/2.4.0-task5-scope-discovery.md`
- Create: `.agents/completed/2.4.0-task5-scope-discovery.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:** Leave no active cursor and exactly one queued implementation.

- [ ] Run `python -m unittest tests.test_quantum_visualization_docs
  tests.test_generated_docs_fresh -v`.
- [ ] Run `python -m compileall -q tests`, strict UTF-8/no-BOM checks for edited
  files, and `git diff --check`.
- [ ] Prove the branch has zero diff under `ChemBlender/`, `worker/`, `.github/`,
  `ChemBlender/blender_manifest.toml` and `CHANGELOG.md`.
- [ ] Move the discovery cursor to completed and record planning/selection
  commits, RED/GREEN, protected-boundary audit and `Remote CI: Not Run`.
- [ ] Commit as `docs: select native PQR export for Task 5`.
- [ ] Re-run the full documentation/static verification and confirm a clean
  worktree. Stop without activating PQR runtime implementation or pushing.
