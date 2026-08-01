# ChemBlender 2.4.0 Scope Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish one evidence-backed, recoverable ChemBlender 2.4.0 scope-discovery task without starting product implementation.

**Architecture:** Keep the released 2.3.0 product and release records immutable. Add one documentation contract test and one active Execution Cursor that route future sessions through live feedback collection and the explicit 2.3.1/2.4.0 version gate.

**Tech Stack:** Markdown, Python 3.13 standard-library `unittest`, Git.

## Global Constraints

- Baseline is `origin/main@224155fa6986a4a51deaae3f9cf3d5f87ea0941a`.
- The approved design is `docs/superpowers/specs/2026-08-01-chemblender-2.4.0-scope-discovery-design.md`.
- Do not modify `ChemBlender/`, `worker/`, `blender_manifest.toml`, `CHANGELOG.md`, tags or Releases.
- Do not create a feature Wave, dependency change, format implementation or UI implementation.
- A reproducible 2.3.0 regression redirects later work to a separate 2.3.1 maintenance design; absent that evidence, the active target remains 2.4.0 Scope Discovery.
- This plan produces local commits only. Do not push, create a PR or modify a remote.
- Use Blender 5.1.2 bundled Python at `C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe`.

---

### Task 1: Lock the next-release documentation contract

**Files:**
- Modify: `tests/test_quantum_visualization_docs.py:8-11`
- Modify: `tests/test_quantum_visualization_docs.py:651-656`

**Interfaces:**
- Consumes: the approved design and this implementation plan.
- Produces: `NEXT_RELEASE_ACTIVE_FILES`, `test_240_scope_discovery_entrypoints_exist()` and `test_240_scope_discovery_cursor_is_recoverable()`, which require exactly one active cursor and its recovery/version-boundary fields.

- [ ] **Step 1: Add the failing contract**

Add the next-release constant beside the existing Wave 2.3.0 constants:

```python
NEXT_RELEASE_ACTIVE_FILES = ("2.4.0-scope-discovery.md",)
```

Change `test_single_active_task()` to compare against `NEXT_RELEASE_ACTIVE_FILES`, then add:

```python
def test_240_scope_discovery_entrypoints_exist(self):
    design_path = (
        "docs/superpowers/specs/"
        "2026-08-01-chemblender-2.4.0-scope-discovery-design.md"
    )
    plan_path = (
        "docs/superpowers/plans/"
        "2026-08-01-chemblender-2.4.0-scope-discovery.md"
    )
    cursor_path = ".agents/active/2.4.0-scope-discovery.md"
    design = self.read_doc(design_path)
    plan = self.read_doc(plan_path)
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
    cursor = self.read_doc(".agents/active/2.4.0-scope-discovery.md")

    for term in (
        "CB240-SCOPE-DISCOVERY",
        "State: `in_progress`",
        "Evidence-backed candidate intake",
        "224155fa6986a4a51deaae3f9cf3d5f87ea0941a",
        design_path,
        plan_path,
        ".agents/completed/2.3.0-release-readiness.md",
        "No product implementation has started",
        "No push",
    ):
        self.assertIn(term, cursor)
```

- [ ] **Step 2: Run the focused test and record RED**

Run:

```powershell
$pythonBin = 'C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe'
& $pythonBin -m unittest `
  tests.test_quantum_visualization_docs.QuantumVisualizationDocsTests.test_single_active_task `
  tests.test_quantum_visualization_docs.QuantumVisualizationDocsTests.test_240_scope_discovery_entrypoints_exist `
  tests.test_quantum_visualization_docs.QuantumVisualizationDocsTests.test_240_scope_discovery_cursor_is_recoverable -v
```

Expected: nonzero exit because `.agents/active/2.4.0-scope-discovery.md` does not exist and the active inventory is empty.

### Task 2: Create the recoverable Execution Cursor

**Files:**
- Create: `.agents/active/2.4.0-scope-discovery.md`
- Test: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Consumes: `NEXT_RELEASE_ACTIVE_FILES` and the exact plan/design paths from Task 1.
- Produces: the sole active Goal ID `CB240-SCOPE-DISCOVERY`, with current task `Evidence-backed candidate intake` and a fail-closed 2.3.1/2.4.0 branch rule.

- [ ] **Step 1: Create the cursor**

Create `.agents/active/2.4.0-scope-discovery.md` with the following complete contract:

```markdown
# ChemBlender 2.4.0 Scope Discovery

## Execution Cursor

- Goal ID: `CB240-SCOPE-DISCOVERY`.
- State: `in_progress`.
- Current task: `Evidence-backed candidate intake`.
- Baseline: `224155fa6986a4a51deaae3f9cf3d5f87ea0941a`.
- Design: `docs/superpowers/specs/2026-08-01-chemblender-2.4.0-scope-discovery-design.md`.
- Plan: `docs/superpowers/plans/2026-08-01-chemblender-2.4.0-scope-discovery.md`.
- Release provenance: `.agents/completed/2.3.0-release-readiness.md`.
- Version decision: default to 2.4.0 discovery; a reproducible 2.3.0 regression, data-loss, install/upgrade, security or in-contract compatibility defect redirects work to a separate 2.3.1 maintenance design.
- Evidence snapshot: on 2026-08-01, live GitHub queries returned zero open Issues, Pull Requests and Milestones; `.agents/active/` and `.agents/queued/` were empty at the baseline.
- Required subgoals:
  - `live-feedback-inventory`;
  - `release-known-limit-review`;
  - `capability-and-performance-gap-review`;
  - `version-classification`;
  - `single-task-prioritization`.
- Allowed changes: planning documents, active/queued/completed task records and their documentation contract tests only.
- Stop boundary: No product implementation has started. Do not modify runtime code, dependencies, manifest version, changelog release entries, tags or Releases during Scope Discovery.
- Resume rule: after compaction or a new session, read `AGENTS.md`, `.agents/README.md`, this cursor, the design and the plan; then refresh Git/GitHub state and continue from the first incomplete subgoal.
- Remote policy: No push, PR, remote modification, tag or Release operation belongs to this local planning checkpoint.
- Remote CI: `Not Run`; no runtime or workflow file changes are present.
```

- [ ] **Step 2: Run the focused test and record GREEN**

Run the same two-test command from Task 1.

Expected: `Ran 3 tests`, `OK`.

- [ ] **Step 3: Run the complete documentation contract**

Run:

```powershell
& $pythonBin -m unittest tests.test_quantum_visualization_docs -v
```

Expected: all tests pass with zero failures and zero errors.

- [ ] **Step 4: Commit the activation**

```powershell
git add -- `
  .agents/active/2.4.0-scope-discovery.md `
  tests/test_quantum_visualization_docs.py
git diff --cached --check
git commit -m "chore: activate ChemBlender 2.4.0 scope discovery"
```

### Task 3: Verify the planning checkpoint

**Files:**
- Verify: `docs/superpowers/specs/2026-08-01-chemblender-2.4.0-scope-discovery-design.md`
- Verify: `docs/superpowers/plans/2026-08-01-chemblender-2.4.0-scope-discovery.md`
- Verify: `.agents/active/2.4.0-scope-discovery.md`
- Verify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Consumes: the design, implementation plan, active cursor and contract test.
- Produces: a clean local planning branch with one active task and no product/runtime diff.

- [ ] **Step 1: Verify exact scope and UTF-8 contract**

Run:

```powershell
git diff --name-only origin/main...HEAD
git diff --quiet origin/main...HEAD -- ChemBlender worker `
  ChemBlender/blender_manifest.toml CHANGELOG.md
```

Expected: only the four authorized documentation/test paths differ, and the scoped runtime diff command exits 0.

Use `Path.read_bytes()` with Blender bundled Python to assert that the three new Markdown files do not start with `b"\xef\xbb\xbf"`.

- [ ] **Step 2: Run final static verification**

```powershell
& $pythonBin -m unittest tests.test_quantum_visualization_docs -v
& $pythonBin -m compileall -q tests
git diff --check
git show --check --stat --oneline origin/main..HEAD
git status --short
```

Expected: documentation tests and `compileall` exit 0; Git checks report no whitespace errors; the worktree is clean.

- [ ] **Step 3: Record the handoff**

Report the design, planning and activation commit SHAs; the RED/GREEN commands; documentation test count; exact modified-file inventory; worktree status; and next active task `Evidence-backed candidate intake`. Stop without product implementation or remote writes.

---

### Task 4: Complete evidence-backed candidate intake

**Files:**
- Create: `docs/quantum-visualization/2.4.0/candidate-intake.md`
- Create: `docs/superpowers/plans/2026-08-01-chemblender-2.4.0-mol2-export.md`
- Create: `.agents/queued/2.4.0-mol2-export.md`
- Modify then move: `.agents/active/2.4.0-scope-discovery.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Consumes: live GitHub feedback, 2.3.0 usability/known-limit evidence, generated format capabilities, performance baselines and Reader API compatibility policy.
- Produces: one completed Scope Discovery record and one `not_started` MOL2 export Task 1; no product task is active.

- [x] **Step 1: Refresh live feedback**

GitHub live queries on 2026-08-01 confirmed that Issues and Discussions were disabled,
there were no issues, open PRs or milestones, and the newly published v2.3.0 ZIP had no
downloads. The evidence window is insufficient for a Reader API stable promotion.

- [x] **Step 2: Apply the 2.3.1/2.4.0 gate**

The release evidence contains 0 Blocker, 0 Major and three non-functional Minor
warnings. No regression, data-loss, installation, upgrade, security or in-contract
compatibility defect was found, so the selected version remains 2.4.0.

- [x] **Step 3: Rank the minimum candidates**

Compare deterministic native MOL2 export, Reader API v1 stable promotion and an
independent human usability gate. Select MOL2 because its import-only F0 export gap,
readiness contract and native fixtures provide the strongest local evidence and the
smallest dependency-free implementation boundary.

- [x] **Step 4: Queue, but do not activate, Task 1**

Create the executable MOL2 plan and `not_started` queued cursor. The plan stops at the
core writer and semantic re-import; Blender UI, PDB/PQR, dependencies and release work
remain out of scope.

- [x] **Step 5: Complete RED/GREEN, review and checkpoint**

Run the focused documentation contract, full documentation module, `compileall`, BOM
audit, runtime-scope diff, `git diff --check` and an independent read-only review. Then
move the Scope Discovery cursor to completed, leave `.agents/active/` empty, record the
planning commit SHA in the queued cursor and commit the checkpoint locally without push.

Independent review found two Important plan gaps and two Minor wording/state gaps. The
plan now includes the documented `NO_CHARGES` readiness correction and the literal
`**** ****` charge-column placeholders; wording and completed-state findings were also
fixed. Focused re-review returned `Ready` with no remaining findings.
