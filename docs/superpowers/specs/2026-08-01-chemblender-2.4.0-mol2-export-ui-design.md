# ChemBlender 2.4.0 MOL2 Export UI Design

## Goal

Expose the completed native MOL2 writer through the existing Project Browser export
workflow without introducing a second UI or export lifecycle.

## Decision

Extend `ChemBlender.ui.export.CHEMBLENDER_OT_export_project_entity`,
`ExportSelection` and `ExportJob`. The existing module already owns format selection,
loss preview, explicit confirmation, background cancellation, progress UI and cleanup.
A MOL2-specific operator would duplicate those boundaries and is rejected.

## Data flow

```text
Project Browser selection
  -> resolve_export_selection()
  -> selected Structure/Topology/Record/Annotations/Datasets
  -> preview_mol2_export()
  -> optional explicit confirmation
  -> ExportJob
  -> export_mol2(destination, is_cancelled=...)
  -> atomic destination replacement
  -> native parse_mol2() semantic check in product smoke
```

`ExportSelection` gains only the Structure-targeted annotations required by the frozen
MOL2 contract. A private projection builds the attribute-based entity collection expected
by the core writer. It contains one selected Structure and its selected topology/record;
it never passes the whole project, so exporting one browser row cannot serialize unrelated
records.

## UI behavior

- Add `mol2` to the existing format enum and `*.mol2` to `filter_glob`.
- Keep the current Project Browser Export button and explicit `.ui.export` registration
  root; add no new class or RNA collection.
- `preview_export_selection(selection, "mol2")` delegates to
  `preview_mol2_export()` and displays its stable loss entries.
- A loss-bearing preview keeps `confirm_loss=False`; execute fails before starting the
  worker until the user explicitly confirms.
- ConformerSet-to-MOL2 is rejected because the selected core contract represents one
  normalized molecular record; SDF remains the conformer export path.
- Existing default-format behavior remains unchanged. MOL2 is an explicit format choice,
  avoiding heuristic inspection of raw bytes in the UI layer.

## Execution and failure behavior

`ExportJob` delegates MOL2 output to `export_mol2()` with the existing cancellation event,
confirmation flag and destination. Task 1 already owns deterministic text, loss policy and
same-directory atomic replacement. The UI does not catch fatal process-control exceptions,
does not write a temporary file itself and does not retain project arrays in RNA.

Cancellation or ordinary failure leaves the prior destination intact and removes writer-owned
temporary files. Operator cleanup continues to join the worker and release progress/timer
ownership exactly once.

## Files and tests

Expected product changes are limited to:

- `ChemBlender/ui/export.py`;
- `tests/test_extxyz_workflow.py` for the shared export workflow;
- `tests/blender_smoke.py` for real MOL2 export and native re-import;
- generated/user capability documentation only if its current text does not already describe
  the resulting UI capability.

TDD must first prove that MOL2 is absent from the format enum, annotations are absent from the
selection projection and `ExportJob` cannot dispatch the writer. Focused GREEN must cover
choice/filter, selection, preview confirmation, background write/re-import, cancellation and
existing registration/RNA bounds. Full tests, compileall, Blender 5.1.2 validate/build,
isolated install/product smoke, ZIP audit and two independent reviews follow before any push.

## Non-goals

No PDB/PQR/Cube exporter, new model, schema/API token, dependency, performance framework,
version bump, changelog release entry, tag or Release belongs to this task.
