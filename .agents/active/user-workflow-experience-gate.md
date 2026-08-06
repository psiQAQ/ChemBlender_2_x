# ChemBlender User Workflow Experience Gate

- Goal ID: `CB-USER-WORKFLOW-EXPERIENCE-GATE`
- State: `active`
- Branch: `codex/user-workflow-experience-gate`
- Worktree: `D:\workspace\ChemBlender_2_x\.worktrees\user-workflow-experience-gate`
- Baseline: `60da41fa450a8715fab39c3e368a4a43af01f9d6`
- Design: `docs/superpowers/specs/2026-08-07-chemblender-user-workflow-experience-gate-design.md`
- Plan: `docs/superpowers/plans/2026-08-07-chemblender-user-workflow-experience-gate.md`
- Current task: `Task 7 — Run Blender MCP build/install workflows and fix reproduced defects`
- Completed tasks: `Design, implementation plan, Tasks 1–6`

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
| Task 2 | `1ae8779` | 5 corpus contracts and 135 reader tests Passed; all 16 inputs below 50 MiB |
| Task 3 | `cbee68b` | 7 workflow documents, 16 sample links and 3 repository entrypoints verified |
| Task 4 | `63d9b34` | 18 plugin prompts, 5 outside-plugin prompts and public-UI safety contracts verified |
| Task 5 | `aec862f` | 9-case UX-GATE, review template and pre-tag release blocking policy verified |
| Task 6 | `1d910da` | Public-Operator runner compiled; 15/15 workflow contracts and `git diff --check` Passed |
| Task 7 fixes | `4fbcf0e` | Two locale-independent identifier lookups fixed; 78 adjacent tests and installed-product smoke Passed |

## Blender Runtime Evidence

- `blender-mcp --help`: Passed.
- Live MCP runtime: Blender `5.1.2`, bundled Python `3.13.9`, Windows,
  `C:\Program Files\Blender Foundation\Blender 5.1\blender.exe`, enabled
  `bl_ext.user_default.chemblender`, empty clean background file.
- Dependency inventory: RDKit `2026.3.3` SHA-256 `f8bd59b2...e767c48` and
  Gemmi `0.7.5` SHA-256 `ad1f72ff...fd337d` matched `dependencies.toml`.
- Extension validate/build and ZIP audit: Passed; `chemblender-2.4.0.zip`,
  29,976,638 bytes after fixes, 189 regular files, CRC clean, exact two wheels.
- Installed-product smoke: Passed in Blender 5.1.2 after fixes, including exact
  RDKit/Gemmi imports, two lifecycle cycles, assets, project reopen, native
  molecular/crystal/grid flows, and 10k-SDF performance checks.

## Defect Ledger

1. Chinese Geometry Nodes categories used localized display text as Blender/Python
   registration identifiers. The installed smoke failed its stable inventory check and
   Blender warned about every Chinese identifier. RED:
   `test_geometry_node_menu_ids_do_not_depend_on_ui_language`; fix: pair canonical
   English identifiers with localized labels; GREEN: 44 registration/repository tests
   and the installed smoke.
2. `surface_view.py` looked up the Principled BSDF node by the English display name.
   Chinese Blender returned `None`, crashing signed-surface scene preset creation. RED:
   `test_surface_material_node_lookup_is_locale_independent`; fix: select the stable
   `BSDF_PRINCIPLED` node type in both material paths; GREEN: 47 adjacent tests and the
   complete 253-second installed-product smoke.

## Workflow Runner Corrections

- Initial report: `.agents/cache/user-workflows/run-4fbcf0e-1/report.json`.
- `DATA-CRYSTAL` exposed a runner context omission: selecting a Project Browser row
  does not activate its Structure View. The runner now activates the matching public
  View with Blender selection APIs before the context-sensitive Operator.
- The original `multimodel.pdb` intentionally has different atom identity sets across
  MODEL records, so the parser correctly creates independent Structures. It remains a
  diagnostic example; MODEL playback now uses the 360-byte `model-trajectory.pdb`
  derived from the repository smoke fixture.
- RED/GREEN: two focused contracts failed before the corrections and passed after;
  all 17 user-workflow contracts and runner compilation then passed.
- Corrected rerun `.agents/cache/user-workflows/run-43f64f1-1/report.json` passed
  through `VIEW-CUBE`, then exposed a runner-only export-gate mismatch: Blender Python
  raises `RuntimeError` when the UI Operator rejects an unconfirmed lossy export. The
  runner now audits that expected rejection and retries with explicit confirmation;
  unexpected Operator errors still fail the case. Focused RED/GREEN passed.

## Deferred External Cases

None currently known.

## Stop Boundary

Do not publish or push. Complete all local workflow evidence and merge normally into
local `main` only after final qualification.

## Next Action

Commit the export-gate runner correction, then start a fresh MCP-backed Blender 5.1
runtime and execute every public-Operator runner checkpoint in a new empty run
directory with report inspection.
