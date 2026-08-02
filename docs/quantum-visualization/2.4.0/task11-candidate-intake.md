# ChemBlender 2.4.0 Task 11 Candidate Intake

## Confirmed Facts

- Baseline: `73e774bb1da93bf009e8dedaa3e67f5860cf6722` on
  `origin/main`.
- Native Cube Export UI PR #17 merged normally for exact head
  `f63b0a5da47f76dd38f7cf5e79a39e99cf918005`.
- Exact-head CI passed:
  - `extension-package` run `30755106798`;
  - `optional-qc-core` run `30755106795`.
- The exact head is an ancestor of the baseline merge commit.
- Cube is now `F5 / project_browser / preview_confirmation`.
- The prior 2.4.0 tasks qualified deterministic core and Project Browser
  export paths for MOL2, PDB, PQR and Cube.
- Reader API remains `1.0-rc1`.
- On 2026-08-02, GitHub code search returned no external
  `chemblender.reader.json` result and both v2.3.0 Release assets reported
  0 downloads. This is an absence of adoption evidence, not proof that no
  private adopter exists.
- `origin/main` contains no active or queued Execution Cursor after PR #17.

## Candidate Comparison

| Candidate | Existing evidence | Remaining uncertainty | Decision |
| --- | --- | --- | --- |
| Task 12 — 2.4.0 Final Qualification | native export product paths, local qualification, exact-head CI and ordinary merges | one consolidated current-tree product and package gate | Selected |
| Reader API v1 stable gate | RC schema, public documentation, conformance kit and failure isolation | no adopter or compatibility feedback | Deferred |

## Inference

Final Qualification is an evidence-consolidation task over existing behavior.
It can detect drift across public models, generated capabilities, package
contents, optional dependencies and Blender product workflows without adding
another scientific feature.

Reader API stable is an irreversible compatibility promise. The repository
has strong internal RC conformance evidence but no external feedback that
would justify changing the public token. The two gates have different rollback
boundaries; do not combine them.

## Recommendation

Select `Task 12 — 2.4.0 Final Qualification`.

- Keep Reader API v1 stable gate `Deferred`; preserve `1.0-rc1` during
  qualification.
- Audit only existing committed interfaces and budgets.
- Require focused fixes and fresh exact-head CI for any qualification finding.
- Use an ordinary merge commit only after every required gate passes.

## Stop Boundary

This intake selects and queues one task only. Final Qualification execution,
Reader API stable promotion, new capabilities, version/CHANGELOG changes,
push, PR, merge, tag and Release remain unstarted.
