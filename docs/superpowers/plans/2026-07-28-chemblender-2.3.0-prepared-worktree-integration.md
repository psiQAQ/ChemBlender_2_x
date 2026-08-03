# ChemBlender 2.3.0 Prepared Worktree Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Status:** Draft / Blocked

**Goal:** Preserve executable integration instructions for the completed
Wave 2 POSCAR syntax and Wave 4 legacy-fixture worktrees without integrating
either branch before its ordered Wave gate.

**Architecture:** Each prepared branch remains an immutable source of ordered
commits. A future active Wave branch, created from the then-current maintained
integration line, re-audits the source tip before cherry-picking. Wave 2 and
Wave 4 use separate integration worktrees, verification gates and checkpoint
commits.

**Tech Stack:** Git worktrees, Python 3.13, standard-library `unittest`,
Blender 5.1.2, PowerShell.

## Global Constraints

- Enforce one active Wave and the order `0 → 1 → 2 → 3 → 4`.
- This plan is blocked until the complete Wave 1 gate passes. Completing the
  RDKit substage does not complete Wave 1.
- Wave 2 POSCAR integration requires completed Wave 1 evidence and formal
  Wave 2 activation.
- Wave 4 fixture integration requires completed Wave 2 and Wave 3 gates plus
  formal Wave 4 activation.
- Re-audit live source HEADs before integration. If either source HEAD differs
  from the reviewed value below, inspect every added commit and update this
  plan in a separate documentation commit before cherry-picking.
- Integrate and verify each Wave independently. Do not combine Wave 2 and
  Wave 4 commits in one branch, worktree, verification run or checkpoint.
- Any required verification marked `Failed` blocks the current gate and every
  later Wave.
- On an unresolved cherry-pick conflict, run `git cherry-pick --abort`.
  Revert already integrated work later with `git revert`; never use
  `git reset --hard`.
- Preserve both completed source worktrees:
  `.worktrees/2.3.0-wave2-poscar-syntax` and
  `.worktrees/2.3.0-wave4-legacy-fixtures`.
- Do not push, modify remotes, create a PR, activate a Wave, publish a tag or
  create a Release while authoring or executing this integration plan.

---

## Live Evidence Recorded on 2026-07-28

All SHAs below were checked from local refs and worktrees without fetching or
otherwise operating on a remote.

| Role | Branch / worktree | Observed HEAD | Merge base | Worktree |
| --- | --- | --- | --- | --- |
| Maintained integration line | `main` | `b749b04df0b57dc73993978bffa79c110da6ffd2` | — | clean |
| Wave 1 | `feat/2.3.0-wave1-native-molecular-grid` | `d36f4b27cc9a4f00d223f0c39272e1422a6375d4` | `main`: `b749b04df0b57dc73993978bffa79c110da6ffd2` | clean |
| Wave 2 prepared POSCAR | `feat/2.3.0-wave2-poscar-syntax` | `ed5b1ca03d81fb9f8cc51bad4532e18bed46448a` | Wave 1: `7d0524d017de4e003d1bb3982b752d013b5d910f` | clean |
| Wave 4 prepared fixtures | `feat/2.3.0-wave4-legacy-fixtures` | `e26319dd7697e49373840e00dbfbb13270b5cc42` | `main`: `b749b04df0b57dc73993978bffa79c110da6ffd2` | clean |

### Wave 1 gate assessment

Confirmed evidence:

- The Wave 1 cursor records topology, extXYZ and RDKit Tasks 1–8 through
  `d36f4b27cc9a4f00d223f0c39272e1422a6375d4`.
- A fresh Blender-Python full run completed `1375` tests with `28` skipped and
  `0` failed.
- The cursor records Blender 5.1.2 validate/build/install/lifecycle and final
  RDKit specification/quality reviews as passed.

Blocking evidence:

- The same authoritative cursor says `Wave 1 remains in progress`.
- Cube Task 1 has not started, so the queued Wave 1 success criterion
  `Cube dataset/semantic/unit/surface UI` is not met.
- The extXYZ `preview_ready <= 0.5 s` gate is deferred until after Cube.
- The cursor records `Remote CI: Not Run`; no remote CI query was performed
  because this plan-only task prohibits remote operations.
- Wave 1 has no completed-Wave transition on the maintained integration line;
  local `main` still contains the earlier single-active Wave 0 state.

Therefore the complete Wave 1 gate is **Blocked**. No Wave 2 activation or
prepared-worktree integration is authorized by this plan.

The supplied review recommends a separate `W1-CUBE-PRE-GATE`. That is an
advisory Wave 1 decision, not an integration action; this plan neither creates
nor executes it.

### Prepared Wave 2 evidence

Reviewed source sequence:

1. `f1add7ce9bcdeb57049367f17f15431d78a365c3`
   `feat: add POSCAR syntax parser`
2. `fcc4f8a5f234576cb7174b4a01760754dfeeca20`
   `fix: bound POSCAR sniffing and parse velocity modes`
3. `30e9a3fbabb3aec03711896b77063d1ae2e46bd2`
   `fix: ignore trailing POSCAR velocity blanks`
4. `ed5b1ca03d81fb9f8cc51bad4532e18bed46448a`
   `fix: parse POSCAR lattice velocity blocks`

Expected file delta:

- Modify: `.agents/reference/code-architecture-guide.md`
- Create: `ChemBlender/core/formats/poscar.py`
- Create/modify: `tests/fixtures/poscar/negative-scale.vasp`
- Create: `tests/fixtures/poscar/vasp4-counts.POSCAR`
- Create/modify: `tests/fixtures/poscar/velocities.CONTCAR`
- Create/modify: `tests/test_poscar_syntax.py`

Existing branch evidence records a broader focused matrix of `57 passed,
2 skipped`; the old `7d0524d` base and POSCAR tip also recorded the same two
full-suite baseline failures. A fresh narrow run on the prepared tip passed
`tests.test_poscar_syntax` 22/22. These results are provenance only: the future
target branch must rerun every required test and may not inherit the old
baseline-failure classification.

### Prepared Wave 4 evidence

Reviewed source sequence:

1. `ab29560a54557ca4bb794e9e8043cd2110abc10b`
   `test: add released legacy blend fixtures`
2. `e26319dd7697e49373840e00dbfbb13270b5cc42`
   `test: lock complete crystal fixture metadata`

Expected file delta:

- Create: `tests/fixtures/legacy-blend/README.md`
- Create: `tests/fixtures/legacy-blend/chemblender-2.1-molecule.blend`
- Create: `tests/fixtures/legacy-blend/chemblender-2.2-crystal.blend`
- Create: `tests/fixtures/legacy-blend/chemblender-2.2-edited-scaffold.blend`
- Create: `tests/test_legacy_fixture_inventory.py`

Fresh inventory verification passed 3/3. Reviewed SHA-256 locks are:

- `chemblender-2.1-molecule.blend`:
  `36b05c3cacbcc067714615a49df35cf20973bc8122329194ddaecd249df6c3d4`
- `chemblender-2.2-crystal.blend`:
  `f2995e826762a85bfb6854e314483175c3d39c2cceef109db3f395ab2e83c06a`
- `chemblender-2.2-edited-scaffold.blend`:
  `a6af8e232fe7b934bf850f8e6b24d396596b79cc1fd38e8ff6eb071c50bf8740`

---

### Task 1: Revalidate the Wave 1 gate and target integration line

**Files:**

- Read: `AGENTS.md`
- Read: `.agents/README.md`
- Read: current `.agents/active/` and `.agents/queued/`
- Read: `docs/superpowers/plans/2026-07-23-chemblender-2.3.0-master-sequencing.md`
- Read: the Wave 1 completed record and exact gate evidence when they exist

**Interfaces:**

- Consumes: the then-current maintained branch, Wave 1 tip and gate evidence.
- Produces: a Wave 1 `Passed` or `Blocked` integration decision.

- [ ] **Step 1: Inspect local topology without changing it**

```powershell
git status --short
git branch --show-current
git worktree list --porcelain
git rev-parse main
git rev-parse feat/2.3.0-wave1-native-molecular-grid
git merge-base main feat/2.3.0-wave1-native-molecular-grid
git log --reverse --format="%H %s" main..feat/2.3.0-wave1-native-molecular-grid
```

Expected: every involved worktree is clean and the intended maintained
integration branch is identified. If the maintained target has changed, record
its exact branch and SHA before continuing.

- [ ] **Step 2: Require complete Wave 1 authority**

Confirm all of the following from tracked authority:

- Wave 1 has a completed record and is no longer the active Wave.
- Cube Tasks 1–6 and the Wave 1 pre-alpha performance gate are completed.
- Full tests, `compileall`, documentation contracts, `git diff --check`,
  Blender 5.1.2 validate/build/ZIP/install/lifecycle and the exact Wave 1
  product smoke are `Passed`.
- A successful remote CI run belongs to the exact Wave 1 gate SHA. This plan
  does not push or dispatch a workflow; the evidence must already exist.
- No required verification is `Failed`, unexpectedly skipped or `Not Run`.

Expected today: `Blocked` because Cube, the performance gate, completed-Wave
transition and remote CI evidence are missing.

- [ ] **Step 3: Stop on an incomplete gate**

If any item in Step 2 is absent, record the missing evidence and stop. Do not
activate Wave 2, create an integration branch or cherry-pick a prepared commit.

### Task 2: Re-audit and authorize the prepared Wave 2 source

**Files:**

- Read: `.agents/active/2.3.0-wave-2-native-crystal.md`
- Read: `docs/superpowers/plans/2026-07-23-chemblender-2.3.0-wave-2-poscar-contcar.md`
- Read: `.agents/reference/code-architecture-guide.md`

**Interfaces:**

- Consumes: a completed Wave 1 gate and formally activated Wave 2 branch.
- Produces: an exact, reviewed POSCAR Task 1 cherry-pick sequence.

- [ ] **Step 1: Require formal Wave 2 activation**

Verify there is exactly one active Wave, it is Wave 2, and the integration
target branch/worktree named by that active cursor starts from the accepted
post-Wave-1 integration line. Run the documentation single-active-Wave test
before touching source commits.

- [ ] **Step 2: Re-audit the prepared source**

```powershell
$source = "feat/2.3.0-wave2-poscar-syntax"
git rev-parse $source
git merge-base HEAD $source
git log --reverse --format="%H %P %s" 7d0524d017de4e003d1bb3982b752d013b5d910f..$source
git diff --name-status 7d0524d017de4e003d1bb3982b752d013b5d910f..$source
```

Expected: source HEAD is
`ed5b1ca03d81fb9f8cc51bad4532e18bed46448a`, with exactly the four reviewed
commits and expected files above.

If the tip, order or file delta differs, inspect every added commit, update
this plan and commit that documentation change before integration. Do not use
the recorded SHAs blindly.

### Task 3: Integrate and gate Wave 2 POSCAR Task 1

**Files:**

- Integrate: the four reviewed Wave 2 commits
- Manually reconcile: `.agents/reference/code-architecture-guide.md`
- Verify: `tests/test_poscar_syntax.py`
- Verify: current target-branch test and documentation suites

**Interfaces:**

- Consumes: the formally active Wave 2 target and authorized source sequence.
- Produces: POSCAR Task 1 on the active Wave 2 branch, independently verified
  and checkpointed.

- [ ] **Step 1: Cherry-pick the reviewed sequence atomically**

```powershell
git cherry-pick `
  f1add7ce9bcdeb57049367f17f15431d78a365c3 `
  fcc4f8a5f234576cb7174b4a01760754dfeeca20 `
  30e9a3fbabb3aec03711896b77063d1ae2e46bd2 `
  ed5b1ca03d81fb9f8cc51bad4532e18bed46448a
```

Expected: four commits are applied in order.

`.agents/reference/code-architecture-guide.md` is an expected manual
coordination point. If it conflicts, compare the current-Wave and prepared
stages, then edit the merged file so it retains every Wave 1 module record and
adds the POSCAR module responsibility. Do not resolve the whole file with
`ours` or `theirs`. Stage the manually reconciled file and continue.

For any unresolved or unexpected conflict:

```powershell
git cherry-pick --abort
git status --short
```

Expected: the target returns to its pre-sequence HEAD and no integration is
claimed.

- [ ] **Step 2: Run POSCAR focused verification first**

```powershell
& $pythonBin -m unittest tests.test_poscar_syntax -v
& $pythonBin -m unittest `
  tests.test_ase_adapter `
  tests.test_quantum_visualization_docs -v
```

Expected: all dependency-free POSCAR syntax tests pass. Optional-dependency
skips must have the previously accepted reason; any unexpected skip or failure
blocks the gate.

- [ ] **Step 3: Run the current target full gate**

```powershell
& $pythonBin -m unittest discover -s tests -p "test_*.py" -v
& $pythonBin -m compileall -q ChemBlender worker tests
& $pythonBin -m unittest tests.test_quantum_visualization_docs -v
git diff --check
git status --short
```

Expected: zero failures, documentation coverage includes both Wave 1 and
POSCAR responsibilities, and only the intended integration state exists. The
old matching pair of baseline failures is not accepted as a current result.

- [ ] **Step 4: Record the independent Wave 2 checkpoint**

Update the active Wave 2 cursor with the four source SHAs, focused/full counts,
accepted skips, manual architecture-guide reconciliation and verification
results. Commit only that checkpoint:

```powershell
git add `
  .agents/active/2.3.0-wave-2-native-crystal.md `
  docs/superpowers/plans/2026-07-28-chemblender-2.3.0-prepared-worktree-integration.md
git commit -m "chore: checkpoint native POSCAR syntax integration"
```

Stop after the Wave 2 Task 1 review/gate. Do not begin POSCAR Task 2 until this
integration is independently reviewed and every required result is `Passed`.
Do not push.

### Task 4: Wait for and re-audit the Wave 4 source

**Files:**

- Read: `.agents/active/2.3.0-wave-4-migration-release.md`
- Read: `docs/superpowers/plans/2026-07-23-chemblender-2.3.0-wave-4-legacy-migration.md`
- Read: prepared fixture README and inventory test

**Interfaces:**

- Consumes: completed Wave 2 and Wave 3 gates plus formal Wave 4 activation.
- Produces: an exact, reviewed legacy-fixture cherry-pick sequence.

- [ ] **Step 1: Require ordered Wave gates**

Confirm Wave 2 and Wave 3 have completed records, no required failure or
unaccepted `Not Run`, and exactly one active Wave exists: Wave 4. Wave 1
completion alone never authorizes this integration.

- [ ] **Step 2: Re-audit the prepared source**

```powershell
$source = "feat/2.3.0-wave4-legacy-fixtures"
git rev-parse $source
git merge-base HEAD $source
git log --reverse --format="%H %P %s" b749b04df0b57dc73993978bffa79c110da6ffd2..$source
git diff --name-status b749b04df0b57dc73993978bffa79c110da6ffd2..$source
```

Expected: source HEAD is
`e26319dd7697e49373840e00dbfbb13270b5cc42`, with exactly the two reviewed
commits and expected files above. If it differs, audit additions and update
this plan before integration.

### Task 5: Integrate and gate Wave 4 legacy fixtures

**Files:**

- Integrate: the two reviewed Wave 4 commits
- Verify: `tests/test_legacy_fixture_inventory.py`
- Verify: the three hash-locked `.blend` fixtures in Blender 5.1+

**Interfaces:**

- Consumes: the formally active Wave 4 target and authorized fixture sequence.
- Produces: legacy migration Task 1 fixtures, independently verified and
  checkpointed.

- [ ] **Step 1: Cherry-pick the reviewed sequence atomically**

```powershell
git cherry-pick `
  ab29560a54557ca4bb794e9e8043cd2110abc10b `
  e26319dd7697e49373840e00dbfbb13270b5cc42
```

Expected: two commits are applied in order.

The three `.blend` files are hash-locked binary evidence. If a fixture path or
binary conflicts, stop immediately:

```powershell
git cherry-pick --abort
git status --short
```

Do not select `ours` or `theirs`, resave a fixture or regenerate a replacement.

- [ ] **Step 2: Verify the fixture inventory**

```powershell
& $pythonBin -m unittest tests.test_legacy_fixture_inventory -v
```

Expected: exact filenames, byte sizes, companion metadata and all three
SHA-256 values match the reviewed inventory.

- [ ] **Step 3: Reopen every fixture in an isolated Blender 5.1+ process**

```powershell
$smokeRoot = Join-Path ([IO.Path]::GetTempPath()) `
  ("cb-wave4-fixtures-" + [guid]::NewGuid().ToString("N"))
$env:BLENDER_USER_RESOURCES = Join-Path $smokeRoot "resources"
New-Item -ItemType Directory -Force -Path $env:BLENDER_USER_RESOURCES |
  Out-Null

$fixtures = @(
  "tests/fixtures/legacy-blend/chemblender-2.1-molecule.blend",
  "tests/fixtures/legacy-blend/chemblender-2.2-crystal.blend",
  "tests/fixtures/legacy-blend/chemblender-2.2-edited-scaffold.blend"
)

foreach ($fixture in $fixtures) {
  $fixturePath = (Resolve-Path $fixture).Path
  $expr = @"
import bpy
bpy.ops.wm.open_mainfile(filepath=r"$fixturePath")
assert bpy.app.version >= (5, 1, 0), bpy.app.version
assert len(bpy.data.libraries) == 0, tuple(lib.filepath for lib in bpy.data.libraries)
external = [
    image.name
    for image in bpy.data.images
    if image.source == "FILE" and image.filepath and image.packed_file is None
]
assert not external, external
print("PASS: legacy fixture reopen")
"@
  & $blenderBin --background --factory-startup --python-exit-code 1 `
    --python-expr $expr
  if ($LASTEXITCODE -ne 0) { throw "fixture reopen failed: $fixture" }
}
```

Expected: each process exits zero, the file opens under Blender 5.1+, and no
linked library or unpacked external image is present.

- [ ] **Step 4: Run the current target full gate**

```powershell
& $pythonBin -m unittest discover -s tests -p "test_*.py" -v
& $pythonBin -m compileall -q ChemBlender worker tests
& $pythonBin -m unittest tests.test_quantum_visualization_docs -v
git diff --check
git status --short
```

Expected: zero failures and no fixture hash change.

- [ ] **Step 5: Record the independent Wave 4 checkpoint**

Update the active Wave 4 cursor with both source SHAs, inventory/full counts,
the three Blender reopen results, library/image inspection and exact fixture
hashes. Commit only that checkpoint:

```powershell
git add `
  .agents/active/2.3.0-wave-4-migration-release.md `
  docs/superpowers/plans/2026-07-28-chemblender-2.3.0-prepared-worktree-integration.md
git commit -m "chore: checkpoint legacy fixture integration"
```

Stop after the Wave 4 Task 1 review/gate. Do not begin migration Task 2 until
every required result is `Passed`. Do not push.

## Plan Stop Boundary

This document authorizes no integration now. Its execution remains blocked by
the incomplete Wave 1 gate. When the preconditions eventually pass, it still
permits only the separately gated Wave 2 POSCAR Task 1 and, much later, the
separately gated Wave 4 legacy fixture Task 1. It never authorizes merge,
rebase, push, PR, tag, Release or deletion of the prepared source worktrees.
