# ChemBlender 2.4.0 Task 9 Scope Discovery Design

## Goal

Close the merged native Cube core-export task with exact remote evidence,
compare the remaining 2.4.0 candidates, select one next task, and leave its
runtime implementation queued but unstarted.

## Baseline and Evidence

- Baseline: `cd265d95c3cc73cae5355657cc0a5a8f1931d98b` on `origin/main`.
- Native Cube export PR #15 merged normally after exact-head CI for
  `164a681bb3d9cb788f778eca71f9fe61a0361019`:
  - `extension-package` run `30747458150` passed;
  - `optional-qc-core` run `30747458152` passed.
- The Cube feature head is an ancestor of the baseline merge commit.
- The capability catalog still reports Cube as
  `F5 / core / preview_confirmation`; every other built-in exporter with a
  product workflow is exposed through `project_browser`.
- Project Browser already projects `Grid3D` rows as selectable dataset
  entities, and `.ui.export` is already an explicit registration root.
- `resolve_export_selection()` currently rejects a selected `Grid3D`; this is
  the narrow product gap between the qualified core writer and the existing
  export operator.
- Reader API remains `1.0-rc1`. A live GitHub code search found no external
  `chemblender.reader.json` adopter, and the public 2.3.0 artifacts still have
  zero downloads. Absence of evidence is not proof of compatibility adoption.

## Candidate Decision

### Selected: native Cube export UI

Cube core readiness, serialization, cancellation, atomic replacement and
semantic re-import are already qualified. The smallest remaining product task
is to route an explicitly selected `Grid3D` through the existing Project
Browser export workflow.

The implementation must reuse:

- the existing `CHEMBLENDER_OT_export_project_entity` operator;
- the existing `ExportSelection`, preview, confirmation and `ExportJob` flow;
- `preview_cube_export()` and `export_cube()` as the sole scientific and
  publication boundary;
- the current `.ui.export` registration root.

It must not add a Cube-specific operator, UI module, registration root,
serializer, model, schema or dependency.

### Deferred: Reader API v1 stable gate

Stable promotion is deferred until there is real adopter or compatibility
evidence. UI routing must not enlarge or rename the Reader API public surface.

### Deferred: 2.4.0 final qualification

Final qualification is premature while Cube remains the only core-qualified
exporter without a Project Browser path. It follows the selected UI task and
does not belong in this discovery checkpoint.

## Selected UI Boundary

The queued implementation will:

1. accept a selected `Grid3D` from the existing Project Browser dataset row;
2. resolve its exact linked `Structure`, matching nuclear-charge property and
   Cube provenance without including unrelated project siblings;
3. add one `Cube` format choice and `*.cube` filter to the existing operator;
4. require an explicit `dataset_index` for multi-dataset grids and expose the
   choice in the existing export dialog rather than silently selecting zero;
5. delegate preview and writing to the core Cube exporter;
6. reuse loss confirmation, background cancellation and atomic publication;
7. change the catalog execution mode from `core` to `project_browser` only
   after an installed Blender export/re-import smoke passes.

Single-dataset grids need no dataset selector. Invalid links, missing nuclear
charges, stale lazy arrays, ambiguous units, non-finite values and unsupported
shapes continue to fail closed in the core exporter.

## Scope Discovery Outputs

This task creates only:

1. a live candidate-intake record under
   `docs/quantum-visualization/2.4.0/`;
2. a detailed native Cube export UI design and implementation plan;
3. one queued Execution Cursor for the selected UI task;
4. documentation contract tests proving routing and stop boundaries.

No visual companion is needed: this task extends an established dialog and
does not introduce a new layout or interaction model.

## Verification and Stop Boundary

Scope Discovery verification is limited to documentation routing, links,
UTF-8 contracts, generated-document freshness and `git diff --check`. Two
independent reviews verify the selection and executable plan. Full product and
Blender runs are deferred because runtime does not change.

Stop after committing the evidence, selected plan and queued cursor. Do not
modify `ChemBlender/`, `worker/`, `.github/`, the manifest, CHANGELOG, schema,
Reader API token, tag or Release. Do not activate the Cube UI task, push or
create a PR.
