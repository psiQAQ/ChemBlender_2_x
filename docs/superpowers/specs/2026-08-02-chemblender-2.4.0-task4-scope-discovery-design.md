# ChemBlender 2.4.0 Task 4 Scope Discovery Design

## Goal

Close native PDB export with exact remote integration evidence, compare four
bounded candidates, and select exactly one ChemBlender 2.4.0 Task 4 without
starting runtime implementation.

## Starting state

- PR #11 merged native PDB core export into `main` with ordinary merge commit
  `79a93f52053fdf809c28c24800366010577a1984`.
- Its exact feature head is
  `2995386744768b424e8276db7cd72a90154edf25`.
- Exact-head runs `30724971581` (`extension-package`) and `30724971598`
  (`optional-qc-core`) passed before merge.
- PDB export is `F5 / core / preview_confirmation`, but `ui.export` exposes no
  PDB format choice. PQR and Cube export remain F0. Reader API remains
  `1.0-rc1`.
- No active or queued cursor exists on the merged baseline.

Dynamic facts are refreshed during execution. This snapshot is recovery
context, not permission to reuse stale evidence.

## Deliverables

This discovery produces planning and recovery artifacts only:

1. record PR #11, exact-head CI, merge and ancestry evidence;
2. create a post-PDB candidate intake;
3. select exactly one Task 4 candidate with explicit deferral reasons;
4. create one implementation plan and one queued cursor for the selection;
5. finish with no active product implementation and zero runtime diff.

## Candidate set

| Candidate | Existing evidence | Primary risk |
| --- | --- | --- |
| PDB Export UI | core PDB writer and loss preview are F5; the shared Project Browser export lifecycle is proven | selecting exactly one Structure, hierarchy, related datasets and source metadata |
| Native PQR export | frozen PQR readiness contract and native reader fixtures | mandatory charge/radius, single-Structure whitespace dialect |
| Native Cube export | mature Structure/Grid3D import and derived-cache boundary | no writer/readiness contract; multi-dataset and native-unit policy |
| Reader API v1 stable gate | `1.0-rc1` snapshot and conformance suite | premature compatibility promise without external adopter evidence |

## Recommended selection

Select **PDB Export UI** if the live audit confirms the current gap. It is the
smallest product closure because `ChemBlender.ui.export` already owns format
selection, preview, confirmation, background cancellation, cleanup and atomic
publication. The implementation should reuse that operator and the existing
`preview_pdb_export()` / `export_pdb()` core boundary.

The UI needs only a selected-entity projection containing one Structure, its
one BiologicalHierarchy, related datasets, topology/source/revision context,
plus one preview and job dispatch branch. It must not create a PDB-specific
operator, model, writer, registration root or lifecycle.

## Selection method

For each candidate, verify current capability maturity, existing contracts,
dependency needs, semantic round-trip proof, Blender product reachability and
scope size. Facts, inference and recommendation remain separate in the intake.
Select none if live evidence invalidates every candidate.

## Recovery transition

The discovery cursor is active only while evidence and plans are written. At
completion it moves to `.agents/completed/`; one selected implementation cursor
moves to `.agents/queued/` with `State: not_started`. Runtime implementation
requires a later explicit activation.

## Verification

- documentation routing and recoverability contracts;
- generated capability documents remain unchanged and fresh;
- UTF-8/no-BOM audit for edited files;
- `python -m compileall -q tests`;
- zero diff under `ChemBlender/`, `worker/`, `.github/`, manifest and CHANGELOG;
- `git diff --check` and clean committed worktree.

## Non-goals

- no PDB UI runtime implementation;
- no PQR or Cube writer;
- no Reader API token change;
- no model, schema, dependency, manifest, workflow, version or release change.
