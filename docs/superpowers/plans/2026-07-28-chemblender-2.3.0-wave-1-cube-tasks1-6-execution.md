# ChemBlender 2.3.0 Wave 1 Cube Tasks 1–6 Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` and `superpowers:test-driven-development`.
> Complete tasks in order, record actual RED/GREEN evidence after each task,
> and stop before Wave 2.

**Goal:** Complete the remaining Wave 1 Cube dataset, semantic-resolution,
Blender view, cache, surface-quality and performance gates.

**Architecture:** `Structure`, `AtomicProperty`, `Grid3D` and provenance remain
the only authoritative scientific records. Semantic resolution creates a new
immutable grid revision; OpenVDB and mesh output stay derived caches. UI code
projects bounded state and delegates scientific operations to pure core
services.

**Tech Stack:** Python 3.13 standard library, Blender-bundled NumPy, existing
`unittest`, Blender 5.1.2 Extension tooling and OpenVDB runtime.

## Global Constraints

- Execute Cube Tasks 1–6 in order and finish
  `W1-PRE-ALPHA2-PERFORMANCE-GATE` before the Wave 1 checkpoint.
- Do not add dependencies, change release metadata, activate Wave 2, push,
  create a PR, tag or Release.
- Reuse existing model, provenance, atomic-path, view-cache and registration
  contracts; do not introduce `CubeAtom`, `CubeStructure`, scientific VDB
  authority or scientific mesh authority.
- Every implementation task requires observed RED, minimal GREEN, focused
  verification, a specification review, a code-quality review and a separate
  commit.
- Fatal exceptions pass through unchanged; cancellation and ordinary failures
  clean owned staging without replacing authoritative project state.

---

## Task Table

| Task | State | Implementation commit | Review |
|---|---|---|---|
| 1 Cube source metadata | completed | `08e020ab736543ec495895f77baa886a0838ca34` | SPEC PASS; QUALITY PASS |
| 2 Grid semantics and presets | completed | `0a466d3de71da2fb0334771a6724744cfbff6607` | SPEC PASS; QUALITY PASS |
| 3 Cube dataset and semantic UI | in progress | — | pending |
| 4 Progress-aware cancellable VDB cache | pending | — | pending |
| 5 Surface quality and bindings | pending | — | pending |
| 6 Product flow and Cube benchmark | pending | — | pending |
| Pre-alpha.2 performance gate | pending | — | pending |
| Wave 1 checkpoint | pending | — | pending |

## Task 1 — Preserve Cube source metadata

**Files:**
- Modify: `ChemBlender/core/cube.py`
- Modify: `tests/test_cube_reader.py`
- Modify: serialization tests only where the new dataset needs explicit
  round-trip coverage

**Interfaces:**
- Produces one `AtomicProperty` with semantic role `nuclear_charge`, atom
  domain, `elementary_charge`, the parsed `Structure.id` and parser provenance.
- Keeps Cube comments, ordered dataset IDs, dataset count and signed axis
  convention in the existing `ProvenanceRecord.parameters`.

- [x] Write tests proving non-default and default nuclear charges are retained,
  report IDs include the property, and project/canonical/sidecar round-trips
  preserve it.
- [x] Run `tests.test_cube_reader` and record the missing-property RED.
- [x] Retain parsed charges, construct the existing `AtomicProperty`, include it
  beside the `Grid3D`, remove the obsolete unsupported diagnostic and update
  parsed capabilities.
- [x] Run Cube, project, canonical and sidecar focused tests.
- [x] Review and commit `feat: preserve Cube source metadata`.

**Evidence:** Initial Cube run had two `StopIteration` errors because no
`AtomicProperty` existed. Focused verification passed 99/99. The first full run
exposed stale reader-matrix and conformance expectations; after synchronizing
the version-2 atomic-property capability, full discovery passed 1376 tests with
28 skips and 0 failures.

## Task 2 — Resolve grid semantics with deterministic presets

**Files:**
- Create: `ChemBlender/core/grid_semantics.py`
- Create: `tests/test_grid_semantics.py`
- Create:
  `docs/quantum-visualization/2.3.0/specs/grid-semantic-presets-v1.md`
- Modify: `ChemBlender/core/__init__.py`
- Modify: `.agents/reference/code-architecture-guide.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- `GridSemanticPreset`
- `GRID_SEMANTIC_PRESETS`
- `resolve_grid_semantics(grid, *, dataset_index, preset_id, value_unit)
  -> ImportBatch`
- `default_grid_isovalue(grid, *, dataset_index, preset_id) -> float`

- [x] Test all seven preset IDs, allowed role/unit pairs, dataset bounds,
  immutable source values, deterministic identity/revision/provenance and
  named default-isovalue policies.
- [x] Run the new module and record the import RED.
- [x] Implement the smallest pure core service using existing arrays and
  provenance; a multi-dataset selection becomes a single-grid dataset without
  modifying source values.
- [x] Run semantic, model, project and scene-preset tests.
- [x] Review and commit `feat: add Cube grid semantic presets`.

**Evidence:** Initial focused run failed to import
`ChemBlender.core.grid_semantics`. The completed service exposes seven frozen
presets, deterministic resolution/provenance and named isovalue policies.
Focused verification passed 34/34; full discovery passed 1382 tests with
28 skips and 0 failures.

## Task 3 — Add bounded Cube dataset and semantic UI

**Files:**
- Create: `ChemBlender/ui/grid.py`
- Create: `tests/test_grid_ui_contract.py`
- Modify: `ChemBlender/ui/import_preview.py`
- Modify: `ChemBlender/ui/project_browser/panel.py`
- Modify: `ChemBlender/ui/properties.py`
- Modify: `ChemBlender/runtime/registration.py`
- Modify: `tests/test_registration_contract.py`
- Modify: `tests/blender_smoke.py`
- Modify: `.agents/reference/code-architecture-guide.md`

**Interfaces:**
- Preview/browser row builders expose bounded Cube shape, dataset IDs, sampled
  value range, units and ambiguity.
- A registered resolve operator calls `resolve_grid_semantics()` and commits the
  returned grid/provenance atomically.
- View actions pass dataset index, role, unit, mode and numeric isovalue to
  existing scene-preset planning.

- [ ] Test two-dataset projection, first-dataset default without semantic
  resolution, invalid action disabling, immutable resolution and explicit
  registration root ownership.
- [ ] Run UI and registration tests and record the missing module/operator RED.
- [ ] Implement only bounded RNA state and delegation; keep arrays out of RNA.
- [ ] Run UI, registration, preview/browser and Blender Cube smoke tests.
- [ ] Review and commit `feat: add Cube semantic and view controls`.

## Task 4 — Prepare OpenVDB cache with progress and cancellation

**Files:**
- Create: `ChemBlender/core/grid_cache_service.py`
- Create: `tests/test_grid_cache_service.py`
- Modify: `ChemBlender/grid_volume.py`
- Modify: `tests/blender_smoke.py`
- Modify: `.agents/reference/code-architecture-guide.md`

**Interfaces:**
- `prepare_volume_cache(grid, request, *, writer, cancelled, progress)
  -> CacheResult`
- The pure service owns cache identity, same-directory short staging,
  verification and atomic replacement; Blender datablocks remain main-thread
  work in `grid_volume.py`.

- [ ] Test cache hit, four cancellation checkpoints, writer failure, publish
  failure, staging cleanup and unchanged prior cache.
- [ ] Run the new service tests and record the import RED.
- [ ] Extract only identity/staging from the current writer and reuse
  `short_sibling_temporary_path()` plus existing cache metadata.
- [ ] Run cache, atomic-path, view-cache and Blender volume smoke tests.
- [ ] Review and commit `feat: add cancellable Cube cache preparation`.

## Task 5 — Enforce surface quality, alignment and complete bindings

**Files:**
- Create: `tests/test_surface_quality_contract.py`
- Modify: `ChemBlender/surface_view.py`
- Modify: `ChemBlender/scene_preset_view.py`
- Modify: `tests/blender_smoke.py`

**Interfaces:**
- A raw ambiguous grid creates an ambiguous, report-ineligible derived view.
- Resolved complete grids may create complete views.
- Property surfaces require equal shape, origin, step vectors and coordinate
  unit within the documented numeric tolerance.
- View/object metadata contains both source grid IDs/revisions, dataset indices,
  roles, units, isovalue, range/colormap and render-cache identity.

- [ ] Test raw/resolved quality, exact/mismatched alignment, no silent
  resampling and full binding persistence.
- [ ] Run surface/scene tests and record the missing validation/binding RED.
- [ ] Add one shared alignment guard and extend existing metadata dictionaries;
  do not add a scientific surface model.
- [ ] Run surface, scene-preset, view-cache and Blender smoke tests.
- [ ] Review and commit `feat: complete Cube surface quality bindings`.

## Task 6 — Close the Cube product and 128³ performance path

**Files:**
- Create: `tests/test_cube_product_flow.py`
- Create: `ChemBlender/scripts/benchmark_cube_flow.py`
- Create:
  `docs/quantum-visualization/2.3.0/benchmarks/cube-flow-baseline.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- A deterministic product-flow test covers raw import, preview, save, semantic
  resolution, signed surface binding and save/reopen.
- The benchmark CLI emits canonical JSON with hardware, dataset size, runs,
  median, p95, peak memory and per-stage results.

- [ ] Write the product-flow and benchmark-contract tests and record RED.
- [ ] Implement a generated 128³ input path without committing a large binary
  fixture; benchmark parse, array staging, save, cold/hot cache and view stages
  separately.
- [ ] Run focused flow tests and the real Blender benchmark.
- [ ] Compare total 128³ time with the 10 s Wave budget; if it fails, profile
  the blocking stage and keep the gate failed.
- [ ] Review and commit `test: close Cube product and performance flow`.

## Pre-alpha.2 performance gate

**Files:**
- Create:
  `docs/superpowers/plans/2026-07-28-chemblender-2.3.0-wave-1-pre-alpha2-performance-gate.md`
- Modify: benchmark baselines only with fresh measured evidence
- Modify: `.agents/active/2.3.0-wave-1-native-molecular-and-grid.md`

**Interfaces:** Evidence gate only; no new feature surface.

- [ ] Re-run extXYZ preview-ready, 10k SDF/RDKit, topology, Cube 128³ and
  browser/filter budgets on the recorded reference environment.
- [ ] Verify all operations over 1 s expose progress/cancellation and leave no
  owned staging/handler leaks after cancellation.
- [ ] Run full tests, `compileall`, docs contracts and `git diff --check`.
- [ ] Run Blender 5.1.2 validate/build, ZIP audit, isolated install, product
  smoke and two lifecycle cycles.
- [ ] Perform separate specification and code-quality reviews; fix every
  Critical, Important and Wave-related Minor finding and repeat verification.
- [ ] Commit `chore: close Wave 1 performance gate`.

## Wave 1 checkpoint

- [ ] Record every Task commit and RED/GREEN result in this plan and the active
  cursor.
- [ ] Record full test counts, Blender package SHA-256, product-smoke and
  benchmark results as local evidence; keep `Remote CI: Not Run`.
- [ ] Confirm Wave 2 remains queued and no release metadata, remote, tag or
  Release was changed.
- [ ] Commit `chore: checkpoint Wave 1 native molecular and grid`.
- [ ] Stop with a clean worktree; do not push.
