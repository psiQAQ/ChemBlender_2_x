# ChemBlender 2.3.0 Wave 0 Pre-Release Persistence and Windows Path Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make derived Grid3D/Surface VDB views durable across save/close/reopen, synchronize shared project links without republishing clean scientific data, and pass the full product smoke under default Windows paths.

**Architecture:** Keep `QCProject` and the verified `.cbq` manifest authoritative. Reuse one pure short sibling-path helper for content-addressed writers, one project-service link transaction for every Scene, and one Blender UI cache coordinator that promotes or reconstructs derived VDB files only from verified project/view metadata.

**Tech Stack:** Python 3.13 standard library, Blender 5.1.2 Python API, NumPy/OpenVDB already supplied by Blender/extension, `unittest`.

## Global Constraints

- Work only on `feat/2.3.0-wave0-platform-foundation` in its existing linked worktree.
- Reviewed baseline is `81994205e322ecb2052ce27d506e08b97a5f1108`.
- `QCProject` and `.cbq` authoritative arrays remain unchanged; VDB files under `cache/render/` are derived data.
- Do not add file formats, dependencies, wheels, Wave 1–4 work, manifest version changes, GitHub Actions changes, PRs, tags or releases.
- Do not start Release Groundwork Task 1.
- Do not push without a new explicit user authorization.
- Preserve UTF-8/BOM/line endings and update the architecture guide in the same commit as source responsibility changes.
- Every behavior change follows RED → minimal GREEN → focused regression → independent review.
- Default Windows `TEMP`/`TMP` product smoke is required; short-path smoke is additional evidence only.
- Remote CI remains `Not Run` unless an actual workflow run is later authorized and observed.

---

### Task 1: Short atomic temporary-path contract

**Files:**
- Create: `ChemBlender/core/storage/atomic_paths.py`
- Create: `tests/test_atomic_path_budget.py`
- Modify: `ChemBlender/core/sidecar.py`
- Modify: `ChemBlender/reader_api/canonical_document.py`
- Modify: `ChemBlender/grid_volume.py`
- Modify: `ChemBlender/surface_view.py`
- Modify only when required by RED evidence: `tests/test_sidecar_storage.py`, `tests/test_reader_canonical_document.py`, `tests/test_scene_preset.py`
- Modify: `.agents/reference/code-architecture-guide.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Produces: `short_sibling_temporary_path(destination, *, suffix=".tmp") -> Path`.
- Consumes: a validated destination; returns a unique same-directory sibling with a complete UUID and a basename no longer than 48 characters.
- Preserves: final content-addressed filename, manifest paths, canonical bytes, hashes, `flush`/`fsync`/`os.replace` and cleanup behavior.

**RED test:**
- Assert `.npy`, JSON and `.vdb` destinations containing 64-character hashes get unique same-directory temporary paths whose basenames do not repeat the hash and are at most 48 characters.
- Exercise sidecar, canonical document and VDB writers with a long destination parent.
- Patch `os.replace` to fail and assert the temporary file is removed without masking the primary error.
- Record current fixture/canonical bytes and SHA values before implementation.

**Expected RED:**
- New helper import fails.
- Existing writers expose basenames containing the 64-character destination hash plus a UUID.
- The reproduced default Windows path reaches the historical path-length failure.

**Minimal implementation:**
- Use `uuid4().hex` and a fixed short prefix/suffix in a pure `bpy`-free helper.
- Replace only the four duplicated content-addressed temporary-name constructions.
- Preserve each writer's existing exception translation and cleanup policy; cleanup failures must not replace an already-active primary error.

**Focused verification:**
- Run `tests.test_atomic_path_budget`, sidecar storage, canonical document, scene preset and documentation contracts.
- Compare production fixture/canonical bytes and hashes before/after.

**Blender verification:**
- Write Grid Volume and Surface VDB files under a default-length Windows parent.
- Re-run the previously failing default `TEMP` path case.

**Commit boundary:**
- Commit source, tests and architecture inventory as `fix: shorten atomic temporary paths`.

**Stop boundary:**
- Do not change session save/relink or cache placement in this task.

---

### Task 2: Link-only Scene synchronization and multi-Scene relink

**Files:**
- Modify: `ChemBlender/core/project_service.py`
- Modify: `ChemBlender/core/__init__.py`
- Modify: `ChemBlender/ui/session.py`
- Modify: `tests/test_project_service.py`
- Modify: `tests/test_core_public_api.py` only if new public service exports require it
- Modify: `tests/test_ui_session_contract.py`
- Modify: `tests/blender_smoke.py`
- Modify: `.agents/reference/code-architecture-guide.md`

**Interfaces:**
- Produces: `sync_project_session_links_for_scenes(*, session, scenes, blend_path) -> ProjectServiceResult`.
- Produces: `relink_project_session_for_scenes(*, session, scenes, sidecar_path, blend_path=None) -> ProjectServiceResult`.
- Preserves: `save_project_session()`, `relink_project_session()` and `verify_project_session()` as one-Scene compatibility wrappers.

**RED test:**
- Prove clean connected all-correct Scenes are a no-op.
- Prove a new empty Scene receives the existing verified link without `solidify_session()`, generation/hash/manifest bytes or array mtimes changing.
- Prove two-Scene relink opens/verifies once, writes identical relative locators, adopts only after all writes, closes the old project once, and closes a rejected candidate.
- Make the second Scene write fail; assert every Scene is restored and structured rollback notes/residual keys survive incomplete rollback.

**Expected RED:**
- Clean new-Scene save calls `solidify_session()`.
- Existing relink has no multi-Scene API and leaves sibling Scenes untouched.

**Minimal implementation:**
- Factor verified-link calculation plus `_write_scene_links()` into link-only synchronization.
- Validate the existing `session.sidecar_path` against project UUID, schema, manifest hash and arrays before projecting it.
- Reuse one candidate link snapshot and the existing atomic multi-Scene write/rollback helper.
- Adopt the candidate only after all Scene writes succeed; close candidate ownership on every earlier exit.
- In `_save_pre_handler()`, full-publish only for missing sidecar or scientific/unknown dirty reasons; route clean connected/new Scene and `project_link` retry to link-only synchronization. Reserve `view_cache` for Task 4 retry routing.

**Focused verification:**
- Run project service, core public API and UI session suites.
- Compare manifest bytes/hash, generation ID and array mtimes around clean synchronization.

**Blender verification:**
- Exercise clean no-op save, new Scene link-only save, two-Scene relink, conflicting old links and second-Scene rollback.

**Commit boundary:**
- Commit source, tests and architecture updates as `fix: synchronize shared project links without republishing`.

**Stop boundary:**
- Do not promote or reconstruct VDB cache in this task.

---

### Task 3: Durable derived View cache promotion

**Files:**
- Create: `ChemBlender/ui/view_cache.py`
- Create: `tests/test_view_cache_persistence.py`
- Modify: `ChemBlender/ui/session.py`
- Modify: `ChemBlender/ui/import_preview.py`
- Modify only when needed to reuse writer/metadata boundaries: `ChemBlender/grid_volume.py`, `ChemBlender/surface_view.py`, `ChemBlender/scene_preset_view.py`
- Modify: `tests/test_import_preview_ui_contract.py`
- Modify: `tests/test_ui_session_contract.py`
- Modify: `tests/blender_smoke.py`
- Modify: `.agents/reference/code-architecture-guide.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:**
- Produces a Blender-only cache coordinator; it does not define a second project, manifest or scientific provenance model.
- Consumes verified `ProjectSession.sidecar_path`, current project entities and Scene preset metadata already stored on owned objects.
- Writes only beneath `<sidecar>.cbq/cache/render/volume/` or `<sidecar>.cbq/cache/render/surface/`.

**RED test:**
- Import Cube before first save and confirm its temporary VDB resides under the session root with complete reconstruction identity.
- After publication, require owned Grid Volume and Surface files to move/copy atomically into verified sidecar render namespaces, update `Volume.filepath` and `cb_cache_path`, and preserve scientific revisions.
- Reject symlink/junction/traversal destinations and malicious/foreign `cb_cache_path`.
- Simulate promotion failure; require `view_cache` dirty state, prior verified path retention and a later save retry.
- Exercise Save As so cache paths follow the newly verified sidecar.

**Expected RED:**
- Saved owned objects still point into `ProjectSession.temporary_root/view-cache`.
- No `view_cache` module or retry dirty reason exists.

**Minimal implementation:**
- Derive destination paths from verified sidecar plus validated object binding/render identity, never from an arbitrary object path.
- Reuse short atomic sibling paths for promotion and existing VDB writer functions for cache generation.
- Prefer Blender-relative `//<sidecar>.cbq/cache/render/...` `Volume.filepath`; keep `cb_cache_path` as a validated cache projection, not provenance.
- Mark `view_cache` dirty on failure and do not report the save fully successful until cache repair succeeds.

**Focused verification:**
- Run view cache, import preview, UI session, scene preset and documentation suites.

**Blender verification:**
- Save Grid Volume, signed isosurface and property surface; assert paths and VDB grids inside the current sidecar.
- Exercise promotion failure and retry plus Save As.

**Commit boundary:**
- This task and Task 4 share the final `fix: persist derived Blender view caches` commit so promotion and reopen reconstruction never land separately.

**Stop boundary:**
- Do not checkpoint until missing-cache reconstruction passes.

---

### Task 4: Missing-cache reconstruction on reopen

**Files:**
- Modify: `ChemBlender/ui/view_cache.py`
- Modify: `ChemBlender/ui/session.py`
- Modify only for reusable cache-only writer entrypoints: `ChemBlender/grid_volume.py`, `ChemBlender/surface_view.py`, `ChemBlender/scene_preset_view.py`
- Modify: `tests/test_view_cache_persistence.py`
- Modify: `tests/blender_smoke.py`
- Modify: `.agents/reference/code-architecture-guide.md`

**Interfaces:**
- Produces: idempotent adoption-time scan/repair of ChemBlender-owned Volume/Surface objects.
- Consumes: preset ID/version, render identity, binding UUID/revision, dataset index and cache format version from object metadata plus the adopted `QCProject`.

**RED test:**
- Delete `cache/render`, reopen/adopt and require the same owned objects to reload reconstructed VDB files without duplicate objects/materials/node groups.
- Cover signed isosurfaces, property surface, corrupt VDB, moved `.blend` + `.cbq`, foreign Volume and malicious cache property.
- Require stale UUID/revision/preset/settings metadata to fail closed.

**Expected RED:**
- `load_post` adopts the project but never scans or repairs missing VDB cache.
- Reopened Volume paths continue pointing to deleted session temporary files.

**Minimal implementation:**
- Validate ownership and plan metadata against the adopted project.
- Rebuild only the missing/corrupt verified cache file with existing OpenVDB writer helpers, then reload the existing Volume datablock.
- Do not create new Blender objects, materials or node groups during repair.
- Clear `view_cache` dirty only after every owned cache validates.

**Focused verification:**
- Run `tests.test_view_cache_persistence` and all UI/session/preset regressions.

**Blender verification:**
- Process A: import, create views, save `.blend` + `.cbq`, record temp root, exit cleanly.
- Process B: assert the old temp root is gone, open the `.blend`, validate cache location/existence/grids/UUID/revision.
- Repeat after `clear_derived_cache()` and after moving `.blend` + `.cbq`.

**Commit boundary:**
- Commit Tasks 3–4 source, tests and architecture updates as `fix: persist derived Blender view caches`.

**Stop boundary:**
- Do not start Release Groundwork.

---

### Task 5: Default-path Windows product smoke

**Files:**
- Modify: `tests/blender_smoke.py` only for missing executable assertions.
- Modify earlier task files only when a failing gate proves a scoped defect.

**Interfaces:**
- Consumes completed Tasks 1–4 and the existing extension build/install/smoke entrypoints.
- Produces fresh local evidence under default and short isolated runtime roots.

**RED test:**
- Re-run the historical default-temp smoke before Task 1 GREEN and record the concrete failing path/error.

**Expected RED:**
- Baseline fails at the long sidecar-array temporary basename while short-path isolated smoke passes.

**Minimal implementation:**
- No new production feature belongs here; fix only defects directly reproduced by product gates.

**Focused verification:**
- Run the nine requested unittest modules, full discovery, `compileall`, `git diff --check` and final status.

**Blender verification:**
- Run native preflight, validate, build, ZIP audit, `user_default` install, default `BLENDER_USER_RESOURCES`/`TEMP`/`TMP` full smoke, short-path isolated smoke and two lifecycle reloads.
- Run clean no-op save, new Scene link-only save, multi-Scene relink/rollback, Cube and Surface cross-process reopen, cache clear/rebuild, Save As and moved pair.

**Commit boundary:**
- No commit unless a product-gate defect requires a reviewed fix.

**Stop boundary:**
- Remote CI stays `Not Run`; no workflow/tag/release/push action.

---

### Task 6: Independent review and checkpoint

**Files:**
- Modify: `.agents/active/2.3.0-wave-0-platform-foundation.md`
- Modify: this plan only to check completed boxes and record exact evidence.
- Modify implementation files only through a reviewed fix commit.

**Interfaces:**
- Consumes all gate commits and fresh verification evidence.
- Produces a completed Execution Cursor whose next task is Release Groundwork Task 1 without starting it.

**RED test:**
- Not applicable to the cursor itself; review findings require a reproducing test before any production fix.

**Expected RED:**
- Any confirmed finding gets one focused failing regression before implementation.

**Minimal implementation:**
- Run independent specification-compliance review, then independent code-quality review.
- Fix every Critical, Important and gate-related Minor finding through the same TDD and scoped re-review loop.
- Record exact full SHAs, test counts, smoke outcomes, unchanged hashes and `Remote CI: Not Run`.

**Focused verification:**
- Re-run all tests covering review fixes, then the full Python suite and static checks.

**Blender verification:**
- Re-run the final native package/install/lifecycle and cross-process persistence gates after review fixes.

**Commit boundary:**
- Optional review fixes: one scoped commit.
- Final cursor/plan: `chore: checkpoint pre-release persistence gate`.

**Stop boundary:**
- Stop with Release Groundwork Task 1 unstarted and no push.

---

## Completion checkpoint

- State: `completed`
- Planning commit:
  `d971a385c006d23fa4733811427e6a7987429f8c`
- Atomic-path implementation:
  `013efd4f06d0c1971758940b7ebf4082a599a8c4`
- Atomic-path review fix:
  `3d4530b46d192dc5a6e042b2be0013a7b92e1b7f`
- Link synchronization and relink:
  `05351b54f8821fd48eedf3cdffb1512256c40b6d`
- Link-locator review fix:
  `0e0913f85e8064d5c3322fa7ce252a38844576a9`
- Durable View cache:
  `11eb3f8a4985946ee9a81d1a23f0c79a616114a2`
- View-cache security/recovery review fix:
  `3a7c47981bdb590b9a46b860c6c40ec606b8963b`
- Save As fallback review fix:
  `e310365fbc5228dd248c5cd6346363e61f71cafd`
- Required focused modules: `206 Passed, 0 Failed`.
- Full unittest discovery: `935 Passed, 27 Skipped, 0 Failed`.
- Default Windows TEMP product smoke: `Passed`.
- Short-path isolated product smoke: `Passed`.
- Blender 5.1.2 validate/build/ZIP/default install/lifecycle: `Passed`.
- Cross-process Grid/Surface reopen and cache reconstruction: `Passed`.
- Clean link-only save, new Scene synchronization and multi-Scene relink:
  `Passed`.
- Fixture and canonical hashes: `Unchanged`.
- Independent specification and code-quality reviews: `Passed`.
- Remote CI: `Not Run`.
- Next plan:
  `docs/superpowers/plans/2026-07-23-chemblender-2.3.0-wave-0-release-groundwork.md`
- Next task: `Task 1 — Add a single release metadata helper`.
- Stop boundary: Release Groundwork Task 1 remains unstarted.
- Remote policy: no push without a new explicit user authorization.
