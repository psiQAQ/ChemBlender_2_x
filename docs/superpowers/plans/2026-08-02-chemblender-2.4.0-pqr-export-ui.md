# ChemBlender 2.4.0 PQR Export UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task by task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose native PQR export through the existing Project Browser
operator with exact entity projection, preview confirmation, cancellable atomic
writing and installed native re-import proof.

**Architecture:** Extend only `ChemBlender.ui.export` format dispatch and reuse
its existing `_pdb_entities()` biological Structure projection, operator and
`ExportJob`. The core PQR exporter remains the sole scientific validation and
serialization boundary. Update the catalog once and regenerate its documents.

**Tech Stack:** Python 3.13, `unittest`, existing ChemBlender native PQR
reader/exporter, Blender 5.1.2 Extensions.

## Global Constraints

- Baseline is ordinary PQR core merge
  `54dd2364b6f935771f6d6c661452f44b7d4b558a`.
- Reuse `_pdb_entities()` directly; add no wrapper, operator, RNA property,
  module, registration root or exporter abstraction.
- Do not change PQR core serialization/readiness, models, sidecar schema,
  Reader API token, dependency set, workflows, manifest version or CHANGELOG
  release version.
- Do not begin Cube export, Reader API v1 stable, tag or Release work.

---

### Task 1: Persist activation and exact core integration evidence

**Files:**
- Create: `.agents/active/2.4.0-pqr-export-ui.md`
- Modify: `.agents/completed/2.4.0-pqr-export.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:** Persist goal `CB240-PQR-EXPORT-UI-T6` and the exact PR #13 CI,
merge and ancestry evidence. No runtime change.

- [x] **Step 1: Write the routing RED**

Add a documentation test that requires the active cursor, design and plan and
asserts the completed core cursor records PR #13, exact head, both run IDs and
merge commit.

- [x] **Step 2: Run the routing RED**

Run:
`python -m unittest tests.test_quantum_visualization_docs.QuantumVisualizationDocsTests.test_pqr_export_ui_routing -v`

Expected: fail because the test or required active routing is absent.

- [x] **Step 3: Persist the cursor and evidence**

Keep the exact values already frozen in the active cursor and archive the core
remote gate in the completed cursor. Do not change product code.

- [x] **Step 4: Run documentation GREEN and commit**

Run the focused documentation module and `git diff --check`, then commit:
`docs: activate native PQR export UI`.

### Task 2: Add PQR choice and metadata-only preview

**Files:**
- Modify: `ChemBlender/ui/export.py`
- Modify: `tests/test_extxyz_workflow.py`

**Interfaces:** Import `preview_pqr_export`; add `("pqr", "PQR", ...)` to
`_FORMAT_ITEMS`, `*.pqr` to `filter_glob`, and dispatch preview with
`preview_pqr_export(_pdb_entities(selection))`.

- [x] **Step 1: Write failing selection and format tests**

Add tests that select `tests/fixtures/pqr/with-chain.pqr`, assert the existing
projection contains exactly one Structure, one matching hierarchy, complete
`partial_charge` and `radius`, no unrelated sibling data, and prove `pqr` and
`*.pqr` are currently absent.

- [x] **Step 2: Write failing preview tests**

Assert the UI preview equals `preview_pqr_export(_pdb_entities(selection))`,
does not call `export_pqr`, preserves stable loss entries, and fails closed for
missing/partial charge, radius or hierarchy.

- [x] **Step 3: Run RED**

Run the named new tests. Expected: enum/filter and preview unsupported failures.

- [x] **Step 4: Implement the minimal preview surface**

Add only the import, tuple item, filter suffix, preview branch and shared
allowed-format error text.

- [x] **Step 5: Run GREEN**

Run `tests.test_extxyz_workflow`, `tests.test_pqr_exporter` and
`tests.test_pdb_export_readiness` with the installed extension shared dependency
path.

### Task 3: Dispatch cancellable atomic PQR export

**Files:**
- Modify: `ChemBlender/ui/export.py`
- Modify: `tests/test_extxyz_workflow.py`

**Interfaces:** Import `export_pqr`; `ExportJob._run()` calls
`export_pqr(_pdb_entities(self.selection), confirm_loss=self.confirm_loss,
destination=self.destination, is_cancelled=self._cancelled.is_set).report`.

- [x] **Step 1: Write job RED**

Add tests proving the current job rejects `pqr`, loss-bearing output does not
write without confirmation, confirmed output reparses through native
`parse_pqr()`, and cancellation preserves an existing destination with no
temporary sibling.

- [x] **Step 2: Run RED**

Run the named job tests. Expected: unsupported `format_name` and no output.

- [x] **Step 3: Add one dispatch branch**

Delegate to the core exporter and update only the shared allowed-format error.
Do not catch fatal exceptions or duplicate atomic-write logic.

- [x] **Step 4: Run GREEN and commit**

Run workflow/PQR/registration tests and commit:
`feat: add native PQR export UI`.

### Task 4: Publish and prove the reachable capability

**Files:**
- Modify: `ChemBlender/core/reader_catalog.py`
- Modify: `docs/quantum-visualization/reader-capability-matrix.json`
- Modify: `docs/user/format-capabilities.json`
- Modify: `docs/user/formats.md`
- Modify: `tests/test_generated_docs_fresh.py`
- Modify: `tests/blender_smoke.py`

**Interfaces:** PQR becomes
`("pqr", "F5", "project_browser", "preview_confirmation")` in the catalog.

- [x] **Step 1: Write capability RED**

Update the generated-doc contract to require `project_browser`; run it and
observe the current `core` mismatch.

- [x] **Step 2: Update the catalog and regenerate documents**

Run:
`python ChemBlender/scripts/generate_format_docs.py`

Only catalog-derived PQR execution claims may change.

- [x] **Step 3: Extend installed Blender smoke**

Within the existing biological workflow, export the selected imported PQR
Structure through `ExportJob`, reparse it with native `parse_pqr()`, and compare
atomic numbers, coordinates, hierarchy labels, partial charges and radii.
Retain register/unregister/reload x2 and the existing small RNA budget.

- [x] **Step 4: Run focused GREEN and commit**

Run workflow, generated docs, PQR reader/exporter, registration and smoke source
contracts, then commit: `docs: publish PQR Project Browser export`.

### Task 5: Full qualification, reviews and checkpoint

**Files:**
- Modify only in-scope files required by findings
- Move: `.agents/active/2.4.0-pqr-export-ui.md`
- Create: `.agents/completed/2.4.0-pqr-export-ui.md`
- Modify: `docs/superpowers/plans/2026-08-02-chemblender-2.4.0-pqr-export-ui.md`

**Interfaces:** No public model/API addition. Completion evidence is persisted
before remote integration.

- [ ] **Step 1: Run local qualification**

Run focused tests, full unittest discovery, `compileall`, generated-doc check,
optional-import audit and `git diff --check`.

- [ ] **Step 2: Run Blender qualification**

Run native preflight, validate/build, exact ZIP audit, isolated install, PQR
Project Browser export/re-import and lifecycle twice with Blender 5.1.2.

- [ ] **Step 3: Run two independent reviews**

Run specification-compliance and code-quality/correctness/security reviews.
Fix all Critical, Important and task-related Minor findings and rerun affected
checks.

- [ ] **Step 4: Checkpoint**

Record exact RED/GREEN/Blender/review evidence, move the cursor to completed,
mark Tasks 1–5 checked and commit: `chore: checkpoint native PQR export UI`.

### Task 6: Exact-head remote integration gate

**Files:**
- No product file changes after the exact feature head enters CI.

**Interfaces:** Only CI with `headSha` equal to the pushed feature head is valid;
merge mode is ordinary merge commit.

- [ ] **Step 1: Push and create a ready PR to `main`**

Confirm a clean worktree and ordinary push. Record the PR URL and exact head.

- [ ] **Step 2: Wait for exact-head CI**

Require `extension-package` (`native-core`, `package`) and `optional-qc-core`
(`cclib`, `iodata`, `gbasis`) to finish successfully for the exact head.

- [ ] **Step 3: Merge and verify**

Use an ordinary merge commit, fetch, and prove the exact head is an ancestor of
`origin/main`. Do not squash, rebase, force-push, delete branches, tag or release.

## Stop Boundary

Stop after PQR Export UI is merged and ancestry is verified. Cube export and
Reader API v1 stable remain unstarted.
