# ChemBlender 2.3.0 Wave 4 CI, Dependency and Release Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split CI by responsibility, ensure real optional integrations do not silently skip, enforce wheel/license/artifact budgets, and make pre-release/final publication use the exact verified artifact.

**Architecture:** Native core, optional scientific core, Blender package and release contract are separate jobs/workflows with explicit dependencies. Metadata comes from one helper. Tag artifacts include package, checksum, size inventory, wheel inventory, licenses and test summary.

**Tech Stack:** GitHub Actions, PowerShell, Bash, Python 3.13, Blender 5.1.2, standard-library tests and GitHub CLI.

## Global Constraints

- Full SHA pins for GitHub-owned actions.
- Routine jobs remain read-only.
- Only authorized publish job gets `contents: write`.
- Release workflow never rebuilds.
- Target optional integration tests cannot skip in their dedicated job.
- Wheels are downloaded from pinned sources and hash-verified; no wheel is committed.
- Final artifacts are derived from exact annotated tag runs.

---

### Task 1: Create machine-readable dependency and license inventory

**Files:**
- Create: `ChemBlender/dependencies.toml`
- Create: `ChemBlender/scripts/dependency_inventory.py`
- Create: `tests/test_dependency_inventory.py`
- Modify: `.agents/reference/dependencies-and-release.md`

**Interfaces:**
- Produces: canonical dependency inventory and generated `wheel-inventory.json`/license copy list.

- [ ] **Step 1: Define inventory schema**

Each dependency records distribution, version, filename, platform, Python ABI, URL, SHA-256, SPDX license, license source path, required/optional boundary and approved size budget. Include RDKit and Gemmi.

- [ ] **Step 2: Write schema and manifest consistency tests**

Manifest wheel paths exactly equal required wheel filenames. Every required wheel has URL/SHA/license. Optional external packages do not appear in manifest wheels.

- [ ] **Step 3: Implement inventory CLI**

After wheels download, verify file hashes, measure compressed/unpacked bytes safely and emit canonical JSON. Reject archive path traversal while measuring.

- [ ] **Step 4: Run and commit**

Commit inventory, script, tests and updated reference.

### Task 2: Split native core CI from Blender package CI

**Files:**
- Create: `.github/workflows/native-core.yml` or refactor existing package workflow into jobs
- Modify: `.github/workflows/extension-package.yml`
- Create/modify workflow contract tests
- Modify: `docs/development/testing-and-ci.md`

**Interfaces:**
- Produces: fast native test feedback and a package job that depends on native success.

- [ ] **Step 1: Add workflow tests**

Assert native job runs unit/compile/docs/format fixtures without downloading Blender. Package job downloads Blender/wheels, builds and installs, and uses `needs` or separate required checks.

- [ ] **Step 2: Implement native job**

Run standard-library tests that require only base source; install no runtime packages beyond actions/setup-python. If Gemmi/RDKit reader tests require wheels, either use the downloaded approved wheels in a separate native-base job or keep them in Blender package job; the split must be documented.

- [ ] **Step 3: Keep authoritative artifact in Blender job**

Only the job that passed validate/build/isolated install/cold install uploads release package.

- [ ] **Step 4: Verify and commit**

Run local contract tests. Push/PR CI remains separately authorized. Commit workflows/docs/tests.

### Task 3: Add optional quantum-core integration CI with zero targeted skips

**Files:**
- Create: `.github/workflows/optional-qc-core.yml`
- Create: `ChemBlender/scripts/run_required_integration.py`
- Create: `tests/test_required_integration_runner.py`
- Modify: optional adapter test modules as needed

**Interfaces:**
- Produces: pinned cclib/IOData/GBasis integration jobs and a skip-enforcing runner.

- [ ] **Step 1: Implement the runner**

Run selected unittest module names and capture result counts. If any test in a required module is skipped, return nonzero with skipped test IDs. Ordinary unrelated optional tests may remain outside the required list.

- [ ] **Step 2: Define pinned environments**

Use the dependency reference versions and submodule commits. Initialize only required submodules or install pinned distributions in an isolated Python matching each backend. GBasis uses its supported Python 3.12/NumPy 1.26 environment, separate from Blender 3.13.

- [ ] **Step 3: Add fixture integrity**

Verify submodule/fixture commit and expected file hashes before tests. Do not treat missing fixtures as skip/success.

- [ ] **Step 4: Upload test summary**

Artifact contains versions, test pass/fail/skip counts and fixture hashes; no large upstream source archive.

- [ ] **Step 5: Verify and commit**

Run runner unit tests and commit workflow/script/docs.

### Task 4: Enforce artifact size and license budgets

**Files:**
- Create: `ChemBlender/scripts/artifact_size_report.py`
- Create: `tests/test_artifact_size_report.py`
- Modify: `.github/workflows/extension-package.yml`
- Modify: `ChemBlender/scripts/verify_release_artifact.py`

**Interfaces:**
- Produces: `artifact-size.json`, baseline comparison and license verification.

- [ ] **Step 1: Write deterministic report tests**

Use small ZIP fixtures with wheels/resources. Assert per-section totals, no double counting, safe paths and comparison to a supplied baseline JSON.

- [ ] **Step 2: Implement budget config**

Read limits from `dependencies.toml` or a dedicated versioned JSON, not workflow literals. Existing RDKit is excluded from new-wheel allowance but included in total artifact report.

- [ ] **Step 3: Add package job steps**

Generate size and wheel inventory, verify license files included as required, then upload alongside ZIP/checksum. Failure occurs before artifact upload for unexplained budget breach.

- [ ] **Step 4: Extend release verification**

Download and verify all metadata artifacts and compare package digest/inventory. Release assets may remain ZIP/checksum only, but verification records inventory; policy decides whether to publish inventory assets.

- [ ] **Step 5: Run and commit**

Run report/artifact tests and commit.

### Task 5: Harden prerelease/final workflow and exact-run selection

**Files:**
- Modify: `.github/workflows/extension-release.yml`
- Modify: `ChemBlender/scripts/release_metadata.py`
- Modify: workflow tests
- Modify: `docs/development/branch-and-release.md`

**Interfaces:**
- Produces: alpha/beta/rc pre-release publication and final latest publication.

- [ ] **Step 1: Validate exact tag/channel**

Tag and manifest version follow the Wave 0 proven scheme. Tag commit must be in origin/main, annotated and have exactly one successful exact-SHA package run with expected artifact name.

- [ ] **Step 2: Verify all artifact members**

Release verify downloads package/checksum/size/wheel/test summary and runs artifact verification against tag source. Root and tag changelog entries must match.

- [ ] **Step 3: Publish behavior**

Create draft, upload assets, compare GitHub asset digests, then publish. For prerelease set prerelease true and latest false. For final set prerelease false and latest after verification.

- [ ] **Step 4: Idempotency**

Existing release causes a controlled refusal unless a separate user-approved repair mode is designed; workflow never edits an existing release silently.

- [ ] **Step 5: Dry-run and commit**

Run static/unit tests and dispatch `publish=false` only when an exact tag artifact exists and user permits. Commit evidence/doc changes.

### Task 6: Add branch protection and required-check documentation

**Files:**
- Modify: `docs/development/branch-and-release.md`
- Modify: `.agents/reference/branch-architecture.md`
- Create: `docs/development/2.3.0-required-checks.md`

**Interfaces:**
- Produces: named required checks and failure ownership.

- [ ] **Step 1: List checks**

Document native core, optional core, package/install, docs/contracts and release dry-run responsibilities. Specify which changes require optional job.

- [ ] **Step 2: Do not change repository settings without authorization**

Provide exact recommended branch protection names but leave actual settings change for an authorized GitHub operation.

- [ ] **Step 3: Verify docs and commit**

Run links/no-BOM tests and commit.
