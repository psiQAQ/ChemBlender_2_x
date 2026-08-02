# ChemBlender 2.4.0 Deterministic Native Cube Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add dependency-free deterministic Cube core export with explicit
dataset selection, stable loss preview, atomic cancellation and native semantic
re-import proof.

**Architecture:** Keep `Structure`, matching nuclear-charge `AtomicProperty`
and selected `Grid3D` as scientific authority. Add one readiness module and one
writer module under the existing exporter package; reuse `ExportReport`, short
sibling atomic publication and native `parse_cube()`. Serialize all geometry as
bohr without mutating source entities and never read OpenVDB or Blender caches.

**Tech Stack:** Python 3.13, NumPy bundled with Blender, standard-library
`unittest`, existing ChemBlender models/export infrastructure, Blender 5.1.2.

## Global Constraints

- Start only after `.agents/queued/2.4.0-cube-export.md` is explicitly
  activated.
- Baseline is the Task 7 Scope Discovery checkpoint containing
  `docs/quantum-visualization/2.4.0/task7-candidate-intake.md`.
- Add no model, sidecar/schema field, dependency, UI control, registration root
  or Reader API token change.
- Cube UI, Reader API v1 stable, manifest version, CHANGELOG release version,
  tags and Releases remain unstarted.
- OpenVDB, Blender Volume and mesh caches are derived data and must never be
  scientific export sources.

---

### Task 1: Freeze Cube export readiness

**Files:**
- Move: `.agents/queued/2.4.0-cube-export.md`
- Create: `.agents/active/2.4.0-cube-export.md`
- Create: `ChemBlender/core/exporters/cube_readiness.py`
- Create: `tests/test_cube_export_readiness.py`
- Create: `docs/quantum-visualization/2.4.0/cube-export-contract.md`
- Modify: `ChemBlender/core/exporters/__init__.py`
- Modify: `ChemBlender/core/__init__.py`
- Modify: `.agents/reference/code-architecture-guide.md`
- Modify: `tests/test_core_public_api.py`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Produces: `CubeExportStatus`, `CubeExportReadiness` and
  `cube_export_readiness(project_entities, *, dataset_index=None)`.
- `CubeExportReadiness` is a frozen, slotted dataclass with `status` and sorted
  `tokens`; it does not serialize or modify entities.

- [ ] **Step 1: Activate the queued cursor and write readiness RED**

Require exactly one selected `Grid3D`, its linked `Structure`, and one matching
complete finite `nuclear_charge` `AtomicProperty` in `elementary_charge` with
shape `("atom",)`. Test missing, duplicate and cross-linked entities, invalid
atom/grid shapes, non-finite values and duplicate UUIDs. The linked Structure
must contain at least one atom. Coordinates, nuclear charges and the selected
grid slice must be real numeric arrays (never bool, complex, string or object)
whose values are finite.

- [ ] **Step 2: Add dataset and unit RED**

Test these exact rules:

```text
xyz grid + dataset_index=None                  -> Ready
xyz grid + dataset_index=0                     -> Invalid
dataset,xyz grid + dataset_index=None          -> MissingSelection
dataset,xyz grid + in-range integer index      -> Ready
dataset,xyz grid + bool/out-of-range index      -> Invalid
coordinate units in {bohr, angstrom}           -> supported
unknown/dimensionless/other coordinate units   -> UnsupportedUnit
```

Structure coordinates and Grid geometry may independently use `bohr` or
`angstrom`; both are converted to one bohr output frame later. Leading dims
other than exactly `("dataset",)` are unsupported.

- [ ] **Step 3: Run RED**

Run:

```powershell
& $pythonBin -m unittest tests.test_cube_export_readiness -v
```

Expected: import error because `cube_readiness.py` and its public symbols do
not exist.

- [ ] **Step 4: Implement the minimum readiness boundary**

Define:

```python
class CubeExportStatus(str, Enum):
    READY = "Ready"
    MISSING_ENTITY = "MissingEntity"
    MISSING_SELECTION = "MissingSelection"
    AMBIGUOUS = "Ambiguous"
    INVALID = "Invalid"
    UNSUPPORTED_UNIT = "UnsupportedUnit"


@dataclass(frozen=True, slots=True)
class CubeExportReadiness:
    status: CubeExportStatus
    tokens: tuple[str, ...]
```

Return stable sorted tokens. Reuse the package's existing entity-container
projection pattern; add no generic selection framework.

- [ ] **Step 5: Publish the contract and run GREEN**

Document the entity, affine-grid, unit, dataset and loss boundaries. Export the
three public readiness symbols through `ChemBlender.core`, update the
architecture inventory, run readiness/public/docs tests and commit:

```powershell
git commit -m "feat: freeze native Cube export readiness"
```

### Task 2: Write deterministic scalar and selected-dataset Cube

**Files:**
- Create: `ChemBlender/core/exporters/cube.py`
- Create: `tests/test_cube_exporter.py`
- Modify: `ChemBlender/core/exporters/__init__.py`
- Modify: `ChemBlender/core/__init__.py`
- Modify: `.agents/reference/code-architecture-guide.md`
- Modify: `tests/test_core_public_api.py`

**Interfaces:**
- Consumes: `cube_export_readiness()` and existing
  `atomic_write_chunks(destination, chunks, *, is_cancelled=None)`.
- Produces: frozen `CubeExport(text: str, report: ExportReport)`,
  `preview_cube_export(project_entities, *, dataset_index=None)` and
  `export_cube(project_entities, *, dataset_index=None, confirm_loss=False,
  destination=None, is_cancelled=None)`.

- [ ] **Step 1: Write scalar-format RED**

Use `tests/fixtures/cube/sheared.cube`. Require two deterministic ASCII comment
lines, atom count/origin, three full affine step-vector lines, atom rows
with distinct atomic number/nuclear charge, C-order values with z fastest, at
most six values per data line and exactly one trailing LF. Repeated export and
dict/tuple container order must produce identical bytes. A scalar grid without
a trustworthy source dataset ID uses positive `NATOMS` and omits `DSET_IDS`.
A scalar grid with one trustworthy source ID preserves it with negative
`NATOMS` and a one-entry `DSET_IDS` record. Both forms write all three voxel
counts as positive integers because output geometry is always bohr.

- [ ] **Step 2: Write bohr output RED**

Create equivalent bohr and angstrom entities. Require byte-identical output
after converting angstrom by:

```python
BOHR_TO_ANGSTROM = 0.529177210903
bohr_value = angstrom_value / BOHR_TO_ANGSTROM
```

Do not alter source arrays or unit tokens. Preserve sheared axes and determinant
sign exactly within the writer's numeric precision.

- [ ] **Step 3: Write explicit dataset selection and DSET_IDS RED**

For `tests/fixtures/cube/two-datasets.cube`, require one explicit selected index.
Write negative `NATOMS`, a one-entry `DSET_IDS` record, positive voxel counts
and only the selected values. Preserve source IDs `(5, 7)` only when exactly
one `ProvenanceRecord` is referenced directly by the selected Grid3D and has
`operation == "parse"`, `format == "cube"`, `dataset_count` equal to the grid's
dataset dimension, and `dataset_ids` of the same length containing non-negative
exact integers (including zero, never bool). Do not traverse unrelated
provenance lineage. Index
1 then writes ID `7`. If those checks fail, use deterministic positive ID
`dataset_index + 1` and report `dataset_id_normalized`. Scalar grids do not use
that fallback: trustworthy one-entry IDs are preserved, ordinary scalars omit
`DSET_IDS`, and malformed scalar provenance is omitted with a
`dataset_id_omitted` confirmation-required loss.

- [ ] **Step 4: Run RED**

Run the named exporter tests. Expected: public import error because `cube.py`
does not exist.

- [ ] **Step 5: Implement the minimum writer**

Use locale-independent uppercase scientific notation with one frozen precision
for geometry, charges and values. Convert source geometry to bohr, stream text
chunks in deterministic order and delegate destination publication to the
existing atomic writer. Do not create a second temporary-path implementation.

- [ ] **Step 6: Run GREEN and commit**

Run Cube reader/readiness/exporter/public tests and commit:

```powershell
git commit -m "feat: export deterministic native Cube data"
```

### Task 3: Qualify authoritative lazy snapshots and semantic losses

**Files:**
- Modify: `ChemBlender/core/exporters/cube.py`
- Modify: `tests/test_cube_exporter.py`
- Modify: `docs/quantum-visualization/2.4.0/cube-export-contract.md`

**Interfaces:** Preview and publication consume one authoritative lazy snapshot;
no new public symbol.

- [ ] **Step 1: Write loss-preview RED**

Require stable sorted entries for semantic role, value unit, project-only
identity/provenance and normalized comment or dataset ID information that Cube
cannot encode. Also report stable losses for every present Structure-only
semantic: cell/periodic metadata, molecular charge, multiplicity, embedded or
referenced topology, and atomic identity. `preview_cube_export()` returns no
written output. Any loss makes `requires_confirmation=True`; `export_cube()`
publishes nothing until exact `confirm_loss=True`.

- [ ] **Step 2: Write authoritative lazy snapshots RED**

Snapshot coordinates, nuclear charges and selected grid values exactly once.
Initially unloaded `LazyNpyArray` objects return to unloaded state after preview,
success, validation failure and cancellation; caller-preloaded arrays remain
loaded. Recompute the authoritative snapshot fingerprints through the existing
`is_cancelled` callback at its final pre-publication checkpoint; mutation
detected by that checkpoint fails without replacing an existing destination.
The contract intentionally makes no impossible claim about mutation in the
unobservable interval after that final checkpoint and before `os.replace()`.

- [ ] **Step 3: Write failure/cancellation RED**

Cover pre-cancel, mid-stream cancel, writer error, `os.replace()` failure and
cleanup failure. The main error remains primary, temporary siblings are absent,
and an existing destination is byte-identical. `KeyboardInterrupt`,
`SystemExit`, `GeneratorExit` and `MemoryError` pass through unchanged. A lazy
array `close()` failure is attached to an existing primary error and never
replaces it; without a primary error the close failure is raised.

- [ ] **Step 4: Write Semantic native re-import RED**

Reparse with native `parse_cube()` and compare:

- atomic numbers and nuclear charges;
- physical coordinates after unit conversion;
- origin and full step vectors;
- grid shape and selected scalar values;
- preserved or explicitly normalized dataset ID.

Do not compare UUID, revision, provenance identity, comment whitespace, value
semantic/unit fields acknowledged as losses, OpenVDB or mesh cache.

- [ ] **Step 5: Implement, run GREEN and commit**

Reuse the existing PQR live-snapshot/resource-ownership pattern only where the
same behavior is needed; do not extract a speculative shared framework. Commit:

```powershell
git commit -m "test: qualify native Cube export semantics"
```

### Task 4: Publish the core Cube export capability

**Files:**
- Modify: `ChemBlender/core/reader_catalog.py`
- Modify: `docs/quantum-visualization/reader-capability-matrix.json`
- Modify: `docs/user/format-capabilities.json`
- Modify: `docs/user/formats.md`
- Modify: `tests/test_generated_docs_fresh.py`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:** Cube export becomes
`("cube", "F5", "core", "preview_confirmation")`; no UI claim.

- [ ] **Step 1: Write capability RED**

Require catalog-derived documents to report Cube as
`F5 / core / preview_confirmation` while Project Browser remains without a Cube
export choice.

- [ ] **Step 2: Run RED**

Run generated-document freshness tests. Expected: current catalog still reports
`F0 / none / not_available`.

- [ ] **Step 3: Change the single catalog source and regenerate**

Run:

```powershell
& $pythonBin ChemBlender/scripts/generate_format_docs.py
```

Only catalog-derived Cube export claims may change.

- [ ] **Step 4: Run GREEN and commit**

Commit as `docs: publish native Cube core export`.

### Task 5: Prove installed export and performance boundaries

**Files:**
- Modify: `tests/blender_smoke.py`
- Modify: `ChemBlender/scripts/benchmark_cube_flow.py`
- Modify: `tests/test_cube_product_flow.py`
- Modify: `docs/quantum-visualization/2.3.0/benchmarks/cube-flow-baseline.md`
- Modify: `.github/artifact-budgets.json`
- Modify: `tests/test_artifact_size_report.py`

**Interfaces:** No UI. The installed extension imports, exports and natively
reparses Cube through core APIs.

- [ ] **Step 1: Extend installed smoke**

Using the existing Cube product workflow, export the selected second dataset,
reparse it, and assert linked Structure, nuclear charge, affine geometry,
selected values and dataset ID. Keep register/unregister/reload x2 and the
existing RNA budget.

- [ ] **Step 2: Extend the existing benchmark minimally**

Add one `export` stage to `benchmark_cube_flow.py` and update the existing exact
stage-set contract in `tests/test_cube_product_flow.py`. For 128 cubed data record
median, p95, output bytes and peak Python memory. Require p95 not to exceed the
existing 10-second Cube product budget; do not add a new benchmark framework.

- [ ] **Step 3: Run native package qualification**

Run Blender 5.1.2 preflight, validate/build, exact ZIP path/CRC/two-wheel audit,
normal `user_default` install, isolated lifecycle and installed Cube
export/re-import. Refresh only measured exact artifact baselines after a fresh
Windows checkout proves required source growth; keep all unexplained-growth
allowances at zero.

- [ ] **Step 4: Commit**

Commit product/benchmark proof as `test: qualify installed native Cube export`
and any exact fresh-checkout budget update separately as
`chore: refresh Cube export package budget`.

### Task 6: Full qualification, reviews and checkpoint

**Files:**
- Modify only files required by findings
- Delete: `.agents/active/2.4.0-cube-export.md`
- Create: `.agents/completed/2.4.0-cube-export.md`
- Modify: `docs/superpowers/plans/2026-08-02-chemblender-2.4.0-cube-export.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:** No additional public API.

- [ ] **Step 1: Run focused and full verification**

Run Cube readiness/exporter/reader/product/docs/artifact tests, full unittest
discovery, `compileall`, generated docs, optional-import audit and
`git diff --check`.

- [ ] **Step 2: Run two independent reviews**

Run specification-compliance and code-quality/correctness/security reviews.
Fix every Critical, Important and task-related Minor finding and rerun affected
checks.

- [ ] **Step 3: Checkpoint**

Record per-task commits, RED/GREEN evidence, 128 cubed performance, exact
package data, Blender results and reviews. Move the cursor to completed, mark
Tasks 1–6 checked and commit:

```powershell
git commit -m "chore: checkpoint native Cube export"
```

### Task 7: Exact-head remote integration gate

**Files:**
- No product changes after the exact feature head enters CI.

**Interfaces:** Only workflow runs whose `headSha` equals the pushed exact head
are valid. Merge mode is ordinary merge commit.

- [ ] **Step 1: Push and create a ready PR to main**

Confirm a clean worktree, ordinary push, and `origin/main` as an ancestor.

- [ ] **Step 2: Wait for exact-head CI**

Require `extension-package` (`native-core`, `package`) and `optional-qc-core`
(`cclib`, `iodata`, `gbasis`) to pass for the exact head.

- [ ] **Step 3: Merge and verify**

Use an ordinary merge commit, fetch, and prove the exact feature head is an
ancestor of `origin/main`. Do not squash, rebase, force-push, delete branches,
tag or publish a Release.

## Stop Boundary

Stop after native Cube core export is merged and ancestry is verified. Cube UI
and Reader API v1 stable remain unstarted.
