# ChemBlender 2.4.0 Final Qualification Design

## Goal

Qualify the complete committed ChemBlender 2.4.0 product surface without
adding a feature, changing a scientific model or making a release.

## Boundary

- Preserve Reader API `1.0-rc1`; stable promotion is a separate decision.
- No new capability, format, model, schema, dependency, workflow, version or
  CHANGELOG entry belongs to this gate.
- Audit only behavior and budgets already committed before activation.
- Findings may receive the smallest focused fix and regression test, but each
  fix invalidates older qualification and exact-head CI evidence.
- Build authority is the clean committed tree, never a mixed-line-ending or
  dirty worktree artifact.

## Qualification Pipeline

### Public and scientific boundaries

Verify public core/Reader API imports, sidecar and canonical schema versions,
reader manifests, generated capability matrices, export maturity and optional
dependency isolation. Third-party objects must not leak into project or
sidecar entities.

### Python and optional dependencies

Run complete Python 3.13 unittest discovery, compileall, generated-document
checks, import isolation and the existing pinned cclib, IOData and GBasis
integration contracts. Existing skipped optional tests remain visible; do not
convert failures into skips.

### Extension artifact

Using Blender 5.1.2 bundled Python and the pinned RDKit/Gemmi wheels, run native
extension validate/build from the committed tree. Audit exact ZIP paths, CRC,
wheel inventory/licenses, hashes, section sizes, artifact budget and release
metadata without changing the manifest version.

### Blender product workflows

Install the built ZIP into an isolated `BLENDER_USER_RESOURCES`, then run
register/unregister/reload twice and representative MOL2, PDB, PQR and Cube
import-export-reimport flows through Project Browser. Validate cancellation,
atomic publication and save/reopen behavior using existing smoke paths.

### Review and remote integration

Require independent specification-compliance and code-quality/security
reviews. Push one final checkpoint head, require both existing workflows to
pass exact-head CI, and integrate only through an ordinary merge commit.

## Failure Policy

- Any required test, package, Blender, optional-dependency or review failure
  blocks the gate.
- Cleanup warnings are non-blocking only when the owning process exited zero
  and scientific artifacts were verified before cleanup.
- A finding outside the frozen qualification boundary is recorded for later;
  it does not authorize unrelated refactoring.
- No old, branch-mismatched or artifact-only workflow run is valid evidence.

## Evidence and Recovery

The active cursor records commands, counts, package hashes, Blender version,
review findings and checkpoint head. If a fix changes the head, rerun affected
local checks and all required remote checks. A later release-planning gate may
persist post-merge run IDs without changing this exact qualification head.

## Stop Boundary

Stop after Final Qualification is ordinarily merged and its exact feature head
is proven an ancestor of `origin/main`. Reader API stable promotion, version
change, CHANGELOG release entry, tag and Release remain unstarted.
