# ChemBlender User Workflow Experience Gate

- Goal ID: `CB-USER-WORKFLOW-EXPERIENCE-GATE`
- State: `active`
- Branch: `codex/user-workflow-experience-gate`
- Worktree: `D:\workspace\ChemBlender_2_x\.worktrees\user-workflow-experience-gate`
- Baseline: `60da41fa450a8715fab39c3e368a4a43af01f9d6`
- Design: `docs/superpowers/specs/2026-08-07-chemblender-user-workflow-experience-gate-design.md`
- Plan: `docs/superpowers/plans/2026-08-07-chemblender-user-workflow-experience-gate.md`
- Current task: `Task 2 — Create the immutable full-format example corpus`
- Completed tasks: `Design, implementation plan, Task 1`

## Goal

Build the user-facing workflow center, full base-format example corpus,
UI-equivalent Blender MCP runner and tracked manual prerelease experience gate.
Exercise every feasible documented workflow in Blender 5.1, fix reproduced
in-scope plugin defects, verify selected reopenable outputs, and merge the
locally committed result into local `main`.

## Constraints

- Local commits only; do not push, create a PR, tag, publish, release or alter remotes.
- ChemBlender automation uses public `bpy.ops.chemblender.*` Operators and public RNA.
- Do not bypass previews/confirmation or directly mutate `.cbq`, caches or private state.
- Examples target less than 50 MB per file and may never exceed 100 MB.
- Restart the exact Blender 5.1 executable and re-query MCP after a crash/disconnect.
- Defer unavailable repositories, external dependencies or unsafe network examples and
  request approval once at the end if the required deferred list is non-empty.

## Checkpoints

| Phase | Commit | Verification |
| --- | --- | --- |
| Design | `9d28023` | 69/69 docs/repository baseline; `git diff --check` Passed |
| Plan | `86d63fc` | 8-task coverage and placeholder scan; 69/69 baseline Passed |

## Blender Runtime Evidence

Not Run. Task 7 begins with `blender-mcp --help` and one live runtime query.

## Defect Ledger

None observed. Add only reproduced product defects with RED/GREEN and runtime evidence.

## Deferred External Cases

None currently known.

## Stop Boundary

Do not publish or push. Complete all local workflow evidence and merge normally into
local `main` only after final qualification.

## Next Action

Write the RED example-manifest contract, copy verified fixture snapshots, generate the
minimal SMILES example, then record measured hashes/sizes and run public reader checks.
