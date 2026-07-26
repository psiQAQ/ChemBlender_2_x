# ChemBlender 2.3.0 Wave 0 Release Task 6 Alpha Candidate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Produce a locally verified, CI-ready `2.3.0-alpha.1` extension
candidate without creating a tag, GitHub Release or remote publication.

**Architecture:** Change only the release metadata already consumed by the
shared release helpers: the production manifest version and one dated
changelog entry. Update exact production-version tests to the new intentional
state; do not add another version source or change runtime behavior.

**Tech Stack:** TOML, Markdown, Python 3.13 standard library, Blender 5.1.2
extension CLI and background runtime, `unittest`.

## Global Constraints

- Baseline: `49443a18232db1e80a717691b37f7f7f3ed870f2`.
- Exact version: `2.3.0-alpha.1`.
- Keep the existing tagline; Wave 4 owns any unapproved product copy change.
- Do not modify GitHub Actions, dependencies or runtime feature code.
- Do not create a PR, tag, workflow dispatch or GitHub Release.
- Build and verification artifacts remain ignored local outputs.
- Push only after Task 6 checkpoint and the final whole-branch gate pass.

---

### Task 1: Candidate metadata and release-note contract

**Files:**
- Modify: `ChemBlender/blender_manifest.toml`
- Modify: `CHANGELOG.md`
- Modify: `tests/test_repository_contract.py`
- Modify: `tests/test_release_metadata.py`
- Modify: `tests/test_release_artifact.py`

**Interfaces:**
- Manifest `version`: `2.3.0-alpha.1`.
- Changelog section: `## [2.3.0-alpha.1] - 2026-07-26`.
- Shared metadata names:
  `chemblender-2.3.0-alpha.1.zip`,
  `chemblender-2.3.0-alpha.1.sha256`,
  `chemblender-2.3.0-alpha.1-windows-x64`.

- [ ] **Step 1: Record RED from exact production contracts**

Run the production manifest, metadata CLI and artifact tests immediately after
the manifest bump. Expected RED: assertions still require stable `2.2.0`
metadata/tag/name bytes.

- [ ] **Step 2: Add the complete dated alpha entry**

Move the release-workflow bullets currently under `Unreleased` into the alpha
entry and describe only verified Wave 0 platform-foundation behavior:
authoritative project/session persistence, transactional import/link recovery,
explicit registration/import UI, format-aware default views and durable derived
view caches. Keep `Unreleased` present and empty.

- [ ] **Step 3: Update exact production-state tests**

Change only tests whose fixture is the live production manifest. Preserve
stable-version unit fixtures that intentionally exercise `2.2.0`.

**Minimal implementation:** one manifest value, one changelog section/link and
the exact expected production strings/tags in existing tests.

**Focused verification:** release metadata, artifact, release-notes,
repository-contract and extension-validator modules.

**Blender verification:** native extension validate must accept the exact alpha
manifest before the candidate metadata commit.

**Commit boundary:** candidate metadata is committed only after all local gates.

**Stop boundary:** no tag, Release or remote publication.

---

### Task 2: Deterministic candidate build and artifact verification

**Files:**
- No tracked source changes expected.
- Local ignored outputs only:
  `ChemBlender/chemblender-2.3.0-alpha.1.zip`,
  a temporary artifact directory and checksum.

**Interfaces:**
- `release_metadata.py --include-channel` reports `alpha` and
  `is_prerelease=true`.
- `build_extension.py` produces the exact metadata-derived ZIP.
- `verify_release_artifact.py` verifies tag `v2.3.0-alpha.1`.

- [ ] **Step 1: Run native validate and build**

Use Blender 5.1.2 and its bundled Python. Confirm exact output name and audit
ZIP paths, CRC, required assets, the single pinned RDKit wheel and packaged
manifest equality.

- [ ] **Step 2: Verify checksum fixture**

Create the checksum only in a temporary artifact directory, run the production
artifact verifier, and record ZIP SHA-256 and byte size.

**Minimal implementation:** reuse Task 1–5 scripts; no new build code.

**Focused verification:** exact CLI JSON/channel, package name, checksum line,
artifact document and ZIP inventory.

**Blender verification:** native validate/build.

**Commit boundary:** none; outputs are evidence, not tracked content.

**Stop boundary:** do not upload artifacts.

---

### Task 3: Real Blender candidate lifecycle

**Files:**
- No tracked source changes expected.

**Interfaces:**
- Installs the exact alpha ZIP into an isolated `user_default` repository.
- Exercises the existing `tests/blender_smoke.py` product/lifecycle contract.

- [ ] **Step 1: Isolated install and lifecycle**

Run background Blender with a temporary short `BLENDER_USER_RESOURCES`,
default Windows TEMP/TMP where applicable, `--factory-startup`,
`--python-exit-code 1`, and the exact alpha ZIP.

- [ ] **Step 2: Runtime and package audit**

Require register/unregister/reload, RDKit import, packaged `.blend` assets and
the product/session smoke sentinels already implemented by the repository.

**Minimal implementation:** reuse the existing smoke harness.

**Focused verification:** smoke exit code and explicit success sentinel.

**Blender verification:** Blender 5.1.2 real extension install/runtime.

**Commit boundary:** none.

**Stop boundary:** do not overwrite a loaded interactive installation.

---

### Task 4: Full regression, independent review and checkpoint

**Files:**
- Modify: `.agents/active/2.3.0-wave-0-platform-foundation.md`
- Modify: this plan

- [ ] **Step 1: Run the full local gate**

Run all `unittest` tests, `compileall`, `git diff --check`, manifest/changelog
hash capture, release-notes extraction, validate/build, ZIP audit, artifact
verification and isolated Blender smoke.

- [ ] **Step 2: Independent specification and code-quality review**

Review the exact version, complete alpha notes, unchanged tagline, dynamic
names, packaged manifest, prerelease channel, artifact provenance and explicit
non-publication boundary. Fix all in-scope findings and rerun affected gates.

- [ ] **Step 3: Commit candidate metadata and checkpoint**

Implementation commit:

```text
chore: prepare 2.3.0 alpha candidate
```

Checkpoint commit:

```text
chore: checkpoint Wave 0 alpha candidate
```

**Minimal implementation:** no runtime/workflow changes.

**Focused verification:** all candidate metadata and release tests.

**Blender verification:** validate/build/isolated lifecycle.

**Commit boundary:** metadata/tests first, cursor/plan second.

**Stop boundary:** Task 6 completes without tag or Release; final branch review
and the user-authorized branch push follow as a separate gate.

---

## Completion checkpoint

- State: `in_progress`
- Baseline: `49443a18232db1e80a717691b37f7f7f3ed870f2`
- Planning commit: pending
- Implementation commit: pending
- Checkpoint commit: pending
- Exact alpha version: `Not Run`
- Full tests: `Not Run`
- Blender validate/build: `Not Run`
- Isolated lifecycle: `Not Run`
- Artifact verification: `Not Run`
- Tag/Release/workflow dispatch: `Not Run`
- Remote CI: `Not Run`
- Next gate: final whole-branch review, verification and authorized push
