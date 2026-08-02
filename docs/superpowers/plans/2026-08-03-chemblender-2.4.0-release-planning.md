# ChemBlender 2.4.0 Release Planning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze an executable `2.4.0-rc.1` then stable `2.4.0` release train, persist final-qualification integration evidence, and ordinarily integrate the planning artifacts without changing a version or publishing a release.

**Architecture:** Reuse the existing manifest-driven release metadata, package verifier and GitHub workflows. This task adds documentation contracts and routing only; later release preparation performs the version/changelog change and runtime qualification.

**Tech Stack:** Markdown, Python standard-library `unittest`, existing GitHub Actions and Blender Extension release scripts.

## Global Constraints

- Follow `docs/superpowers/specs/2026-08-03-chemblender-2.4.0-release-planning-design.md`.
- Preserve manifest `2.3.0`, Reader API `1.0-rc1`, schemas, dependencies and workflows.
- Do not add product code, a capability, tag or GitHub Release.
- External writes require current explicit authority for the named gate. A
  green workflow never grants merge, tag or publication authority.
- Use ordinary commits and merges; no rebase, force-push, squash or branch deletion.
- Tagging and publishing require separate explicit authorizations.

### Task 0: Activate release planning

**Files:**
- Create: `.agents/active/2.4.0-release-planning.md`
- Create: `docs/superpowers/plans/2026-08-03-chemblender-2.4.0-release-planning.md`

**Interfaces:**
- Consumes: `origin/main` after ordinary PR #19 integration.
- Produces: the sole active goal `CB240-RELEASE-PLANNING` on an isolated branch.

- [x] **Step 1: Record the live baseline**

Record branch, full baseline SHA, final-qualification PR/run/merge evidence and
the planning stop boundary. Do not copy the stale pre-CI checkpoint status.

- [x] **Step 2: Verify and commit activation**

Run `git diff --check` and commit the plan plus active cursor as
`docs: activate 2.4.0 release planning`.

### Task 1: Freeze release scope and qualification evidence

**Files:**
- Create: `docs/quantum-visualization/2.4.0/release-planning.md`
- Modify: `.agents/active/2.4.0-release-planning.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Consumes: final qualification evidence, merged capabilities, manifest and release automation.
- Produces: a checked release-scope/evidence record with no runtime change.

- [x] **Step 1: Write documentation RED**

Require the record to name `2.4.0-rc.1`, stable `2.4.0`, frozen capabilities,
Reader API `1.0-rc1`, PR #19, both exact-head workflow runs and the ordinary
merge SHA. Require manifest/version/tag/Release to remain unchanged.

- [x] **Step 2: Run the focused failing test**

Run:

```powershell
& $pythonBin -m unittest `
  tests.test_quantum_visualization_docs.ReleasePlanningContractTests -v
```

The expected RED is the missing evidence document and active-cursor terms.

- [x] **Step 3: Add the minimum evidence record**

Document only verified scope, live integration evidence, release stages,
failure policy and explicit stop boundaries. Do not duplicate release scripts.

- [x] **Step 4: Run focused GREEN and commit**

Run the focused test and `git diff --check`. Commit as
`docs: freeze 2.4.0 release train`.

### Task 2: Qualify and checkpoint the planning gate

**Files:**
- Delete: `.agents/active/2.4.0-release-planning.md`
- Create: `.agents/completed/2.4.0-release-planning.md`
- Modify: `docs/superpowers/plans/2026-08-03-chemblender-2.4.0-release-planning.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Consumes: frozen planning evidence and current release contracts.
- Produces: a clean checkpoint ready for exact-head CI.

- [ ] **Step 1: Run focused release/document contracts**

Run:

```powershell
& $pythonBin -m unittest `
  tests.test_quantum_visualization_docs `
  tests.test_release_metadata `
  tests.test_release_artifact `
  tests.test_release_notes `
  tests.test_prerelease_probe_script `
  tests.test_artifact_size_report -v
```

- [ ] **Step 2: Run static verification**

Run `compileall`, `git diff --check`, verify the manifest and CHANGELOG hashes
are unchanged, and confirm no workflow or runtime source file changed.

- [ ] **Step 3: Review the frozen boundary**

Perform specification-compliance and code-quality/YAGNI reviews. Fix every
task-related finding and rerun affected checks.

- [ ] **Step 4: Complete the cursor and checkpoint**

Move the active cursor to completed, mark this plan complete and commit as
`chore: checkpoint 2.4.0 release planning`.

### Task 3: Exact-head remote integration

**Files:**
- No repository changes unless a confirmed CI defect requires a focused fix.

**Interfaces:**
- Consumes: the clean planning checkpoint head.
- Produces: exact-head CI and ordinary merge ancestry on `origin/main`.

- [ ] **Step 1: Push and create a ready PR**

After confirming current push/PR authority, ordinarily push
`codex/2.4.0-release-planning` and create one ready PR to `main`. Record the
exact feature head. Without that authority, stop and report the checkpoint.

- [ ] **Step 2: Require exact-head CI**

Require every job in `extension-package` and `optional-qc-core` to finish
success with `headSha` equal to the checkpoint head. Old or branch-mismatched
runs are invalid.

- [ ] **Step 3: Stop for merge authority, then merge ordinarily**

Report exact-head CI and require current merge authority. Only then use a
normal merge commit. Do not delete the feature branch.

- [ ] **Step 4: Require exact merge-SHA CI and verify ancestry**

Fetch, prove the checkpoint head is an ancestor of `origin/main`, and require
both workflows to pass for the exact merge commit SHA. This evidence does not
authorize any tag or Release.

## Stop Boundary

Stop after release planning is merged and ancestry is verified. The next
recommended task is 2.4.0 RC preparation. Manifest/CHANGELOG changes, tagging
and Release publication have not started.
