# ChemBlender 2.4.0 Task 11 Scope Discovery Design

## Goal

Close the merged Native Cube Export UI task with exact remote evidence,
compare the two remaining 2.4.0 candidates, select one next task, and leave
that task queued but unstarted.

## Baseline and Live Evidence

- Baseline: `73e774bb1da93bf009e8dedaa3e67f5860cf6722` on
  `origin/main`.
- Native Cube Export UI PR #17 merged normally after exact-head CI for
  `f63b0a5da47f76dd38f7cf5e79a39e99cf918005`:
  - `extension-package` run `30755106798` passed `native-core` and `package`;
  - `optional-qc-core` run `30755106795` passed `cclib`, `iodata` and
    `gbasis`.
- The exact feature head is an ancestor of the baseline merge commit.
- Cube now reports `F5 / project_browser / preview_confirmation`, matching
  the common product workflow used by the other qualified native exporters.
- The merged branch recorded 2198 Passed / 26 Skipped / 0 Failed, Blender
  5.1.2 validate/build/isolated install/product smoke, a clean 189-member ZIP
  audit and two independent `Ready` reviews.
- `origin/main` contains no active or queued Execution Cursor after PR #17.
- Reader API remains `1.0-rc1`. A live GitHub code search returned no external
  `chemblender.reader.json` adopter, and both 2.3.0 Release assets still report
  zero downloads. Absence of evidence is not proof of compatibility adoption.

## Candidate Decision

### Selected: 2.4.0 Final Qualification

The remaining export work selected by prior 2.4.0 discovery gates is now
complete: MOL2, PDB, PQR and Cube have deterministic core writers, explicit
loss previews, Project Browser execution, cancellation, atomic publication,
native semantic re-import checks and exact-head CI evidence.

Final Qualification is therefore the smallest justified next boundary. It
consolidates evidence for the already-built product without adding another
format, model, schema, dependency or public API promise.

### Deferred: Reader API v1 stable gate

Stable promotion remains deferred. The repository has an RC schema,
documentation, conformance kit and failure-isolated discovery path, but no
external adopter or compatibility feedback. Final Qualification must preserve
the `1.0-rc1` token and may audit it, but must not silently promote it.

### Rejected: combined stable promotion and Final Qualification

Combining an irreversible public compatibility promise with product
qualification would couple two independent acceptance and rollback
boundaries. A later stable gate requires its own evidence and decision.

## Scope Discovery Outputs

Task 11 creates only:

1. final PR #17 and exact-head CI evidence in the completed Cube UI cursor;
2. one live candidate-intake record under
   `docs/quantum-visualization/2.4.0/`;
3. one Final Qualification design and executable implementation plan;
4. one queued Final Qualification Execution Cursor with state `not_started`;
5. documentation contract tests proving routing and stop boundaries.

The Task 11 cursor is completed in the same branch. No runtime, workflow,
manifest, model, schema, dependency, version, changelog, tag or Release file
changes belong to this discovery task.

## Selected Final Qualification Boundary

The queued gate will qualify, without enlarging, the current 2.4.0 product:

- audit the public model, sidecar schema, Reader API `1.0-rc1`, capability
  matrix and generated user documentation for drift;
- rerun complete standard-library, optional-dependency and generated-document
  suites plus `compileall` and import-isolation checks;
- validate the exact extension ZIP inventory, hashes, wheel pins, artifact
  budget and path safety from a clean committed tree;
- run Blender 5.1.2 native validate/build, isolated install, repeated
  register/unregister/reload and representative MOL2/PDB/PQR/Cube
  import-export-reimport workflows;
- rerun performance and memory contracts only where an existing committed
  budget already defines a pass/fail threshold;
- obtain specification-compliance and code-quality/security reviews;
- push one exact feature head, require both existing GitHub Actions workflows
  to pass that SHA, and use an ordinary merge commit only after the gate is
  green.

The gate may fix qualification findings with focused tests, but it may not add
new scientific capabilities or promote Reader API stable. Any product change
invalidates prior exact-head CI evidence and must be requalified.

## Error and Trust Boundaries

- Only CI whose `headSha` equals the final pushed qualification head is valid.
- A failed required unit, package, Blender, optional-dependency, documentation
  or review gate blocks merge; old or unrelated runs cannot substitute.
- Generated artifacts are rebuilt from the committed tree; mixed-line-ending
  worktree artifacts are not budget authority.
- Fatal Blender/runtime failures remain failures rather than cleanup warnings.
- Findings outside the qualification boundary are recorded and deferred, not
  folded into an unrelated refactor.

## Verification and Stop Boundary

Task 11 verification is documentation-only: focused routing tests,
generated-document tests, `compileall -q tests`, UTF-8/no-BOM checks,
protected-path diff audit and `git diff --check`, followed by two independent
reviews.

Stop after committing the candidate evidence, queued Final Qualification plan
and completed Task 11 cursor. Do not activate Final Qualification, promote
Reader API stable, modify a version or changelog, push, create a PR, tag or
publish a Release.
