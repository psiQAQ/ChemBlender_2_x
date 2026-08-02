# ChemBlender 2.4.0 Release Planning

## Decision

Prepare `2.4.0-rc.1` before Stable `2.4.0`. This planning gate changes no
runtime, manifest version, CHANGELOG release entry, workflow, tag or Release.

## Frozen Product Scope

Frozen scope: `MOL2, PDB, PQR, Cube`; Reader API: `1.0-rc1`; source: PR #19.

The release contains only the capabilities already qualified and merged by
PR #19:

- deterministic MOL2 export and Project Browser preview/confirmation;
- deterministic PDB export and Project Browser preview/confirmation;
- deterministic PQR export and Project Browser preview/confirmation;
- deterministic multi-dataset Cube export and Project Browser
  preview/confirmation;
- focused Final Qualification fixes and evidence.

No new format, scientific model, dependency, schema or UI capability belongs
to the release train.

## Frozen Public and Runtime Boundaries

- Reader API `1.0-rc1` remains unchanged.
- Sidecar/project schema `1.0` and canonical document `0.1` remain unchanged.
- Supported release runtime remains Windows x64 with Blender 5.1.2 or newer.
- Existing pinned RDKit and Gemmi wheels remain the dependency inventory.
- `CHANGELOG.md` remains the single Release-body source.

Reader API stable promotion is deferred because no verified adoption evidence
justifies coupling that API transition to the exporter release.

## Final Qualification Remote Evidence

- PR #19: `https://github.com/psiQAQ/ChemBlender_2_x/pull/19`.
- `extension-package` run `30759984026`: `Passed` for exact feature head
  `98b4da6e13e28fa95c7abdc52494dd4aa7e1e86e`.
- `optional-qc-core` run `30759984023`: `Passed` for exact feature head
  `98b4da6e13e28fa95c7abdc52494dd4aa7e1e86e`.
- Ordinary merge `9763d2afbb38a68061161a855ec333ce0e970fe4`:
  `Passed`; exact feature head ancestry: `Passed`.

These post-checkpoint results replace the completed cursor's earlier
pre-remote `Not Run` snapshot. Old or branch-mismatched runs remain invalid.

## Executable Release Stages

1. Create a separate RC preparation branch from live `origin/main`.
2. Change the manifest to `2.4.0-rc.1` and add its dated CHANGELOG entry in
   the same commit.
3. From the clean committed RC tree run full Python tests, compileall,
   generated-document checks, native Blender validate/build, ZIP
   inventory/budget, isolated install and product smoke.
4. With current push/PR authorization, require exact PR-head CI, then stop for
   merge authorization.
5. After an ordinary merge, require both workflows to pass for the exact
   `origin/main` merge SHA.
6. Stop for tag authorization, create the annotated RC tag, then require
   exact-tag CI and installed-runtime evidence.
7. Run `extension-release` with `publish=false`, then stop for separate
   publication authorization.
8. Review RC feedback before a separate Stable `2.4.0` preparation change.

Release order: exact PR-head CI -> ordinary merge -> exact merge-SHA CI -> tag
authorization -> annotated tag -> exact-tag CI and installed-runtime evidence
-> verification-only release run -> publication authorization.

CI success is evidence, not merge or publication authority.

## Failure Policy

Any required test, package, Blender, artifact or exact-head CI failure blocks
its stage. A correction gets the smallest focused regression test and fresh
invalidated evidence. Use ordinary commits and later `git revert`; never use
force-push, rebase or `reset --hard` for recovery.

## Planning Stop Boundary

This gate may integrate planning documents through an ordinary PR. It must not
change the manifest or CHANGELOG, create a tag, publish a Release, or perform
Reader API promotion. The next recommended task is RC preparation; tagging
and publication remain behind explicit tag/Release authorization.
