# ChemBlender 2.4.0 Release Planning Design

## Goal

Turn the ordinarily merged and qualified 2.4.0 feature set into an executable
release train without changing a version, tagging a commit or publishing a
Release during planning.

## Frozen Scope

- Release only the capabilities already merged through PR #19: deterministic
  MOL2, PDB, PQR and Cube exporters, their Project Browser workflows, and the
  final qualification fixes.
- Preserve Reader API `1.0-rc1`, sidecar schema `1.0`, canonical document
  `0.1`, Windows x64 support and Blender 5.1.2 minimum support.
- Preserve the pinned RDKit and Gemmi dependency inventory. Dependency or
  workflow changes require a confirmed release-blocking defect.
- Do not add a format, model, dependency, migration or UI capability.

## Release Train

Prepare `2.4.0-rc.1` first. Promote to stable `2.4.0` only after the RC has
exact-tag package evidence, installed-runtime evidence and a documented
feedback review. Do not publish stable directly from the planning branch.

The RC preparation branch must update `ChemBlender/blender_manifest.toml` and
the dated `CHANGELOG.md` entry in the same commit. `CHANGELOG.md` remains the
only Release-body source.

## Evidence Chain

1. Persist the already observed final-qualification PR, exact feature-head
   workflow runs and ordinary merge ancestry.
2. Prepare the RC version and changelog on a separate release branch.
3. Re-run full Python tests, compileall, generated-document checks, native
   Blender validate/build, ZIP inventory/budget, isolated install and product
   smoke from the clean committed RC tree.
4. With current external-write authorization, push and open the pull request;
   require exact PR-head CI, then stop for merge authorization.
5. After an ordinary merge, require both workflows to pass for the exact
   `origin/main` merge SHA.
6. Stop for tag authorization, create the annotated RC tag, then require
   exact-tag package CI and installed-runtime evidence.
7. Run `extension-release` with `publish=false`; stop again for independent
   publication authorization before any GitHub Release is created.
8. Review RC feedback and evidence before creating a separate stable-release
   preparation change.

No old run, branch-mismatched run or merely existing artifact can replace
exact commit/tag evidence.

CI success is evidence, not merge or publication authority. A current explicit
authorization may satisfy one named gate, but must not be inferred from an old
instruction or from a green workflow.

## Reader API Decision

Reader API promotion is excluded. The current public Release has no observed
download/adoption evidence sufficient to justify removing `rc1`; release
planning therefore preserves the tested API boundary instead of coupling an
API transition to exporter delivery.

## Failure and Recovery

- Any required test, build, artifact, Blender or exact-head CI failure blocks
  the release stage that produced it.
- Fix the smallest confirmed defect with a regression test and regenerate all
  invalidated evidence.
- Use ordinary commits and `git revert` for later rollback. Do not rebase,
  force-push or use `reset --hard`.
- A cleanup warning is non-blocking only when the owning process exited zero
  and its scientific artifacts were verified first.

## Planning Deliverables

This gate produces one execution plan, one active/completed cursor and
documentation contracts for the frozen scope, evidence chain and stop
boundaries. It may ordinarily integrate those planning artifacts through a
PR, but it does not modify the manifest, CHANGELOG, workflow, tag or Release.

## Stop Boundary

Stop the planning gate after its exact feature head is ordinarily merged and
proven an ancestor of `origin/main`. The next recommended task is 2.4.0 RC
preparation. Tagging and publishing remain separately authorized operations.
