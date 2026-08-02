# ChemBlender 2.4.0 Task 7 Scope Discovery Design

## Goal

Close the merged PQR Export UI task with exact remote evidence, compare the
remaining 2.4.0 candidates, select one next task, and leave its implementation
queued but unstarted.

## Baseline and Evidence

- Baseline: `eb3fc4ea6f86e8fc3f9475bd03d379445349db57` on `main`.
- PQR Export UI PR #14 merged normally after exact-head CI for
  `3bab75429d37276e27dc158ba5bbf69d9085b9bd`:
  - `extension-package` run `30741155445` passed;
  - `optional-qc-core` run `30741155450` passed.
- GitHub Issues and Discussions are disabled, open PR count is zero, and the
  2.3.0 package and checksum still have zero downloads.
- A GitHub code search found no external `chemblender.reader.json` adopter.
  Absence of evidence is not proof of compatibility adoption.
- The repository has no active or queued task after PQR Export UI completion.

## Candidate Decision

### Selected: deterministic native Cube export

Cube is the last dependency-free built-in reader whose export capability is
`F0 / none`. Existing code already provides:

- `Structure`, `AtomicProperty` and `Grid3D` authority;
- scalar and multi-dataset Cube parsing;
- non-orthogonal step vectors and `bohr` geometry;
- nuclear-charge and source-convention provenance;
- sidecar/canonical round-trip;
- derived OpenVDB cache reconstruction and product-flow benchmarks.

The remaining uncertainty is narrow and testable: writer/readiness rules,
dataset selection, native-unit preservation, source comments, dataset IDs and
semantic loss confirmation.

### Deferred: Reader API v1 stable

The public token remains `1.0-rc1`, with schema snapshots and a conformance
suite. Stable promotion is deferred because there is no external adopter or
compatibility feedback. Export work must not silently enlarge this promise.

### Rejected: combined Cube core, UI and API promotion

Combining scientific serialization, product UI and a stable public API would
couple three independent validation and rollback boundaries. Cube core export
must qualify first; UI remains a later task using the proven core contract.

## Scope Discovery Outputs

This task creates only:

1. a live candidate-intake record under
   `docs/quantum-visualization/2.4.0/`;
2. a detailed deterministic native Cube export implementation plan;
3. one queued Execution Cursor for the selected Cube task;
4. documentation contract tests proving the routing and stop boundary.

The Scope Discovery cursor is completed in the same branch. It does not leave
an active task because the selected implementation remains queued.

## Selected Cube Export Boundary

The queued implementation will design and test a pure-core exporter that:

- accepts exactly one linked `Structure`, one selected `Grid3D`, and the
  matching complete `nuclear_charge` `AtomicProperty`;
- supports scalar `xyz` grids and one explicitly selected dataset from a
  `dataset, x, y, z` grid;
- preserves affine origin and full step vectors without orthogonalization;
- writes coordinates, origin and steps in a single explicit Cube length unit;
- preserves atom nuclear charges separately from atomic numbers;
- emits deterministic comments, counts, values and line endings;
- preserves source dataset IDs when they remain valid, otherwise reports a
  stable, confirmation-required normalization loss;
- snapshots lazy arrays once, writes through the existing short-sibling atomic
  path, and cleans up on cancellation or failure;
- reparses through native `parse_cube()` and compares scientific semantics,
  not UUIDs, provenance identity, whitespace or cache artifacts.

Ambiguous field role/value unit may be exported only with explicit loss
confirmation because the Cube syntax cannot reliably encode those semantics.
OpenVDB, Blender Volume and mesh caches are never export sources.

## Error and Trust Boundaries

- Missing or cross-linked Structure/nuclear-charge data fails closed.
- Unknown, dimensionless or mixed coordinate units fail before publication.
- Non-finite values, invalid shapes and unsupported leading dimensions fail
  before a destination is replaced.
- Multi-dataset grids require one explicit valid dataset selection; the writer
  does not silently export the first dataset.
- A live mutation between preview and publication invalidates the snapshot.
- Fatal exceptions are not converted into ordinary export diagnostics.

## Verification and Stop Boundary

Scope Discovery verification is limited to documentation routing, link and
UTF-8 contracts plus `git diff --check`. Two independent reviews verify the
selection and plan. No full product or Blender run is needed because runtime
does not change.

Stop after committing the candidate evidence, plan and queued cursor. Do not
create a Cube exporter, modify UI, change the Reader API token, schema,
dependencies, manifest version, CHANGELOG, tag or Release.
