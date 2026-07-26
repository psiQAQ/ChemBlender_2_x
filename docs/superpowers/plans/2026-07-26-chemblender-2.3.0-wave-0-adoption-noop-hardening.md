# ChemBlender 2.3.0 Wave 0 Adoption and View-Cache No-op Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make verified-project adoption transactional on every service entrypoint and make View-cache repair a true filesystem no-op when no ChemBlender-owned Volume or Surface needs repair.

**Architecture:** Reuse the existing Scene link snapshots, rollback report and candidate cleanup in `project_service.py` behind one private adoption transaction used by verify and relink. In `view_cache.py`, first project the owned Volume repair plans without touching the sidecar, then create the durable cache root only when that projection is non-empty; fatal exceptions bypass fallback and retain their original type.

**Tech Stack:** Python 3.13 standard library, Blender 5.1.2 Python API, existing NumPy/OpenVDB runtime, `unittest`.

## Global Constraints

- Work only on `feat/2.3.0-wave0-platform-foundation` in its existing linked worktree.
- Reviewed baseline is `97bb15f9d1965c8b98a669fa41c7b44235539168`.
- `QCProject` and `.cbq` remain authoritative; Blender datablocks and VDB files remain derived views/cache.
- Do not modify `blender_manifest.toml`, GitHub workflows, `CHANGELOG.md`, dependencies, file formats or Wave 1–4 work.
- Do not start Release Groundwork Task 1.
- Do not create a PR, tag or Release, and do not push without a new explicit user authorization after this gate.
- Preserve UTF-8/BOM/line endings; update the architecture guide only if a module responsibility or public entrypoint changes.
- Every behavior change follows RED → minimal GREEN → focused regression → independent review.
- `KeyboardInterrupt`, `SystemExit`, `GeneratorExit` and `MemoryError` must remain fatal and unwrapped.
- Remote CI remains `Not Run` unless an actual workflow run is later authorized and observed.

---

### Task 1: Transactional verified-project adoption

**Files:**
- Modify: `tests/test_project_service.py`
- Modify: `ChemBlender/core/project_service.py`

**Interfaces:**
- Reuse: `_write_scene_links(scenes, values, links) -> tuple[tuple[scene, snapshot], ...]`.
- Reuse: `_rollback_scene_links(snapshots, write_error, *, attempted=None)`.
- Reuse: `_close_candidate_after_failure(candidate, error)`.
- Produce: one private adoption transaction, named `_adopt_verified_project(...)` or an equivalent local name, shared by multi-Scene verify, single-Scene verify and multi-Scene relink.

- [x] **Step 1: Add failing multi-Scene adoption tests**

Add tests that open a candidate containing a loaded `LazyNpyArray`, patch `close_project(previous)` to raise `OSError("old project close failed")`, and assert:

```python
with self.assertRaisesRegex(OSError, "old project close failed"):
    verify_project_session_for_scenes(
        session=session,
        scenes=(linked, empty),
    )
self.assertEqual(tuple(dict(scene) for scene in scenes), originals)
self.assertIs(session.project, previous)
self.assertFalse(candidate_values.loaded)
```

Also make Scene rollback fail and assert `SceneLinkWriteRecoveryError.write_error` is the original adoption error, `rollback_failures` and `residual_keys` identify the remaining link, and candidate cleanup still unloads the lazy array. Make candidate cleanup fail in that test and assert the structured recovery error receives a cleanup note without replacement.

**RED test:**
- Run `python -m unittest tests.test_project_service -v`.

**Expected RED:**
- Multi-Scene verify leaves the empty Scene projected to the candidate after adoption failure.
- Candidate `LazyNpyArray.loaded` remains true because the candidate is not closed.
- Incomplete rollback cannot be reported because verify never attempts rollback.

- [x] **Step 2: Add failing single-Scene ownership test**

Open and load a candidate array, fail `close_project(previous)`, then assert the original exception is re-raised, the session tuple `(project, sidecar_path, link_status, dirty_reasons)` is unchanged, and the candidate array is unloaded.

**Expected RED:**
- `verify_project_session()` leaks the candidate array after `_adopt_project()` raises.

- [x] **Step 3: Implement the shared transaction**

Move only the existing relink adoption failure sequence into one helper:

```python
try:
    _adopt_project(session, candidate, path)
except Exception as error:
    if scene_snapshots:
        try:
            _rollback_scene_links(scene_snapshots, error)
        except Exception as recovery_error:
            _close_candidate_after_failure(candidate, recovery_error)
            raise
    _close_candidate_after_failure(candidate, error)
    raise
```

Call it from `verify_project_session_for_scenes()`, `verify_project_session()` and `relink_project_session_for_scenes()`. Successful adoption transfers candidate ownership to the session and closes the previous project exactly once; no success path closes the candidate.

**Minimal implementation:**
- One private helper, no new public API or transaction type.
- Preserve every current successful verify/relink result and link locator.
- Keep Scene write failure cleanup before adoption unchanged.

**Focused verification:**
- Run `python -m unittest tests.test_project_service -v`.
- Re-run the specific successful ownership, relink rollback and candidate cleanup tests.

**Blender verification:**
- Pure Python service tests prove injected old-project close failure.
- Real Blender normal multi-Scene reopen must continue to adopt one project and project one coherent link to all Scenes.

**Commit boundary:**
- This task shares the single implementation commit with Tasks 2–4: `fix: make project adoption and cache repair transactional`.

**Stop boundary:**
- Do not change publication, sidecar schema or save routing.

---

### Task 2: Candidate resource ownership

**Files:**
- Modify: `tests/test_project_service.py`
- Modify: `ChemBlender/core/project_service.py`

**Interfaces:**
- Consumes the Task 1 adoption transaction.
- Preserves `close_project(previous)` exactly once on success.
- Guarantees `close_project(candidate)` on every adoption failure before ownership transfer.

- [x] **Step 1: Complete ownership matrix tests**

Cover:

```text
multi-Scene verify success     -> previous closed once, candidate retained
multi-Scene verify failure     -> previous remains, candidate closed
single-Scene verify failure    -> previous remains, candidate closed
multi-Scene relink success     -> previous closed once, candidate retained
multi-Scene relink failure     -> previous remains, candidate closed
```

The tests must observe real `LazyNpyArray.loaded` state, not only mock call counts.

**RED test:**
- Run `python -m unittest tests.test_project_service -v` before production edits.

**Expected RED:**
- The two verify failure rows leak the loaded candidate.

**Minimal implementation:**
- Reuse Task 1 helper; do not add another cleanup wrapper.
- Cleanup failure is added as an exception note and never replaces the adoption or rollback error.

**Focused verification:**
- Run the full `tests.test_project_service` module.

**Blender verification:**
- Open a valid shared project in Blender and confirm a normal successful adoption leaves its arrays readable.

**Commit boundary:**
- Included in `fix: make project adoption and cache repair transactional`.

**Stop boundary:**
- Do not alter `LazyNpyArray` or `close_project()` semantics.

---

### Task 3: Multi-Scene link rollback

**Files:**
- Modify: `tests/test_project_service.py`
- Modify: `ChemBlender/core/project_service.py`

**Interfaces:**
- Consumes Scene snapshots returned by `_write_scene_links()`.
- Preserves `SceneLinkWriteRecoveryError(write_error, rollback_failures, residual_keys)`.

- [x] **Step 1: Verify complete and incomplete adoption rollback**

For a linked Scene plus an empty Scene, capture every link key before verify. On adoption failure, assert both snapshots are restored. For a rollback write failure, assert:

```python
self.assertIsInstance(error, SceneLinkWriteRecoveryError)
self.assertEqual(str(error.write_error), "old project close failed")
self.assertEqual(
    tuple((failure.scene_index, failure.key) for failure in error.rollback_failures),
    ((expected_scene_index, MANIFEST_HASH_KEY),),
)
self.assertEqual(error.residual_keys, ((expected_scene_index, MANIFEST_HASH_KEY),))
```

**RED test:**
- Run `python -m unittest tests.test_project_service -v`.

**Expected RED:**
- Current verify path leaves projected links in place and never raises the structured recovery error.

**Minimal implementation:**
- Pass the snapshots already returned by `_write_scene_links()` into the Task 1 transaction.
- Roll back before candidate cleanup so residual Scene state is fully reported even when cleanup also fails.

**Focused verification:**
- Re-run multi-Scene verify and relink success/write-failure/adoption-failure tests.

**Blender verification:**
- Verify normal multi-Scene reopen; keep close-failure injection in pure Python if Blender cannot safely inject it.

**Commit boundary:**
- Included in `fix: make project adoption and cache repair transactional`.

**Stop boundary:**
- Do not make implicit relink decisions for conflicting existing links.

---

### Task 4: True no-op View-cache repair

**Files:**
- Modify: `tests/test_view_cache_persistence.py`
- Modify: `ChemBlender/ui/view_cache.py`

**Interfaces:**
- Preserve: `repair_project_view_caches(*, session, objects, blend_path, previous_sidecar_path=None) -> int`.
- Produce internally: a tuple of `(obj, plan)` for current ChemBlender-owned Volume/Surface views before any durable cache path is inspected or created.

- [x] **Step 1: Add failing zero-object and foreign-object tests**

For `objects=()`, a foreign Volume and a non-Volume ChemBlender object, patch `_durable_cache_root` and assert it is never called. Assert no `cache/`, `render/`, `volume/` or `surface/` path is created, no object metadata changes, result is `0`, and only `view_cache` is cleared from dirty reasons.

**RED test:**
- Run `python -m unittest tests.test_view_cache_persistence -v`.

**Expected RED:**
- `_durable_cache_root()` is called and creates all four namespaces before object inspection.

- [x] **Step 2: Preserve owned and stale behavior**

Move the linked-render-root rejection test to use a valid owned Grid Volume. Keep the existing valid Grid/Surface repairs. Assert stale owned metadata still raises `ViewCacheError`, marks `view_cache` dirty and does not call a writer.

**Expected RED:**
- The zero-object no-op tests fail before this change; owned/stale tests characterize behavior that must remain.

- [x] **Step 3: Add fatal exception passthrough test**

Raise `MemoryError("cache exhausted")` from the owned cache writer and assert:

```python
with self.assertRaisesRegex(MemoryError, "cache exhausted"):
    repair_project_view_caches(...)
self.assertEqual(session.dirty_reasons, frozenset({"view_cache"}))
fallback.assert_not_called()
```

Cover the same fatal classifier for `KeyboardInterrupt`, `SystemExit` and `GeneratorExit` with a small table-driven test if it remains readable.

**Expected RED:**
- Current `except BaseException` enters fallback and raises `ViewCacheError` instead of the fatal exception.

- [x] **Step 4: Implement scan-before-create and fatal passthrough**

Inside the existing outer dirty-state guard:

```python
planned = tuple(
    (obj, plan)
    for obj in tuple(objects)
    if getattr(obj, "type", None) == "VOLUME"
    if (plan := _current_plan(obj, session.project)) is not None
)
if not planned:
    clear_view_cache_reason()
    return 0
```

Then validate connected session, create `_durable_cache_root()`, and repair `planned`. Add one private fatal exception tuple or predicate; fatal errors re-raise before any previous-sidecar or old-filepath fallback. Ordinary writer/reload exceptions keep the current verified fallback behavior.

**Minimal implementation:**
- Reorder existing work and narrow the existing exception branches.
- No new cache format, metadata, writer, directory abstraction or public API.

**Focused verification:**
- Run `python -m unittest tests.test_view_cache_persistence tests.test_ui_session_contract -v`.
- Confirm valid Grid, signed Surface, Save As fallback, stale metadata and malicious path tests remain green.

**Blender verification:**
- Save/reopen a Structure-only project and assert `<sidecar>/cache/render/` is absent.
- Reopen Cube Volume and signed Surface projects and assert the existing durable VDB repair remains successful.

**Commit boundary:**
- Included in `fix: make project adoption and cache repair transactional`.

**Stop boundary:**
- Do not alter cache identity, VDB layout or Blender object creation.

---

### Task 5: Full regression and checkpoint

**Files:**
- Modify only if findings require it: `ChemBlender/core/project_service.py`, `ChemBlender/ui/view_cache.py`, their two test modules.
- Modify: `.agents/active/2.3.0-wave-0-platform-foundation.md`
- Modify: this plan for the completed checkpoint.

**Interfaces:**
- Consumes the verified implementation commit.
- Produces a completed `W0-PRE-RELEASE-ADOPTION-NOOP-HARDENING` cursor whose next task is Release Groundwork Task 1 without starting it.

- [x] **Step 1: Run focused and full Python verification**

```powershell
& $pythonBin -m unittest `
  tests.test_project_service `
  tests.test_view_cache_persistence `
  tests.test_ui_session_contract -v
& $pythonBin -m unittest discover -s tests -p "test_*.py" -v
& $pythonBin -m compileall -q ChemBlender worker tests
git diff --check
git status --short
```

**RED test:**
- Any confirmed review finding must first receive a focused failing regression.

**Expected RED:**
- A review-fix RED must fail for the named behavior rather than syntax or fixture setup.

**Minimal implementation:**
- Fix only confirmed Critical, Important and gate-related Minor findings.

**Focused verification:**
- Re-run the focused modules after every review fix, then the full suite once.

- [x] **Step 2: Run Blender 5.1.2 regression**

Run native preflight, extension validate/build, ZIP audit, `user_default` install, short-path isolated lifecycle, normal multi-Scene reopen, Structure-only save/reopen without render cache, Cube Volume save/reopen and signed Surface save/reopen. Use pure Python for injected adoption failure if Blender cannot safely patch the old-project close.

**Blender verification:**
- Record command, exit code and PASS sentinel for each executed gate.

- [x] **Step 3: Run two independent reviews**

Dispatch one specification-compliance review and one code-quality review. Fix all Critical, Important and gate-related Minor findings with TDD, then perform scoped re-review.

**Commit boundary:**
- Implementation: `fix: make project adoption and cache repair transactional`.
- Checkpoint: `chore: checkpoint project adoption hardening`.

**Stop boundary:**
- Stop after the clean completed checkpoint.
- Release Groundwork Task 1, workflow changes, prerelease probes, manifest/changelog changes and push remain unstarted.

---

## Completion checkpoint

- State: `completed`
- Reviewed baseline: `97bb15f9d1965c8b98a669fa41c7b44235539168`
- Planning commit: `bd0e94a21be9e7069d3181628a788eec19a4201d`
- Implementation commit: `4dabc04b8cb5e7ed3c9356662f4ae21cf889e10b`
- Review-fix commit: `41ce00bc47b469b0042d3fb30aa75a950e92dacd`
- RED evidence:
  adoption 42 tests with 2 failures and 1 error; View-cache 15 tests with
  2 failures and 5 errors; fallback review 17 tests with 2 errors; fatal
  adoption review 2 tests with 3 subtest failures and 1 error.
- GREEN evidence:
  focused 99/99 Passed; full 944 Passed, 27 Skipped and 0 Failed; compileall
  and diff-check Passed.
- Blender verification:
  Blender 5.1.2 native preflight, validate, build, ZIP audit, default
  `user_default` install/lifecycle and short-path isolated lifecycle Passed;
  Structure-only no-cache and Grid Volume/signed Surface cross-process reopen
  Passed; missing VDB reconstruction Passed without duplicate objects.
- Independent reviews:
  specification compliance and code-quality reviews Passed after their
  findings were fixed and scoped re-reviewed.
- Remote CI: `Not Run`
- Next plan: `docs/superpowers/plans/2026-07-23-chemblender-2.3.0-wave-0-release-groundwork.md`
- Next task: `Task 1 — Add a single release metadata helper`
- Stop boundary: Release Groundwork Task 1 remains unstarted.
- Remote policy: no push without a new explicit user authorization.
