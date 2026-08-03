# ChemBlender 2.4.0 Post-release Cleanup Design

**Goal:** Reduce post-release documentation and Git navigation noise while
preserving every authoritative release, architecture and review record, then
provide a repeatable human UX review entrypoint for the published 2.4.0
Extension.

**Approved approach:** Keep historical plans and specifications in place,
remove only Git objects whose content is recoverable from maintained history,
and add a focused 2.4.0 human-review checklist. Product behavior is out of
scope.

## Live baseline

The approved design was based on `main` and `origin/main` at
`174e6c3691790362c500742f76aae76fb80d55aa`, with a clean root worktree, no
open pull request and no tracked active or queued task.

The live inventory contained:

- 100 implementation plans, 41 design specifications and 58 completed task
  records;
- 31 local branches, 25 remote branches and 29 registered worktrees;
- 27 local branches already retained by `origin/main`;
- three prepared local branches and one immutable archive branch that were not
  ancestors of `origin/main`;
- two clean detached verification worktrees.

These counts are audit inputs, not permanent repository facts. Every cleanup
decision must be recalculated immediately before deletion.

## Documentation organization

Historical `docs/superpowers/plans/` and `docs/superpowers/specs/` files remain
at their existing paths. Their unchecked task boxes are historical execution
notation and must not be mass-edited, moved or interpreted as current work.

Create `docs/superpowers/README.md` as the single navigation boundary for this
material. It must explain:

- current task authority comes from `.agents/active/` and `.agents/queued/`;
- completed evidence comes from `.agents/completed/`;
- plans and specs retain approved design and implementation provenance;
- the current released baseline is ChemBlender 2.4.0;
- a new product change requires a new goal rather than reopening old checkbox
  lists.

Update only the existing entrypoints needed to expose that boundary:

- root `README.md`;
- `docs/README.md`;
- `.agents/README.md`;
- `.agents/reference/branch-architecture.md`.

User-facing format text must describe the published 2.4.0 capability surface.
Correct stale version labels and Cube/PQR export statements by changing their
authoritative source and regenerating generated sections; never hand-edit a
generated block.

## Human UX review handoff

Create `docs/user/2.4.0-experience-review.md`. It is a human observation guide,
not another automated qualification report. It covers this ordered workflow:

1. download and install the public 2.4.0 ZIP in Blender 5.1 or newer;
2. locate ChemBlender and understand the first visible action;
3. import a basic molecular file and a Grid3D/Cube source;
4. resolve Import Preview decisions and diagnostics;
5. find, filter and select data in Project Browser;
6. inspect the default Structure, Volume or Surface view;
7. export a supported format and understand any loss preview;
8. save, close and reopen the `.blend` plus `.cbq` project pair;
9. exercise cancellation and one recoverable error path.

Each observation records environment, workflow step, severity, reproducibility,
expected result, actual result and minimal evidence. The guide may link existing
user documentation and public sample formats, but must not embed screenshots,
invent findings or prescribe implementation fixes.

Human findings become a separate approved goal after review. This cleanup must
not change runtime code in response to issues noticed while writing the guide.

## Git retention policy

The final baseline keeps:

- local and remote `main`;
- immutable `archive/*` history;
- remote `snapshot/*` evidence;
- all annotated release tags and GitHub Releases;
- any branch that fails a retention or equivalence check.

A merged development or release branch is removable only when all conditions
hold:

1. its live SHA is known;
2. it is an ancestor of `origin/main`;
3. its pull request or release evidence is recoverable;
4. its mapped worktree is clean;
5. ignored files contain no unique evidence;
6. its path resolves inside the repository `.worktrees/` directory.

Before deleting a remote branch, its live remote SHA must equal the audited PR
head and be retained by `origin/main`. After deletion, fetch with prune and
verify both the live ref and local tracking ref are absent.

Detached worktrees are removable only when their HEAD is retained by
`origin/main`, they are clean and ignored files are disposable generated data.

## Prepared non-ancestor branches

The prepared branches are not deleted merely because their work is believed to
have shipped. For each branch:

- list its commits after the merge base;
- compare changed paths and patch IDs with maintained history;
- compare the final relevant files or fixture hashes with `origin/main`;
- locate the completed cursor, PR or release evidence that records integration;
- run the narrow contract test when file equivalence alone is insufficient.

Delete the branch and worktree only if every unique change is represented in
maintained history. Otherwise retain it and record the exact unmatched content.

## Execution sequence

Work occurs on `codex/2.4.0-post-release-cleanup` in an isolated worktree.

1. Commit this approved design and the implementation plan.
2. Add documentation navigation, current capability corrections and the human
   UX review guide with focused documentation tests.
3. Audit ignored content and non-ancestor prepared branches.
4. Remove verified redundant worktrees and local branches.
5. Remove verified redundant remote branches.
6. Record the final inventory in a completed cursor.
7. Push the cleanup branch, obtain exact-head CI and merge it with a normal
   merge commit.
8. Verify merge-head CI, then remove the merged cleanup branch and worktree.

Git history must not be rebased, force-pushed or reset. A failed destructive
step stops cleanup for that target; it does not widen deletion scope.

## Verification

Documentation verification includes:

- local Markdown link resolution;
- generated capability documents matching their source;
- single-active-task and documentation-routing contracts;
- UTF-8 without BOM and preserved line endings;
- `git diff --check`.

Git verification includes:

- final local and remote ref inventory;
- `git worktree list --porcelain`;
- `git worktree prune --dry-run --verbose` returning no stale metadata;
- retained branches resolving to their audited SHAs;
- `main` and `origin/main` matching after integration;
- annotated tags and public 2.4.0 Release remaining unchanged.

The cleanup pull request requires exact-head repository CI. The final result is
ready for human UX review only when the root `main` worktree is clean and the
review guide is reachable from the normal documentation entrypoints.

## Stop boundary

Stop after repository cleanup, exact CI integration and the human UX review
handoff. Do not implement UX findings, change the 2.4.0 tag or Release, publish
a new package, add dependencies or activate a new product roadmap.
