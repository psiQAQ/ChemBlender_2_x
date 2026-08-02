# ChemBlender 2.4.0 Native Cube Export UI Design

## Goal

Expose the completed deterministic native Cube exporter through the existing
Project Browser export workflow, using an explicitly selected `Grid3D`, exact
linked entities, explicit multi-dataset choice, loss confirmation, background
cancellation and installed native re-import proof.

## Starting State

- Native Cube core export merged through PR #15 at ordinary merge commit
  `cd265d95c3cc73cae5355657cc0a5a8f1931d98b`.
- Its exact feature head `164a681bb3d9cb788f778eca71f9fe61a0361019`
  passed `extension-package` run `30747458150` and `optional-qc-core` run
  `30747458152` before merge.
- Project Browser already exposes `Grid3D` dataset rows with their entity UUID.
- `ChemBlender.ui.export` already owns the operator, preview, explicit loss
  confirmation, worker cancellation, progress and publication flow.
- `resolve_export_selection()` currently rejects a selected `Grid3D`.
- Cube is `F5 / core / preview_confirmation`; Reader API remains `1.0-rc1`.

## Selected Approach

Reuse `ChemBlender.ui.export`. Extend `ExportSelection` with one optional
`Grid3D` field and add one selected-grid branch to
`resolve_export_selection()`. Project only:

- the selected grid;
- its exact linked `Structure`;
- all matching `nuclear_charge` `AtomicProperty` candidates, so the core
  readiness boundary still detects missing or ambiguous charges;
- direct provenance needed by the core writer;
- topology context already used for loss reporting.

Pass that projection to `preview_cube_export()` and `export_cube()`. The core
exporter remains the sole readiness, snapshot, loss, serialization and atomic
publication boundary.

Add no Cube-specific operator, module, registration root, readiness wrapper,
serializer, model or generic export abstraction.

## Interaction and Data Flow

1. The user selects a `Grid3D` row in Project Browser and invokes the existing
   export operator.
2. Default format becomes `cube`; the filter includes `*.cube`.
3. Scalar grids pass `dataset_index=None`.
4. Multi-dataset grids expose one integer `Dataset Index` field. Its initial
   value is `-1`, meaning not selected. On first `invoke()`, this incomplete UI
   state opens the existing file dialog with a `Select Dataset Index` message
   instead of calling the core preview and cancelling the dialog. This is an
   explicit dataset index, never a default selection.
5. Property updates call the core preview once the index is valid. `execute()`
   always rejects `-1` or an out-of-range index, so the incomplete invoke state
   can never publish output.
6. `preview_export_selection()` delegates to `preview_cube_export()` and shows
   the existing loss messages and confirmation checkbox.
7. `ExportJob` delegates to `export_cube()` with the same projection, selected
   index, destination, confirmation and cancellation callback.
8. The capability catalog changes to `project_browser` only after installed
   Blender export and native `parse_cube()` re-import succeed.

The `-1` sentinel is UI state only and is converted to `None`; it never enters
the core model, sidecar, manifest or provenance. A scalar grid ignores stale UI
index state and always passes `None`.

## Failure and Trust Boundaries

- Selecting anything other than a supported export entity remains unchanged.
- Missing/cross-linked Structure or nuclear charge fails closed.
- More than one matching charge property fails closed; the UI never chooses
  among ambiguous scientific entities.
- Another `Grid3D` linked to the same Structure is excluded unless it is the
  selected grid; the UI must not recreate the core `grid.ambiguous` condition.
- Multi-dataset export never silently selects index zero.
- The incomplete `-1` invoke state may open the dialog but cannot execute or
  create/replace a destination.
- Loss-bearing output requires the existing exact confirmation bool.
- Cancellation and failure preserve an existing destination and leave no
  temporary sibling.
- Fatal exceptions retain current passthrough behavior.
- OpenVDB, Blender Volume and surface/mesh caches are never export sources.

## Verification

- A dedicated pure-Python UI contract test covers exact selected-grid
  projection, sibling exclusion, scalar/multi-dataset preview, explicit index,
  confirmation, background dispatch, cancellation and native re-import.
- Existing Project Browser and registration tests prove the row and explicit
  `.ui.export` root remain unchanged.
- Generated capability documents move Cube from `core` to `project_browser`.
- Blender 5.1.2 installed smoke selects a multi-dataset Cube grid, exports one
  explicit dataset through `ExportJob`, reparses it with native `parse_cube()`
  and verifies structure, nuclear charges, affine grid, dataset identity and
  scalar values.
- Full tests, compileall, optional-import audit, validate/build, ZIP audit,
  isolated lifecycle and two independent reviews precede exact-head CI.

## Non-Goals

- no Cube core serializer/readiness/model change;
- no new UI class, module or registration root;
- no automatic dataset selection or batch Cube export;
- no Reader API stable promotion or 2.4.0 Final Qualification;
- no dependency, schema, workflow, manifest version, CHANGELOG version, tag or
  Release change.
