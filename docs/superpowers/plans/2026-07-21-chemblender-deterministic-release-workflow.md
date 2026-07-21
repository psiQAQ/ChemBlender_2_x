# Deterministic Extension Release Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a manual, deterministic workflow that publishes only the exact successful tag CI artifact after checksum and package-contract verification.

**Architecture:** A standard-library validator owns the artifact contract. A read-only workflow job resolves and verifies the tag CI run; a conditional `release`-environment job downloads the same artifact again, creates a draft, verifies GitHub asset digests, and publishes it.

**Tech Stack:** GitHub Actions, GitHub CLI, Bash, Python 3 standard library, `unittest`.

## Global Constraints

- Keep `.github/workflows/extension-package.yml` read-only and unchanged.
- Add no dependency and use only Python's standard library in the validator.
- Require an annotated `vMAJOR.MINOR.PATCH` tag contained in `origin/main`.
- Bind Release assets to the successful `extension-package` run with the same tag and exact commit SHA.
- Keep publication off by default; use job-level `contents: write` only in the conditional publish job.
- Create a draft, verify asset SHA-256 digests, and publish only after those checks pass.
- Pin every GitHub Action to a reviewed full commit SHA.
- Do not push, dispatch the workflow, or publish a Release without explicit authorization.

---

### Task 1: Release artifact validator

**Files:**
- Create: `ChemBlender/scripts/verify_release_artifact.py`
- Create: `tests/test_release_artifact.py`

**Interfaces:**
- Consumes: artifact directory, extension source root, and `vMAJOR.MINOR.PATCH` tag.
- Produces: `verify_artifact(artifact_dir: Path, extension_root: Path, tag: str) -> dict[str, str]` and a zero/nonzero CLI.

- [x] **Step 1: Write the failing tests**

Create temporary artifacts with the real manifest plus placeholder license, wheel, and `.blend` entries. Assert that a valid pair succeeds, a changed ZIP fails checksum validation, and an extra wheel or excluded path fails the package contract.

- [x] **Step 2: Verify RED**

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe' -m unittest tests.test_release_artifact -v
```

Expected: import failure because `verify_release_artifact.py` does not exist.

- [x] **Step 3: Implement the minimum validator**

Use `argparse`, `hashlib`, `re`, `tomllib`, and `zipfile`. Derive both filenames from the tag, require exactly those two artifact files, verify the adjacent checksum record, reject unsafe/excluded ZIP paths, compare the packaged manifest bytes to the checked-out manifest, and require exactly the manifest-declared wheels plus `LICENSE`, `Chem_Nodes.blend`, and `Chem_Nodes_En.blend`.

- [x] **Step 4: Verify GREEN**

Run the Task 1 command and require all validator tests to pass.

### Task 2: Manual Release workflow

**Files:**
- Create: `.github/workflows/extension-release.yml`
- Modify: `tests/test_repository_contract.py`

**Interfaces:**
- Consumes: `workflow_dispatch` inputs `tag: string` and `publish: boolean=false`, the successful `extension-package` Actions run, and the Task 1 validator CLI.
- Produces: read-only `verify` outputs `run_id`, `version`, and `artifact_name`; conditional `publish` job creating a verified public GitHub Release.

- [x] **Step 1: Write the failing workflow contract**

Require manual-only triggering, both inputs, global `actions: read`/`contents: read`, publish-only `contents: write`, `environment: release`, full SHA action pins, exact tag/run selection, two validator invocations, `--draft`, GitHub asset digest checks, and `--draft=false --latest`.

- [x] **Step 2: Verify RED**

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe' -m unittest tests.test_repository_contract.RepositoryContractTests.test_release_workflow_is_manual_and_deterministic -v
```

Expected: failure because `.github/workflows/extension-release.yml` does not exist.

- [x] **Step 3: Implement the minimum workflow**

The `verify` job checks out the workflow commit and requested tag separately, validates tag shape/type/main ancestry/manifest version, uses `gh run list` to select the one successful exact-SHA tag run, confirms one unexpired expected artifact, downloads it, and calls the validator. The conditional `publish` job repeats download and validation, extracts the matching `CHANGELOG.md` entry, refuses an existing Release, creates a draft with that body, compares both GitHub asset digests with local SHA-256 values, publishes latest, and confirms the latest API tag.

- [x] **Step 4: Verify GREEN**

Run the Task 2 command, then all repository contracts.

### Task 3: Durable workflow documentation

**Files:**
- Modify: `docs/development/branch-and-release.md`
- Modify: `docs/development/testing-and-ci.md`
- Modify: `.agents/reference/dependencies-and-release.md`
- Modify: `docs/superpowers/plans/2026-07-21-chemblender-deterministic-release-workflow.md`

**Interfaces:**
- Consumes: the implemented workflow input and failure behavior.
- Produces: one canonical future release procedure and stable Agent rules.

- [x] **Step 1: Replace the manual upload procedure**

Document validation-only dispatch first, publication dispatch second, the optional `release` environment reviewer configuration, and the rule that the workflow reuses rather than rebuilds the tag artifact.

- [x] **Step 2: Remove stale authority statements**

State that PR/main runs gate integration, the tag run owns release bytes, and `extension-release` verifies and publishes them.

- [x] **Step 3: Run complete local verification**

```powershell
$pythonBin = 'C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe'
& $pythonBin -m unittest discover -s tests -p 'test_*.py' -v
& $pythonBin -m compileall -q ChemBlender tests
git diff --check
```

Also download the existing `v2.2.0` Release assets into ignored `.agents/cache/`, run the validator against them, and confirm the validator-reported ZIP SHA-256 equals the current GitHub Release asset digest. Do not dispatch the new workflow.

- [x] **Step 4: Commit the implementation**

```powershell
git add -- .github/workflows/extension-release.yml ChemBlender/scripts/verify_release_artifact.py tests/test_release_artifact.py tests/test_repository_contract.py docs/development/branch-and-release.md docs/development/testing-and-ci.md .agents/reference/dependencies-and-release.md docs/superpowers/plans/2026-07-21-chemblender-deterministic-release-workflow.md
git commit -m "ci: automate verified extension releases"
```
