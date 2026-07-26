# ChemBlender 2.3.0 Wave 0 Release Task 1 Metadata Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one standard-library `ReleaseMetadata` source and make build and artifact verification consume its deterministic names.

**Architecture:** `release_metadata.py` strictly reads the production manifest once and derives versioned package, checksum and artifact names. Build and verification scripts import that helper in module and direct-script modes; they do not reconstruct names.

**Tech Stack:** Python 3.13 standard library, `tomllib`, `dataclasses`, `argparse`, `unittest`, Blender 5.1.2 extension CLI.

## Global Constraints

- Task baseline is `05c0429479759b297a7d6a4b80fd623bd4c09674`.
- Do not modify `ChemBlender/blender_manifest.toml`, `CHANGELOG.md` or GitHub workflows.
- Do not run a prerelease manifest probe; that belongs to Task 3.
- Production manifest remains byte-identical and reports `chemblender`, `2.2.0`, `windows-x64`.
- Use only the Python standard library and `tomllib`; do not import Blender.
- Preserve direct-script execution and module import.
- Stop after Task 1 checkpoint; the continuous goal controller then starts Task 2.

---

### Task 1: Manifest metadata contract

**Files:**
- Create: `ChemBlender/scripts/release_metadata.py`
- Create: `tests/test_release_metadata.py`

**Interfaces:**
- Produce: frozen, slotted `ReleaseMetadata(extension_id, version, platform, package_name, checksum_name, artifact_name)`.
- Produce: `read_release_metadata(extension_root: Path) -> ReleaseMetadata`.
- Produce: `release_metadata_document(metadata: ReleaseMetadata) -> dict[str, str]`.

- [x] **Step 1: Write strict manifest RED tests**

Cover the production manifest and temporary manifests with missing or wrong exact types for `id`, `version` and `platforms`; wrong ID; zero/multiple/wrong platforms; empty, trimmed, non-ASCII and unsafe versions.

Version rejects control characters, NUL, `< > : " / \ | ? *`, and trailing dot/space. It does not parse SemVer in this task.

- [x] **Step 2: Run RED**

Run:

```powershell
& $pythonBin -m unittest tests.test_release_metadata -v
```

Expected: import failure because `release_metadata.py` does not exist.

- [x] **Step 3: Implement the minimum helper**

Read `blender_manifest.toml` as bytes with `tomllib.loads()`. Require:

```text
id == "chemblender"
platforms == ["windows-x64"]
```

Derive exactly:

```text
chemblender-2.2.0.zip
chemblender-2.2.0.sha256
chemblender-2.2.0-windows-x64
```

- [x] **Step 4: Verify GREEN**

Run `tests.test_release_metadata` and confirm the dataclass is frozen and the production manifest bytes did not change.

---

### Task 2: Canonical CLI JSON

**Files:**
- Modify: `ChemBlender/scripts/release_metadata.py`
- Modify: `tests/test_release_metadata.py`

**Interfaces:**
- Produce CLI: `python ChemBlender/scripts/release_metadata.py --extension-root ChemBlender --format json`.

- [x] **Step 1: Add CLI RED tests**

Assert success/failure exit codes and canonical UTF-8 JSON using `sort_keys=True`, compact separators and one LF.

- [x] **Step 2: Implement CLI**

Print only the canonical metadata document on stdout; validation errors go to stderr and return 1.

- [x] **Step 3: Verify deterministic bytes**

Run the CLI twice and compare exact stdout bytes.

---

### Task 3: Build script integration

**Files:**
- Modify: `ChemBlender/scripts/build_extension.py`
- Modify: `tests/test_release_metadata.py`

**Interfaces:**
- Consume: `read_release_metadata(extension_root)`.

- [x] **Step 1: Add build integration RED tests**

Assert direct-script and module imports work, metadata is read once, and the exact expected package must exist as a regular file after native build.

- [x] **Step 2: Implement dual-mode import and exact output check**

Use:

```python
if __package__:
    from .release_metadata import read_release_metadata
else:
    from release_metadata import read_release_metadata
```

Retain current Python/Blender/Windows/WSL resolution. Do not glob, rename packages or modify the manifest.

- [x] **Step 3: Verify build contracts**

Run metadata and existing package/build-related tests.

---

### Task 4: Artifact verifier integration

**Files:**
- Modify: `ChemBlender/scripts/verify_release_artifact.py`
- Modify: `tests/test_release_artifact.py`

**Interfaces:**
- Consume: metadata `version`, `package_name`, `checksum_name`.

- [x] **Step 1: Add verifier RED tests**

Assert package/checksum document names come from metadata while stable tag `v2.2.0`, checksum, ZIP path safety, CRC, required files, wheel inventory and packaged-manifest equality remain unchanged.

- [x] **Step 2: Replace duplicate naming**

Read metadata once and require tag version to equal `metadata.version`. Preserve the current stable tag grammar; prerelease grammar belongs to Task 4 of the parent plan.

- [x] **Step 3: Verify artifact contracts**

Run `tests.test_release_artifact` and `tests.test_release_metadata`.

---

### Task 5: Stable build regression, review and checkpoint

**Files:**
- Modify if responsibilities changed: `.agents/reference/code-architecture-guide.md`
- Modify: `.agents/active/2.3.0-wave-0-platform-foundation.md`
- Modify: this plan

**Interfaces:**
- Produce: stable `2.2.0` package/verifier evidence and completed Task 1 cursor.

- [x] **Step 1: Run focused and full Python verification**

```powershell
& $pythonBin -m unittest tests.test_release_metadata tests.test_release_artifact tests.test_release_notes tests.test_quantum_visualization_docs -v
& $pythonBin -m unittest discover -s tests -p "test_*.py" -v
& $pythonBin -m compileall -q ChemBlender worker tests
git diff --check
```

- [x] **Step 2: Run stable Blender verification**

Run canonical metadata CLI, native validate/build, exact ZIP audit, a temporary checksum fixture, `verify_release_artifact`, and ZIP inventory/CRC. Confirm the production manifest SHA-256 is unchanged.

- [x] **Step 3: Run independent specification and quality reviews**

Fix all Critical, Important and task-related Minor findings with focused tests and scoped re-review.

- [x] **Step 4: Commit implementation and checkpoint**

Implementation commit:

```text
refactor: derive release metadata from manifest
```

Checkpoint records:

```text
Prerelease probe: Not Run — Task 3
Workflow modification: Not Run — Task 2
Remote CI: Not Run
Next task: Task 2 — Remove hardcoded 2.2.0 names from package workflow
```

Stop without changing Task 2 files; the continuous goal controller starts Task 2 only after this checkpoint is clean.

---

## Completion checkpoint

- State: `completed`
- Baseline: `05c0429479759b297a7d6a4b80fd623bd4c09674`
- Planning commit: `dec0ca2f2de4ecace4ae6310157a669e66800e89`
- Implementation commit: `26d81e102e69de1fd98c86d8af2ad821a1e923aa`
- RED evidence:
  `tests.test_release_metadata` and `tests.test_release_artifact` failed with
  `ModuleNotFoundError: release_metadata`; canonical CLI then reproduced CRLF
  on Windows before binary UTF-8 output fixed it.
- GREEN evidence:
  focused 41/41 Passed; full 963 Passed, 27 Skipped and 0 Failed; compileall
  and diff-check Passed.
- Stable 2.2.0 validate/build/verify: `Passed`
- Package:
  `chemblender-2.2.0.zip`,
  SHA-256 `ad8178a068cc22973f8c4e33e411b2c2ce176f33df19b8c2bdc32ae44a4ad1a0`
- Production manifest unchanged:
  `Passed`,
  SHA-256 `ed8ae130d6946725e9f2ed1bb141e2486c6d5cf80a589209480181ad7ea66f4e`
- Independent review: `APPROVED`; 0 Critical, 0 Important, 0 Minor.
- Prerelease probe: `Not Run — Task 3`
- Workflow modification: `Not Run — Task 2`
- Remote CI: `Not Run`
- Next task: `Task 2 — Remove hardcoded 2.2.0 names from package workflow`
