# ChemBlender 2.1.1 and 2.2.0 Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the maintained fork as a clean 2.1.1 legacy add-on release, then establish the tracked Agent knowledge base and migrate ChemBlender to a Blender 5.1 extension released as 2.2.0.

**Architecture:** Preserve the current extension experiment as an archive, reconstruct 2.1.1 from the immutable 2.1.0 import, and start 2.2.0 from the maintained 2.1.1 `main`. The extension lives under `ChemBlender/`; its RDKit wheel is absent from Git, downloaded with a pinned checksum for local builds and CI, and packaged through Blender's extension-native tooling.

**Tech Stack:** Git, Python 3.13 standard library, Blender 5.1 extension CLI/API, GitHub Actions, RDKit 2026.3.3 Windows CPython 3.13 wheel.

## Global Constraints

- `78c2d8d8d6361302bf8f19a568c3d7cfccde4c19` is the immutable 2.1.0 import baseline.
- 2.1.1 is a legacy add-on containing only the two compressed `.blend` files and `bl_info["version"] = (2, 1, 1)`.
- 2.1.1 must not contain `blender_manifest.toml`, extension namespace fixes, tests, tracked wheels, or repository governance files.
- 2.2.0 is extension-only, uses `ChemBlender/` as the extension root, and targets Blender 5.1.0 or newer on `windows-x64`.
- NumPy comes from Blender. Runtime code must not install Python packages or request network access.
- RDKit file name is `rdkit-2026.3.3-cp313-cp313-win_amd64.whl`.
- RDKit source is `https://files.pythonhosted.org/packages/68/d0/5de3d0d7e66f0e7e7795ab94a53b826e257176c15c9ee79f15621ac040ed/rdkit-2026.3.3-cp313-cp313-win_amd64.whl`.
- RDKit SHA-256 is `f8bd59b24e128c9c70c975bfb1920cf610ba3096439a24ca2850eb861e767c48`.
- Stable Agent instructions, indexes, decisions, summaries, local skills, and `skills-lock.json` are tracked from 2.2.0 onward.
- `.whl`, `.zip`, `.agents/cache/`, large archived evidence, `.blend-analysis/`, and `.worktrees/` remain ignored.
- No remote changes, pushes, or GitHub releases occur without a separate explicit approval.

## Target File Map

| Path | Responsibility |
| --- | --- |
| `AGENTS.md` | Stable session rules and knowledge routing only |
| `.agents/README.md` | Agent knowledge index and recovery order |
| `.agents/active/2.2.0-extension.md` | Current 2.2.0 task authority |
| `.agents/reference/branch-architecture.md` | Maintained/upstream branch roles and lifecycle |
| `.agents/reference/dependencies-and-release.md` | Blender, RDKit, wheel, CI, and release rules |
| `.agents/decisions/0001-version-and-extension-roadmap.md` | Immutable rationale for 2.1.1/2.2.0 boundaries |
| `.agents/completed/2.1.0-import-and-2.1.1-slimming.md` | Finished legacy release provenance |
| `docs/README.md` | Human documentation index |
| `docs/development/branch-and-release.md` | Contributor branch/release workflow |
| `docs/migration/2.2.0-extension.md` | Legacy-to-extension migration guide |
| `ChemBlender/blender_manifest.toml` | 2.2.0 extension metadata and wheel declaration |
| `ChemBlender/__init__.py` | Minimal autoload orchestration |
| `ChemBlender/extension.py` | Existing menu, node-group loading, properties, and lifecycle side effects |
| `ChemBlender/auto_load.py` | Template-derived registration and reload ordering |
| `ChemBlender/scripts/validate_extension.py` | Local and Blender extension validation |
| `ChemBlender/scripts/build_extension.py` | Unified extension build entrypoint |
| `tests/test_repository_contract.py` | Standard-library repository and packaging contract |
| `tests/blender_smoke.py` | Real Blender install/register/reload/unregister smoke check |
| `.github/workflows/extension-package.yml` | Pinned Blender/RDKit validation and package artifact build |

---

### Task 1: Preserve the experiment and create the 2.1.1 release branch

**Files:** None.

**Interfaces:**
- Consumes: current clean `snapshot/20260707-current-state`, baseline `78c2d8d`, compressed assets in `21b4c5a`.
- Produces: local archive ref `archive/extension-spike-20260707` and checked-out `release/2.1.1`.

- [ ] **Step 1: Verify the repository and immutable ancestry**

```powershell
git status --short --branch
git rev-parse HEAD
git rev-parse 78c2d8d^
git merge-base --is-ancestor 9077096 78c2d8d
```

Expected: worktree is clean; `78c2d8d^` is `9077096b776cd18ca85adb4b50253a0d3c18fd76`; the ancestry command exits `0`.

- [ ] **Step 2: Preserve the complete current state**

```powershell
git branch archive/extension-spike-20260707 HEAD
git show-ref --verify refs/heads/archive/extension-spike-20260707
```

Expected: the archive ref points to the pre-rebuild HEAD containing the extension spike, compressed assets, approved spec, and this plan.

- [ ] **Step 3: Create the release branch from the 2.1.0 import**

```powershell
git switch -c release/2.1.1 78c2d8d
git status --short --branch
git ls-tree --name-only HEAD
```

Expected: branch is `release/2.1.1`; no manifest, tests, wheels, `docs/`, or `.agents/` are tracked.

---

### Task 2: Produce and verify the minimal 2.1.1 legacy add-on

**Files:**
- Modify: `Chem_Nodes.blend`
- Modify: `Chem_Nodes_En.blend`
- Modify: `__init__.py:4`

**Interfaces:**
- Consumes: compressed asset blobs from `21b4c5a`.
- Produces: one focused 2.1.1 release commit and a locally verified legacy ZIP.

- [ ] **Step 1: Restore only the two compressed assets**

```powershell
git restore --source=21b4c5a -- Chem_Nodes.blend Chem_Nodes_En.blend
git diff --name-only
```

Expected: exactly `Chem_Nodes.blend` and `Chem_Nodes_En.blend` are listed.

- [ ] **Step 2: Change only the legacy version tuple**

Use `apply_patch`:

```diff
-    "version" : (2, 1, 0),
+    "version" : (2, 1, 1),
```

- [ ] **Step 3: Enforce the release scope**

```powershell
$changedFiles = @(git diff --name-only)
$expectedFiles = @('__init__.py', 'Chem_Nodes.blend', 'Chem_Nodes_En.blend')
if (Compare-Object $expectedFiles $changedFiles) { throw 'Unexpected 2.1.1 files' }
if (Test-Path -LiteralPath 'blender_manifest.toml') { throw '2.1.1 must remain a legacy add-on' }
if (Test-Path -LiteralPath 'wheels') { throw '2.1.1 must not contain wheels' }
```

Expected: no output and exit `0`.

- [ ] **Step 4: Run the real Blender asset check**

First satisfy the Blender MCP gate: `blender-mcp --help`, then query `bpy.app.version_string`, `bpy.app.binary_path`, `bpy.app.binary_path_python`, and `platform.system()` together. Use the returned Blender executable below.

```powershell
if (-not $blenderBin) { throw 'Assign binary_path returned by Blender MCP to $blenderBin' }
& $blenderBin --background --factory-startup --python-expr "import bpy; p=r'$((Resolve-Path 'Chem_Nodes.blend').Path)'; bpy.ops.wm.open_mainfile(filepath=p); assert len(bpy.data.node_groups)==174; print('PASS Chem_Nodes.blend')"
& $blenderBin --background --factory-startup --python-expr "import bpy; p=r'$((Resolve-Path 'Chem_Nodes_En.blend').Path)'; bpy.ops.wm.open_mainfile(filepath=p); assert len(bpy.data.node_groups)==171; print('PASS Chem_Nodes_En.blend')"
```

Expected: Blender is at least 5.1.0 and both commands print `PASS` with exit `0`.

- [ ] **Step 5: Commit the legacy release**

```powershell
git add -- __init__.py Chem_Nodes.blend Chem_Nodes_En.blend
git diff --cached --check
git commit -m "release: prepare legacy add-on 2.1.1"
```

- [ ] **Step 6: Build a legacy ZIP without adding build scripts**

```powershell
$releaseZip = Join-Path (Split-Path (Get-Location) -Parent) 'ChemBlender-2.1.1.zip'
git archive --format=zip --prefix=ChemBlender/ --output=$releaseZip HEAD
if (-not (Test-Path -LiteralPath $releaseZip)) { throw 'Legacy release ZIP was not created' }
```

Expected: the ZIP exists outside the repository and contains a top-level `ChemBlender/` directory.

---

### Task 3: Advance maintained `main` and create the local 2.1.1 tag

**Files:** None.

**Interfaces:**
- Consumes: verified `release/2.1.1`.
- Produces: local maintained `main` and annotated `v2.1.1`; remote state remains unchanged.

- [ ] **Step 1: Fast-forward maintained main**

```powershell
$releaseCommit = git rev-parse release/2.1.1
git switch main
git merge --ff-only release/2.1.1
if ((git rev-parse HEAD) -ne $releaseCommit) { throw 'main did not fast-forward to 2.1.1' }
```

- [ ] **Step 2: Tag and verify the exact release tree**

```powershell
git tag -a v2.1.1 -m "ChemBlender 2.1.1"
git describe --exact-match --tags HEAD
git diff --name-only 78c2d8d..v2.1.1
```

Expected: tag is `v2.1.1`; diff lists only the version file and two `.blend` files.

- [ ] **Step 3: Record the no-push boundary**

Do not push `main`, `release/2.1.1`, the archive branch, or `v2.1.1`. Report the local refs and wait for explicit remote authorization after the complete 2.2.0 validation.

---

### Task 4: Establish the tracked 2.2.0 development workspace

**Files:**
- Create: `AGENTS.md`
- Create: `.agents/README.md`
- Track: `.agents/skills/blender-mcp-skills/**`
- Create: `.agents/active/2.2.0-extension.md`
- Create: `.agents/reference/branch-architecture.md`
- Create: `.agents/reference/dependencies-and-release.md`
- Create: `.agents/decisions/0001-version-and-extension-roadmap.md`
- Create: `.agents/completed/2.1.0-import-and-2.1.1-slimming.md`
- Create: `docs/README.md`
- Create: `docs/development/branch-and-release.md`
- Create: `docs/migration/2.2.0-extension.md`
- Restore: `docs/superpowers/specs/2026-07-20-chemblender-2.2.0-repository-governance-design.md`
- Restore: `docs/superpowers/plans/2026-07-21-chemblender-2.1.1-and-2.2.0-rebuild.md`
- Modify: `.gitignore`
- Track: `skills-lock.json`

**Interfaces:**
- Consumes: maintained `main@v2.1.1` and planning documents from the archive branch.
- Produces: `feat/2.2.0-extension` with stable, routed, tracked Agent knowledge.

- [ ] **Step 1: Create the extension feature branch and restore approved planning records**

```powershell
git switch -c feat/2.2.0-extension main
git restore --source=archive/extension-spike-20260707 -- docs/superpowers
if (-not (Test-Path -LiteralPath '.agents\skills\blender-mcp-skills\SKILL.md')) { throw 'Local blender-mcp-skills is missing' }
if (-not (Test-Path -LiteralPath 'skills-lock.json')) { throw 'Local skills-lock.json is missing' }
```

- [ ] **Step 2: Replace `.gitignore` with the tracked-knowledge policy**

```gitignore
__pycache__/
*.py[cod]
*.zip
.pytest_cache/
.blend-analysis/
Thumbs.db
.agents/cache/
.agents/archive/*
!.agents/archive/README.md
.worktrees/
ChemBlender/wheels/*.whl
```

- [ ] **Step 3: Write the root session contract**

`AGENTS.md` must contain these exact sections and no dynamic SHA/run status:

```markdown
# ChemBlender Repository Instructions

## Communication

- Use Chinese by default. Keep code, commands, paths, APIs, and errors in English.
- Lead with conclusion, evidence, plan, and verification. Separate confirmed facts, inference, and recommendation.

## Session Recovery

After a new conversation or context compaction:

1. Read this file.
2. Read `.agents/README.md`.
3. Read the relevant `.agents/active/` or `.agents/queued/` document.
4. Read only the referenced decision or reference documents needed for the task.
5. Verify Git, Blender, dependency, test, and CI state live.

Do not infer current status from this file, completed work, archived evidence, or old conversations.

## Release Boundaries

- `78c2d8d` is the imported 2.1.0 baseline.
- 2.1.1 is the final legacy add-on release and changes only the version plus two compressed `.blend` files.
- 2.2.0 is the first extension release and uses `ChemBlender/` as its extension root.
- The repository root is the development workspace, not the packaged extension root.

## Branch Roles

- `origin/main` is the maintained release line.
- `upstream/main` is the upstream reference.
- `archive/*` is immutable investigation history and never a release base.
- `release/*` contains focused release preparation.
- `feat/*` contains maintained downstream features.
- Formal `upstream-pr/*` branches start from freshly fetched `upstream/main` and exclude downstream governance, packaging, and extension history.

## Repository Layout

- `ChemBlender/`: packaged extension source and manifest.
- `tests/`: repository contracts and Blender runtime smoke checks.
- `docs/`: durable human-facing development, migration, and release documentation.
- `.agents/active/`: current task authority.
- `.agents/queued/`: approved work not yet started.
- `.agents/reference/`: stable operational rules.
- `.agents/decisions/`: numbered decision rationale.
- `.agents/completed/`: finished summaries used only for provenance.
- `.agents/skills/`: repository-local skills and templates.

## Task Execution

- Before editing, state Goal, Success Criteria, Constraints, and Verification.
- Inspect `git status`, the current branch, affected source, callers, tests, and recent commits before modifying files.
- Use the smallest change that solves the confirmed problem. Reuse existing code and standard-library/platform features.
- Do not add speculative abstractions, dependencies, compatibility layers, or unrelated cleanup.
- Protect user changes and preserve existing file encoding and line endings.

## Python Environment

- Prefer project `.venv`, then an existing `uv` environment, then Blender bundled Python returned by MCP.
- Do not install or change Python dependencies without explicit approval.
- Do not install packages into Blender's global `site-packages`.

## Blender Extension Workflow

- Before Blender operations, run `blender-mcp --help` and query Blender version, executable, bundled Python, runtime system, and extension repositories together.
- Require Blender 5.1.0 or newer for the supported release.
- Build and install through Blender Extensions; never copy 2.2.0 source into a legacy add-on directory.
- Verify the enabled key `bl_ext.user_default.chemblender`.
- Validate register, unregister, repeated reload, scene properties, `.blend` assets, and RDKit import in the real runtime.

## Dependency Policy

- Use Blender's bundled NumPy.
- RDKit is an offline manifest wheel downloaded by developers or CI.
- Never track `.whl` files or install packages during import, `register()`, or add-on enable.
- Pin dependency filenames, sources, versions, and SHA-256 values in the dependency reference and CI.

## Git and External Writes

- One complete logical phase per commit; commit messages describe the actual change.
- Use independent branches for risky work and prefer `git revert` over history destruction.
- Never use `git reset --hard` without explicit approval.
- Do not push, alter remotes, open or change PRs/issues, or publish releases without explicit approval.

## Verification

- Run the narrowest relevant unit test first, then static package checks, Blender extension validate/build, and real install smoke tests when applicable.
- Report results as Passed, Failed, or Not Run with a reason.
- A ZIP existing, a manifest parsing, or CI being green is not sufficient by itself; inspect package contents and runtime behavior.
- Run `git diff --check` and confirm the final worktree before claiming completion.

## Documentation and Agent Memory

- Update docs only for features, architecture, installation, release flow, or explicit requests.
- Root `AGENTS.md` contains stable rules and routing only, never live commit/run status or chat transcripts.
- Update `.agents/active/` only after a material state change. Polling without change produces no edit.
- Record branch-role, release-boundary, dependency-source, and packaging-policy changes in the same commit.
- Append decisions instead of rewriting old rationale. Move finished work to `completed/` with concise evidence.

## Windows Files

- Preserve UTF-8 BOM state and line endings. Do not use Windows PowerShell 5.1 `Set-Content`, `Out-File`, `>`, or `>>` for UTF-8 source files.
- `.bat` files use UTF-8 without BOM and CRLF, starting with `@echo off` and `chcp 65001 >nul`.
- Sort paths ordinally, not with culture-sensitive `Sort-Object`.

## Knowledge Entrypoints

- Current extension migration: `.agents/active/2.2.0-extension.md`
- Branch architecture: `.agents/reference/branch-architecture.md`
- Dependency and release policy: `.agents/reference/dependencies-and-release.md`
- Version roadmap decision: `.agents/decisions/0001-version-and-extension-roadmap.md`
- Completed 2.1 history: `.agents/completed/2.1.0-import-and-2.1.1-slimming.md`
```

- [ ] **Step 4: Create the routed knowledge documents**

Use the approved design as the source of truth. Each file has one responsibility:

- `.agents/README.md`: recovery order, index table, and update ownership.
- `.agents/active/2.2.0-extension.md`: goal, current phase, confirmed constraints, completed gates, next action, and validation record.
- `.agents/reference/branch-architecture.md`: the two baselines, archive/release/feature/upstream-PR roles, and the rule that branch lifecycle changes are recorded in the same commit.
- `.agents/reference/dependencies-and-release.md`: Blender 5.1+, Python CPython 3.13, exact RDKit filename/URL/SHA-256, no runtime network install, build/install commands, and release gates.
- `.agents/decisions/0001-version-and-extension-roadmap.md`: context, decision, consequences, and rejected mixed-2.1.1 approach.
- `.agents/completed/2.1.0-import-and-2.1.1-slimming.md`: immutable commits, exact three-file 2.1.1 scope, Blender asset counts, and tag.
- `docs/README.md`: links to development, migration, release, approved spec, and implementation plan.
- `docs/development/branch-and-release.md`: human-facing branch table and local-to-remote authorization boundary.
- `docs/migration/2.2.0-extension.md`: legacy/extension path mapping, wheel download command, validation/build/install flow, and known Windows-only boundary.

- [ ] **Step 5: Verify knowledge tracking and links**

```powershell
git check-ignore -q .agents/README.md
if ($LASTEXITCODE -eq 0) { throw '.agents knowledge must be tracked' }
git check-ignore -q skills-lock.json
if ($LASTEXITCODE -eq 0) { throw 'skills-lock.json must be tracked' }
git check-ignore -v .agents/cache/example.bin ChemBlender/wheels/example.whl .worktrees/example
rg -n 'T[B]D|T[O]DO|current HEAD|latest run' AGENTS.md .agents docs
git diff --check
```

Expected: stable knowledge is not ignored; cache/wheel/worktree paths are ignored; the placeholder scan has no matches.

- [ ] **Step 6: Commit the development workspace**

```powershell
git add -- AGENTS.md .gitignore .agents docs skills-lock.json
git diff --cached --check
git commit -m "chore: establish 2.2.0 development workspace"
```

---

### Task 5: Move the legacy source into the extension package

**Files:**
- Move: plugin `*.py`, `*.json`, and `*.blend` files into `ChemBlender/`
- Copy: `LICENSE` to `ChemBlender/LICENSE` while retaining root `LICENSE`
- Modify: `README.md`
- Create: `ChemBlender/blender_manifest.toml`
- Create from template: `ChemBlender/scripts/validate_extension.py`
- Create from template: `ChemBlender/scripts/build_extension.py`
- Create: `tests/test_repository_contract.py`

**Interfaces:**
- Consumes: the verified 2.1.1 legacy source and repository-local extension template.
- Produces: a static 2.2.0 extension tree; runtime behavior is completed in Task 6.

- [ ] **Step 1: Write the failing repository contract**

Create `tests/test_repository_contract.py`:

```python
import subprocess
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "ChemBlender"
WHEEL = "rdkit-2026.3.3-cp313-cp313-win_amd64.whl"


class RepositoryContractTests(unittest.TestCase):
    def test_extension_layout_and_manifest(self):
        manifest = tomllib.loads((EXTENSION / "blender_manifest.toml").read_text(encoding="utf-8"))
        self.assertEqual(manifest["id"], "chemblender")
        self.assertEqual(manifest["version"], "2.2.0")
        self.assertEqual(manifest["blender_version_min"], "5.1.0")
        self.assertEqual(manifest["platforms"], ["windows-x64"])
        self.assertEqual(manifest["wheels"], [f"./wheels/{WHEEL}"])
        self.assertTrue((EXTENSION / "__init__.py").exists())
        self.assertTrue((EXTENSION / "scripts" / "build_extension.py").exists())

    def test_generated_and_local_dependencies_are_not_tracked(self):
        tracked = subprocess.run(
            ["git", "ls-files", "ChemBlender/wheels/*.whl", ".agents/cache/**"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.assertEqual(tracked, "")

    def test_runtime_source_has_no_package_install(self):
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in EXTENSION.rglob("*.py")
            if "scripts" not in path.parts
        ).lower()
        self.assertNotIn("pip install", source)
        self.assertNotIn('"-m", "pip"', source)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify the extension layout is absent**

```powershell
if (-not $pythonBin) { throw 'Assign binary_path_python returned by Blender MCP to $pythonBin' }
& $pythonBin -m unittest tests.test_repository_contract -v
```

Expected: `test_extension_layout_and_manifest` fails because `ChemBlender/blender_manifest.toml` does not exist.

- [ ] **Step 3: Move only plugin runtime files**

```powershell
New-Item -ItemType Directory -Path 'ChemBlender' | Out-Null
$pluginFiles = @(
    '__init__.py', 'auto_load.py', 'Chem_data.py', 'chem_utils.py', 'crys_utils.py',
    'ex_package.py', 'mesh.py', 'node.py', 'output.py', 'panel.py', 'periodictable.py',
    'read.py', 'scaffold.py', '_math.py', 'GN_menu.json', 'GN_menu_En.json',
    'Chem_Nodes.blend', 'Chem_Nodes_En.blend'
)
foreach ($pluginFile in $pluginFiles) {
    git mv -- $pluginFile (Join-Path 'ChemBlender' $pluginFile)
}
Copy-Item -LiteralPath 'LICENSE' -Destination 'ChemBlender\LICENSE'
```

- [ ] **Step 4: Add the exact extension manifest**

Create `ChemBlender/blender_manifest.toml`:

```toml
schema_version = "1.0.0"
id = "chemblender"
version = "2.2.0"
name = "ChemBlender"
tagline = "Molecular and crystal structure tools for Geometry Nodes"
maintainer = "LiHaodong"
type = "add-on"
website = "https://www.chemblender.com"
blender_version_min = "5.1.0"
license = ["SPDX:GPL-3.0-or-later"]
platforms = ["windows-x64"]
wheels = ["./wheels/rdkit-2026.3.3-cp313-cp313-win_amd64.whl"]

[permissions]
files = "Import molecular and crystal structure files selected by the user"

[build]
paths_exclude_pattern = [
  "__pycache__/",
  "*.zip",
  "tests/",
]
```

- [ ] **Step 5: Reuse only the required template build scripts**

```powershell
New-Item -ItemType Directory -Path 'ChemBlender\scripts' | Out-Null
Copy-Item -LiteralPath '.agents\skills\blender-mcp-skills\templates\extension_addon\scripts\validate_extension.py' -Destination 'ChemBlender\scripts\validate_extension.py'
Copy-Item -LiteralPath '.agents\skills\blender-mcp-skills\templates\extension_addon\scripts\build_extension.py' -Destination 'ChemBlender\scripts\build_extension.py'
```

Do not copy example panels/operators, `preferences.py`, `deps/site-packages`, `dependency_manager.py`, or `sync_and_reload.py`.

- [ ] **Step 6: Update the root README for the development workspace**

Replace the legacy one-line README with a concise project entrypoint that states:

```markdown
# ChemBlender

ChemBlender provides molecular and crystal structure modeling and visualization tools for Blender Geometry Nodes.

The maintained 2.2.x line is a Blender Extension. Extension source and `blender_manifest.toml` live in `ChemBlender/`; the repository root is the development workspace.

## Development

- Documentation index: `docs/README.md`
- Extension migration and local build: `docs/migration/2.2.0-extension.md`
- Branch and release workflow: `docs/development/branch-and-release.md`

RDKit is bundled into release packages by CI. Wheel files are downloaded locally when needed and are not tracked by Git.

Project website: https://www.chemblender.com
```

- [ ] **Step 7: Run the static contract**

```powershell
if (-not $pythonBin) { throw 'Assign binary_path_python returned by Blender MCP to $pythonBin' }
& $pythonBin -m unittest tests.test_repository_contract -v
```

Expected: all three tests pass; the actual Blender validator is intentionally deferred until the ignored wheel is present.

---

### Task 6: Convert registration and dependency behavior to extension-native lifecycle

**Files:**
- Replace: `ChemBlender/__init__.py`
- Create: `ChemBlender/extension.py`
- Replace from template and adapt: `ChemBlender/auto_load.py`
- Modify: `ChemBlender/ex_package.py`
- Modify: `ChemBlender/panel.py`
- Create: `tests/blender_smoke.py`

**Interfaces:**
- Consumes: moved legacy code and template autoload implementation.
- Produces: repeatable extension register/unregister/reload behavior with offline RDKit detection.

- [ ] **Step 1: Add a failing source lifecycle contract**

Extend `tests/test_repository_contract.py`:

```python
    def test_extension_uses_minimal_autoload_entrypoint(self):
        init_source = (EXTENSION / "__init__.py").read_text(encoding="utf-8")
        auto_load_source = (EXTENSION / "auto_load.py").read_text(encoding="utf-8")
        self.assertNotIn("bl_info", init_source)
        self.assertIn("auto_load.init()", init_source)
        self.assertIn("auto_load.register()", init_source)
        self.assertIn("auto_load.unregister()", init_source)
        self.assertIn('"wheels"', auto_load_source)
        self.assertIn("clear_submodule_cache", auto_load_source)
```

Run:

```powershell
if (-not $pythonBin) { throw 'Assign binary_path_python returned by Blender MCP to $pythonBin' }
& $pythonBin -m unittest tests.test_repository_contract.RepositoryContractTests.test_extension_uses_minimal_autoload_entrypoint -v
```

Expected: failure because the legacy `bl_info` and manual registration remain.

- [ ] **Step 2: Replace the package entrypoint**

Replace `ChemBlender/__init__.py` with:

```python
from . import auto_load


def register():
    auto_load.init()
    auto_load.register()


def unregister():
    auto_load.unregister()
```

- [ ] **Step 3: Adopt the template autoloader**

Copy `.agents/skills/blender-mcp-skills/templates/extension_addon/auto_load.py` to `ChemBlender/auto_load.py`. Keep its excluded directories, submodule cache clearing, dependency ordering, safe class registration, reverse module unregister, and reverse class unregister unchanged unless a failing ChemBlender runtime smoke check proves an adaptation necessary.

- [ ] **Step 4: Move legacy package behavior into `extension.py`**

Start from the former `ChemBlender/__init__.py` content before Step 2, remove `bl_info`, imports used only for manual class lists, `classes`, `auto_cls`, `panel_cls`, and every direct class registration loop. Keep menu construction and node-group loading behavior.

Its module hooks must follow this shape:

```python
def register():
    global geo_node_group
    json_file = "GN_menu.json" if language else "GN_menu_En.json"
    with open(os.path.join(dir_path, json_file), "r", encoding="utf-8") as stream:
        geo_node_group = json.load(stream)

    bpy.types.NODE_MT_add.append(add_chem_button)
    bpy.types.Object.cif_original = bpy.props.PointerProperty(type=CIF_Structure)
    bpy.types.Object.cif_current = bpy.props.PointerProperty(type=CIF_Structure)
    bpy.types.Scene.my_tool = bpy.props.PointerProperty(type=CHEM_texts)
    cat_generator()


def unregister():
    clear_generated_menus()
    try:
        bpy.types.NODE_MT_add.remove(add_chem_button)
    except (ValueError, RuntimeError):
        pass

    for owner, name in (
        (bpy.types.Object, "cif_original"),
        (bpy.types.Object, "cif_current"),
        (bpy.types.Scene, "my_tool"),
    ):
        if hasattr(owner, name):
            delattr(owner, name)
```

Change `cat_list` to store `(menu_type, draw_callback)` pairs. Implement `clear_generated_menus()` so each callback is removed from `NODE_MT_chem_GN_menu`, each generated class is safely unregistered, and `cat_list` is cleared. This is required for repeated reloads; do not leave the legacy dynamic menu classes registered.

- [ ] **Step 5: Remove runtime package installation**

Port only the focused behavior from `b040f57`:

- `ChemBlender/ex_package.py` retains `safe_check_rdkit()` and contains no Blender operator, mirror list, subprocess, or pip command.
- `ChemBlender/panel.py` displays RDKit available/unavailable status and tells the user to reinstall the packaged extension when unavailable.
- The manifest has no `network` permission.

- [ ] **Step 6: Add the Blender smoke script**

Create `tests/blender_smoke.py` to accept the built ZIP after `--`, install it into `user_default` with `overwrite=True`, and verify the complete lifecycle:

```python
import sys
from importlib.metadata import version
from pathlib import Path

import bpy


def assert_enabled(module_key):
    assert module_key in bpy.context.preferences.addons
    assert hasattr(bpy.types.Object, "cif_original")
    assert hasattr(bpy.types.Object, "cif_current")
    assert hasattr(bpy.types.Scene, "my_tool")


def assert_disabled(module_key):
    assert module_key not in bpy.context.preferences.addons
    assert not hasattr(bpy.types.Object, "cif_original")
    assert not hasattr(bpy.types.Object, "cif_current")
    assert not hasattr(bpy.types.Scene, "my_tool")


arguments = sys.argv[sys.argv.index("--") + 1 :]
assert len(arguments) == 1, "expected one extension ZIP path"
package = Path(arguments[0]).resolve()
assert package.is_file(), package

result = bpy.ops.extensions.package_install_files(
    filepath=str(package),
    repo="user_default",
    enable_on_install=True,
    overwrite=True,
)
assert result == {"FINISHED"}, result

module_key = "bl_ext.user_default.chemblender"
assert_enabled(module_key)

import rdkit
assert rdkit.__version__
assert version("rdkit") == "2026.3.3"

for _ in range(2):
    assert bpy.ops.preferences.addon_disable(module=module_key) == {"FINISHED"}
    assert_disabled(module_key)
    assert bpy.ops.preferences.addon_enable(module=module_key) == {"FINISHED"}
    assert_enabled(module_key)

assert bpy.ops.preferences.addon_disable(module=module_key) == {"FINISHED"}
assert_disabled(module_key)
print("PASS: ChemBlender extension lifecycle")
```

- [ ] **Step 7: Run the static tests and commit the migration**

```powershell
if (-not $pythonBin) { throw 'Assign binary_path_python returned by Blender MCP to $pythonBin' }
& $pythonBin -m unittest discover -s tests -p 'test_*.py' -v
git diff --check
git add -- ChemBlender tests README.md docs/migration/2.2.0-extension.md .agents/active/2.2.0-extension.md
git commit -m "refactor: migrate ChemBlender to extension layout"
```

Expected: repository contract passes. The Blender smoke script is present but is run only after packaging in Task 7.

---

### Task 7: Add reproducible wheel download, package CI, and real runtime validation

**Files:**
- Create: `.github/workflows/extension-package.yml`
- Modify: `.agents/reference/dependencies-and-release.md`
- Modify: `.agents/active/2.2.0-extension.md`
- Modify: `docs/development/branch-and-release.md`
- Modify: `docs/migration/2.2.0-extension.md`

**Interfaces:**
- Consumes: 2.2.0 extension source, exact RDKit metadata, Blender 5.1.2 Windows ZIP.
- Produces: validated `chemblender-2.2.0.zip` artifact without tracking the wheel.

- [ ] **Step 1: Download and verify the local wheel without committing it**

```powershell
$wheelDir = 'ChemBlender\wheels'
$wheelPath = Join-Path $wheelDir 'rdkit-2026.3.3-cp313-cp313-win_amd64.whl'
New-Item -ItemType Directory -Path $wheelDir -Force | Out-Null
Invoke-WebRequest -Uri 'https://files.pythonhosted.org/packages/68/d0/5de3d0d7e66f0e7e7795ab94a53b826e257176c15c9ee79f15621ac040ed/rdkit-2026.3.3-cp313-cp313-win_amd64.whl' -OutFile $wheelPath
$actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $wheelPath).Hash.ToLowerInvariant()
if ($actualHash -ne 'f8bd59b24e128c9c70c975bfb1920cf610ba3096439a24ca2850eb861e767c48') { throw 'RDKit wheel hash mismatch' }
git check-ignore -v $wheelPath
```

- [ ] **Step 2: Run the Blender MCP and build gates**

Query Blender MCP for version, executable, Python executable, runtime system, and extension root. Save the returned runtime facts in an ignored `.agents/cache/blender-mcp-info.json`, then run:

```powershell
if (-not $blenderBin) { throw 'Assign binary_path returned by Blender MCP to $blenderBin' }
if (-not $pythonBin) { throw 'Assign binary_path_python returned by Blender MCP to $pythonBin' }
& $pythonBin ChemBlender/scripts/validate_extension.py --source-path ChemBlender --blender $blenderBin
& $pythonBin ChemBlender/scripts/build_extension.py --blender $blenderBin
```

Expected: local preflight, Blender extension validation, and build all pass; generated ZIP is outside Git tracking.

- [ ] **Step 3: Run a clean extension-native install smoke test**

```powershell
if (-not $blenderBin) { throw 'Assign binary_path returned by Blender MCP to $blenderBin' }
$package = Get-ChildItem -Path 'ChemBlender' -Filter 'chemblender-2.2.0.zip' -File | Select-Object -First 1
if (-not $package) { throw '2.2.0 package not found' }
& $blenderBin --background --factory-startup --python tests/blender_smoke.py -- $package.FullName
```

Expected: install operator finishes; `bl_ext.user_default.chemblender` enables; RDKit 2026.3.3 imports; two disable/enable cycles pass; unregister removes properties.

- [ ] **Step 4: Add the Windows package workflow**

Create `.github/workflows/extension-package.yml` with:

```yaml
name: extension-package

on:
  pull_request:
  push:
    branches: [main]
    tags: ["v*"]

jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - name: Verify tag matches manifest
        if: github.ref_type == 'tag'
        shell: pwsh
        run: |
          $manifestVersion = python -c "import tomllib; print(tomllib.load(open('ChemBlender/blender_manifest.toml','rb'))['version'])"
          $tagVersion = $env:GITHUB_REF_NAME.TrimStart('v')
          if ($manifestVersion -ne $tagVersion) { throw "Tag $tagVersion does not match manifest $manifestVersion" }
      - name: Download pinned RDKit wheel
        shell: pwsh
        run: |
          $wheelDir = "ChemBlender/wheels"
          $wheelPath = "$wheelDir/rdkit-2026.3.3-cp313-cp313-win_amd64.whl"
          New-Item -ItemType Directory -Path $wheelDir -Force | Out-Null
          Invoke-WebRequest -Uri "https://files.pythonhosted.org/packages/68/d0/5de3d0d7e66f0e7e7795ab94a53b826e257176c15c9ee79f15621ac040ed/rdkit-2026.3.3-cp313-cp313-win_amd64.whl" -OutFile $wheelPath
          $hash = (Get-FileHash -Algorithm SHA256 $wheelPath).Hash.ToLowerInvariant()
          if ($hash -ne "f8bd59b24e128c9c70c975bfb1920cf610ba3096439a24ca2850eb861e767c48") { throw "RDKit wheel hash mismatch" }
      - name: Download Blender 5.1.2
        shell: pwsh
        run: |
          Invoke-WebRequest -Uri "https://download.blender.org/release/Blender5.1/blender-5.1.2-windows-x64.zip" -OutFile "blender.zip"
          Invoke-WebRequest -Uri "https://download.blender.org/release/Blender5.1/blender-5.1.2.sha256" -OutFile "blender.sha256"
          $line = Get-Content "blender.sha256" | Where-Object { $_ -match "blender-5.1.2-windows-x64.zip$" }
          if (-not $line) { throw "Blender checksum entry missing" }
          $expected = ($line -split "\s+")[0].ToLowerInvariant()
          $actual = (Get-FileHash -Algorithm SHA256 "blender.zip").Hash.ToLowerInvariant()
          if ($actual -ne $expected) { throw "Blender archive hash mismatch" }
          Expand-Archive -LiteralPath "blender.zip" -DestinationPath "blender"
      - name: Test, validate, build, and install
        shell: pwsh
        run: |
          $blender = (Get-ChildItem "blender" -Recurse -Filter "blender.exe" | Select-Object -First 1).FullName
          python -m unittest discover -s tests -p "test_*.py" -v
          python ChemBlender/scripts/build_extension.py --blender $blender
          $package = (Get-ChildItem "ChemBlender" -Filter "chemblender-2.2.0.zip" | Select-Object -First 1).FullName
          & $blender --background --factory-startup --python tests/blender_smoke.py -- $package
      - uses: actions/upload-artifact@v4
        with:
          name: chemblender-2.2.0-windows-x64
          path: ChemBlender/chemblender-2.2.0.zip
          if-no-files-found: error
```

- [ ] **Step 5: Verify the tag/manifest consistency gate**

Inspect the workflow and confirm the `Verify tag matches manifest` step runs only for tags, strips the leading `v`, and fails when the two semantic versions differ.

- [ ] **Step 6: Finish Agent memory and documentation**

Update `.agents/active/2.2.0-extension.md` with the exact local validation commands and results. Once every gate passes, move its concise result to `.agents/completed/2.2.0-extension-migration.md` and remove the active file. Update `docs/migration/2.2.0-extension.md` with the manual wheel download, build, install, module key, and Windows-only limitation.

- [ ] **Step 7: Commit the package workflow**

```powershell
git add -- .github .agents docs ChemBlender tests
git diff --cached --check
git commit -m "ci: build and validate ChemBlender 2.2.0"
```

---

### Task 8: Final local audit and remote handoff

**Files:** None unless the audit finds a task-scoped defect.

**Interfaces:**
- Consumes: completed local 2.1.1 and 2.2.0 histories.
- Produces: evidence-backed push/PR/release recommendation; no external write.

- [ ] **Step 1: Verify release ancestry and branch roles**

```powershell
git status --short --branch
git log --graph --decorate --oneline --all -20
git merge-base --is-ancestor v2.1.1 feat/2.2.0-extension
git diff --name-only 78c2d8d..v2.1.1
git branch -vv
git remote -v
```

Expected: feature branch descends from `v2.1.1`; the 2.1.1 diff has exactly three files; remotes are unchanged.

- [ ] **Step 2: Re-run all local release gates**

```powershell
if (-not $blenderBin) { throw 'Assign binary_path returned by Blender MCP to $blenderBin' }
if (-not $pythonBin) { throw 'Assign binary_path_python returned by Blender MCP to $pythonBin' }
& $pythonBin -m unittest discover -s tests -p 'test_*.py' -v
& $pythonBin ChemBlender/scripts/validate_extension.py --source-path ChemBlender --blender $blenderBin
& $pythonBin ChemBlender/scripts/build_extension.py --blender $blenderBin
$package = Get-ChildItem -Path 'ChemBlender' -Filter 'chemblender-2.2.0.zip' -File | Select-Object -First 1
& $blenderBin --background --factory-startup --python tests/blender_smoke.py -- $package.FullName
git diff --check
git status --short
```

Expected: all tests, validate, build, and smoke checks pass; worktree is clean except ignored wheel/build/cache files.

- [ ] **Step 3: Report the exact remote actions requiring approval**

Present, but do not run:

```powershell
git push origin archive/extension-spike-20260707
git push origin release/2.1.1
git push origin main
git push origin v2.1.1
git push -u origin feat/2.2.0-extension
```

Recommend pushing 2.1.1 first, validating remote CI if added to that line, then pushing the 2.2.0 feature branch and opening a draft PR into the maintained `origin/main`. A future upstream PR must instead start from a freshly fetched `upstream/main`.
