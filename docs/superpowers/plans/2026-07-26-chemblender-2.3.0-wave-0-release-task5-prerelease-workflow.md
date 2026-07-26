# ChemBlender 2.3.0 Wave 0 Release Task 5 Prerelease Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the deterministic Release workflow classify prerelease tags from shared metadata, publish prereleases without marking them latest, and retain tagged package artifacts long enough for review.

**Architecture:** A small release-channel helper built on the shared parser exposes `final|alpha|beta|rc` plus `is_prerelease` without changing Task 1's canonical metadata JSON. The Release workflow reads exact metadata from the tagged source, selects the matching package run/artifact, and branches only at final publication flags; it never rebuilds.

**Tech Stack:** Python 3.13 standard library, GitHub Actions YAML, Bash, PowerShell, GitHub CLI, `unittest`.

## Global Constraints

- Baseline: `0efa828d6c7e8114d3d66c5e0bb926a7c1b7ce15`.
- Do not modify the production manifest or changelog version/content.
- Do not create a tag, GitHub Release, PR, workflow dispatch or publication.
- Release workflow never rebuilds package artifacts and must select one successful exact-tag run.
- Prerelease publication uses `--prerelease` and never `--latest`.
- Final publication verifies and sets latest exactly as before.
- Only the publish job has `contents: write`; actions stay pinned to full SHAs.
- Task 1 canonical metadata JSON remains byte-compatible for package workflow consumers.

---

### Task 1: Release channel classification

**Files:**
- Modify: `ChemBlender/scripts/release_metadata.py`
- Modify: `tests/test_release_metadata.py`

**Interfaces:**
- Produce: `release_channel_document(version: str) -> dict[str, str | bool]`.
- Output: `{"channel": "final", "is_prerelease": false}` for stable, and the
  exact prerelease channel with `true` otherwise.
- Produce a CLI opt-in that adds these two fields while the existing CLI
  command remains byte-identical.

- [ ] **Step 1: Add classification RED tests**

Cover stable/alpha/beta/rc and invalid versions. Assert the default canonical
CLI bytes from Task 1 do not change.

- [ ] **Step 2: Implement via shared parser**

Do not add a second regex or version split. The new CLI option only merges the
channel document when explicitly requested.

---

### Task 2: Release workflow metadata routing

**Files:**
- Modify: `.github/workflows/extension-release.yml`
- Modify: `tests/test_repository_contract.py`

- [ ] **Step 1: Add release workflow RED assertions**

Require tagged-source metadata helper invocation, exact tag `v<metadata.version>`,
metadata-derived artifact/package/checksum names and channel outputs. Remove
hardcoded release-name construction and the stable-only Bash tag regex.

- [ ] **Step 2: Route verify/publish jobs**

Expose verify job outputs for version, artifact/package/checksum names, channel
and `is_prerelease`. Download and verify the exact existing artifact; never
rebuild.

---

### Task 3: Prerelease-safe publication

**Files:**
- Modify: `.github/workflows/extension-release.yml`
- Modify: `tests/test_repository_contract.py`

- [ ] **Step 1: Add flag-branch RED assertions**

Prerelease branch must create/edit with `--prerelease`, publish the draft
without `--latest`, assert `isPrerelease`, and assert the tag is not the latest
release. Final branch must retain `--latest` and latest-tag verification.

- [ ] **Step 2: Implement one final/prerelease branch**

Keep common draft creation, asset digest verification and notes handling. Only
publication flags and post-publication assertions branch.

---

### Task 4: Tagged artifact retention and documentation

**Files:**
- Modify: `.github/workflows/extension-package.yml`
- Modify: `docs/development/branch-and-release.md`
- Modify: `tests/test_repository_contract.py`

- [ ] **Step 1: Extend retention**

Use 30 days for tag artifacts and retain 14 days for non-tag builds through one
GitHub expression. Document the review window.

- [ ] **Step 2: Document prerelease procedure**

Update tag grammar, CI-to-release table and publication behavior. Explicitly
state prereleases are never latest and publication remains manual.

---

### Task 5: Static verification, review and checkpoint

**Files:**
- Modify: `.agents/active/2.3.0-wave-0-platform-foundation.md`
- Modify: this plan

- [ ] **Step 1: Run focused/full tests**

Run release metadata/repository contract/docs tests, full `unittest`,
`compileall`, workflow hardcode/action-pin audits and `git diff --check`.

- [ ] **Step 2: Independent review**

Review tagged-source trust, exact-run selection, shell quoting, output routing,
permissions, prerelease/latest flags, digest verification and documentation.

- [ ] **Step 3: Commit and checkpoint**

Implementation commit:

```text
ci: make release workflow prerelease aware
```

Remote behavior remains `Not Run`; next task is:

```text
Task 6 — Build the Wave 0 alpha candidate without publishing
```

---

## Completion checkpoint

- State: `in_progress`
- Baseline: `0efa828d6c7e8114d3d66c5e0bb926a7c1b7ce15`
- Planning commit: pending
- Implementation commit: pending
- Prerelease publication static contract: `Not Run`
- Final publication regression: `Not Run`
- Workflow dispatch/publication: `Not Run`
- Remote CI: `Not Run`
- Next task: `Task 6 — Build the Wave 0 alpha candidate without publishing`
