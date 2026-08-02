# ChemBlender 2.4.0-rc.1 Preparation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare, qualify and ordinarily integrate the `2.4.0-rc.1` metadata commit without creating a tag or GitHub Release.

**Architecture:** Reuse the manifest-driven release metadata, changelog extractor, prerelease probe, artifact verifier and existing workflows. The only release-state changes are the production manifest version, one dated CHANGELOG entry/link and exact production-state tests.

**Tech Stack:** TOML, Markdown, Python 3.13 standard-library `unittest`, Blender 5.1.2 Extensions and existing GitHub Actions.

## Global Constraints

- Follow `docs/superpowers/specs/2026-08-03-chemblender-2.4.0-release-planning-design.md`.
- Exact version: `2.4.0-rc.1`; intended future tag: `v2.4.0-rc.1`.
- Update manifest and dated CHANGELOG entry in the same implementation commit.
- Preserve Reader API `1.0-rc1`, schemas, dependencies, workflows and runtime code.
- Do not create or push a tag, dispatch `extension-release` or publish a Release.
- Ordinary push/PR/merge authority is provided by the current goal; no rebase,
  force-push, squash or branch deletion.

### Task 0: Activate RC preparation

**Files:**
- Create: `.agents/active/2.4.0-rc1-preparation.md`
- Create: `docs/superpowers/plans/2026-08-03-chemblender-2.4.0-rc1-preparation.md`
- Modify: `tests/test_quantum_visualization_docs.py`

- [x] **Step 1: Record the live release-planning integration evidence**

Record PR #20, exact feature-head runs, ordinary merge SHA, exact merge-SHA
runs and ancestry. Branch from that exact live `origin/main`.

- [x] **Step 2: Activate one recoverable cursor**

Require exactly one active cursor and commit as
`docs: activate 2.4.0 RC preparation`.

### Task 1: Prepare candidate metadata and notes with TDD

**Files:**
- Modify: `ChemBlender/blender_manifest.toml`
- Modify: `CHANGELOG.md`
- Modify: `tests/test_repository_contract.py`
- Modify: `tests/test_release_metadata.py`
- Modify: `tests/test_release_artifact.py`
- Modify: `tests/test_prerelease_probe_script.py`
- Create: `tests/test_240_rc_readiness.py`

**Interfaces:**
- Version: `2.4.0-rc.1`.
- Package: `chemblender-2.4.0-rc.1.zip`.
- Checksum: `chemblender-2.4.0-rc.1.sha256`.
- Artifact: `chemblender-2.4.0-rc.1-windows-x64`.

- [x] **Step 1: Change only the manifest and capture RED**

Run production repository/metadata/readiness tests. Expected failures are old
`2.3.0` production expectations and the missing dated RC entry/link.

- [x] **Step 2: Add the complete RC CHANGELOG entry**

Describe only merged 2.4.0 behavior: deterministic MOL2/PDB/PQR/Cube core and
Project Browser export, explicit loss confirmation/cancellation, frozen public
boundaries, compatibility, known format losses and Final Qualification.

- [x] **Step 3: Update exact production-state tests**

Preserve generic `2.3.0` fixtures. Update only tests that read the production
manifest and add one RC readiness contract for names, notes and boundaries.

- [x] **Step 4: Run focused GREEN and commit**

Run release metadata, notes, artifact, repository, readiness and documentation
tests. Commit as `chore: prepare 2.4.0 release candidate`.

### Task 2: Qualify the candidate locally

**Files:**
- Create: `docs/quantum-visualization/2.4.0/rc1-readiness.md`
- Modify: `.agents/active/2.4.0-rc1-preparation.md`
- Modify: `tests/test_240_rc_readiness.py`

- [x] **Step 1: Run metadata, probe and release-note qualification**

Require exact metadata JSON/channel, native prerelease validation probe, and
byte-preserving production manifest behavior outside the intentional commit.

- [x] **Step 2: Run the full Python gate**

Run complete unittest discovery with the existing pinned dependency site,
`compileall`, generated-document check and `git diff --check`. Do not turn a
failure into a skip.

- [x] **Step 3: Validate/build/audit the committed RC tree**

Use Blender 5.1.2 and the existing pinned wheels. Require native validate and
build, exact ZIP/checksum names, ZIP path/CRC/member audit, dependency/license
inventory, zero unexplained artifact growth and both package/release-assets
verifier modes.

- [x] **Step 4: Run isolated installed-product smoke**

Install the exact RC ZIP under fresh `BLENDER_USER_RESOURCES`, run two
lifecycle cycles and representative MOL2/PDB/PQR/Cube workflows. Record the
package SHA, size, member count and success markers.

### Task 3: Review and checkpoint

**Files:**
- Delete: `.agents/active/2.4.0-rc1-preparation.md`
- Create: `.agents/completed/2.4.0-rc1-preparation.md`
- Modify: `docs/quantum-visualization/2.4.0/rc1-readiness.md`
- Modify: `docs/superpowers/plans/2026-08-03-chemblender-2.4.0-rc1-preparation.md`
- Modify: `tests/test_quantum_visualization_docs.py`

- [x] **Step 1: Run independent reviews**

Require specification-compliance and code-quality/release-safety reviews. Fix
all Critical, Important and task-related Minor findings and rerun affected
gates.

- [x] **Step 2: Freshly rerun the complete local gate**

Re-run focused/full tests, compileall, docs, committed-tree artifact audit,
installed Blender smoke and `git diff --check`.

- [x] **Step 3: Complete the cursor and checkpoint**

Move active to completed and commit as
`chore: checkpoint 2.4.0 release candidate`.

### Task 4: Exact-head remote integration

**Files:**
- No repository changes unless a confirmed CI defect requires a regression fix.

- [ ] **Step 1: Push and create one ready PR**

Push `release/2.4.0-rc.1`, create one ready PR to `main`, and record the exact
checkpoint head.

- [ ] **Step 2: Require exact PR-head CI**

Require all `extension-package` and `optional-qc-core` jobs to succeed for the
exact checkpoint SHA.

- [ ] **Step 3: Merge ordinarily and require exact merge-SHA CI**

Use a normal merge commit, verify ancestry, then require both workflows to
succeed for the exact `origin/main` merge SHA.

## Stop Boundary

Stop after ordinary integration and exact merge-SHA CI. The next operation is
annotated tag creation, which requires separate explicit tag authorization;
no tag, `extension-release` dispatch or GitHub Release belongs to this plan.
