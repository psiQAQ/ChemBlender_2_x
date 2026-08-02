# ChemBlender 2.4.0 PQR Export UI Design

## Goal

Expose the completed deterministic native PQR exporter through the existing
Project Browser export workflow, with exact selected-entity projection, loss
preview, explicit confirmation, background cancellation, atomic publication
and installed Blender native re-import proof.

## Starting state

- Native PQR core export merged through PR #13 at ordinary merge commit
  `54dd2364b6f935771f6d6c661452f44b7d4b558a`.
- Its exact feature head `0abb4e32c6269a2a327bccfb0427c626f70084fb`
  passed `extension-package` run `30739236959` and `optional-qc-core` run
  `30739237004` before merge.
- `ChemBlender.ui.export` already owns the Project Browser operator, selected
  Structure projection, loss confirmation, worker cancellation, progress and
  atomic exporter dispatch.
- `_pdb_entities()` already projects exactly the entity families consumed by
  PQR: one Structure, its BiologicalHierarchy, Structure-bound datasets and
  associated topologies.
- PQR remains `F0 / none`; Cube export and Reader API v1 stable remain deferred.

## Selected approach

Extend the existing `ChemBlender.ui.export` format table and dispatches. Reuse
`_pdb_entities()` directly for PQR preview and writing because it is a
vendor-neutral biological Structure projection despite its private historical
name. Do not add a wrapper, operator, RNA property, registration root, module or
generic exporter abstraction.

Rejected alternatives:

- `_pqr_entities()` delegating to `_pdb_entities()` adds a name without a new
  contract.
- A PQR-specific operator or module duplicates established preview, threading,
  cancellation and cleanup behavior.

## Data flow

1. `resolve_export_selection()` resolves the active Structure and its exact
   BiologicalHierarchy, Structure-bound datasets and associated topologies.
2. `preview_export_selection(selection, "pqr")` calls
   `preview_pqr_export(_pdb_entities(selection))` without serializing or writing.
3. Existing operator logic blocks any loss-bearing report until the exact
   `confirm_loss` bool is true.
4. `ExportJob` calls `export_pqr()` with the same projection, destination,
   confirmation and cancellation callback.
5. The core exporter remains the sole owner of snapshot validation, mandatory
   complete `partial_charge`/`radius` checks, deterministic ASCII/LF output,
   atomic replacement and temporary cleanup.

Missing or ambiguous hierarchy, missing/partial/invalid charge or radius,
FrameSet input and invalid live arrays continue to fail closed in the core
boundary. The UI must not choose among ambiguous entities or repair data.

## Product surface

- Add one `PQR` format choice and `*.pqr` file filter.
- Do not change the default-format heuristic; users explicitly choose PQR.
- Keep the existing loss-preview labels and confirmation checkbox.
- Change the catalog execution mode for PQR from `none` to `project_browser`;
  maturity becomes `F5` with `preview_confirmation`, matching the completed
  reachable workflow.
- Regenerate/check the capability documents from the catalog source.

## Verification

- RED proves PQR is absent from enum/filter/preview/job dispatch and remains F0.
- Selection tests prove the existing projection includes only the selected
  Structure, its exact hierarchy, charge/radius datasets and associated
  topology, excluding unrelated siblings.
- Preview tests prove no writer call, stable core report equality, fail-closed
  missing/partial data and explicit loss confirmation.
- Job tests prove deterministic native re-import, cancellation preservation,
  no temporary residue and unchanged fatal exception behavior.
- Blender 5.1.2 installed smoke selects an imported PQR Structure, exports via
  Project Browser, reparses with native `parse_pqr()` and verifies atom identity,
  hierarchy, coordinates, charges and radii.
- Full tests, compileall, optional-import audit, validate/build, ZIP audit,
  isolated lifecycle and two independent reviews must pass before exact-head CI.

## Non-goals

- no PQR serializer/readiness/model changes;
- no FrameSet or multi-Structure PQR dialect;
- no new UI class, module, RNA collection or registration change;
- no Cube export or Reader API v1 stable work;
- no dependency, schema, workflow, manifest version, CHANGELOG version, tag or
  Release change.

