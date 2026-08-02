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

- Baseline is ordinary Cube core merge
  `cd265d95c3cc73cae5355657cc0a5a8f1931d98b`.
- Follow
  `docs/superpowers/specs/2026-08-02-chemblender-2.4.0-cube-export-ui-design.md`.
- Reuse the existing operator, `ExportSelection`, preview and `ExportJob`.
- Do not change Cube core serialization/readiness, models, sidecar schema,
  Reader API token, dependency set, workflows, manifest version or CHANGELOG.
- Do not begin Reader API v1 stable, Final Qualification, tag or Release work.

---

### Task 1: Resolve selected Grid3D export context

**Files:**
- Modify: `ChemBlender/ui/export.py`
- Create: `tests/test_cube_export_ui_contract.py`

**Interfaces:** Add `grid: Grid3D | None = None` to `ExportSelection`; teach
`resolve_export_selection(project, entity_id)` to resolve one selected
`Grid3D`; add a private `_cube_entities(selection)` projection.

- [ ] **Step 1: Write selection RED**

Parse `tests/fixtures/cube/sheared.cube` and a second unrelated Cube into one
project. Select the first grid UUID and assert exact linked Structure, selected
grid, one matching complete `nuclear_charge`, direct provenance and associated
topology only. Assert unrelated sibling grids/charges are excluded.

- [ ] **Step 2: Write fail-closed RED**

Cover missing/cross-linked Structure, missing/duplicate nuclear charge and a
non-Grid dataset. Expected: current resolver reports the selected Grid3D is not
exportable.

- [ ] **Step 3: Implement the minimal projection**

Import `Grid3D`; add the optional field last to preserve existing construction.
Resolve the selected dataset before FrameSet handling. `_cube_entities()` must
return one Structure, the selected Grid3D, matching charge, direct provenance
and associated topology; it must not duplicate core readiness.

- [ ] **Step 4: Run GREEN and commit**

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

Assert Cube is absent from the current enum/filter and a selected grid does not
default to Cube.

- [ ] **Step 2: Write preview RED**

Assert scalar preview delegates with `dataset_index=None`; multi-dataset
preview fails while unset and matches `preview_cube_export()` after explicit
selection. Patch `export_cube` and prove preview never writes.

- [ ] **Step 3: Implement the UI-only choice**

Import `IntProperty` and `preview_cube_export`; add Cube format/filter/default;
show `Dataset Index` only for a selected multi-dataset grid. Convert `-1` to
`None`; never infer zero. Keep scalar grids at `None`.

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
- Move: `.agents/queued/2.4.0-cube-export-ui.md`
- Create: `.agents/active/2.4.0-cube-export-ui.md`
- Create: `.agents/completed/2.4.0-cube-export-ui.md`
- Modify: `docs/superpowers/plans/2026-08-02-chemblender-2.4.0-cube-export-ui.md`

**Interfaces:** No model or Reader API addition. Persist local completion
evidence before remote integration.

- [ ] **Step 1: Activate from the queued cursor**

On a clean branch from current `origin/main`, atomically move the queued cursor
to active, record the actual baseline and commit activation before runtime work.

- [ ] **Step 2: Run local qualification**

Run focused tests, full unittest discovery, `compileall`, generated-doc check,
optional-import audit and `git diff --check`.

- [ ] **Step 3: Run Blender qualification**

Run native preflight, validate/build, exact ZIP audit, isolated install,
selected-grid Cube Project Browser export/re-import and lifecycle twice with
Blender 5.1.2.

- [ ] **Step 4: Run two independent reviews**

Run specification-compliance and code-quality/correctness/security reviews.
Fix all Critical, Important and task-related Minor findings and rerun affected
checks.

- [ ] **Step 5: Checkpoint**

Record exact RED/GREEN/Blender/review evidence, move the cursor to completed,
mark Tasks 1-5 checked and commit as
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
