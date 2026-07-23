# ChemBlender 2.3.0 Master Sequencing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the approved 2.3.0 planning documents, execute Waves 0–4 in a safe order, and produce exact-tag pre-releases and a final Windows x64 release.

**Architecture:** This plan is the routing plan. Each Wave has separate design and implementation plans and must complete a real-file-to-Blender vertical slice before the next Wave activates. Existing public imports and sidecar data remain compatible through explicit façades and migrations.

**Tech Stack:** Git, Superpowers workflow, Python 3.13, standard-library `unittest`, Blender 5.1.2 Extension tooling, PowerShell, GitHub Actions.

## Global Constraints

- Read live `AGENTS.md`, `.agents/README.md`, the active task, relevant ADRs and architecture guide before every implementation session.
- Verify current branch, worktree, remotes, Blender executable, bundled Python, runtime system, extension repositories, dependency state and CI live.
- Only one Wave may be active.
- Do not install packages into Blender global `site-packages` or at extension import/register time.
- Every code task follows red test, observed failure, minimal implementation, observed pass, review and focused commit.
- Protect user changes; never use destructive reset.
- Update `.agents/reference/code-architecture-guide.md` in the same commit as any responsibility or public entrypoint change.
- Pre-release tags are prohibited until Blender 5.1.2 native validation proves the chosen manifest version syntax.
- Publishing, pushing, PR creation and release creation require explicit user authorization.

---

### Task 1: Integrate the planning bundle as documentation only

**Files:**
- Create: all files listed by `INTEGRATION_MANIFEST.json`
- Modify: `.agents/README.md`
- Modify: `docs/README.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Consumes: the unpacked planning bundle.
- Produces: discoverable ADR, spec, plan and queued-task entrypoints without changing runtime code.

- [ ] **Step 1: Inspect live conflicts**

Run:

```powershell
git status --short
git log -10 --oneline
Get-ChildItem .agents\decisions | Sort-Object Name | Select-Object -Last 15
Get-ChildItem docs\superpowers\specs | Sort-Object Name | Select-Object -Last 10
```

Expected: the worktree state and any ADR/date filename conflicts are known. Do not copy conflicting files until names are resolved.

- [ ] **Step 2: Copy only non-conflicting new documents**

Use a file copy that does not overwrite existing paths. If ADR numbers 0029–0040 already exist, renumber the new ADRs consecutively and update all references before staging.

- [ ] **Step 3: Extend documentation tests**

Add explicit entrypoint assertions to `tests/test_quantum_visualization_docs.py`:

```python
def test_230_planning_entrypoints_exist(self):
    paths = (
        "docs/quantum-visualization/2.3.0/README.md",
        "docs/quantum-visualization/2.3.0/roadmap.md",
        "docs/quantum-visualization/2.3.0/audits/2026-07-23-main-deep-audit.md",
        "docs/superpowers/specs/2026-07-23-chemblender-2.3.0-native-platform-design.md",
        "docs/superpowers/plans/2026-07-23-chemblender-2.3.0-master-sequencing.md",
    )
    for relative in paths:
        self.assertTrue((ROOT / relative).is_file(), relative)
```

Also add a check that exactly five new Wave queue files exist and active remains unchanged during documentation integration.

- [ ] **Step 4: Run documentation verification**

Run:

```powershell
& $pythonBin -m unittest tests.test_quantum_visualization_docs -v
git diff --check
git status --short
```

Expected: all document tests pass, links resolve, no BOM or whitespace errors, and runtime files are untouched.

- [ ] **Step 5: Commit documentation integration**

```bash
git add .agents docs tests/test_quantum_visualization_docs.py
git commit -m "docs: add ChemBlender 2.3.0 execution roadmap"
```

### Task 2: Activate Wave 0 only

**Files:**
- Create: `.agents/active/2.3.0-wave-0-platform-foundation.md`
- Modify: `.agents/queued/2.3.0-wave-0-platform-foundation.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Consumes: integrated Wave 0 queue document.
- Produces: one authoritative active task.

- [ ] **Step 1: Re-verify live state against the audit snapshot**

Run:

```powershell
git fetch --all --prune
git status --short
git branch --show-current
git log -5 --oneline
```

Inspect runtime files named in the deep audit. Record any corrected finding in the active document before implementation.

- [ ] **Step 2: Create the active task**

Copy the Wave 0 queued content into `.agents/active/2.3.0-wave-0-platform-foundation.md`, add:

Add a `## Live Baseline` section containing the observed branch name, full starting commit SHA, MCP-discovered Blender version/executable/Python/system/repositories, `Verification status: Not Run`, and the first plan path `docs/superpowers/plans/2026-07-23-chemblender-2.3.0-wave-0-core-modularization.md`. Write the actual observed values directly; do not insert template tokens.

- [ ] **Step 3: Update the single-active-task test**

Set the expected filename to the Wave 0 active file while leaving all other queue files queued.

- [ ] **Step 4: Verify and commit task activation**

```powershell
& $pythonBin -m unittest tests.test_quantum_visualization_docs -v
git diff --check
git add .agents tests/test_quantum_visualization_docs.py
git commit -m "chore: activate ChemBlender 2.3.0 wave 0"
```

### Task 3: Execute Wave 0 plans in fixed order

**Files:**
- Execute plans listed below.

**Interfaces:**
- Consumes: one active Wave 0 task.
- Produces: `2.3.0-alpha.1` release candidate state.

- [ ] **Step 1: Execute core modularization**

Use `2026-07-23-chemblender-2.3.0-wave-0-core-modularization.md`.

- [ ] **Step 2: Execute source/session storage**

Use `2026-07-23-chemblender-2.3.0-wave-0-source-session-sidecar.md`.

- [ ] **Step 3: Execute import transaction and diagnostics**

Use `2026-07-23-chemblender-2.3.0-wave-0-import-transaction-diagnostics.md`.

- [ ] **Step 4: Execute Reader API 0.x**

Use `2026-07-23-chemblender-2.3.0-wave-0-reader-api.md`.

- [ ] **Step 5: Execute explicit registration and UI skeleton**

Use `2026-07-23-chemblender-2.3.0-wave-0-registration-ui.md`.

- [ ] **Step 6: Execute alpha release groundwork**

Use `2026-07-23-chemblender-2.3.0-wave-0-release-groundwork.md`.

- [ ] **Step 7: Run the Wave 0 gate**

Run all CPython tests, compileall, extension validate/build, isolated install, session import/save/reopen smoke and `git diff --check`. Update the active task with Passed/Failed/Not Run evidence.

### Task 4: Advance Waves only after their release gate

**Files:**
- Move current active summary to `.agents/completed/`.
- Activate the next queued Wave.

**Interfaces:**
- Consumes: a Wave with all gate evidence.
- Produces: one completed summary and one active next Wave.

- [ ] **Step 1: Review gate evidence**

Do not advance if any required test is skipped, failed or not run without an accepted reason.

- [ ] **Step 2: Create a concise completed record**

The completed record includes Result, Evidence, Known Limits, release/tag status and the exact next Wave.

- [ ] **Step 3: Update roadmap maturity**

Mark only the maturity actually proven: Contract, Synthetic Integration, Real-file Integration, Product UX or Release-qualified.

- [ ] **Step 4: Activate exactly one next Wave**

Wave order is 0 → 1 → 2 → 3 → 4. Repeat the documentation test and commit the transition separately from runtime work.

### Task 5: Final 2.3.0 release handoff

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `ChemBlender/blender_manifest.toml`
- Modify: release documentation and completed record.

**Interfaces:**
- Consumes: Wave 4 RC with fixes only after tag.
- Produces: a user-authorized exact-tag final release workflow input.

- [ ] **Step 1: Verify final requirements line by line**

Use the master design, each Wave exit criterion, format maturity matrix, dependency budget and performance budget as a checklist. Record any gap instead of assuming completion.

- [ ] **Step 2: Run the full local release sequence**

Use MCP-discovered Blender and Python paths. Run repository tests, optional integration, validate/build, ZIP audit, isolated install, cold real install and release artifact verification.

- [ ] **Step 3: Run read-only release verification**

After an annotated tag and successful package CI exist, dispatch the release workflow with `publish=false`. Publishing remains separately authorized.

- [ ] **Step 4: Create final completion evidence**

Record tag, commit, workflow run, artifact SHA-256, wheel inventory, size, test counts and known limits. Do not claim final completion before this evidence exists.
