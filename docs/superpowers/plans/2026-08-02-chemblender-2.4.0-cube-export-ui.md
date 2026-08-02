# ChemBlender 2.4.0 Native Cube Export UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task by task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose native Cube export through the existing Project Browser
operator with exact selected-grid projection, explicit multi-dataset choice,
preview confirmation, cancellable atomic writing and installed native re-import
proof.

**Architecture:** Extend only `ChemBlender.ui.export` selection and dispatch.
The core Cube exporter remains the sole scientific validation, snapshot,
serialization and publication boundary. Update the catalog once and regenerate
its documents.

**Tech Stack:** Python 3.13, `unittest`, existing ChemBlender native Cube
reader/exporter, Blender 5.1.2 Extensions.

## Global Constraints

- The ordinary Cube core merge
  `cd265d95c3cc73cae5355657cc0a5a8f1931d98b` must be an ancestor. The
  implementation baseline is the then-current `origin/main` recorded by Task 0
  after Task 9 integration; do not hardcode the older merge as the new branch
  baseline.
- Follow
  `docs/superpowers/specs/2026-08-02-chemblender-2.4.0-cube-export-ui-design.md`.
- Reuse the existing operator, `ExportSelection`, preview and `ExportJob`.
- Do not change Cube core serialization/readiness, models, sidecar schema,
  Reader API token, dependency set, workflows, manifest version or CHANGELOG.
- Do not begin Reader API v1 stable, Final Qualification, tag or Release work.

---

### Task 0: Activate the queued implementation

**Files:**
- Delete: `.agents/queued/2.4.0-cube-export-ui.md`
- Create: `.agents/active/2.4.0-cube-export-ui.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:** Create the implementation branch from live `origin/main` and
persist its exact baseline before any runtime edit.

- [x] **Step 1: Verify the activation gate**

Fetch read-only state, require a clean worktree, prove Task 9 is integrated and
`cd265d9...` is an ancestor of live `origin/main`, and confirm no competing
active task.

- [x] **Step 2: Create the implementation branch/worktree**

Create an isolated `codex/2.4.0-cube-export-ui` worktree from live
`origin/main`. Do not reuse the discovery branch or rewrite history.

- [x] **Step 3: Move queued to active and write routing RED/GREEN**

Move the cursor, record the actual full baseline SHA, preserve goal
`CB240-CUBE-EXPORT-UI-T10`, and update the documentation routing contract.

- [x] **Step 4: Commit activation**

Run the focused documentation test and `git diff --check`; commit as
`docs: activate native Cube export UI`. Only then begin Task 1.

### Task 1: Resolve selected Grid3D export context

**Files:**
- Modify: `ChemBlender/ui/export.py`
- Create: `tests/test_cube_export_ui_contract.py`

**Interfaces:** Add `grid: Grid3D | None = None` to `ExportSelection`; teach
`resolve_export_selection(project, entity_id)` to resolve one selected
`Grid3D`; add a private `_cube_entities(selection)` projection.

- [x] **Step 1: Write selection RED**

Parse `tests/fixtures/cube/sheared.cube`, then add both an unrelated Cube and a
second `Grid3D` with the selected grid's same `structure_id`. Select the first
grid UUID and assert exact linked Structure, selected grid, all matching
`nuclear_charge` candidates, direct provenance and associated topology only.
Assert both unrelated and same-Structure sibling grids are excluded.

- [x] **Step 2: Write fail-closed RED**

Cover missing/cross-linked Structure in the resolver and a non-Grid dataset.
For a valid linked grid with missing or duplicate nuclear charge, assert
`_cube_entities()` preserves zero or all matching candidates and the delegated
core preview reports `dataset.nuclear_charge.missing` or
`dataset.nuclear_charge.ambiguous`. Expected RED: the current resolver rejects
the Grid3D before these target contracts are reachable.

- [x] **Step 3: Implement the minimal projection**

Import `Grid3D`; add the optional field last to preserve existing construction.
Resolve the selected dataset before FrameSet handling. `_cube_entities()` must
return one Structure, the selected Grid3D, all matching charge candidates,
direct provenance and associated topology; it must not duplicate core
readiness or choose among ambiguous charges.

- [x] **Step 4: Run GREEN and commit**

Run:

```powershell
& $pythonBin -m unittest `
  tests.test_cube_export_ui_contract `
  tests.test_project_browser_model `
  tests.test_cube_export_readiness -v
```

Commit as `feat: resolve Cube export selections`.

### Task 2: Add Cube format, dataset choice and preview

**Files:**
- Modify: `ChemBlender/ui/export.py`
- Modify: `tests/test_cube_export_ui_contract.py`

**Interfaces:** Add `cube` to `_FORMAT_ITEMS` and `*.cube` to `filter_glob`;
add an integer `cube_dataset_index` UI property with `-1` unset; extend
`preview_export_selection(..., dataset_index=None)`.

- [ ] **Step 1: Write format/filter RED**

Assert the target behavior: Cube is present in enum/filter and a selected
`Grid3D` defaults to Cube. Expected RED: all three assertions fail on the
baseline.

- [ ] **Step 2: Write preview RED**

Assert scalar preview delegates with `dataset_index=None`; an unset
multi-dataset selection opens the dialog, records `Select Dataset Index` and
does not call core preview; `execute()` while unset fails without writing.
After explicit selection, preview matches `preview_cube_export()`. Patch
`export_cube` and prove preview never writes.

- [ ] **Step 3: Implement the UI-only choice**

Import `IntProperty` and `preview_cube_export`; add Cube format/filter/default;
show `Dataset Index` only for a selected multi-dataset grid. During initial
`invoke()`, keep `-1` as an incomplete dialog state and skip core preview; all
non-invoke preview/execute paths convert it to missing selection and fail
closed. Never infer zero. Keep scalar grids at `None`.

- [ ] **Step 4: Run GREEN and commit**

Run the new UI contract, Cube readiness/exporter and existing extXYZ workflow
tests. Commit as `feat: add native Cube export preview`.

### Task 3: Dispatch cancellable atomic Cube export

**Files:**
- Modify: `ChemBlender/ui/export.py`
- Modify: `tests/test_cube_export_ui_contract.py`

**Interfaces:** Add `dataset_index` to `ExportJob`; dispatch
`export_cube(_cube_entities(selection), dataset_index=..., confirm_loss=...,
destination=..., is_cancelled=...).report`.

- [ ] **Step 1: Write job RED**

Assert the current job rejects `cube`, unconfirmed loss leaves the destination
untouched, confirmed scalar and explicit multi-dataset output reparses through
native `parse_cube()`, and cancellation preserves an existing destination with
no temporary sibling.

- [ ] **Step 2: Implement one dispatch branch**

Import `export_cube`; store one UI dataset selection in `ExportJob`; delegate
all validation, snapshots and publication to core. Do not catch fatal
exceptions or add another atomic writer.

- [ ] **Step 3: Run GREEN and commit**

Run the UI contract, Cube exporter/readiness/product-flow and registration
tests. Commit as `feat: add native Cube export UI`.

### Task 4: Publish and prove the reachable capability

**Files:**
- Modify: `ChemBlender/core/reader_catalog.py`
- Modify: `docs/quantum-visualization/reader-capability-matrix.json`
- Modify: `docs/user/format-capabilities.json`
- Modify: `docs/user/formats.md`
- Modify: `tests/test_generated_docs_fresh.py`
- Modify: `tests/blender_smoke.py`

**Interfaces:** Cube becomes
`("cube", "F5", "project_browser", "preview_confirmation")` in the catalog.

- [ ] **Step 1: Write capability RED**

Require `project_browser`; run the generated-doc contract and observe the
current `core` mismatch.

- [ ] **Step 2: Update catalog and regenerate documents**

Run `python ChemBlender/scripts/generate_format_docs.py`. Only catalog-derived
Cube execution claims may change.

- [ ] **Step 3: Extend installed Blender smoke**

Select the imported multi-dataset Cube `Grid3D`, set one explicit zero-based
dataset index, export through `ExportJob`, reparse with native `parse_cube()`
and compare atomic numbers, nuclear charges, coordinates, affine grid, dataset
ID and selected values. Retain lifecycle x2 and RNA budget checks.

- [ ] **Step 4: Run focused GREEN and commit**

Run UI/Cube/generated-doc/registration/smoke source contracts. Commit as
`docs: publish Cube Project Browser export`.

### Task 5: Full qualification, reviews and checkpoint

**Files:**
- Modify only in-scope files required by findings
- Delete: `.agents/active/2.4.0-cube-export-ui.md`
- Create: `.agents/completed/2.4.0-cube-export-ui.md`
- Modify: `docs/superpowers/plans/2026-08-02-chemblender-2.4.0-cube-export-ui.md`

**Interfaces:** No model or Reader API addition. Persist local completion
evidence before remote integration.

- [ ] **Step 1: Run local qualification**

Run focused tests, full unittest discovery, `compileall`, generated-doc check,
optional-import audit and `git diff --check`.

- [ ] **Step 2: Run Blender qualification**

Run native preflight, validate/build, exact ZIP audit, isolated install,
selected-grid Cube Project Browser export/re-import and lifecycle twice with
Blender 5.1.2.

- [ ] **Step 3: Run two independent reviews**

Run specification-compliance and code-quality/correctness/security reviews.
Fix all Critical, Important and task-related Minor findings and rerun affected
checks.

- [ ] **Step 4: Checkpoint**

Record exact RED/GREEN/Blender/review evidence, move the cursor to completed,
mark Tasks 0-5 checked and commit as
`chore: checkpoint native Cube export UI`.

### Task 6: Exact-head remote integration gate

**Files:**
- No product file changes after the exact feature head enters CI.

**Interfaces:** Only CI with `headSha` equal to the pushed feature head is
valid; merge mode is ordinary merge commit.

- [ ] **Step 1: Push and create a ready PR to `main`**

Confirm a clean worktree and ordinary push. Record PR URL and exact head.

- [ ] **Step 2: Wait for exact-head CI**

Require `extension-package` (`native-core`, `package`) and `optional-qc-core`
(`cclib`, `iodata`, `gbasis`) to finish successfully for the exact head.

- [ ] **Step 3: Merge and verify**

Use an ordinary merge commit, fetch, and prove the exact head is an ancestor of
`origin/main`. Do not squash, rebase, force-push, delete branches, tag or
release.

## Stop Boundary

Stop after Cube Export UI is merged and ancestry is verified. Reader API v1
stable and 2.4.0 Final Qualification remain unstarted.
