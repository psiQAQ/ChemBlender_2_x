# ChemBlender 2.3.0 Wave 0 Registration/UI Final Product Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the four Registration/UI product gaps before Release Groundwork: one project per `.blend`, real FileHandler drops, explicit import decisions, and format-aware default views.

**Architecture:** A loaded Blender file owns one in-memory `ProjectSession`; Scenes retain only presentation and verified link projections. Quick Import remains the single staging path, Import Preview owns explicit user decisions, and a pure default-view planner selects existing Blender adapters without entering the scientific model.

**Tech Stack:** Python 3.13 standard library, Blender 5.1.2 Python API, existing ChemBlender core/import/session services, `unittest`.

## Global Constraints

- Work only on `feat/2.3.0-wave0-platform-foundation` in its existing linked worktree.
- Blender RNA and datablock changes occur only on the main thread.
- `QCProject` and `.cbq` remain authoritative; Scene state is presentation/link projection only.
- Quick Import, FileHandler and Import Preview use the existing Reader Plugin Registry and Import Pipeline.
- Do not add formats, dependencies, wheels, version changes, tags, releases, PRs or Wave 1–4 work.
- Do not start Release Groundwork.
- Preserve the known 276-character Windows install-path limitation as a known limit.
- Every source responsibility change updates `.agents/reference/code-architecture-guide.md` in the same implementation commit.
- Each behavior change follows RED → minimal GREEN → focused regression → independent review → commit.

---

### Task 1: One project per loaded Blender file

**Files:**
- Modify: `ChemBlender/ui/session.py`
- Modify: `ChemBlender/core/project_service.py`
- Modify: `ChemBlender/ui/properties.py` only if shared-session UI invalidation requires it
- Modify: `tests/test_ui_session_contract.py`
- Modify: `tests/test_project_service.py`
- Modify: `tests/blender_smoke.py`
- Modify: `.agents/reference/code-architecture-guide.md`

**Interfaces:**
- Consumes: `ProjectSession`, `save_project_session()`, `verify_project_session()`, Scene project-link helpers.
- Produces: backward-compatible `get_scene_session(scene)` returning one shared scientific session per loaded `.blend`, plus pure multi-Scene save/verification helpers.

- [x] **Step 1: Write failing ownership tests**

Add tests proving two Scene identities return the same `ProjectSession`, share imported entities and one temporary root, close the session once, and continue to support the existing single-Scene API.

- [x] **Step 2: Write failing multi-Scene persistence tests**

Add pure service tests proving all Scene links are updated to the same project UUID/schema/locator/hash only after every link write succeeds. A later write failure must restore every prior link, leave the session dirty, and report no connected state.

- [x] **Step 3: Verify RED**

Run:

```powershell
& $pythonBin -m unittest tests.test_ui_session_contract tests.test_project_service -v
```

Expected: failures show distinct Scene sessions and non-atomic link projection.

- [x] **Step 4: Implement the minimum shared owner**

Replace per-Scene scientific session ownership with one module-owned session entry for the loaded file. Keep Scene identity only for status/presentation projection and retain `get_scene_session(scene)` as the compatibility entry.

- [x] **Step 5: Implement atomic multi-Scene link projection**

Put snapshot/write/rollback in the pure project-service boundary. Save or adopt one verified project, then project its identical link to all Scenes; any projection failure restores every original link and preserves dirty state.

- [x] **Step 6: Cover load/save handlers**

`load_post` must accept no links, one valid link plus empty Scenes, or identical valid links; conflicting valid links fail closed. `save_pre` must publish at most once regardless of active Scene.

- [x] **Step 7: Focused and Blender verification**

Run the focused tests and extend Blender smoke for two-Scene shared session, save/reopen, link equality and conflicting-link fail-closed behavior.

- [x] **Step 8: Review and commit**

Commit only the changed files with:

```text
fix: share one project session per Blender file
```

**Stop boundary:** Do not change FileHandler behavior in this task.

---

### Task 2: Execute Quick Import directly from FileHandler paths

**Files:**
- Modify: `ChemBlender/ui/quick_import.py`
- Modify: `ChemBlender/ui/file_handlers.py` only if the handler contract requires it
- Modify: `tests/test_quick_import_contract.py`
- Modify: `tests/test_file_handler_contract.py`
- Modify: `tests/blender_smoke.py`
- Modify: `.agents/reference/code-architecture-guide.md`

**Interfaces:**
- Consumes: `_selected_paths()`, existing Quick Import staging, `bl_import_operator`.
- Produces: hidden non-persistent `directory`, `files`, optional `filepath`, and an `invoke()` branch that executes injected paths without opening the File Browser.

- [x] **Step 1: Write failing path-injection tests**

Cover no-path manual invocation, one injected filepath, injected `directory/files`, multiple files, stale property non-reuse, safe path validation and no directory scanning.

- [x] **Step 2: Write failing RNA and Blender invocation tests**

Assert `SKIP_SAVE` and `HIDDEN` on path properties. In Blender invoke `bpy.ops.chemblender.quick_import("INVOKE_DEFAULT", ...)` with one and multiple files and require Import Preview without a File Browser.

- [x] **Step 3: Verify RED**

Run:

```powershell
& $pythonBin -m unittest tests.test_quick_import_contract tests.test_file_handler_contract -v
```

Expected: injected paths still call `fileselect_add()` or RNA options are absent.

- [x] **Step 4: Implement one deterministic invocation branch**

If `_selected_paths()` yields injected paths, call the existing staging path immediately; otherwise call `fileselect_add()`. Normalize/clear transient inputs so a later invocation cannot reuse previous paths.

- [x] **Step 5: Focused and Blender verification**

Run focused tests and Blender smoke for manual selection, single-file drop, multi-file drop, both FileHandlers and clean register/unregister.

- [x] **Step 6: Review and commit**

Commit only the changed files with:

```text
fix: execute Quick Import from file drops
```

**Stop boundary:** Do not alter conflict/grouping decisions in this task.

---

### Task 3: Require explicit conflict targets and grouping decisions

**Files:**
- Modify: `ChemBlender/ui/import_preview.py`
- Modify: `ChemBlender/ui/properties.py`
- Modify: `ChemBlender/core/import_pipeline/grouping.py` only if the existing decision contract cannot represent the approved choice
- Modify: `ChemBlender/core/import_pipeline/transaction.py` only if needed to pass existing decision objects
- Modify: `tests/test_import_preview_ui_contract.py`
- Modify: `tests/blender_smoke.py`
- Modify: `.agents/reference/code-architecture-guide.md`

**Interfaces:**
- Consumes: live `ImportConflict` candidates, `suggest_source_groups()`, `GroupingDecision`, `ImportCommitDecisions`, existing live revalidation.
- Produces: RNA-safe conflict candidate and grouping suggestion projections, explicit selected target IDs, and `Keep Independent`/`Accept Group` decisions.

- [x] **Step 1: Write failing conflict-target tests**

Construct one staged source with two candidate revisions. Confirm must fail with no target, bind exactly the selected candidate A or B, and reject UUIDs absent from the live candidate set.

- [x] **Step 2: Write failing grouping tests**

Project suggestion count, confidence, review flag and evidence summaries. Default `Keep Independent` creates no group; `Accept Group` with evidence connecting all sources creates one `.cbq`-round-trippable `CalculationGroup`; stale suggestions fail closed.

- [x] **Step 3: Verify RED**

Run:

```powershell
& $pythonBin -m unittest tests.test_import_preview_ui_contract -v
```

Expected: target actions silently choose the first candidate and grouping suggestions cannot be confirmed.

- [x] **Step 4: Implement RNA-safe projections**

Store only UUID strings, labels, counts, enum strings and booleans. Preselect the sole candidate only; leave multiple candidates unselected. Project grouping suggestions and expose only `Keep Independent` and `Accept Group`; mark Split/Edit unavailable in alpha.1 where documented.

- [x] **Step 5: Build existing decision objects**

Create `ConflictDecision` and `GroupingDecision` only from currently staged live snapshots, combine them in one `ImportCommitDecisions`, and preserve existing commit-time live revalidation.

- [x] **Step 6: Focused and Blender verification**

Run focused tests and Blender smoke for two-candidate selection, invalid target rejection, Keep Independent and Accept Group.

- [x] **Step 7: Review and commit**

Commit only the changed files with:

```text
feat: confirm import conflicts and source groups explicitly
```

**Stop boundary:** Do not create or apply format-aware views in this task.

---

### Task 4: Plan format-aware default views

**Files:**
- Create: `ChemBlender/ui/default_views.py`
- Modify: `ChemBlender/ui/import_preview.py`
- Modify: `ChemBlender/core/scene_preset.py`
- Modify: `ChemBlender/scene_preset_view.py`
- Modify: `ChemBlender/grid_volume.py` only if its existing adapter lacks required metadata/cache inputs
- Modify: `ChemBlender/ui/project_browser/model.py` only if Grid3D view counting lacks an existing path
- Modify: `ChemBlender/ui/project_browser/panel.py` only if Grid3D view projection lacks an existing path
- Modify: `tests/test_import_preview_ui_contract.py`
- Modify: `tests/test_scene_preset.py`
- Modify: `tests/test_project_browser_model.py`
- Modify: `tests/blender_smoke.py`
- Modify: `.agents/reference/code-architecture-guide.md`
- Modify: `tests/test_quantum_visualization_docs.py` only if its expected inventory is explicit

**Interfaces:**
- Consumes: committed SourceRevision entity IDs, `Grid3D.status`, `semantic_role`, existing `structure_publication`, `signed_isosurface`, `create_grid_volume()`, session temporary root.
- Produces: pure frozen `DefaultViewPlan` and `grid_volume` scene preset/adapter dispatch.

- [x] **Step 1: Write failing pure planning tests**

Require Complete Grid3D to outrank Structure; signed/MO roles select `signed_isosurface`; other Grid3D selects `grid_volume`; Structure-only selects `structure_publication`; no supported entity returns no plan.

- [x] **Step 2: Write failing application tests**

Require disabled default view to create nothing, cache paths under the session root, dataset UUID/revision/render identity metadata, one browser revision increment, and attempt-local view rollback while preserving committed scientific data.

- [x] **Step 3: Verify RED**

Run:

```powershell
& $pythonBin -m unittest tests.test_import_preview_ui_contract tests.test_scene_preset tests.test_project_browser_model -v
```

Expected: Cube selects only `structure_publication` and no `grid_volume` preset exists.

- [x] **Step 4: Implement the pure planner**

Add a frozen UI-only plan carrying source revision, preset, bindings, settings and label. It must not import `bpy`, enter `QCProject`, the model registry or sidecar entities.

- [x] **Step 5: Reuse existing view adapters**

Add the smallest `grid_volume` preset/dispatch that calls `create_grid_volume()` with the session-controlled cache root and chosen dataset index. Keep all Blender datablock writes on the main thread.

- [x] **Step 6: Integrate Import Preview and browser projection**

Display the selected label, apply plans only after commit, roll back all attempt-created views on adapter failure, preserve committed data, report `data committed; view failed`, and increment browser revision once.

- [x] **Step 7: Focused and Blender verification**

Run focused tests and Blender smoke: `water.xyz` creates a Structure Mesh bound to its UUID/revision; `sheared.cube` creates a Grid3D Volume or signed isosurface bound to Grid3D UUID/revision with cache under the session root.

- [x] **Step 8: Review and commit**

Commit only the changed files with:

```text
feat: create format-aware default import views
```

**Stop boundary:** Do not add a reader, scientific entity or release change.

---

### Task 5: Native Blender product gate

**Files:**
- Modify: `tests/blender_smoke.py` only for missing end-to-end assertions
- Modify: files from Tasks 1–4 only when a gate reveals a confirmed defect

**Interfaces:**
- Consumes: completed Tasks 1–4 and existing build/install scripts.
- Produces: fresh local product-gate evidence.

- [x] **Step 1: Run focused regression**

```powershell
& $pythonBin -m unittest tests.test_ui_session_contract tests.test_project_service tests.test_quick_import_contract tests.test_file_handler_contract tests.test_import_preview_ui_contract tests.test_project_browser_model tests.test_scene_preset tests.test_quantum_visualization_docs -v
```

- [x] **Step 2: Run full pure-Python regression**

```powershell
& $pythonBin -m unittest discover -s tests -p "test_*.py" -v
& $pythonBin -m compileall -q ChemBlender worker tests
git diff --check
```

- [x] **Step 3: Run native package gates**

Run package preflight, Blender 5.1.2 native validate, extension build and ZIP inventory audit.

- [x] **Step 4: Run real installs and lifecycle**

Run default-user-repository install and short-path isolated install, then register/unregister/reload twice. Record the artificial 276-character path as the unchanged known limit.

- [x] **Step 5: Run product flows**

Verify two-Scene ownership/save/reopen/conflict, manual and dropped Quick Import, explicit conflict/grouping decisions, XYZ/Cube default views, Project Browser modes, workspace behavior, Reader API handle lifecycle and optional-stack non-import.

- [x] **Step 6: Record CI truth**

Record `Remote CI: Not Run`; local commands are not remote CI.

**Commit boundary:** No commit unless verification requires a reviewed fix.

**Stop boundary:** Do not start Release Groundwork.

---

### Task 6: Independent reviews and final checkpoint

**Files:**
- Modify: `.agents/active/2.3.0-wave-0-platform-foundation.md`
- Modify: this plan only to check completed boxes or record exact verified outcomes

**Interfaces:**
- Consumes: all Task commits and fresh verification evidence.
- Produces: completed Execution Cursor pointing to Release Groundwork Task 1 without starting it.

- [x] **Step 1: Run independent specification review**

Review the complete gate diff against this plan and the approved review prompt. Fix every Critical, Important and in-scope Minor finding, then rerun covering tests.

- [x] **Step 2: Run independent code-quality review**

Review correctness, ownership, failure rollback, threading, Blender lifecycle, API compatibility and unnecessary complexity. Fix every finding and rerun covering tests.

- [x] **Step 3: Rerun final verification**

Rerun the focused suite, full suite, compileall, diff check, native validate/build/ZIP/install/lifecycle and the four end-to-end product subgoals.

- [x] **Step 4: Complete the cursor**

Record every commit SHA, RED and GREEN command/result, local test count, Blender gate status, `Remote CI: Not Run`, the unchanged long-path limitation, and next task `Release Groundwork Task 1 — Centralize manifest metadata and artifact naming`.

- [x] **Step 5: Commit checkpoint**

```text
chore: checkpoint registration UI final product gate
```

**Stop boundary:** Release Groundwork Task 1 remains unstarted; do not push.

## Verified outcomes

- Planning commit:
  `202950158d758e458345b21a8de7f9a06a6dd9a5`.
- Implementation commits:
  `c83a851b0fc9cf1589c41f607a3a62241dc6f613`,
  `6bd458b2e22c869db1658a8708ec9ed61875e08f`,
  `5b16686bdac45a467cbf71e7694173f65854983a`,
  `50704754bffda09464697675a60dc32aa831dec6`,
  `ea8158f4f90bc5298c7707094ce7a1ff1a1c6673` and
  `e4aa6d3efe18a23d280b7e6a980841d541ad9797`.
- Final pure-Python verification: 890 Passed, 27 skipped, 0 failed.
- Blender 5.1.2 local preflight, native validate, build, ZIP audit,
  `user_default` install and fresh short-path isolated lifecycle smoke:
  Passed.
- End-to-end product flows: Passed for the four target subgoals.
- Independent specification and code-quality review: Passed after all
  findings were fixed and scoped re-reviewed.
- Remote CI: Not Run.
- Known limit: the unchanged Windows long temporary sidecar-array path still
  fails; the current package passes with short isolated runtime roots.
- Release Groundwork Task 1 and Wave 1–4 remain unstarted.
