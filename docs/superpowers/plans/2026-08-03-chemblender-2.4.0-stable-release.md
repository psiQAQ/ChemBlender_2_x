# ChemBlender 2.4.0 Stable Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote the published `2.4.0-rc.1` candidate to Stable `2.4.0` with exact local, Git, CI, tag, public-asset and Release-body evidence.

**Architecture:** Reuse the existing manifest-driven metadata, CHANGELOG extractor, package verifier and GitHub workflows. The implementation changes release metadata and evidence only; runtime code, schemas, Reader API, dependencies and workflow definitions remain unchanged.

**Tech Stack:** TOML, Markdown, Python 3.13 standard-library `unittest`, Blender 5.1.2 Extensions, Git and GitHub Actions.

## Global Constraints

- Follow `docs/superpowers/specs/2026-08-03-chemblender-2.4.0-stable-release-design.md`.
- Exact version: `2.4.0`; tag: `v2.4.0`.
- Package: `chemblender-2.4.0.zip`; checksum: `chemblender-2.4.0.sha256`; artifact: `chemblender-2.4.0-windows-x64`.
- Preserve Reader API `1.0-rc1`, sidecar/project schema `1.0`, canonical document `0.1`, dependencies, workflows and runtime source.
- Preserve the published `2.4.0-rc.1` CHANGELOG entry, tag, Release body and assets.
- Use ordinary commits and an ordinary merge commit; no rebase, squash, force-push, tag movement or branch deletion.
- Any required Failed verification blocks merge, tag or publication.

---

### Task 0: Activate Stable preparation

**Files:**
- Create: `.agents/active/2.4.0-stable-release.md`
- Create: `docs/superpowers/plans/2026-08-03-chemblender-2.4.0-stable-release.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Consumes: `origin/main` at the published `v2.4.0-rc.1` commit and the approved Stable design.
- Produces: the sole active goal `CB240-STABLE-RELEASE` on `release/2.4.0`.

- [ ] **Step 1: Record the exact baseline and publication evidence**

Record main/tag ancestry, exact-tag package run `30770885098`, verification-only
run `30771253311`, publication run `30772029322`, public Release URL and public
asset hashes from the approved design. Record that Issues and Discussions are
disabled, no PR is open and no blocker was reported.

- [ ] **Step 2: Verify the plan and cursor**

Run:

```powershell
& $pythonBin -m unittest tests.test_quantum_visualization_docs -v
& $pythonBin -m compileall -q ChemBlender worker tests
git diff --check
```

- [ ] **Step 3: Commit activation**

```powershell
git add .agents/active/2.4.0-stable-release.md docs/superpowers/plans/2026-08-03-chemblender-2.4.0-stable-release.md tests/test_quantum_visualization_docs.py
git commit -m "docs: activate stable 2.4.0 release"
```

### Task 1: Prepare Stable metadata, notes and feedback record with TDD

**Files:**
- Create: `tests/test_240_release_readiness.py`
- Create: `docs/quantum-visualization/2.4.0/rc1-feedback-review.md`
- Modify: `ChemBlender/blender_manifest.toml`
- Modify: `CHANGELOG.md`
- Modify: `tests/test_240_rc_readiness.py`
- Modify: `tests/test_repository_contract.py`
- Modify: `tests/test_release_metadata.py`
- Modify: `tests/test_release_artifact.py`

**Interfaces:**
- Consumes: existing `read_release_metadata()` and `extract_release_notes()`.
- Produces: production metadata `2.4.0`, stable package names and a checked feedback-review record; it adds no runtime API.

- [ ] **Step 1: Write the Stable contract before production changes**

Create `tests/test_240_release_readiness.py` with assertions that current
metadata is `2.4.0`, package/checksum/artifact names are exact, Stable notes
contain `### Changed`, `### Compatibility`, `### Known Limitations` and
`### Verification`, the RC entry/link remains present, `[Unreleased]` compares
from `v2.4.0`, and the feedback/readiness documents exist.

- [ ] **Step 2: Run RED and record the exact failures**

```powershell
& $pythonBin -m unittest tests.test_240_release_readiness -v
```

Expected: fail because production metadata is `2.4.0-rc.1` and the Stable
entry, links and evidence documents do not exist.

- [ ] **Step 3: Apply the minimal Stable metadata and notes change**

Change only the manifest version. Add one dated `2.4.0` CHANGELOG entry that
states promotion from the qualified RC, unchanged product/API/schema/dependency
scope, retained known limitations and verification boundary. Add exact Stable
compare/release links without altering the RC entry.

- [ ] **Step 4: Preserve RC readiness as historical evidence**

Change `tests/test_240_rc_readiness.py` so it checks the immutable published RC
entry and readiness evidence without requiring current production metadata to
remain prerelease. Add `rc1-feedback-review.md` containing the exact RC tag,
runs, Release URL, public hashes, issue/discussion/PR audit and blocker result.

- [ ] **Step 5: Update only production-state assertions**

Update exact production expectations in repository/metadata/artifact tests to
`2.4.0` and Stable filenames. Preserve generic prerelease fixtures and tag
mismatch coverage.

- [ ] **Step 6: Run GREEN and commit**

```powershell
& $pythonBin -m unittest tests.test_240_release_readiness tests.test_240_rc_readiness tests.test_release_metadata tests.test_release_artifact tests.test_release_notes tests.test_repository_contract -v
git diff --check
git add ChemBlender/blender_manifest.toml CHANGELOG.md docs/quantum-visualization/2.4.0/rc1-feedback-review.md tests/test_240_release_readiness.py tests/test_240_rc_readiness.py tests/test_release_metadata.py tests/test_release_artifact.py tests/test_repository_contract.py
git commit -m "chore: prepare stable 2.4.0 release"
```

### Task 2: Qualify the committed Stable tree

**Files:**
- Create: `docs/quantum-visualization/2.4.0/stable-readiness.md`
- Modify: `.agents/active/2.4.0-stable-release.md`
- Modify: `tests/test_240_release_readiness.py`

**Interfaces:**
- Consumes: committed Stable metadata tree.
- Produces: reproducible local release evidence with exact package identity.

- [ ] **Step 1: Run focused and full Python gates**

Run focused Stable/release/document tests, then:

```powershell
& $pythonBin -m unittest discover -s tests -p "test_*.py" -v
& $pythonBin -m compileall -q ChemBlender worker tests
git diff --check
```

Record passed/skipped/failed counts; do not convert failures into skips.

- [ ] **Step 2: Validate, build and audit with Blender 5.1.2**

Run the existing native preflight, Extension validate/build, exact ZIP name,
CRC/path/type/member inventory, dependency/license inventory and artifact-size
budget. Run both package-CI and release-assets verifier modes against the built
Stable package and checksum.

- [ ] **Step 3: Verify the installed product**

Install the exact Stable ZIP under a fresh `BLENDER_USER_RESOURCES`, run two
register/unregister/reload cycles and representative MOL2/PDB/PQR/Cube Project
Browser workflows. Run the stable manifest probe; do not reuse the RC install.

- [ ] **Step 4: Record exact readiness and test it**

Write `stable-readiness.md` with the actual package SHA, checksum SHA, size,
member count, Python results, Blender results and `Remote CI: Not Run` boundary.
Extend the Stable readiness test to require those exact values, rerun it, then
commit as `docs: record stable 2.4.0 local qualification`.

### Task 3: Review and checkpoint Stable preparation

**Files:**
- Delete: `.agents/active/2.4.0-stable-release.md`
- Create: `.agents/completed/2.4.0-stable-release.md`
- Modify: `docs/superpowers/plans/2026-08-03-chemblender-2.4.0-stable-release.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Consumes: verified Stable metadata and local qualification evidence.
- Produces: a clean checkpoint suitable for one ready PR.

- [ ] **Step 1: Review scope and release safety**

Confirm the diff contains no runtime, schema, dependency, wheel, workflow or RC
entry modification. Review every design requirement and all release-sensitive
tests; fix task-related findings only.

- [ ] **Step 2: Rerun the complete local gate freshly**

Rerun focused/full tests, compileall, native validate/build, ZIP/verifier audit,
isolated installed-product smoke and `git diff --check` from the committed tree.

- [ ] **Step 3: Complete and commit the cursor**

Move the active cursor to completed, mark Tasks 0-3 complete and commit as
`chore: checkpoint stable 2.4.0 release`.

### Task 4: Integrate, tag and publish Stable

**Files:**
- No repository changes before public evidence exists.

**Interfaces:**
- Consumes: the clean Stable checkpoint SHA.
- Produces: ordinary main integration, annotated `v2.4.0`, exact CI and public non-prerelease Release.

- [ ] **Step 1: Push and create one ready PR**

Push `release/2.4.0`, open one ready PR to `main`, and record its exact head SHA.
Require `extension-package` and `optional-qc-core` success for that exact SHA.

- [ ] **Step 2: Merge ordinarily and verify the merge SHA**

Use a normal merge commit, fetch, prove the checkpoint is an ancestor of
`origin/main`, and require both workflows for the exact merge commit.

- [ ] **Step 3: Create the annotated Stable tag and require tag CI**

Create annotated `v2.4.0` at the exact merge commit, push only the tag, and
require exact-tag `extension-package` success including installed-runtime
evidence. Never move or recreate a published tag.

- [ ] **Step 4: Verify then publish through the existing workflow**

Dispatch `extension-release` for `v2.4.0` with `publish=false` and require a
successful verification job with publication skipped. Then dispatch the same
tag with `publish=true` and require a successful non-prerelease publication.

- [ ] **Step 5: Independently verify the public Release**

Download both public assets to a fresh temporary directory. Verify checksum,
ZIP inventory and release-assets mode; extract tagged CHANGELOG notes and
require byte-identical public Release body. Record Release/run URLs and IDs.

### Task 5: Record post-release evidence and close the roadmap

**Files:**
- Modify: `.agents/completed/2.4.0-stable-release.md`
- Modify: `docs/quantum-visualization/2.4.0/stable-readiness.md`
- Modify: `docs/superpowers/plans/2026-08-03-chemblender-2.4.0-stable-release.md`

**Interfaces:**
- Consumes: public Stable Release and exact run evidence.
- Produces: final durable evidence and a verified audit of remaining plans.

- [ ] **Step 1: Add exact public evidence**

Record PR, checkpoint/merge/tag object and peeled SHAs, exact PR/merge/tag CI,
verification/publication runs, Release URL/ID, public asset hashes, body match
and ancestry.

- [ ] **Step 2: Audit all plan states**

Inspect `.agents/active/`, `.agents/queued/`, roadmap entrypoints and unchecked
implementation-plan boxes. Distinguish historical unmarked remote steps from
approved unfinished product work; do not invent work merely to satisfy old
checkboxes whose final state is already evidenced elsewhere.

- [ ] **Step 3: Commit the post-release checkpoint**

Run documentation contracts and `git diff --check`, then commit the evidence
as `chore: record stable 2.4.0 release evidence` on a focused post-release
branch and integrate it through an ordinary PR with exact-head CI.

## Stop Boundary

The release is complete only after the public non-prerelease `v2.4.0` Release,
independent asset/body verification and integrated post-release evidence. Close
the persistent project-plan goal only when the final audit finds no approved
unfinished plan.
