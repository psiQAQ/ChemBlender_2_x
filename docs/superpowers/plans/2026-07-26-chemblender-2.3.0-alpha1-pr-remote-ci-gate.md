# ChemBlender 2.3.0 Alpha.1 PR Remote CI Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a draft Wave 0 PR, obtain green `extension-package` PR CI, and independently verify the exact final-HEAD artifact without merging, tagging, dispatching the Release workflow, or creating a Release.

**Architecture:** Keep release identity derived from `release_metadata.py`, add one fail-closed default-branch guard at the start of the Release workflow, and preserve the package workflow unchanged. Treat the PR run and its downloaded artifact as remote evidence tied to one exact PR HEAD, then persist that evidence before a final checkpoint push and CI rerun.

**Tech Stack:** Python 3.13 `unittest`, PowerShell, Bash, GitHub Actions, GitHub CLI, Blender 5.1.2.

## Global Constraints

- Work only on `feat/2.3.0-wave0-platform-foundation`.
- Push only the current feature branch; never push `main` or a tag.
- Do not merge the PR, create a tag, dispatch `extension-release.yml`, create a GitHub Release, or enter Wave 1–4.
- Do not modify `ChemBlender/blender_manifest.toml` or the version content in `CHANGELOG.md`.
- Preserve the reviewed 179-commit history; do not reset, rebase, force-push, or alter remotes.
- Keep `.github/workflows/extension-package.yml` byte-identical.
- Remote evidence is valid only when the run `event`, `headSha`, workflow, and conclusion match the final PR HEAD.

---

### Task 1: Public Documentation and Privacy Hygiene

**Files:**
- Modify: `docs/development/branch-and-release.md`
- Modify: `docs/development/2.3.0-prerelease-version-probe.md`
- Modify: `.agents/active/2.3.0-wave-0-platform-foundation.md`

**Goal:** Remove stale release-version literals and personal local paths while preserving exact technical evidence.

**RED or audit evidence:**
- `docs/development/branch-and-release.md` contains `$version = '2.2.0'`.
- Tracked agent/probe Markdown contains `C:\Users\ustcw` and exact random temporary paths.
- The active cursor records externally reviewed HEAD `97bb15f9...`.

**Implementation:**
- Replace the fixed version with one `release_metadata.py --format json` call, validate `$LASTEXITCODE`, and consume `version`, `package_name`, `checksum_name`, and `artifact_name` from the returned object.
- Add the `2.3.0-alpha.1` current-version boundary.
- Redact local usernames/random tokens to `%APPDATA%`, `%LOCALAPPDATA%\Temp\chemblender-prerelease-probe-<random>`, and `<repository-worktree>` forms.
- Preserve Blender version, command structure, exit code, stdout/stderr semantics, hashes, and cleanup result.
- Set the reviewed baseline to `8f8234fc1617c8bb9f07608d9b3a6195bd46dc5b`.

**Verification:**
- Run an ordinal tracked-text scan for `C:\Users\ustcw`.
- Run `python -m unittest tests.test_repository_contract tests.test_quantum_visualization_docs -v`.
- Confirm the manifest and changelog version bytes are unchanged.

**Commit boundary:** Fold into `docs: harden alpha release handoff` after Task 2 is green.

**Remote evidence:** None; this task is local documentation hygiene.

**Stop boundary:** Do not push until Tasks 1–3 and both independent reviews pass.

### Task 2: Default-Branch Release Workflow Dispatch Guard

**Files:**
- Modify: `.github/workflows/extension-release.yml`
- Modify: `tests/test_repository_contract.py`
- Modify: `docs/development/branch-and-release.md`

**Goal:** Reject `workflow_dispatch` runs whose workflow ref is not the repository default branch.

**RED or audit evidence:**
- Add a repository-contract test requiring the guard before checkout, tag lookup, package-run lookup, artifact access, or any Release command.
- Add assertions that both documented dispatch commands use `--ref main`.
- Run `python -m unittest tests.test_repository_contract.RepositoryContractTests.test_release_workflow_requires_default_branch_dispatch_ref tests.test_repository_contract.RepositoryContractTests.test_release_documentation_dispatches_release_workflow_from_main -v`; expect both tests to fail because the guard and `--ref main` are absent.

**Implementation:**
- Add one first verify-job step named `Require default-branch workflow ref`.
- Compare `${{ github.ref }}` with `refs/heads/${{ github.event.repository.default_branch }}` and exit nonzero on mismatch.
- Add `--ref main` to both documented `publish=false` and `publish=true` commands.
- Do not change `.github/workflows/extension-package.yml`, workflow permissions, or publish-job ownership.

**Verification:**
- Re-run the two RED tests and all `tests.test_repository_contract`.
- Extract every `shell: bash` run block from the workflow and run `bash -n`.
- Confirm every GitHub-owned action remains pinned to a 40-character SHA.
- Confirm `publish=false` remains read-only and `publish` is the only `contents: write` owner.

**Commit boundary:** `docs: harden alpha release handoff`.

**Remote evidence:** The later draft-PR run must parse and execute the guarded workflow files without affecting package CI.

**Stop boundary:** Never dispatch `extension-release.yml` in this goal.

### Task 3: Local Final Regression

**Files:**
- Verify only; do not add generated packages, checksums, wheels, caches, or temporary profiles to Git.

**Goal:** Prove the PR handoff tree remains a valid alpha.1 source/package/runtime candidate.

**RED or audit evidence:**
- Record the focused pre-change failures from Task 2 and the audit findings from Task 1.

**Implementation:**
- Run the specified focused release-contract modules and the full unit-test suite.
- Run `compileall`, `git diff --check`, release metadata CLI, native Blender 5.1.2 validate/build, ZIP audit, artifact verifier, and isolated lifecycle.
- Record the newly built package size and SHA as local-only evidence.

**Verification:**
- Focused release tests: zero failures.
- Full `unittest` discovery: zero failures, with exact passed/skipped counts recorded.
- Blender validate/build and isolated lifecycle: exit 0.
- ZIP inventory/CRC and artifact verifier: pass.
- Production manifest hash and changelog version content: unchanged.

**Commit boundary:** Verification precedes `docs: harden alpha release handoff`; generated artifacts remain untracked/ignored.

**Remote evidence:** None yet; local evidence must not be described as remote CI.

**Stop boundary:** Do not create/update the PR until the commit is locally verified and reviewed.

### Task 4: Independent Review and Draft PR Creation

**Files:**
- Review the diff from `8f8234fc1617c8bb9f07608d9b3a6195bd46dc5b` through the hygiene/workflow commit.

**Goal:** Obtain independent specification and code-quality approval, push the feature branch, and create or update one draft PR to `main`.

**RED or audit evidence:**
- Independent reviewers report every Critical, Important, and gate-related Minor finding.

**Implementation:**
- Fix valid findings with focused tests and repeat both reviews until approved.
- Push the feature branch without force.
- Query matching head/base PRs; create one draft PR only if none exists.
- Use title `feat: prepare ChemBlender 2.3.0-alpha.1 platform foundation`.
- Include exact local verification, local-only package hash, pending remote gates, known RDKit cleanup warning, and merge-history policy.

**Verification:**
- `gh pr view` reports base `main`, exact feature head, `isDraft=true`, and expected title/body.
- Remote tag `v2.3.0-alpha.1` and GitHub Release remain absent.

**Commit boundary:** Review fixes, if any, use separate focused commits before the initial PR push.

**Remote evidence:** Record PR number, URL, and initial head SHA.

**Stop boundary:** Keep the PR draft and unmerged.

### Task 5: Remote Package CI Diagnosis and Repair Loop

**Files:**
- Modify only files proven necessary by a deterministic failing PR check.

**Goal:** Make every check on the current PR HEAD green without weakening any gate.

**RED or audit evidence:**
- For each failure, capture run ID, job, failing step, and complete relevant log before editing.

**Implementation:**
- Watch `gh pr checks <PR> --watch --interval 20`.
- On failure, invoke `superpowers:systematic-debugging`, prove root cause, write a focused regression test, implement the smallest fix, run focused/full local verification, commit, and push.
- Repeat against the new PR HEAD; never rerun a deterministic failure to hide it.

**Verification:**
- `gh pr checks <PR>` exits 0 for the exact current head.
- The successful `extension-package` run has `event=pull_request`, `headSha=<current PR head>`, and `conclusion=success`.

**Commit boundary:** One focused commit per independently proven CI fix.

**Remote evidence:** Record all CI-fix commits or `none`, final successful run ID, URL, jobs, and conclusions.

**Stop boundary:** Do not merge, tag, or dispatch any workflow.

### Task 6: PR Artifact Download and Independent Verification

**Files:**
- Local ignored cache only: `.agents/cache/alpha1-pr-artifact/`

**Goal:** Independently verify the exact artifact produced by the final successful PR-head package run.

**RED or audit evidence:**
- Reject any run whose event, head SHA, workflow, or conclusion differs from the final PR head contract.

**Implementation:**
- Read version/package/checksum/artifact names from `release_metadata.py`.
- Query the exact run and require one unexpired artifact with the metadata-derived name.
- Download it to `.agents/cache/alpha1-pr-artifact/`.
- Run `verify_release_artifact.py --tag v2.3.0-alpha.1`.
- Inspect ZIP CRC/entry count and compute package/checksum SHA-256.
- Add one PR evidence comment stating PR CI is green, the artifact was independently verified, and main/tag/release gates remain unrun.

**Verification:**
- Artifact verifier exits 0.
- Artifact contains exactly the metadata-derived ZIP and checksum.
- Record artifact ID/name, package size/SHA-256, checksum SHA-256, ZIP entry count, and Blender job conclusion.

**Commit boundary:** No source commit; evidence is persisted in Task 7.

**Remote evidence:** Exact final-HEAD run/artifact values and the verified PR comment.

**Stop boundary:** Treat this as PR evidence only, never as the final Release artifact.

### Task 7: Remote Checkpoint and Final Stop Boundary

**Files:**
- Modify: `.agents/active/2.3.0-wave-0-platform-foundation.md`
- Modify: `docs/superpowers/plans/2026-07-26-chemblender-2.3.0-alpha1-pr-remote-ci-gate.md`

**Goal:** Persist the exact final remote evidence, push the checkpoint, and prove the new final PR HEAD is green.

**RED or audit evidence:**
- The checkpoint push changes the PR HEAD, so all earlier green checks become evidence for the previous head only.

**Implementation:**
- Record planning/hygiene/CI-fix commits, PR URL, exact remote run/artifact evidence, local suite counts, and explicit Not Run/Not Created states.
- Mark all plan tasks complete and the cursor `completed`.
- Commit `chore: checkpoint alpha PR remote CI gate` and push only the feature branch.
- Wait for checks on the checkpoint commit and independently verify the checkpoint-head artifact again if the workflow produces a new artifact.

**Verification:**
- Local/remote feature refs equal the checkpoint SHA.
- Final checkpoint HEAD PR checks are all green.
- Final checkpoint-head artifact verifier exits 0 and its evidence replaces prior-head evidence.
- Worktree is clean.
- `main` is unchanged; no tag, workflow dispatch, or GitHub Release exists.

**Commit boundary:** `chore: checkpoint alpha PR remote CI gate`.

**Remote evidence:** Final PR HEAD, final package run ID/URL, artifact ID/name, hashes, verifier result, and PR comment.

**Stop boundary:** Stop with the draft PR unmerged. The next action requires explicit authorization to merge the reviewed PR.
