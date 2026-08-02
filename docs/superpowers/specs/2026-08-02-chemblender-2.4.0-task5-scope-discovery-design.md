# ChemBlender 2.4.0 Task 5 Scope Discovery Design

## Goal

Close PDB Export UI with exact remote integration evidence, compare the three
remaining bounded candidates, and select exactly one ChemBlender 2.4.0 Task 5
without starting runtime implementation.

## Starting state

- PR #12 merged PDB Export UI into `main` with ordinary merge commit
  `d5028aa5d8568a44181b822293fbe62462d9a496`.
- Its exact feature head is
  `5756532077d8aca8cebc54becf411133af7f96d8`.
- Exact-head runs `30728969782` (`extension-package`) and `30728969751`
  (`optional-qc-core`) passed before merge.
- PDB export is `F5 / project_browser / preview_confirmation`. PQR and Cube
  export remain F0. Reader API remains `1.0-rc1`.
- The merged PDB UI cursor still records the pre-merge remote gate and must be
  archived with the final evidence.

Dynamic facts are refreshed during execution. This snapshot is recovery
context, not permission to reuse stale evidence.

## Deliverables

This discovery produces planning and recovery artifacts only:

1. archive the PDB UI cursor with PR #12, exact-head CI, merge and ancestry
   evidence;
2. create a post-PDB-UI candidate intake;
3. select exactly one Task 5 candidate with explicit deferral reasons;
4. create one implementation plan and one queued cursor for the selection;
5. finish with no active product implementation and zero runtime diff.

## Candidate set

| Candidate | Existing evidence | Primary risk |
| --- | --- | --- |
| Native PQR export | frozen `pqr_export_readiness()`, native whitespace reader and four fixture families | mandatory charge/radius, single-Structure dialect and explicit loss reporting |
| Native Cube export | mature Structure/Grid3D import and derived-cache boundary | no writer/readiness contract; multi-dataset and native-unit policy |
| Reader API v1 stable gate | `1.0-rc1` snapshot and conformance suite | premature compatibility promise without external adopter evidence |

## Recommended selection

Select **Native PQR export** if the live audit confirms the current gap. It is
the smallest evidence-backed core slice: the internal Structure, hierarchy,
charge/radius datasets, readiness tokens, reader and fixtures already exist.
The missing boundary is a dependency-free deterministic writer with preview,
loss confirmation, atomic publication, cancellation cleanup and semantic
native re-import.

The implementation should reuse the existing PDB exporter report and atomic
writer patterns without merging the PDB and PQR serializers. It must remain a
single-Structure PQR dialect task and must not add UI, FrameSet support, a new
model, schema, dependency or Reader API token.

## Selection method

For each candidate, verify current capability maturity, existing contracts,
dependency needs, semantic round-trip proof, product reachability and scope
size. Facts, inference and recommendation remain separate in the intake.
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

- no PQR runtime implementation or UI;
- no Cube writer;
- no Reader API token change;
- no model, schema, dependency, manifest, workflow, version or release change.
