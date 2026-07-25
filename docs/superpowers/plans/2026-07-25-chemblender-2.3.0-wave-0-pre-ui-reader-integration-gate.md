# ChemBlender 2.3.0 Wave 0 Pre-UI Reader Integration Gate Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` and test-driven development.

**Goal:** Close the Reader API-to-import-pipeline boundary before any
Registration/UI runtime implementation begins.

**Architecture:** Keep `ReaderPluginRegistry` as the plugin boundary and the
existing import pipeline as the only staging/preview/commit path. Validate
public results before they reach staging, preserve source identity, and expose
the initialized runtime registry only through an internal accessor. Correct
the Registration/UI plan so later UI code consumes this bridge without
touching private registries or project internals.

**Tech Stack:** Python 3.13 standard library, existing Reader API 0.x,
`unittest`, Blender 5.1.2 extension tooling.

## Constraints

- Do not create Registration/UI runtime modules or implement UI classes.
- Do not change Reader API version `0.1` or canonical schema `0.1`.
- Do not add dependencies, pickle, dynamic imports, or a second registry.
- Do not mutate `QCProject`, Blender scenes, or datablocks during preflight.
- Preserve built-in XYZ/Cube behavior and no-copy array semantics.
- Do not enter Release Groundwork or Wave 1–4, and do not push.

## Task 1: Correct checkpoint and remote-state records

**Files:**
- Modify: `.agents/active/2.3.0-wave-0-platform-foundation.md`
- Modify: `docs/superpowers/plans/2026-07-24-chemblender-2.3.0-reader-api-final-hardening.md`

- [ ] Record externally reviewed remote HEAD `32b26bb4508a29d3ac0763256869fb9e8daac5f4`.
- [ ] Mark the previously authorized final-hardening push as complete.
- [ ] Persist this gate as the only active execution cursor.

## Task 2: Validate registry results and preserve fatal exceptions

**Files:**
- Modify: `ChemBlender/reader_api/registry.py`
- Modify: `tests/test_reader_api_registry.py`

- [ ] Write failing tests for sniff/parse `MemoryError`, plugin exceptions,
  incomplete or invalid exact public batches, and valid XYZ/Cube no-copy
  results.
- [ ] Continue after ordinary sniff failures and return stable failed batches
  for ordinary parse/result-validation failures.
- [ ] Re-raise `MemoryError` unchanged.
- [ ] Validate every exact `PublicImportBatch` through
  `internal_batch_from_public()` before success without replacing the public
  result.

## Task 3: Stabilize incomplete canonical model errors

**Files:**
- Modify: `ChemBlender/reader_api/canonical_document.py`
- Modify: `tests/test_reader_canonical_document.py`

- [ ] Write a failing regression for an exact but incomplete `Grid3D`.
- [ ] Convert incomplete public model access to
  `CanonicalDocumentIntegrityError("incomplete public model value")`.
- [ ] Preserve existing typed canonical errors, recursion handling, document
  bytes, artifact hashes, and schema `0.1`.

## Task 4: Bridge ReaderPluginRegistry into import preview staging

**Files:**
- Create: `ChemBlender/reader_api/import_pipeline_bridge.py`
- Create: `tests/test_reader_api_import_bridge.py`
- Modify: `ChemBlender/runtime/reader_api_bridge.py`
- Modify: `ChemBlender/core/import_pipeline/parse.py`
- Modify: `ChemBlender/core/import_pipeline/preflight.py`
- Modify: `ChemBlender/core/import_pipeline/__init__.py`
- Modify: `.agents/reference/code-architecture-guide.md`
- Test: `tests/test_quantum_visualization_docs.py`

- [ ] Write failing bridge tests for exact input contracts, selection,
  overrides, unavailable readers, cancellation, source recheck, failure
  staging, complete external source identity, built-in fallback, external
  handle registration/unregistration, and XYZ/Cube preview/commit flow.
- [ ] Expose the initialized registry through internal
  `get_reader_plugin_registry()` without adding it to the public handle.
- [ ] Implement `preflight_reader_plugins()` with a 65536-byte sniff prefix,
  canonical parameters, progress/cancellation, stable diagnostics, and exactly
  one staged internal batch per source.
- [ ] Refactor source/revision staging into one shared helper while preserving
  `staged_reader_batch()` compatibility and parse-identity semantics.
- [ ] Keep project mutation exclusively in the existing confirmed
  `commit_import_preview()` path.

## Task 5: Correct the Registration/UI execution plan

**Files:**
- Modify: `docs/superpowers/plans/2026-07-23-chemblender-2.3.0-wave-0-registration-ui.md`

- [ ] Correct Task 1 live file state and require Blender 5.1.2 registration
  inventory before implementation.
- [ ] Define module-by-module registration growth and Reader API handle
  lifecycle/rollback without clearing the initialized registry.
- [ ] Route Quick Import through `get_reader_plugin_registry()` and
  `preflight_reader_plugins()`.
- [ ] Correct `save_pre` semantics and define `ViewRecord` as UI/session-only
  state with monotonic browser revision invalidation.

## Task 6: Full regression, Blender verification, and checkpoint

- [ ] Run focused tests, full discovery, compileall, optional-import isolation,
  `git diff --check`, and final worktree inspection.
- [ ] Run Blender 5.1.2 native validate/build, ZIP audit, isolated install,
  register/unregister/reload, and Reader API handle lifecycle.
- [ ] Obtain independent specification and code-quality reviews and close all
  Critical, Important, and directly related Minor findings.
- [ ] Record exact evidence in the active cursor and stop before
  Registration/UI Task 1.

