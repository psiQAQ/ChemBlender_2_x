# ChemBlender 2.4.0 MOL2 Export UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the completed native MOL2 exporter through the existing Project Browser export workflow with selection-safe metadata, explicit loss confirmation, background cancellation and Blender export/re-import proof.

**Architecture:** Extend the existing `ChemBlender.ui.export` format table, immutable `ExportSelection`, preview dispatcher and `ExportJob`. Project only the selected Structure, TopologyRecord, MolecularRecord, ChemicalAnnotations and datasets into the attribute-based collection already accepted by `preview_mol2_export()` and `export_mol2()`; reuse the existing operator, RNA, worker and atomic writer lifecycle.

**Tech Stack:** Python 3.13, standard-library `dataclasses`, `types.SimpleNamespace` and `unittest`, existing ChemBlender core exporter, Blender 5.1.2 Extensions.

## Global constraints

- Baseline is merge commit `63f6043bdfe1a15fa411662f2bd418de6ebee85e`.
- Preserve the frozen model, sidecar schema, Reader API and dependency set.
- Add no operator, registration root, RNA collection or second export lifecycle.
- Do not implement PDB, PQR or Cube export.
- Do not modify manifest version, CHANGELOG release version, tag or Release.
- Push, ready PR, exact-head CI monitoring and ordinary merge are authorized by the active goal only after all local gates pass.

---

### Task 1: Persist the approved implementation boundary

**Files:**
- Create: `docs/superpowers/plans/2026-08-01-chemblender-2.4.0-mol2-export-ui.md`
- Modify: `.agents/active/2.4.0-mol2-export-ui.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:** The active cursor points to this plan and records that the written design was approved. No runtime interface changes in this task.

- [x] Update the documentation contract to require the implementation plan and approved-design state.
- [x] Run `tests.test_quantum_visualization_docs` and `git diff --check`.
- [x] Commit as `docs: plan MOL2 export UI implementation`.
- [x] Stop before runtime edits if the documentation gate fails.

### Task 2: Project exactly one MOL2 export selection

**Files:**
- Modify: `ChemBlender/ui/export.py`
- Modify: `tests/test_extxyz_workflow.py`

**Interfaces:** `ExportSelection` gains immutable `annotations: tuple = ()`. Selection resolution includes only `ChemicalAnnotation` values whose `target_id` belongs to the selected Structure, selected TopologyRecord, selected MolecularRecord or selected related dataset. A private helper returns a `SimpleNamespace` with `structures`, `topologies`, `molecular_records`, `annotations` and `datasets` tuples for the core MOL2 exporter.

- [x] **RED:** prove a MOL2 fixture selection does not contain its Tripos/substructure annotations and cannot produce the expected core projection.
- [x] **Expected RED:** focused test fails because `ExportSelection` has no `annotations` field/helper.
- [x] Add the field, resolve only target-bound annotations and build the five-tuple entity projection.
- [x] Reject a `ConformerSet` selection for MOL2; SDF remains the conformer path.
- [x] Prove unrelated structures, records, annotations and datasets are absent from the projection, including sibling records from one `multi.mol2` source revision.
- [x] Run the selection-focused `tests.test_extxyz_workflow` cases.
- [x] Keep the changes uncommitted until Tasks 3 and 4 complete as one runtime feature boundary.

### Task 3: Add MOL2 preview and explicit confirmation

**Files:**
- Modify: `ChemBlender/ui/export.py`
- Modify: `tests/test_extxyz_workflow.py`

**Interfaces:** Add `mol2` to `_FORMAT_ITEMS`; add `*.mol2` to the existing hidden filter. `preview_export_selection(selection, "mol2")` delegates to `preview_mol2_export(projected_entities)` and returns the core `ExportReport` unchanged.

- [x] **RED:** prove the format enum/filter omit MOL2 and preview dispatch raises the old allowed-format error.
- [x] **Expected RED:** exact choice/filter/preview assertions fail without runtime changes.
- [x] Import and delegate to `preview_mol2_export()`; update only the existing allowed-format message.
- [x] Prove loss entries and `requires_confirmation` are identical to the core preview.
- [x] Prove the operator clears stale confirmation when MOL2 selection/format changes.
- [x] Prove preview performs no serialization or destination write.
- [x] Run the preview/operator-focused `tests.test_extxyz_workflow` cases.

### Task 4: Dispatch background atomic MOL2 export

**Files:**
- Modify: `ChemBlender/ui/export.py`
- Modify: `tests/test_extxyz_workflow.py`

**Interfaces:** `ExportJob._run()` delegates `mol2` to `export_mol2(projected_entities, confirm_loss=..., destination=..., is_cancelled=...)` and stores its `.report`, matching existing MOL/SDF/SMILES behavior.

- [x] **RED:** prove `ExportJob(format_name="mol2")` reaches the old unsupported-format branch.
- [x] **Expected RED:** job completes with `ValueError` and no destination.
- [x] Add one dispatch branch and update only the existing allowed-format message.
- [x] Prove a loss-bearing export is blocked without confirmation and succeeds with it.
- [x] Prove cancellation leaves an existing destination byte-identical and no sibling temporary file.
- [x] Prove fatal exceptions remain unwrapped and existing UI cleanup tests still pass.
- [x] Run `python -m unittest tests.test_extxyz_workflow tests.test_mol2_exporter -v`.
- [x] Commit runtime and focused tests as `feat: add native MOL2 export UI` (`8b546558917abe5672cb81dc59d976f3fe85b2e3`).

### Task 5: Prove the installed Blender product workflow

**Files:**
- Modify: `tests/blender_smoke.py`

**Interfaces:** The existing installed-extension smoke selects the imported MOL2 molecular record, previews export, runs `ExportJob`, parses the written file through native `parse_mol2()` and compares the selected Structure/topology/annotation semantics.

- [x] **RED:** product dispatch was first proved by the focused failing choice/preview/job tests before the installed smoke was extended.
- [x] **Expected RED:** the pre-implementation format choice/preview/job path failed before output could be written.
- [x] Reuse the existing `assert_mol2_browser_view()` fixture/project and export worker; add no separate Blender operator.
- [x] Verify export, native re-import, atom/bond inventory, Tripos annotations, atom types, substructures and partial charges.
- [x] Verify loss preview/confirmation and atomic-destination preservation across focused and installed-product paths.
- [x] Run focused pure-Python tests before invoking Blender.
- [x] Keep the smoke change for the final implementation/review commit unless an in-scope defect requires a separate fix.

### Task 6: Full verification, independent review and checkpoint

**Files:**
- Modify only if required by an in-scope finding: `ChemBlender/ui/export.py`, `tests/test_extxyz_workflow.py`, `tests/blender_smoke.py`
- Modify: `.agents/active/2.4.0-mol2-export-ui.md`
- Modify: `docs/superpowers/plans/2026-08-01-chemblender-2.4.0-mol2-export-ui.md`

**Interfaces:** No new public model/API surface. Completion evidence is persisted in the cursor.

- [x] Run focused MOL2/export/registration/documentation tests.
- [x] Run full `unittest` discovery, `compileall`, `git diff --check` and verify the manifest/version/dependency lock are unchanged.
- [x] Run Blender 5.1.2 native preflight, extension validate/build, ZIP safe-path/duplicate/CRC/wheel audit, isolated install and installed MOL2 export/re-import lifecycle.
- [x] Perform separate specification-compliance and code-quality reviews; fix every in-scope Critical, Important and Minor finding and rerun affected verification.
- [x] Mark every completed checkbox, record RED/GREEN/Blender/review evidence and set cursor state `completed_local`.
- [x] Commit review fixes/checkpoint as one logical commit if needed; leave the worktree clean.

### Task 7: Remote integration gate

**Files:**
- Modify only the active cursor if exact-head CI or merge evidence must be persisted before integration.

**Interfaces:** The exact pushed head is the only acceptable CI identity. Integration uses an ordinary merge commit.

- [ ] Push `feat/2.4.0-mol2-export-ui` normally and create a ready PR to `main`.
- [ ] Wait for every required GitHub Actions check on the exact pushed head SHA; record workflow/run/job conclusions.
- [ ] Diagnose and minimally fix any exact-head CI failure; each new head invalidates old CI evidence.
- [ ] Merge the ready PR with an ordinary merge commit only after exact-head CI passes.
- [ ] Fetch and prove the exact feature head is an ancestor of `origin/main`; verify PR state and merge commit parents.
- [ ] Fast-forward local `main` only if its worktree is clean; do not rebase, force-push, tag or release.
- [ ] Mark the active goal complete only after the requirement-by-requirement completion audit passes.
