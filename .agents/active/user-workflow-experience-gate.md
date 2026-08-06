# ChemBlender User Workflow Experience Gate

- Goal ID: `CB-USER-WORKFLOW-EXPERIENCE-GATE`
- State: `active`
- Branch: `codex/user-workflow-experience-gate`
- Worktree: `D:\workspace\ChemBlender_2_x\.worktrees\user-workflow-experience-gate`
- Baseline: `60da41fa450a8715fab39c3e368a4a43af01f9d6`
- Design: `docs/superpowers/specs/2026-08-07-chemblender-user-workflow-experience-gate-design.md`
- Plan: `docs/superpowers/plans/2026-08-07-chemblender-user-workflow-experience-gate.md`
- Current task: `Task 8 — Final qualification, archive and local main merge`
- Completed tasks: `Design, implementation plan, Tasks 1–7`

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
| Task 7 runner | `43f64f1`, `a161f8f`, `69e93c0`, `588beef` | UI context, export confirmation, first-save and resume evidence contracts Passed |
| Task 7 publication | `4e46d63` | Windows sidecar publication path bounded; 94 adjacent tests and packaged migration Passed |
| Task 7 prompts | `3218cfd` | Renderability, material fallback and rendered-image inspection added after live MCP diagnosis |

## Blender Runtime Evidence

- `blender-mcp --help`: Passed.
- Live MCP runtime: Blender `5.1.2`, bundled Python `3.13.9`, Windows,
  `C:\Program Files\Blender Foundation\Blender 5.1\blender.exe`, enabled
  `bl_ext.user_default.chemblender`, empty clean background file.
- Dependency inventory: RDKit `2026.03.3` SHA-256 `f8bd59b2...e767c48` and
  Gemmi `0.7.5` SHA-256 `ad1f72ff...fd337d` matched `dependencies.toml`.
- Extension validate/build and ZIP audit: Passed; current
  `chemblender-2.4.0.zip` is 29,976,721 bytes, 189 regular files, CRC clean,
  exact two wheels, 32,064,525 unpacked bytes, and exact zero-growth budgets.
  SHA-256: `079b00b8a47dba56298eb9635b5a5dff76bcb1c4983aeefe5dfe360cc149c79d`.
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
3. Legacy migration nested an atomic sidecar publication below a long working path.
   Publication stage/backup names repeated the destination name, making the final NPY
   replace path 283 characters and failing with Windows `WinError 3`. RED:
   `test_sidecar_publication_orphan_names_stay_bounded_and_discoverable` observed a
   126-character stage name. Fix: destination names longer than 15 characters use a
   stable 12-hex association prefix while UUID recovery semantics stay unchanged.
   GREEN: 66 atomic-path/publication/migration tests; isolated packaged Blender 5.1.2
   public preview/migrate/save Operators all returned `FINISHED`, producing a verified
   `.blend`/`.cbq` pair and `ChemBlender Legacy Backup` collection.
   Final adjacent verification: 94/94 publication, migration, artifact-budget and
   user-workflow contracts Passed; modified Python and runner compilation Passed.

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
- Fresh run `.agents/cache/user-workflows/run-a161f8f-1/report.json` passed all
  imports, scientific operations, Views and 11 exports. Its lifecycle check exposed
  the established first-save contract: `Save As` determines the new `.blend` path,
  then a second `Save Project` publishes the `.cbq` via `save_pre`. The repository
  smoke confirms this behavior. The runner and lifecycle guide now perform and explain
  both UI steps; focused RED/GREEN passed.
- Run `.agents/cache/user-workflows/run-69e93c0-1/report.json` passed main and LIFE
  cold reopen, then preserved the `WinError 3` migration failure that led to defect 3.
- The final resume checkpoints replaced each LIFE/MIG record and discarded the earlier
  save/migration Operator list and elapsed time. The runner now carries prior Operator
  evidence forward and accumulates elapsed time; a focused contract prevents regression.

## Final Public-Operator Run

- Fresh isolated profile: `.agents/cache/user-workflows/profile-4e46d63-final`.
  Exact package SHA-256: `079b00b8a47dba56298eb9635b5a5dff76bcb1c4983aeefe5dfe360cc149c79d`.
- Final run: `.agents/cache/user-workflows/run-588beef-1/report.json`. Four fresh
  Blender 5.1.2 processes exercised the main flow, project cold reopen, legacy
  migration and migrated-project cold reopen. All 11 cases are `passed`; `deferred=[]`.
- LIFE evidence retains both `bpy.ops.wm.save_as_mainfile` and
  `bpy.ops.wm.save_mainfile`: 88 Project Browser rows, 16 objects and clean state.
  MIG evidence retains preview, confirmed migration and both Save As calls: 7 rows,
  2 objects and the `legacy_formaldehyde` backup.
- The portable tracked result is
  `examples/user-workflows/results/local-2.4.0.json`; its focused contract and all
  22 user-workflow contracts Passed.
- `examples/user-workflows/outputs/` contains 52 files totaling 479,453 bytes. The
  largest file is 200,053 bytes. Both `.blend`/`.cbq` pairs cold reopened from their
  tracked paths; workflow Volume paths stay inside the paired sidecar and no external
  files are missing.

## Outside-Plugin Prompt Correction

- The explicitly selected Biological View had two points and zero evaluated polygons;
  the render Operator returned `FINISHED` and wrote a PNG, but visual inspection found
  an almost black image. The guide now requires live evaluated-geometry checks, a
  no-material fallback, and image inspection instead of accepting status/file existence.
- A second MCP run selected the only visible Structure View with an enabled Geometry
  Nodes modifier and nonzero evaluated polygons, then exercised material, world, Area
  light, camera, Collection and Eevee settings. The visually inspected 320x240 PNG was
  84,047 bytes; mesh coordinates, Object transform and custom-property keys stayed
  unchanged. Ordinary Save As was correctly not called because the `.cbq` pair exists.

## Deferred External Cases

None currently known.

## Stop Boundary

Do not publish or push. Complete all local workflow evidence and merge normally into
local `main` only after final qualification.

## Next Action

Commit the tracked runtime evidence, run final repository/package/runtime qualification,
archive this cursor, then normally merge the clean feature branch into local `main`.
