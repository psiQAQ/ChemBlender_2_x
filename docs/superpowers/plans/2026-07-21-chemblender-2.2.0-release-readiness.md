# ChemBlender 2.2.0 Release Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a focused ChemBlender 2.2.0 repository and extension package, prove clean and real Blender installations, and obtain a green GitHub Actions run on a draft pull request.

**Architecture:** Keep the existing dependency-free repository contracts, add package and real-Blender assertions to the existing smoke script, and use Blender's native extension validator/builder. Treat this plan as the live task authority: update checked steps and correct commands when verified runtime evidence invalidates an assumption.

**Tech Stack:** Blender 5.1.2, Blender Python 3.13, Python `unittest`/stdlib, PowerShell, Git, GitHub Actions, RDKit 2026.3.3 Windows x64 wheel.

## Global Constraints

- Continue on `feat/2.2.0-extension`; do not implement on `main`.
- Do not add pytest or another test dependency.
- Use Blender's bundled NumPy and Requests.
- Do not bundle Pillow while extension code does not import PIL or use Pillow-dependent RDKit features.
- Keep `ChemBlender/wheels/*.whl`, generated ZIPs, Blender test profiles, and caches ignored and untracked.
- Do not terminate an interactive Blender process or discard unsaved Blender data.
- Push only the refs approved in design; do not merge the draft pull request or publish a release.
- Preserve UTF-8 BOM state and line endings; use `apply_patch` for tracked edits.

---

### Task 1: Make release policy and Agent routing current

**Files:**
- Modify: `AGENTS.md`
- Modify: `.agents/README.md`
- Modify: `.agents/reference/dependencies-and-release.md`
- Create: `.agents/decisions/0002-release-testing-and-pillow-scope.md`
- Create: `.agents/active/2.2.0-release-readiness.md`
- Create: `docs/development/testing-and-ci.md`

**Interfaces:**
- Consumes: approved release-readiness design and current completed migration record.
- Produces: conspicuous stable rules plus a current task authority pointing to this plan.

- [x] **Step 1: Prove the current routing is stale**

Run:

```powershell
rg -n 'active/2\.2\.0-extension\.md' AGENTS.md .agents/README.md
Test-Path '.agents/active/2.2.0-extension.md'
```

Expected: both indexes reference the path and `Test-Path` returns `False`.

- [x] **Step 2: Update the stable rules**

Add a concise `Release Testing Policy` section to `AGENTS.md` requiring:

- standard-library tests until pytest has a demonstrated need;
- repository contract, native validate/build, ZIP audit, isolated install, real install, and GitHub Actions gates;
- temporary `BLENDER_USER_RESOURCES` for isolated runtime tests;
- actual runtime permissions in the manifest;
- full commit SHA pins for GitHub-owned actions.

Replace the stale current-task entry with `.agents/active/2.2.0-release-readiness.md`.

- [x] **Step 3: Update Agent routing and stable dependency policy**

Update `.agents/README.md` to index the new active task and completed migration. Update `.agents/reference/dependencies-and-release.md` with the same release gates, Pillow deferral boundary, isolated-profile rule, and real-CI requirement.

- [x] **Step 4: Record the dependency/testing decision**

Create `.agents/decisions/0002-release-testing-and-pillow-scope.md` with:

- `unittest` remains the runner;
- Pillow is excluded while no extension code imports PIL or exercises Pillow-dependent RDKit APIs;
- adding such code requires revisiting the manifest wheel set and CI;
- Blender's bundled NumPy and Requests are verified only from an isolated user resource root;
- network permission describes molecular/scaffold downloads and never runtime package installation.

- [x] **Step 5: Create current task authority and developer guide**

The active document links this plan, states the approved remote sequence, lists the current phase as repository policy cleanup, and contains no claimed future result. `docs/development/testing-and-ci.md` explains the four test layers and exact local commands.

- [x] **Step 6: Verify routing and commit**

Run:

```powershell
rg -n 'active/2\.2\.0-extension\.md' AGENTS.md .agents/README.md
rg -n '2\.2\.0-release-readiness' AGENTS.md .agents/README.md .agents/active/2.2.0-release-readiness.md
git diff --check
git add -- AGENTS.md .agents docs/development/testing-and-ci.md
git commit -m "docs: define extension release testing policy"
```

Expected: the stale search has no matches, current routing has matches, and the commit succeeds.

---

### Task 2: Enforce manifest permissions and package boundaries

**Files:**
- Modify: `tests/test_repository_contract.py`
- Modify: `ChemBlender/blender_manifest.toml`
- Modify: `docs/migration/2.2.0-extension.md`

**Interfaces:**
- Consumes: source calls to `requests.get`, current build script location, and manifest parser.
- Produces: declared network permission and a package that excludes development scripts.

- [x] **Step 1: Add failing manifest contract assertions**

In `test_extension_layout_and_manifest`, add:

```python
self.assertIn("network", manifest["permissions"])
self.assertLessEqual(len(manifest["permissions"]["network"]), 64)
self.assertIn("scripts/", manifest["build"]["paths_exclude_pattern"])
```

- [x] **Step 2: Run RED test**

Run:

```powershell
& $pythonBin -m unittest tests.test_repository_contract.RepositoryContractTests.test_extension_layout_and_manifest -v
```

Expected: FAIL because `network` and `scripts/` are absent.

- [x] **Step 3: Apply the minimal manifest fix**

Set:

```toml
[permissions]
files = "Import molecular and crystal structure files selected by users"
network = "Download molecular and scaffold data requested by users"

[build]
paths_exclude_pattern = [
  "__pycache__/",
  "*.zip",
  "scripts/",
  "tests/",
]
```

Document that network access supports explicit data-download features and is unrelated to dependency installation.

- [x] **Step 4: Run GREEN tests and native build**

Run:

```powershell
& $pythonBin -m unittest discover -s tests -p 'test_*.py' -v
& $pythonBin ChemBlender/scripts/validate_extension.py --source-path ChemBlender --blender $blenderBin
& $pythonBin ChemBlender/scripts/build_extension.py --python $pythonBin --blender $blenderBin
```

Expected: contracts, validate, and build pass.

- [x] **Step 5: Verify scripts are absent from the ZIP and commit**

Run:

```powershell
& $pythonBin -c "import zipfile; z=zipfile.ZipFile('ChemBlender/chemblender-2.2.0.zip'); assert not any(n.startswith('scripts/') for n in z.namelist())"
git diff --check
git add -- ChemBlender/blender_manifest.toml tests/test_repository_contract.py docs/migration/2.2.0-extension.md
git commit -m "fix: declare extension release boundaries"
```

Expected: ZIP assertion and commit pass.

---

### Task 3: Harden the release artifact and Blender smoke test

**Files:**
- Modify: `tests/blender_smoke.py`
- Modify: `tests/test_repository_contract.py`

**Interfaces:**
- Consumes: one built extension ZIP passed after `--` and optional `--keep-enabled`.
- Produces: package audit, installed asset/RDKit verification, and either clean disable or a persistent verified installation.

**Execution correction:** Run Step 5 before Steps 1-4 to establish the required RED contract before changing the smoke implementation.

- [x] **Step 1: Add a package-content assertion**

Add a helper using `zipfile.ZipFile` that requires:

```python
required = {
    "blender_manifest.toml",
    "LICENSE",
    "Chem_Nodes.blend",
    "Chem_Nodes_En.blend",
    "wheels/rdkit-2026.3.3-cp313-cp313-win_amd64.whl",
}
forbidden_prefixes = ("scripts/", "tests/", "__pycache__/")
```

It also rejects nested `.zip` entries and requires exactly one `.whl`.

- [x] **Step 2: Verify representative RDKit compiled functionality**

After installation, run:

```python
from rdkit import Chem
from rdkit.Chem import AllChem

mol = Chem.AddHs(Chem.MolFromSmiles("CCO"))
assert AllChem.EmbedMolecule(mol, randomSeed=0xC0FFEE) == 0
```

- [x] **Step 3: Verify installed blend libraries**

Resolve the installed extension root with `importlib.util.find_spec(module_key)`. For each installed library, inspect `data_from.node_groups` through `bpy.data.libraries.load` without assigning any datablocks:

```python
expected_node_groups = {
    "Chem_Nodes.blend": 174,
    "Chem_Nodes_En.blend": 171,
}
```

Assert the installed files exist and counts match.

- [x] **Step 4: Add real-install mode**

Accept either:

```text
tests/blender_smoke.py -- package.zip
tests/blender_smoke.py -- package.zip --keep-enabled
```

The default path retains two disable/enable cycles and a final disable. `--keep-enabled` performs the same assertions but leaves the verified extension enabled for the real user repository.

- [x] **Step 5: Strengthen the repository contract for the smoke script**

Assert the smoke source contains the two expected blend filenames, `EmbedMolecule`, package-content audit, and `--keep-enabled`.

- [x] **Step 6: Run isolated Blender smoke and commit**

Run:

```powershell
$env:BLENDER_USER_RESOURCES = (New-Item -ItemType Directory -Path '.agents/cache/blender-user-clean' -Force).FullName
$package = (Get-Item 'ChemBlender/chemblender-2.2.0.zip').FullName
& $blenderBin --background --factory-startup --python tests/blender_smoke.py -- $package
Remove-Item Env:BLENDER_USER_RESOURCES
git diff --check
git add -- tests
git commit -m "test: verify packaged extension behavior"
```

Expected: package audit, RDKit operation, both blend libraries, lifecycle, and commit pass.

---

### Task 4: Remove confirmed local debris

**Files:**
- Delete ignored local artifacts only; no tracked source files.

**Interfaces:**
- Consumes: explicit `git clean -ndX` evidence.
- Produces: focused local workspace while retaining the verified ignored RDKit wheel.

- [ ] **Step 1: Preview ignored targets**

Run:

```powershell
git clean -ndX
```

Expected targets include caches, `.blend-analysis/`, generated extension ZIP, and obsolete root `chemblender-2.1.0.zip`.

- [ ] **Step 2: Resolve and remove only approved targets**

Verify every resolved path remains under `D:\workspace\ChemBlender_2_x`, then remove:

```text
.blend-analysis/
chemblender-2.1.0.zip
ChemBlender/chemblender-2.2.0.zip
ChemBlender/__pycache__/
ChemBlender/scripts/__pycache__/
tests/__pycache__/
.agents/cache/
```

Retain `ChemBlender/wheels/rdkit-2026.3.3-cp313-cp313-win_amd64.whl` until all local install gates finish.

- [ ] **Step 3: Verify tracked state is unchanged**

Run:

```powershell
git status --short
git ls-files 'ChemBlender/wheels/*.whl' '.agents/cache/**' '*.zip'
```

Expected: clean tracked state and no prohibited tracked artifact.

---

### Task 5: Harden the GitHub Actions workflow

**Files:**
- Modify: `.github/workflows/extension-package.yml`
- Modify: `tests/test_repository_contract.py`
- Modify: `docs/development/testing-and-ci.md`

**Interfaces:**
- Consumes: pinned official download URLs and the same local test/build/smoke commands.
- Produces: a least-privilege Windows CI job and uploaded verified package/checksum.

- [ ] **Step 1: Add failing workflow contract assertions**

Require these exact action pins:

```text
actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97
actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a
```

Also require `permissions:`, `contents: read`, `timeout-minutes:`, `BLENDER_USER_RESOURCES`, and `chemblender-2.2.0.sha256`.

- [ ] **Step 2: Run RED workflow contract**

Run:

```powershell
& $pythonBin -m unittest tests.test_repository_contract.RepositoryContractTests.test_package_workflow_pins_and_verifies_release_inputs -v
```

Expected: FAIL because the workflow still uses mutable major tags and lacks the isolated profile/checksum record.

- [ ] **Step 3: Apply minimal workflow hardening**

Update the workflow to:

- use the three full action SHAs with version comments;
- set top-level `permissions: contents: read`;
- set job `timeout-minutes: 30`;
- keep PR, `main`, and `v*` triggers;
- create `$env:BLENDER_USER_RESOURCES` under `$env:RUNNER_TEMP` before smoke;
- generate `ChemBlender/chemblender-2.2.0.sha256` with .NET UTF-8 without BOM;
- upload the ZIP and checksum with `retention-days: 14`.

Do not add cache, matrix, pytest, coverage, or automatic release publication.

- [ ] **Step 4: Run GREEN contracts and local workflow equivalent**

Run all commands from Task 6 below once. Update `docs/development/testing-and-ci.md` with the exact CI/local equivalence and the fact that GitHub Actions is authoritative.

- [ ] **Step 5: Commit workflow hardening**

Run:

```powershell
git diff --check
git add -- .github/workflows/extension-package.yml tests/test_repository_contract.py docs/development/testing-and-ci.md
git commit -m "ci: harden ChemBlender release validation"
```

Expected: commit succeeds without generated artifacts.

---

### Task 6: Run complete local release gates and reinstall the real extension

**Files:**
- Generated ignored artifacts only.

**Interfaces:**
- Consumes: clean tracked tree, ignored RDKit wheel, Blender 5.1.2 executable and bundled Python.
- Produces: local package SHA-256, isolated install evidence, and enabled real `user_default` installation.

- [ ] **Step 1: Re-query Blender MCP runtime facts**

Run `blender-mcp --help`, then query Blender version, executable, system, extension repositories, active file, and dirty state. Require Blender 5.1.2 on Windows and `user_default` enabled.

- [ ] **Step 2: Restore and verify the pinned wheel if absent**

Download the exact URL in `.agents/reference/dependencies-and-release.md` only when the ignored wheel is absent. Require SHA-256:

```text
f8bd59b24e128c9c70c975bfb1920cf610ba3096439a24ca2850eb861e767c48
```

- [ ] **Step 3: Run the full local equivalent pipeline**

Run:

```powershell
& $pythonBin -m unittest discover -s tests -p 'test_*.py' -v
& $pythonBin -m compileall -q ChemBlender tests
& $pythonBin ChemBlender/scripts/validate_extension.py --source-path ChemBlender --blender $blenderBin
& $pythonBin ChemBlender/scripts/build_extension.py --python $pythonBin --blender $blenderBin
$package = Get-Item 'ChemBlender/chemblender-2.2.0.zip'
$env:BLENDER_USER_RESOURCES = (New-Item -ItemType Directory -Path '.agents/cache/blender-release-clean' -Force).FullName
& $blenderBin --background --factory-startup --python tests/blender_smoke.py -- $package.FullName
Remove-Item Env:BLENDER_USER_RESOURCES
git diff --check
```

Expected: every command exits zero. Existing regex escape warnings are recorded but do not hide a failed command.

- [ ] **Step 4: Audit and hash the package**

Use stdlib `zipfile` to print sorted entries and verify the contract. Record package size and SHA-256 in `.agents/cache/release-evidence.json`, which remains ignored.

- [ ] **Step 5: Reinstall into the real user repository**

If the connected Blender is dirty or has loaded ChemBlender/RDKit DLLs, ask the user to save and close Blender. Once no interactive Blender process is using the package, run a fresh default-profile background Blender process:

```powershell
& $blenderBin --background --python tests/blender_smoke.py -- $package.FullName --keep-enabled
```

Then reconnect/query Blender and verify `bl_ext.user_default.chemblender`, three registered properties, installed path, RDKit operation, and both `.blend` files.

- [ ] **Step 6: Confirm commit and artifact state**

Run:

```powershell
git status --short --branch
git ls-files 'ChemBlender/wheels/*.whl' '.agents/cache/**' '*.zip'
```

Expected: clean tracked tree and only ignored local release artifacts.

---

### Task 7: Push approved refs and obtain the first real CI result

**Files:** None unless CI exposes a reproduced defect.

**Interfaces:**
- Consumes: locally verified commits and user-approved remote strategy A.
- Produces: durable 2.1.1 baseline/archive, feature branch, draft PR, and GitHub Actions run.

- [ ] **Step 1: Verify exact push refs**

Require:

```text
main -> 2b72abf9e0e1f987014c8a95193bed06cc8dd988
v2.1.1 -> annotated tag whose peeled commit is 2b72abf9e0e1f987014c8a95193bed06cc8dd988
archive/extension-spike-20260707 -> 24520d991ba17c81db93afa888809c27574a3875
feat/2.2.0-extension -> current verified HEAD
```

- [ ] **Step 2: Push the maintained baseline and archive**

Run:

```powershell
git push origin main
git push origin v2.1.1
git push origin archive/extension-spike-20260707
```

Do not push `release/2.1.1` or overwrite `snapshot/20260707-current-state`.

- [ ] **Step 3: Push the feature branch**

Run:

```powershell
git push -u origin feat/2.2.0-extension
```

- [ ] **Step 4: Create a draft pull request**

Create a draft PR into `psiQAQ/ChemBlender_2_x:main` summarizing the 2.2.0 extension layout, offline RDKit wheel policy, release tests, Windows limitation, and local evidence. Do not include memory citations or claim CI is green before the run completes.

- [ ] **Step 5: Wait for and inspect Actions**

Use `gh pr checks --watch` or bounded `gh run watch`. Inspect failed logs rather than rerunning blindly. Download the successful artifact into ignored `.agents/cache/ci-artifact/` and audit the ZIP entries.

- [ ] **Step 6: Correct reproduced CI failures**

For each failure, update this plan with the observed cause, write the narrowest regression check, fix the root cause, rerun local gates, commit, push the feature branch, and wait for the replacement run. Stop only for unavailable GitHub permissions/service or another user-only blocker.

---

### Task 8: Record green CI and remove redundant local branches

**Files:**
- Delete: `.agents/active/2.2.0-release-readiness.md`
- Create: `.agents/completed/2.2.0-release-readiness.md`
- Modify: `.agents/README.md`
- Modify: `docs/development/testing-and-ci.md`
- Modify: this plan's checkbox state and verified corrections.

**Interfaces:**
- Consumes: successful PR check URL, run ID, artifact name, package SHA-256, and verified remote refs.
- Produces: durable completion evidence and a minimal local branch set.

- [ ] **Step 1: Record authoritative CI evidence**

Move the active summary to completed form with the PR URL, workflow run URL/ID, tested commit, package checksum, local and CI results, warnings, and remaining Windows-only limitation. Update the developer guide with any command correction discovered in CI.

- [ ] **Step 2: Commit and push the evidence**

Run:

```powershell
git diff --check
git add -- .agents docs
git commit -m "docs: record 2.2.0 release validation"
git push origin feat/2.2.0-extension
```

Wait for the new PR-head Actions run and require it to pass.

- [ ] **Step 3: Verify replacement refs before local branch deletion**

Require remote `archive/extension-spike-20260707`, `main`, and `v2.1.1` to match the intended commits. Then delete only duplicate local names:

```powershell
git branch -d snapshot/20260707-current-state
git branch -d release/2.1.1
```

Keep `archive/extension-spike-20260707`, `main`, and `feat/2.2.0-extension`.

- [ ] **Step 4: Final audit**

Run repository contracts, native validate/build, isolated Blender smoke, Git ancestry/ref audit, PR checks, package artifact audit, `git diff --check`, and `git status --short --branch` one final time.

Expected: all local and remote checks pass, current feature branch is clean, and no wheel/ZIP/cache is tracked.

- [ ] **Step 5: Report excluded actions**

Report without performing:

- merging the draft PR;
- creating/publishing the 2.2.0 GitHub release;
- deleting remote `snapshot/20260707-current-state`.

Each remains a separate explicit user decision.
