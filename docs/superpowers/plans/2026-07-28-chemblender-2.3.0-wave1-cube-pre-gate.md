# ChemBlender 2.3.0 Wave 1 Cube Pre-Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` or `superpowers:subagent-driven-development`.
> Apply `superpowers:test-driven-development` and
> `superpowers:verification-before-completion`.

**Goal:** Freeze the existing Cube/Grid scientific-data boundary before Cube
Task 1, close the missing Cube-to-Structure binding, and prove that authoritative
grid data remains independent of Blender-derived caches.

**Architecture:** Reuse the existing `Structure`, `Grid3D`, `PropertyDataset`,
`.cbq`, canonical document, and view-cache contracts. A Cube import owns one
`Structure`; its `Grid3D.structure_id` points to that structure. Coordinate and
value units remain separate tokens, with source/conversion detail in provenance.
OpenVDB and generated meshes remain deletable Blender-derived caches.

**Tech Stack:** Python standard library, NumPy already supplied by Blender,
existing `unittest`, `.cbq`/canonical serializers, Blender 5.1.2.

**Reviewed baseline:** `d36f4b27cc9a4f00d223f0c39272e1422a6375d4`

**Stop boundary:** Complete this gate and checkpoint it. Do not begin Cube Task
1, add Cube source metadata, implement a new Cube reader, add VDB functionality,
change release metadata, or push.

---

### Task 1: Freeze the scientific Grid/Structure contract

**Files:**
- Create: `.agents/decisions/0041-cube-structure-reference-policy.md`
- Modify: `.agents/reference/code-architecture-guide.md` only if a source-file
  responsibility changes

**Interfaces:**
- Existing `Grid3D.structure_id: UUID | None`
- Existing `PropertyDataset.source_calculation` and `provenance_ids`

**RED test:** None. This task records an already-implemented architectural
boundary; fabricating a new runtime abstraction solely to produce RED is out of
scope.

**Expected RED:** Not applicable.

**Minimal implementation:** Record that Cube atoms map to `Structure`, continuous
values map to `Grid3D`, and the grid references that structure. Reject
`CubeAtom`, `CubeStructure`, scientific VDB authority, and scientific mesh
authority.

**Focused verification:** Documentation contract tests and source inventory.

**Blender verification:** Not required for the documentation-only boundary.

**Commit boundary:** Planning/ADR/cursor commit.

**Stop boundary:** Do not change the Cube metadata model in this task.

### Task 2: Bind existing Cube grids to their Structure

**Files:**
- Modify: `tests/test_cube_reader.py`
- Modify: `ChemBlender/core/cube.py`

**Interfaces:**
- `parse_cube(source) -> ImportBatch`
- `Grid3D.structure_id`

**RED test:** Assert that the parsed grid immediately references the parsed
structure and that `QCProject.commit()` preserves the binding.

**Expected RED:** `grid.structure_id` is `None`.

**Minimal implementation:** Pass the already-created `structure_id` to the
existing `Grid3D` constructor. Do not introduce a metadata wrapper or duplicate
structure type.

**Focused verification:** `tests.test_cube_reader`,
`tests.test_periodic_model`, and project graph tests.

**Blender verification:** Import the existing Cube fixture and confirm the
project grid and Blender-owned Volume metadata retain the same structure UUID.

**Commit boundary:** `fix: bind Cube grids to their structures`

**Stop boundary:** Do not preserve nuclear charges or dataset source metadata;
those remain Cube Task 1.

### Task 3: Lock unit and persistence behavior

**Files:**
- Modify existing tests only if the current assertions do not cover the contract:
  - `tests/test_cube_reader.py`
  - `tests/test_sidecar_storage.py`
  - `tests/test_reader_canonical_document.py`

**Interfaces:**
- `Structure.coordinates.unit`
- `Grid3D.coordinate_unit`
- `Grid3D.data.unit`
- `.cbq` and canonical public document round-trip

**RED test:** Add only missing assertions: Cube coordinates and grid geometry use
the same source length unit; `bohr` and `angstrom` remain distinct; sidecar and
canonical round-trips preserve `structure_id`, coordinate unit, and value unit.

**Expected RED:** No new RED where the existing contract already passes. Reuse
existing coverage rather than duplicate it.

**Minimal implementation:** No unit class, conversion registry, `native_unit`,
or `display_unit`. Existing unit tokens plus provenance are authoritative.

**Focused verification:** Cube, sidecar, canonical document, and core import
tests.

**Blender verification:** Confirm Blender display conversion metadata does not
alter the source `Grid3D.coordinate_unit`.

**Commit boundary:** Include only assertions needed to make the boundary
enforceable.

**Stop boundary:** Do not change the established Cube convention that its stored
coordinates are `bohr`; any broader format policy belongs to Cube Task 1 review.

### Task 4: Lock derived-cache and surface lifecycle

**Files:**
- Verify: `ChemBlender/ui/view_cache.py`
- Verify: `ChemBlender/grid_volume.py`
- Verify: `ChemBlender/surface_view.py`
- Modify existing tests only if a required boundary is uncovered:
  - `tests/test_view_cache_persistence.py`
  - `tests/blender_smoke.py`

**Interfaces:**
- `repair_project_view_caches(...)`
- Existing volume/surface render-cache identities

**RED test:** Reuse the existing missing-cache repair path. Add a test only if
deleting a ChemBlender-owned VDB cannot be reconstructed from `Grid3D`.

**Expected RED:** None expected; the persistence gate already implemented this
behavior.

**Minimal implementation:** No new VDB writer or general surface model.
`SurfaceProperty` remains the Fermi-surface vertex/face property type. Cube
isosurfaces and volume meshes are derived Blender views.

**Focused verification:** View-cache persistence and scene preset tests.

**Blender verification:** Delete/rebuild an owned Cube Volume cache and reopen
the project without changing the scientific grid revision.

**Commit boundary:** No runtime commit unless verification exposes a real gap.

**Stop boundary:** Do not start progress/cancellation work from Cube Task 4.

### Task 5: Full regression, two review passes, and checkpoint

**Files:**
- Modify: `.agents/active/2.3.0-wave-1-native-molecular-and-grid.md`
- Modify: this plan with final evidence

**Interfaces:** Execution Cursor only.

**RED test:** Record the actual Cube binding failure from Task 2.

**Expected RED:** One binding assertion failure.

**Minimal implementation:** Run focused tests, full discovery, `compileall`,
documentation contracts, `git diff --check`, Blender validate/build/ZIP/install,
Cube import/cache rebuild/save/reopen, and lifecycle. Perform one specification
review and one separate code-quality review.

**Focused verification:** All tests named above.

**Blender verification:** Blender 5.1.2 native and isolated runtime gates.

**Commit boundary:** `chore: checkpoint Cube pre-gate`

**Stop boundary:** Cursor next task is Cube Task 1; do not start it and do not
push.
