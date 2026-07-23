# ChemBlender 2.3.0 Wave 0 Release Groundwork Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove 2.2.0 hardcoding, prove the prerelease manifest version scheme, and prepare reproducible alpha artifacts without publishing.

**Architecture:** Version and artifact metadata are derived by one standard-library helper. A disposable manifest probe is validated by Blender 5.1.2 before workflows accept prerelease tags. Release behavior distinguishes prerelease and final artifacts.

**Tech Stack:** Python 3.13 `tomllib`, Blender native extension CLI, PowerShell, Bash, GitHub Actions, `unittest`.

## Global Constraints

- Do not change the production manifest to a prerelease version before the native probe passes.
- Do not create or push tags in this plan without explicit authorization.
- Release workflow never rebuilds package artifacts.
- GitHub-owned actions remain pinned to full SHAs.
- All generic workflow code derives version names; fixture tests may contain explicit versions.

---

### Task 1: Add a single release metadata helper

**Files:**
- Create: `ChemBlender/scripts/release_metadata.py`
- Create: `tests/test_release_metadata.py`
- Modify: `ChemBlender/scripts/build_extension.py`
- Modify: `ChemBlender/scripts/verify_release_artifact.py`

**Interfaces:**
- Produces: `ReleaseMetadata`, `read_release_metadata(extension_root)`, CLI JSON output.

- [ ] **Step 1: Write metadata tests**

```python
def test_metadata_derives_names_from_manifest(self):
    metadata = read_release_metadata(self.extension_root)
    self.assertEqual(metadata.package_name, f"chemblender-{metadata.version}.zip")
    self.assertEqual(metadata.checksum_name, f"chemblender-{metadata.version}.sha256")
    self.assertEqual(metadata.artifact_name, f"chemblender-{metadata.version}-windows-x64")
```

Add validation for extension ID, platform and version text.

- [ ] **Step 2: Implement helper and CLI**

`python release_metadata.py --extension-root ChemBlender --format json` emits canonical JSON. Build/verify scripts import the helper rather than reconstructing names.

- [ ] **Step 3: Run and commit**

Run release script tests and existing package contracts, then commit.

### Task 2: Remove hardcoded 2.2.0 names from package workflow

**Files:**
- Modify: `.github/workflows/extension-package.yml`
- Modify: `tests/test_extension_package_workflow.py` or the existing workflow contract test

**Interfaces:**
- Produces: dynamic environment outputs `version`, `package_name`, `checksum_name`, `artifact_name`.

- [ ] **Step 1: Add failing workflow contract assertions**

Assert the workflow text does not contain `chemblender-2.2.0` and invokes `release_metadata.py`.

- [ ] **Step 2: Add metadata step**

Use PowerShell to call the helper and append fields to `$GITHUB_OUTPUT`. Refer to step outputs for package lookup, checksum, artifact upload name and paths.

- [ ] **Step 3: Verify YAML and tests**

Run workflow contract tests and parse YAML if the repository already has a parser; otherwise rely on textual contract plus GitHub Actions validation on the branch.

- [ ] **Step 4: Commit**

Commit workflow and test only.

### Task 3: Probe Blender 5.1.2 prerelease manifest support

**Files:**
- Create: `ChemBlender/scripts/probe_prerelease_version.py`
- Create: `tests/test_prerelease_probe_script.py`
- Create: `docs/development/2.3.0-prerelease-version-probe.md`

**Interfaces:**
- Produces: a reproducible probe command and recorded native validator result.

- [ ] **Step 1: Implement a disposable manifest copy**

The script copies the extension source to a temporary directory excluding wheels/build artifacts, changes only manifest version to `2.3.0-alpha.1`, and runs:

```text
& $blenderBin --command extension validate $probeRoot
```

It never edits the working manifest.

- [ ] **Step 2: Unit-test safe behavior**

Mock subprocess to assert the temporary manifest changes, production manifest stays byte-identical, and exit code/report are propagated.

- [ ] **Step 3: Run the real probe**

Use MCP-discovered Blender 5.1.2. Record executable, version, command, stdout/stderr and result in the document. If FAIL, stop release-scheme work and create a replacement ADR before Task 4. If PASS, record SemVer prerelease as accepted.

- [ ] **Step 4: Commit evidence**

Commit script, tests and observed probe document. Do not tag.

### Task 4: Extend changelog and release validators for the proven scheme

**Files:**
- Modify: `ChemBlender/scripts/extract_release_notes.py`
- Modify: `ChemBlender/scripts/validate_extension.py`
- Modify: `ChemBlender/scripts/verify_release_artifact.py`
- Modify: related tests.

**Interfaces:**
- Produces: accepted version parser matching the observed Blender-supported scheme.

- [ ] **Step 1: Write valid/invalid version cases**

If probe passed SemVer prerelease, valid cases are `2.3.0`, `2.3.0-alpha.1`, `2.3.0-beta.2`, `2.3.0-rc.1`; invalid cases include missing numeric identifiers, spaces, leading `v` in manifest and path separators.

- [ ] **Step 2: Implement one shared parser**

Place version parsing in `release_metadata.py`; all scripts import it. Changelog headings accept the exact version and a date. No duplicate parser regex remains.

- [ ] **Step 3: Run tests and commit**

Run changelog, validator, artifact and release metadata tests.

### Task 5: Add prerelease-aware release workflow behavior

**Files:**
- Modify: `.github/workflows/extension-release.yml`
- Modify: release workflow contract tests
- Modify: `docs/development/branch-and-release.md`

**Interfaces:**
- Produces: dry-run verification for prerelease tags and publication flags that never mark prerelease latest.

- [ ] **Step 1: Test tag classification**

Add a script/helper test returning channel alpha/beta/rc/final and `is_prerelease`.

- [ ] **Step 2: Modify workflow**

Use metadata outputs. For prerelease publication, call `gh release create` with `--prerelease` and do not call `--latest`. For final, publish and verify latest. Exact-tag package run selection remains mandatory.

- [ ] **Step 3: Increase artifact retention for tagged builds**

Set a retention sufficient for the release process using a conditional or a common value justified in docs; do not let alpha artifacts expire before review.

- [ ] **Step 4: Run read-only local/static validation and commit**

No publish action. Commit workflow, tests and docs.

### Task 6: Build the Wave 0 alpha candidate without publishing

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `ChemBlender/blender_manifest.toml`
- Modify: `.agents/active/2.3.0-wave-0-platform-foundation.md`

**Interfaces:**
- Consumes: all Wave 0 code and a proven version scheme.
- Produces: local and CI-ready alpha.1 package state.

- [ ] **Step 1: Set exact alpha version and changelog entry**

Use the proven manifest string. Update tagline only if the release description is already approved; otherwise defer tagline to Wave 4. Add a dated, complete alpha entry.

- [ ] **Step 2: Run full Wave 0 verification**

```powershell
& $pythonBin -m unittest discover -s tests -p 'test_*.py' -v
& $pythonBin -m compileall -q ChemBlender tests
& $pythonBin ChemBlender/scripts/validate_extension.py --source-path ChemBlender --blender $blenderBin
& $pythonBin ChemBlender/scripts/build_extension.py --python $pythonBin --blender $blenderBin
```

Then run isolated Blender smoke against the dynamically named ZIP and verify artifact.

- [ ] **Step 3: Record evidence**

Update the active task with exact test counts, Blender version, package path/hash, size and Not Run status for remote CI/tag if not authorized.

- [ ] **Step 4: Commit candidate metadata**

Commit manifest/changelog only after all local gates pass. Tag/push/release remain separate authorized actions.
