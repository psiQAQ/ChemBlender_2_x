# ChemBlender 2.3.0 Wave 0 Release Task 2 Package Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove every production `2.2.0` artifact name from the package workflow and consume Task 1 metadata outputs instead.

**Architecture:** One early PowerShell step invokes `release_metadata.py`, parses canonical JSON and publishes `version`, `package_name`, `checksum_name` and `artifact_name` through `$GITHUB_OUTPUT`. Every later package lookup, checksum record and upload-artifact field consumes those outputs.

**Tech Stack:** GitHub Actions YAML, PowerShell, Python 3.13, `unittest`.

## Global Constraints

- Baseline: `27fa6304cd6e4b7bd169c4aa1bce53665756c288`.
- Modify only `.github/workflows/extension-package.yml` and its existing repository contract tests.
- Keep all GitHub-owned actions pinned to the existing reviewed full SHAs.
- Do not modify the release workflow, manifest, changelog or metadata helper.
- Do not perform a prerelease probe, create a tag, publish an artifact or push during this task.
- Workflow production code must not contain `chemblender-2.2.0`; fixture tests may.
- Preserve checksum UTF-8 without BOM and LF behavior.

---

### Task 1: Dynamic package metadata outputs

**Files:**
- Modify: `.github/workflows/extension-package.yml`
- Modify: `tests/test_repository_contract.py`

**Interfaces:**
- Consume: `release_metadata.py --extension-root ChemBlender --format json`.
- Produce step outputs: `version`, `package_name`, `checksum_name`, `artifact_name`.

- [ ] **Step 1: Add workflow RED assertions**

Assert the workflow has no `chemblender-2.2.0`, invokes the helper once, writes all four names to `$GITHUB_OUTPUT`, and keeps action pins/permissions/runtime smoke contracts.

- [ ] **Step 2: Run RED**

```powershell
& $pythonBin -m unittest tests.test_repository_contract -v
```

Expected: failures for the hardcoded package/checksum/artifact names and absent metadata step outputs.

- [ ] **Step 3: Add the metadata step**

Use a step ID such as `release_metadata`. Parse helper JSON with `ConvertFrom-Json`; append each exact field to `$env:GITHUB_OUTPUT` using explicit UTF-8 without BOM and LF.

---

### Task 2: Replace every downstream artifact name

**Files:**
- Modify: `.github/workflows/extension-package.yml`
- Modify: `tests/test_repository_contract.py`

**Interfaces:**
- Consume: `${{ steps.release_metadata.outputs.* }}`.

- [ ] **Step 1: Route validation and tag checks**

Use metadata version for changelog extraction and tag matching; do not parse the manifest separately in workflow code.

- [ ] **Step 2: Route build/smoke/checksum**

Require the exact package path from `package_name`, run Blender smoke against it, and write the checksum record using `checksum_name` plus the exact package basename.

- [ ] **Step 3: Route artifact upload**

Use `artifact_name` for upload name and the two exact metadata-derived paths. Preserve `if-no-files-found: error` and current retention for Task 5 to revisit.

- [ ] **Step 4: Run GREEN**

Run repository contract, release metadata, artifact and documentation tests. Confirm the workflow has no `chemblender-2.2.0`.

---

### Task 3: Review and checkpoint

**Files:**
- Modify: `.agents/active/2.3.0-wave-0-platform-foundation.md`
- Modify: this plan

- [ ] **Step 1: Run full static verification**

Run full `unittest`, `compileall` and `git diff --check`. No remote workflow run is expected because the feature-branch push trigger is not configured.

- [ ] **Step 2: Run independent review**

Review expression quoting, PowerShell output encoding, exact-name consumption and action pins. Fix all Critical, Important and task-related Minor findings.

- [ ] **Step 3: Commit and checkpoint**

Implementation commit:

```text
ci: derive package workflow names from metadata
```

Checkpoint next task:

```text
Task 3 — Probe Blender 5.1.2 prerelease manifest support
```

---

## Completion checkpoint

- State: `in_progress`
- Baseline: `27fa6304cd6e4b7bd169c4aa1bce53665756c288`
- Planning commit: pending
- Implementation commit: pending
- RED evidence: `Not Run`
- GREEN evidence: `Not Run`
- Hardcoded production package names: `Present`
- Remote CI: `Not Run`
- Next task: `Task 3 — Probe Blender 5.1.2 prerelease manifest support`
