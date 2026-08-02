# ChemBlender 2.4.0 Task 4 Scope Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` task by task.

**Goal:** Close Task 3 remote integration evidence, select exactly one
evidence-backed Task 4, and leave its runtime implementation queued but
unstarted.

**Architecture:** This is a documentation-only state transition. Record the
merged PDB core gate, compare four bounded candidates, and route one selected
slice into an implementation plan and queued cursor. Product/runtime state is
read-only.

**Tech Stack:** Git, GitHub CLI read-only evidence, Python 3.13 standard-library
`unittest`, Markdown documentation contracts.

## Global constraints

- Work only on `codex/2.4.0-task4-scope-discovery` from merge commit
  `79a93f52053fdf809c28c24800366010577a1984`.
- Use the approved design in
  `docs/superpowers/specs/2026-08-02-chemblender-2.4.0-task4-scope-discovery-design.md`.
- Select at most one of PDB Export UI, native PQR export, native Cube export or
  Reader API v1 stable gate.
- Do not modify runtime, dependencies, schema, manifest, workflows, version,
  CHANGELOG, tags or Releases.

### Task 1: Persist the Task 4 discovery boundary

**Files:**
- Create: `docs/superpowers/specs/2026-08-02-chemblender-2.4.0-task4-scope-discovery-design.md`
- Create: `docs/superpowers/plans/2026-08-02-chemblender-2.4.0-task4-scope-discovery.md`
- Create: `.agents/active/2.4.0-task4-scope-discovery.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:** Produce one active recovery cursor; no product interface.

- [x] Write the routing/recoverability RED before creating the files.
- [x] Record baseline, stop boundary and exact Task 3 integration evidence.
- [x] Run focused documentation GREEN and `git diff --check`.
- [x] Commit as `docs: start Task 4 scope discovery`.

### Task 2: Audit and select one candidate

**Files:**
- Create: `docs/quantum-visualization/2.4.0/task4-candidate-intake.md`
- Modify: `.agents/active/2.4.0-task4-scope-discovery.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:** Consume live GitHub state, generated capabilities, UI export
dispatch, PDB/PQR readiness, Cube contracts and Reader API policy. Produce one
auditable selection.

- [ ] Confirm PR #11, exact feature head, two exact-head runs, merge commit and
  ancestry live.
- [ ] Confirm PDB is core-only F5 and absent from `_FORMAT_ITEMS`; confirm PQR
  and Cube are F0 and Reader API is `1.0-rc1`.
- [ ] Record separate facts, inference, recommendation and deferral reasons.
- [ ] Select exactly one bounded implementation or explicitly select none.

### Task 3: Queue the selected implementation

**Files:**
- Create: one selected implementation plan under `docs/superpowers/plans/`
- Create: one selected `.agents/queued/` cursor
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:** Produce an executable TDD plan with files, exact integration
points, RED/GREEN commands, Blender verification, reviews, commits, remote gate
and stop boundary. Runtime stays untouched.

- [ ] Add the selection/queue documentation RED.
- [ ] Write the minimum implementation design into the plan; reuse existing
  code paths and add no speculative abstraction.
- [ ] Set the queued cursor to `State: not_started`.
- [ ] Keep all deferred candidates unstarted.

### Task 4: Verify and checkpoint

**Files:**
- Move: `.agents/active/2.4.0-task4-scope-discovery.md`
- Create: `.agents/completed/2.4.0-task4-scope-discovery.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:** Leave no active cursor and exactly one queued implementation.

- [ ] Run focused documentation and generated-capability tests.
- [ ] Run `python -m compileall -q tests`, UTF-8/no-BOM audit and
  `git diff --check`.
- [ ] Prove zero runtime/dependency/manifest/workflow/version diff.
- [ ] Obtain an independent read-only documentation review and fix every
  Critical, Important and task-related Minor finding.
- [ ] Move the cursor to completed, record evidence and commit the checkpoint.
- [ ] Push the scope-discovery branch normally; do not create a PR, tag or
  Release.
