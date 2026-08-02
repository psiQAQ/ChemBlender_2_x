# ChemBlender 2.4.0 Task 11 Scope Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close Native Cube Export UI remote integration, select exactly one remaining 2.4.0 task, and leave that task queued but unstarted.

**Architecture:** Reuse the established odd-numbered scope-discovery pattern. Persist exact remote evidence in the completed producer cursor, make the candidate decision in a separate evidence record, and keep runtime work behind a queued cursor and explicit activation gate.

**Tech Stack:** Markdown, Python 3.13 standard-library `unittest`, Git, GitHub CLI.

## Global Constraints

- Baseline is `73e774bb1da93bf009e8dedaa3e67f5860cf6722` on `origin/main`.
- Work only on `codex/2.4.0-task11-scope-discovery` in its isolated worktree.
- Runtime, workflow, manifest, model, schema, dependency, version, CHANGELOG, tag and Release files are protected.
- Reader API remains `1.0-rc1`; this discovery cannot promote stable.
- Select exactly one of Reader API v1 stable gate or 2.4.0 Final Qualification.
- Do not activate or execute the selected task in this plan.
- No push, PR, merge, tag or Release belongs to Task 11.

---

### Task 1: Persist the Task 11 discovery boundary

**Files:**
- Modify: `tests/test_quantum_visualization_docs.py`
- Create: `.agents/active/2.4.0-task11-scope-discovery.md`
- Create: `docs/superpowers/plans/2026-08-02-chemblender-2.4.0-task11-scope-discovery.md`

**Interfaces:**
- Consumes: approved design `docs/superpowers/specs/2026-08-02-chemblender-2.4.0-task11-scope-discovery-design.md`.
- Produces: the sole active goal `CB240-TASK11-SCOPE-DISCOVERY` and no queued task.

- [x] **Step 1: Write the routing RED**

Set the routing constants to:

```python
TASK11_SCOPE_ACTIVE_FILE = "2.4.0-task11-scope-discovery.md"
TASK11_SCOPE_COMPLETED_FILE = "2.4.0-task11-scope-discovery.md"
FINAL_QUALIFICATION_CURSOR_FILE = "2.4.0-final-qualification.md"
NEXT_RELEASE_ACTIVE_FILES = (TASK11_SCOPE_ACTIVE_FILE,)
NEXT_RELEASE_QUEUED_FILES = ()
```

Add `test_240_task11_scope_discovery_is_recoverable()` requiring the approved
design, this plan, baseline, candidate set and no-runtime/no-push boundary.

- [x] **Step 2: Run RED**

Run:

```powershell
& $pythonBin -m unittest `
  tests.test_quantum_visualization_docs.QuantumVisualizationDocsTests.test_single_active_task `
  tests.test_quantum_visualization_docs.QuantumVisualizationDocsTests.test_240_task11_scope_discovery_is_recoverable -v
```

Expected and observed: exit 1, two failures because the active cursor is
absent.

- [x] **Step 3: Create the active cursor and plan**

Record baseline, design/plan paths, two candidates, current task
`Live candidate audit`, resume rule, protected boundaries and `No push`.

- [ ] **Step 4: Run GREEN and commit**

Run the two focused tests and `git diff --check`. Commit as
`docs: start Task 11 scope discovery`.

### Task 2: Freeze Native Cube Export UI remote evidence

**Files:**
- Modify: `.agents/completed/2.4.0-cube-export-ui.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Consumes: PR #17, exact feature head, two exact-head workflow runs and merge ancestry.
- Produces: final `Remote CI: Passed` evidence without changing qualified product files.

- [ ] **Step 1: Write the exact-remote RED**

Require the completed Cube cursor to contain:

```text
PR #17
f63b0a5da47f76dd38f7cf5e79a39e99cf918005
30755106798
30755106795
73e774bb1da93bf009e8dedaa3e67f5860cf6722
Remote CI: `Passed`
```

- [ ] **Step 2: Run RED**

Run the Task 11 recoverability test. Expected: failure because the completed
Cube cursor still records the pre-merge retry boundary.

- [ ] **Step 3: Replace only stale remote state**

Preserve local tests, package, Blender and review evidence. Add final PR/run/job,
ordinary merge and ancestor verification facts; remove the stale instruction
that the post-fix run is pending.

- [ ] **Step 4: Run GREEN and commit**

Run the focused Task 9 and Task 11 recoverability tests. Commit as
`docs: record Cube UI remote integration`.

### Task 3: Audit and select one candidate

**Files:**
- Create: `docs/quantum-visualization/2.4.0/task11-candidate-intake.md`
- Modify: `.agents/active/2.4.0-task11-scope-discovery.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Consumes: live capability catalog, Reader API token/adoption evidence and completed export-product matrix.
- Produces: one explicit candidate selection with alternatives and deferral rationale.

- [ ] **Step 1: Recheck live facts**

Confirm PR #17 exact-head CI and ancestry, Cube
`F5 / project_browser / preview_confirmation`, Reader API `1.0-rc1`, external
manifest code-search result and 2.3.0 Release asset download counts.

- [ ] **Step 2: Write candidate-intake RED**

Require both candidates, explicit selection of
`Task 12 — 2.4.0 Final Qualification`, explicit Reader API stable deferral and
the prohibition on combining the gates.

- [ ] **Step 3: Write evidence and update cursor**

Separate confirmed facts, inference and recommendation. Record the selection
only after the live facts match the approved design.

- [ ] **Step 4: Run GREEN and commit**

Run Task 11 recoverability and `git diff --check`. Commit as
`docs: select 2.4.0 final qualification`.

### Task 4: Queue 2.4.0 Final Qualification

**Files:**
- Create: `docs/superpowers/specs/2026-08-02-chemblender-2.4.0-final-qualification-design.md`
- Create: `docs/superpowers/plans/2026-08-02-chemblender-2.4.0-final-qualification.md`
- Create: `.agents/queued/2.4.0-final-qualification.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Consumes: selected boundary from the Task 11 design and candidate intake.
- Produces: queued goal `CB240-FINAL-QUALIFICATION-T12`, state `not_started`.

- [ ] **Step 1: Write plan/queue RED**

Require the future plan to contain these independently reviewable tasks:

```text
Task 0: Activate the queued qualification
Task 1: Audit frozen public and scientific boundaries
Task 2: Run complete Python and dependency qualification
Task 3: Rebuild and audit the committed extension artifact
Task 4: Run Blender product qualification
Task 5: Review, checkpoint and exact-head remote gate
```

Require preservation of Reader API `1.0-rc1`, no new capability, ordinary
merge only, and explicit version/tag/Release stop boundaries.

- [ ] **Step 2: Run RED**

Run the Task 11 recoverability test. Expected: failure/error because selected
design, plan and queued cursor do not exist.

- [ ] **Step 3: Create selected design, plan and queued cursor**

Define exact commands and evidence for full unittest discovery, optional
dependency integrations, generated docs, compileall/import isolation, clean
committed-tree package/ZIP audit, Blender 5.1.2 validate/build/install/product
smoke, two reviews, exact-head CI and ordinary merge. State remains
`not_started`.

- [ ] **Step 4: Run GREEN and commit**

Run Task 11 recoverability and documentation tests. Commit as
`docs: queue 2.4.0 final qualification`.

### Task 5: Verify, review and checkpoint

**Files:**
- Delete: `.agents/active/2.4.0-task11-scope-discovery.md`
- Create: `.agents/completed/2.4.0-task11-scope-discovery.md`
- Modify: `docs/superpowers/plans/2026-08-02-chemblender-2.4.0-task11-scope-discovery.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Consumes: all Task 11 commits and review findings.
- Produces: no active cursor and exactly one queued Final Qualification cursor.

- [ ] **Step 1: Run documentation qualification**

Run:

```powershell
& $pythonBin -m unittest `
  tests.test_quantum_visualization_docs `
  tests.test_generated_docs_fresh -v
& $pythonBin -m compileall -q tests
git diff --check
```

Audit all changed text as UTF-8 without BOM and prove zero diff under
`ChemBlender/`, `worker/`, `.github/`, `ChemBlender/blender_manifest.toml` and
`CHANGELOG.md`.

- [ ] **Step 2: Run two independent reviews**

Run specification-compliance and plan/code-quality/scientific-correctness
reviews. Fix every Critical, Important and task-related Minor finding, then
rerun affected verification.

- [ ] **Step 3: Write completion RED**

Change routing constants to no active cursor and exactly one queued Final
Qualification cursor. Require completed goal `CB240-TASK11-SCOPE-DISCOVERY`.
Run focused routing and observe failure until the completed cursor replaces
the active cursor.

- [ ] **Step 4: Checkpoint and commit**

Record design/planning/evidence/selection/queue/review commit SHAs, RED/GREEN
evidence, reviews, zero runtime diff and `Remote CI: Not Run`. Mark all plan
steps checked and commit as `chore: checkpoint Task 11 scope discovery`.

- [ ] **Step 5: Final verification and stop**

Rerun the documentation qualification and confirm a clean worktree. Do not
activate Final Qualification or perform any remote mutation.

## Stop Boundary

Stop after Task 11 is completed and `2.4.0 Final Qualification` is queued.
Reader API stable, Final Qualification execution, version, CHANGELOG, push,
PR, merge, tag and Release remain unstarted.
