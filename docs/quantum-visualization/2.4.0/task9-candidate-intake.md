# ChemBlender 2.4.0 Task 9 Candidate Intake

## Confirmed Facts

- Baseline: `cd265d95c3cc73cae5355657cc0a5a8f1931d98b`.
- Native Cube export PR:
  `https://github.com/psiQAQ/ChemBlender_2_x/pull/15`.
- Exact feature head: `164a681bb3d9cb788f778eca71f9fe61a0361019`.
- Exact-head CI passed:
  - `extension-package` run `30747458150`;
  - `optional-qc-core` run `30747458152`.
- Ordinary merge and ancestry: `cd265d95c3cc73cae5355657cc0a5a8f1931d98b`,
  `Passed`.
- Current capabilities:
  - Cube: F5 / core / preview_confirmation;
  - Reader API: 1.0-rc1.
- `Grid3D` is already a selectable Project Browser dataset row.
- `ChemBlender.ui.export` is already an explicit registration root and owns
  format choice, preview, confirmation, background cancellation and export
  publication.
- `resolve_export_selection()` currently accepts Structure, MolecularRecord,
  ConformerSet and FrameSet, but rejects a selected `Grid3D`.
- A live GitHub code search found no external `chemblender.reader.json` adopter;
  the 2.3.0 Release artifacts still report zero downloads.

## Candidate Comparison

| Candidate | Evidence | Remaining uncertainty | Decision |
| --- | --- | --- | --- |
| Native Cube Export UI | Qualified core writer and existing Project Browser flow | exact Grid3D projection and explicit dataset choice | selected |
| Reader API v1 stable gate | rc1 schema and conformance suite exist | no external adopter or compatibility feedback | deferred |
| 2.4.0 Final Qualification | accumulated 2.4.0 export tasks are qualified | Cube still lacks the common product workflow | deferred |

## Inference

Cube UI is a narrow reachability task, not a new scientific serializer. The
existing Project Browser already exposes the selected entity and the existing
operator already supplies preview, explicit confirmation, cancellation and
atomic publication. Extending this route has a smaller validation and rollback
surface than promoting a public API without adopter evidence or qualifying a
release with one remaining core-only exporter.

## Recommendation

Select `Task 10 — Native Cube Export UI`.

- Reader API stable: deferred until real adopter or compatibility evidence
  exists.
- Final Qualification: deferred until Cube reaches the same Project Browser
  execution path as the other product exporters.

The next task must reuse `ChemBlender.ui.export`, `preview_cube_export()` and
`export_cube()`. It must not create a Cube-specific operator/module, duplicate
readiness or atomic-write logic, or change the Reader API token, model, schema
or dependencies.

## Stop Boundary

This intake selects and queues a task only. Cube UI runtime implementation,
Reader API stable promotion, Final Qualification, versioning, push, PR, tag and
Release remain unstarted.
