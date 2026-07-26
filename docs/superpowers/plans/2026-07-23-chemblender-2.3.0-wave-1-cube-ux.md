# ChemBlender 2.3.0 Wave 1 Cube Dataset and Surface UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Productize the existing Cube reader and OpenVDB/surface adapters with dataset selection, semantic/unit resolution, presets, progress, caching and quality-aware reports.

**Architecture:** Parsing remains semantic-neutral where the source is ambiguous. User resolution creates a derived Grid3D revision or annotation entity, preserving the raw ambiguous grid. View plans bind a selected dataset index and resolved semantic metadata.

**Tech Stack:** Existing Cube reader, Grid3D, NPY sidecar, Blender OpenVDB, Geometry Nodes Volume-to-Mesh, UIList and `unittest`/Blender smoke.

## Global Constraints

- Never infer a final scientific semantic solely from filename.
- Raw Cube values, origin, steps, dataset IDs and nuclear charges are preserved.
- User semantic/unit resolution is explicit and provenance-recorded.
- No lossless source rewrite promise.
- Large parse/cache operations expose progress and cancellation.

---

### Task 1: Preserve Cube atom nuclear charges and dataset metadata

**Files:**
- Modify: `ChemBlender/core/model/grids.py`
- Modify: `ChemBlender/core/cube.py`
- Modify: `tests/test_cube_reader.py`
- Add: fixtures for nondefault nuclear charge and multi-dataset IDs.

**Interfaces:**
- Produces: `GridSourceMetadata` or typed fields containing dataset IDs, comments, nuclear charges and source conventions.

- [ ] **Step 1: Write metadata tests**

Parse a Cube with ECP-like nuclear charges and negative NATOMS dataset IDs. Assert values and IDs are retained, not only reported unsupported.

- [ ] **Step 2: Extend the model**

Attach immutable source metadata to Grid3D or a source envelope referenced by it. Nuclear charges are an AtomicProperty with `elementary_charge` and the same structure ID.

- [ ] **Step 3: Keep ambiguity diagnostics**

Semantic role and value unit remain ambiguous unless declared by a recognized extension or user resolution. Negative voxel count convention remains documented.

- [ ] **Step 4: Run and commit**

Run Cube, sidecar and project tests; commit.

### Task 2: Add grid semantic resolution and presets

**Files:**
- Create: `ChemBlender/core/grid_semantics.py`
- Create: `tests/test_grid_semantics.py`
- Create: `docs/quantum-visualization/2.3.0/specs/grid-semantic-presets-v1.md`

**Interfaces:**
- Produces: `GridSemanticPreset`, `resolve_grid_semantics()` and built-in presets.

- [ ] **Step 1: Define presets**

Presets include generic scalar, molecular orbital, electron density, spin density, electrostatic potential, reduced density gradient and sign-lambda2-rho. Each defines expected value unit choices, signedness, default surface mode, default isovalue policy and colormap class.

- [ ] **Step 2: Write resolution tests**

Resolving an ambiguous grid creates a new Grid3D revision with parent provenance, chosen dataset index/role/unit and no value changes. Invalid role/unit pairs are rejected.

- [ ] **Step 3: Implement deterministic default isovalue policies**

Policies are named and parameterized; the stored view records the actual numeric isovalue. Do not silently recalculate defaults after data revision changes.

- [ ] **Step 4: Run and commit**

Run semantic and scene preset tests; commit.

### Task 3: Add Cube dataset and semantic UI

**Files:**
- Create: `ChemBlender/ui/grid.py`
- Modify: `ChemBlender/ui/import_preview.py`
- Modify: `ChemBlender/ui/project_browser/panel.py`
- Modify: `ChemBlender/ui/properties.py`
- Create: `tests/test_grid_ui_contract.py`

**Interfaces:**
- Produces: dataset-index selector, semantic preset, unit, resolve action, volume/surface actions.

- [ ] **Step 1: Show multi-dataset information in Preview**

Display dataset count, source IDs, value range sample, grid shape, coordinate unit and ambiguity. Default view selects the first dataset but does not mark semantics resolved.

- [ ] **Step 2: Implement resolution operator**

The operator validates selected preset/unit, creates the derived grid batch through the core service, commits it and updates active selection. It never edits the raw grid object.

- [ ] **Step 3: Implement view controls**

Volume, signed surface and property-on-surface actions use existing scene preset planning. Disable invalid combinations and show required source grids.

- [ ] **Step 4: Run and commit**

Run UI contract and Blender smoke with two-dataset Cube; commit.

### Task 4: Make OpenVDB cache creation progress-aware and cancellable

**Files:**
- Modify: `ChemBlender/grid_volume.py`
- Create: `ChemBlender/core/grid_cache_service.py`
- Create: `tests/test_grid_cache_service.py`
- Modify: `tests/blender_smoke.py`

**Interfaces:**
- Produces: `prepare_volume_cache(grid, request) -> CacheResult` and modal UI integration.

- [ ] **Step 1: Extract pure cache identity and staging**

The service computes path/identity, writes a temporary VDB and atomically replaces the cache only after verification. Existing valid cache returns immediately.

- [ ] **Step 2: Add cancellation checkpoints**

Check before array load, after dataset slice, after VDB population and before publish. Cancellation removes temp file and returns Cancelled without changing ViewRecord.

- [ ] **Step 3: Keep Blender object creation on main thread**

Background work may prepare data/cache, but `bpy.data.volumes.new` and object linking occur in the operator completion callback.

- [ ] **Step 4: Test failure and commit**

Simulate write failure, cancellation and cache hit. Blender smoke creates volume from successful result. Commit.

### Task 5: Complete surface quality and metadata behavior

**Files:**
- Modify: `ChemBlender/surface_view.py`
- Modify: `ChemBlender/scene_preset_view.py`
- Create: `tests/test_surface_quality_contract.py`
- Modify: `tests/blender_smoke.py`

**Interfaces:**
- Produces: quality propagation and resolved semantic metadata on signed/property surfaces.

- [ ] **Step 1: Write quality tests**

Raw ambiguous grid creates a preview surface whose ViewRecord is Ambiguous and report-ineligible. Resolved grid creates a Complete view when source quality permits.

- [ ] **Step 2: Validate grid alignment for property surfaces**

Require matching shape/origin/steps/coordinate unit within documented tolerance or perform a separate explicit resampling derivation; never sample mismatched grids silently.

- [ ] **Step 3: Store full bindings**

Object/ViewRecord store source grid IDs/revisions, dataset indices, isovalue, colormap/range, semantic roles, units and render cache identity.

- [ ] **Step 4: Run and commit**

Run surface, scene preset and Blender smoke; commit.

### Task 6: Add Cube end-to-end and performance gates

**Files:**
- Create: `tests/test_cube_product_flow.py`
- Create: `ChemBlender/scripts/benchmark_cube_flow.py`
- Create: `docs/quantum-visualization/2.3.0/benchmarks/cube-flow-baseline.md`

**Interfaces:**
- Produces: a fixed end-to-end test and benchmark JSON/Markdown.

- [ ] **Step 1: Test product flow**

Import multi-dataset Cube, confirm preview, save raw ambiguous project, resolve dataset 1 as MO, create signed surfaces, save/reopen and verify raw/resolved IDs and view bindings.

- [ ] **Step 2: Benchmark 128³**

Measure parse, stage NPY, save, cache VDB and view creation separately. Record cold/hot cache median/p95 on reference hardware.

- [ ] **Step 3: Verify budget and commit**

If 128³ total exceeds 10 s, profile and document the blocking stage before alpha.2. Commit tests/benchmark/evidence.
