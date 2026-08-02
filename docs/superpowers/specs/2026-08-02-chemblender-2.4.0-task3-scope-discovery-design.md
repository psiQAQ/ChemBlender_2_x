# ChemBlender 2.4.0 Task 3 Scope Discovery Design

## Goal

Close the completed MOL2 Export UI work with exact remote evidence, refresh the
post-MOL2 product evidence, compare four bounded candidates, and select exactly
one ChemBlender 2.4.0 Task 3 without starting runtime implementation.

## Starting state

- `main` and `origin/main` are both
  `99548d8aff8bea162651273ff5d723e57be5279c`.
- MOL2 Export UI PR #10 is merged. Its exact feature head is
  `819575f3210d9db92b33b2e5e11cc02590680564`.
- Exact-head runs `30708862898` (`extension-package`) and `30708862900`
  (`optional-qc-core`) passed before the ordinary merge commit.
- MOL2 export is F5 through the Project Browser. PDB, PQR and Cube export remain
  F0. Reader API remains `1.0-rc1`.
- `.agents/queued/` does not currently contain a next task.

All dynamic facts must be refreshed before the selection checkpoint. This
snapshot is recovery context, not permission to copy stale conclusions.

## Deliverables

The discovery task produces only planning and recovery artifacts:

1. move the completed MOL2 Export UI cursor from `.agents/active/` to
   `.agents/completed/` and add PR #10, exact-head CI and merge evidence;
2. create a post-MOL2 candidate intake under
   `docs/quantum-visualization/2.4.0/`;
3. select exactly one Task 3 candidate, with explicit rejected/deferred reasons;
4. create one implementation plan and one queued cursor for the selected task;
5. leave no active product implementation after the discovery checkpoint.

The discovery may select none if live evidence invalidates every candidate. It
must not invent work merely to keep the roadmap busy.

## Candidate set

Only these candidates are in scope:

| Candidate | Existing evidence | Primary risk |
| --- | --- | --- |
| Native PDB export | F0 capability; frozen `pdb_export_readiness()` contract and PDB fixtures | fixed-column formatting, hierarchy, MODEL/altloc and controlled topology loss |
| Native PQR export | F0 capability; frozen `pqr_export_readiness()` contract and PQR fixtures | validated whitespace dialect, mandatory charge/radius and single-structure boundary |
| Native Cube export | F0 capability; mature Structure/Grid3D import and scientific cache boundary | no frozen writer/readiness contract; multi-dataset and native-unit semantics |
| Reader API v1 stable gate | public token remains `1.0-rc1`; conformance suite exists | premature compatibility promise without external adopter evidence |

PDB and PQR remain separate implementation candidates. A shared readiness
module is not evidence that both writers should be bundled.

## Selection method

Refresh GitHub feedback and release adoption evidence, then score each candidate
against the same questions:

- Is there a confirmed user, compatibility or capability need?
- Is the scientific representation contract already frozen?
- Can one dependency-neutral vertical slice be completed and semantically
  re-imported without changing the model, sidecar schema or Reader API token?
- Can loss be enumerated and explicitly confirmed rather than silently dropped?
- Can the installed Blender product path prove the result?
- Does the task stay smaller and lower-risk than the alternatives?

The intake records facts separately from inference and recommendation. It names
one selected task, its minimum result, stop boundary, required verification and
the evidence that deferred every other candidate.

## Recovery-state transition

The completed MOL2 cursor is archived before a new queued cursor is created.
The archived record must include PR #10, both exact-head run IDs, the verified
head SHA, ordinary merge commit and ancestor result. The new queued cursor must
name the selected Task 3 plan and remain `not_started`.

There is no simultaneous active Wave or hidden product implementation. The
discovery checkpoint itself is represented by the completed discovery record;
the selected implementation becomes active only after a later explicit user
instruction.

## Failure handling

- If local and remote `main` diverge, stop before writing selection evidence.
- If PR #10 or its runs do not match the recorded exact head, mark the closeout
  blocked rather than substituting another run.
- If live feedback points to a reproducible 2.3.0 regression, route it to a
  separate maintenance intake; do not hide it inside Task 3.
- If a candidate requires a new dependency, schema change or model expansion,
  defer it unless that expansion is independently justified and designed.

## Verification

- focused documentation contracts for active/completed/queued routing;
- generated capability documentation remains fresh;
- `python -m compileall -q tests`;
- UTF-8 without BOM and existing line endings for every edited text file;
- zero runtime, dependency, manifest, version, workflow and release diff;
- `git diff --check` and a clean checkpoint worktree.

## Non-goals

- no PDB, PQR or Cube writer code;
- no Project Browser or Blender UI change;
- no model, sidecar, Reader API, dependency or workflow change;
- no manifest version, CHANGELOG release entry, tag or Release;
- no push, PR or other remote write in this discovery task.
