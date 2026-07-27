# ChemBlender 2.3.0 Wave 1 RDKit Pre-Adapter Binding Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make built-in Reader results bind `MolecularRecord` entities to the host's final `SourceRevision` before full graph validation, while tightening source-local record, typed-column and conformer invariants.

**Architecture:** The host allocates one final revision UUID before parsing and passes it through `ParseRequest`. Exact built-in plugins may cross one private structural conversion boundary before source projection; the host then stages the matching `SourceRecord`/`SourceRevision` and performs the normal full `QCProject.commit()` graph validation before registering a preview. Extension and worker readers keep the strict public contract: they must return a complete source/revision graph whose revision UUID and identity fields match the host request.

**Tech Stack:** Python 3.13, dataclasses, UUID, NumPy supplied by Blender 5.1.2, Reader API/canonical document 0.1, project/sidecar schema 0.2, `unittest`.

## Global Constraints

- Complete only `W1-RDKIT-PRE-ADAPTER-BINDING-GATE`; RDKit Task 2 remains unstarted.
- Do not import RDKit or implement MOL/SDF/SMILES readers, exporters, grouping UI or Cube runtime.
- Do not change manifest, CHANGELOG, release version, tag, workflow, Reader API version, canonical schema version, project schema version or sidecar manifest version.
- Do not add or upgrade dependencies.
- Preserve strict external Reader identity validation and strict unknown-field/type rejection.
- Do not use `None`, zero UUID or another persistable placeholder as a record source revision.
- Do not copy large scientific arrays during binding.
- No push, PR, tag or Release.

---

### Task 1: Reproduce the built-in MolecularRecord staging failure

**Files:**
- Create: `tests/test_molecular_record_staging.py`
- Read: `ChemBlender/reader_api/registry.py`
- Read: `ChemBlender/reader_api/import_pipeline_bridge.py`
- Read: `ChemBlender/core/import_pipeline/parse.py`

**Current failure:** `ReaderPluginRegistry.parse()` calls `internal_batch_from_public()` before host staging. A built-in batch containing a `MolecularRecord` but no `SourceRevision` fails with a dangling revision reference.

**Target invariant:** One synthetic built-in reader traverses `ReaderPluginRegistry -> preflight_reader_plugins() -> StagedImportSession -> ImportPreview -> commit_import_preview()` and commits a record whose `source_revision_id` equals the staged revision ID.

**Interfaces:**
- Consumes: `ParseRequest.source_revision_id`.
- Produces: a product-path regression fixture that does not hand-construct the final `SourceRevision`.

- [ ] **Step 1: Write the failing product-path test**

Define a synthetic built-in `ReaderDescriptor.parse_request` that reads `request.source_revision_id` and returns `Structure`, `MolecularRecord`, provenance and an exact `ParserReport`.

- [ ] **Step 2: Run RED**

Run:

```powershell
& $pythonBin -m unittest tests.test_molecular_record_staging -v
```

Expected RED: `ParseRequest` lacks `source_revision_id`, or the registry rejects the record before host staging with a dangling source-revision error.

- [ ] **Step 3: Record the failing boundary**

Keep the exact command, exit code and first contract failure in the plan completion evidence.

**Minimal implementation:** None in this task.

**Focused verification:** The new test must fail for the reviewed defect, not for fixture construction.

**Compatibility verification:** Existing XYZ/extXYZ/Cube built-in readers remain untouched during RED.

**Commit boundary:** Test and implementation land together in the Gate implementation commit.

**Stop boundary:** Do not weaken `MolecularRecord.source_revision_id`.

---

### Task 2: Define one host source-revision binding contract

**Files:**
- Modify: `ChemBlender/reader_api/protocol.py`
- Modify: `ChemBlender/reader_api/conformance.py`
- Modify: `ChemBlender/reader_api/registry.py`
- Modify: `ChemBlender/reader_api/import_pipeline_bridge.py`
- Modify: `worker/reader_operation.py`
- Test: `tests/test_reader_api_registry.py`
- Test: `tests/test_reader_api_import_bridge.py`

**Current failure:** Parse identity is created after the reader returns, so record-producing readers cannot name the final revision.

**Target invariant:** The host creates exactly one UUID per source parse. That UUID is immutable in `ParseRequest`, is used by built-in record entities, and must equal the full `SourceRevision.id` returned by an external reader.

**Interfaces:**
- Produces: `ParseRequest.source_revision_id: UUID`.
- Produces: `stage_import_batch(..., revision_id: UUID | None = None)`.
- Preserves: complete external `SourceRecord` and `SourceRevision` output.

- [ ] **Step 1: Add RED contract tests**

Cover non-UUID rejection, frozen request identity, exact built-in propagation, external matching identity acceptance and external wrong identity rejection.

- [ ] **Step 2: Run focused RED**

```powershell
& $pythonBin -m unittest tests.test_reader_api_registry tests.test_reader_api_import_bridge -v
```

Expected RED: constructor/call sites lack the new identity and an external mismatched revision is not checked against the host request.

- [ ] **Step 3: Add the minimal request field**

Validate with exact `UUID` type in `ParseRequest.__post_init__()`. Allocate it once in host preflight and pass it through all direct, conformance and worker call sites.

- [ ] **Step 4: Verify the identity contract**

Run the two modules above and the worker reader-operation tests discovered by `rg`.

**Minimal implementation:** One required immutable UUID field plus call-site propagation; no new identity formula.

**Focused verification:** Exact UUID equality from request to final `SourceRevision` and records.

**Compatibility verification:** External readers still provide complete source/revision entities; no host-only unbound external path exists.

**Commit boundary:** Gate implementation commit.

**Stop boundary:** Do not bump Reader API 0.1.

---

### Task 3: Bind built-in results before final graph validation

**Files:**
- Modify: `ChemBlender/reader_api/builtin_bridge.py`
- Modify: `ChemBlender/reader_api/registry.py`
- Modify: `ChemBlender/reader_api/import_pipeline_bridge.py`
- Modify: `ChemBlender/core/import_pipeline/parse.py`
- Test: `tests/test_molecular_record_staging.py`
- Test: `tests/test_reader_api_import_bridge.py`

**Current failure:** The only public-to-internal converter performs full graph validation before source projection.

**Target invariant:** Exact `_BuiltinReaderPlugin` results receive structural/public-value validation, are staged with the request revision UUID, then pass complete project graph validation before `_register_preview()`.

**Interfaces:**
- Produces private `_internal_batch_from_public_unchecked(batch) -> ImportBatch`.
- Produces private `_validate_internal_batch_graph(batch) -> None`.
- Keeps public `internal_batch_from_public()` fully strict.

- [ ] **Step 1: Add RED tests for the controlled boundary**

Prove a built-in record batch succeeds only after binding; prove a malformed built-in graph is rejected before preview registration; prove an extension plugin cannot use the private unbound route.

- [ ] **Step 2: Implement the private conversion**

Reuse `_validate_public_batch_values()` and the existing `_BATCH_FIELDS`. Restrict the unchecked branch with exact `type(plugin) is _BuiltinReaderPlugin`.

- [ ] **Step 3: Stage with the preallocated revision**

Use the request UUID for diagnostics, `SourceRevision.id` and record binding. After staging, call `_validate_internal_batch_graph()` once before registration.

- [ ] **Step 4: Verify failure cleanup**

Assert graph failure and cancellation leave no registered staged batch, committed project entity or leaked staging artifact.

**Minimal implementation:** Split the existing converter into a private structural conversion plus the existing graph-validation wrapper; no duplicate model conversion logic.

**Focused verification:** `tests.test_molecular_record_staging`, Reader API registry/bridge modules.

**Compatibility verification:** Existing built-ins without records follow the same staged graph validation and produce identical scientific entities.

**Commit boundary:** Gate implementation commit.

**Stop boundary:** Never export the unchecked helper from `ChemBlender.reader_api.__all__`.

---

### Task 4: Complete SourceRevision and ParserReport entity accounting

**Files:**
- Modify: `ChemBlender/core/import_pipeline/parse.py`
- Modify: `ChemBlender/core/import_pipeline/transaction.py`
- Modify: `ChemBlender/core/import_pipeline/grouping.py`
- Modify: `ChemBlender/reader_api/import_pipeline_bridge.py`
- Modify: `ChemBlender/reader_api/conformance.py`
- Modify: `worker/reader_operation.py`
- Test: `tests/test_molecular_record_staging.py`
- Test: `tests/test_project_transaction.py`
- Test: `tests/test_reader_api_import_bridge.py`

**Current failure:** Several duplicated entity-group inventories omit `molecular_records`; the bridge scientific inventory also omits `topologies`.

**Target invariant:** Records and topologies participate in created-ID accounting, supplied-identity validation, report equality, conflict/remap/merge paths, conformance and worker success detection.

**Interfaces:**
- `_ENTITY_GROUPS` includes `molecular_records`.
- `_SCIENTIFIC_GROUPS` includes `topologies` and `molecular_records`.
- `_BATCH_ENTITY_FIELDS` includes `molecular_records`.

- [ ] **Step 1: Add RED accounting tests**

Assert exact `SourceRevision.created_entity_ids`, exact `ParserReport.created_entity_ids`, record remapping/merge visibility and invalid result rejection before preview registration.

- [ ] **Step 2: Update only active inventories**

Add the missing group names in existing canonical order. Do not introduce a new shared registry abstraction in this Gate.

- [ ] **Step 3: Run transaction and bridge tests**

```powershell
& $pythonBin -m unittest tests.test_molecular_record_staging tests.test_project_transaction tests.test_reader_api_import_bridge -v
```

**Minimal implementation:** Extend the existing tuples; no registry refactor.

**Focused verification:** Created/report ID exactness and atomic failure.

**Compatibility verification:** Existing entity order is preserved; old batches without records are unchanged.

**Commit boundary:** Gate implementation commit.

**Stop boundary:** Do not start conformer grouping behavior.

---

### Task 5: Harden MolecularRecord source-local identity

**Files:**
- Modify: `ChemBlender/core/model/records.py`
- Modify: `ChemBlender/core/model/project.py`
- Test: `tests/test_chemical_identity_records.py`

**Current failure:** `block_version` accepts arbitrary text, and record key/index uniqueness is not checked per source revision.

**Target invariant:** `block_version` is `V2000`, `V3000` or `None`; `(source_revision_id, record_key)` and `(source_revision_id, source_record_index)` are unique in the final project graph.

- [ ] **Step 1: Write RED model/graph tests**

Cover invalid block version, duplicates within one revision, the same key/index in different revisions, and zero project mutation on failure.

- [ ] **Step 2: Implement model and final-graph checks**

Reject invalid block versions in `MolecularRecord.__post_init__()`. In `QCProject.commit()`, build source-local key/index sets from existing plus incoming records before mutation.

- [ ] **Step 3: Run focused tests**

```powershell
& $pythonBin -m unittest tests.test_chemical_identity_records tests.test_project_graph_integrity -v
```

**Minimal implementation:** Two set-based uniqueness checks at the shared project commit boundary.

**Compatibility verification:** Raw bytes and ordered duplicate SD properties are unchanged.

**Commit boundary:** Gate implementation commit.

**Stop boundary:** Do not parse record properties.

---

### Task 6: Harden RecordPropertyColumn and ConformerSet

**Files:**
- Modify: `ChemBlender/core/model/records.py`
- Modify: `ChemBlender/core/model/project.py`
- Test: `tests/test_chemical_identity_records.py`
- Test: `tests/test_sidecar_storage.py`

**Current failure:** Complex columns are accepted; finite-value checks are missing; conformer role/domain/key alignment is incomplete.

**Target invariant:** Record columns accept only bool, signed/unsigned integer and floating dtype. Valid numeric positions are finite. Conformer coordinates are finite real values with `semantic_role="coordinates"` and `domain="conformer"`, and each `record_key` equals the paired record's key.

- [ ] **Step 1: Write RED tests**

Cover complex/object/structured/subarray rejection, Complete non-finite rejection, Partial mask-true non-finite rejection, mask-false sentinel tolerance, conformer role/domain failures, non-finite coordinates, key mismatch and independent-Structure records.

- [ ] **Step 2: Implement no-copy finite checks**

Use NumPy views/masks without constructing nested Python values. Preserve lazy sidecar behavior by restoring an initially unopened `LazyNpyArray` after validation rather than retaining a loaded mapping.

- [ ] **Step 3: Validate paired record keys in QCProject**

Resolve `record_ids` in order and compare the resulting keys exactly before project mutation.

- [ ] **Step 4: Run focused and sidecar tests**

Run chemical identity, project graph and sidecar lazy-array modules.

**Minimal implementation:** Tighten the current dataclass checks and add one ordered key comparison in the existing `ConformerSet` graph branch.

**Compatibility verification:** Existing lazy round-trip remains closable and no scientific array is copied.

**Commit boundary:** Gate implementation commit.

**Stop boundary:** Do not infer typed SDF columns.

---

### Task 7: Preserve sidecar and canonical compatibility

**Files:**
- Test: `tests/test_sidecar_storage.py`
- Test: `tests/test_public_import_batch.py`
- Test: `tests/test_reader_canonical_document.py`
- Test: `tests/test_chemical_identity_records.py`

**Current failure:** None expected; this task guards against accidental schema/API expansion.

**Target invariant:** Sidecar/project remain 0.2; Reader API/canonical remain 0.1; old alpha.1 and old canonical documents remain readable; unknown fields/types remain rejected.

- [ ] **Step 1: Run compatibility modules**

```powershell
& $pythonBin -m unittest tests.test_sidecar_storage tests.test_public_import_batch tests.test_reader_canonical_document -v
```

- [ ] **Step 2: Verify optional imports**

Start fresh interpreters and assert `ChemBlender.core` and `ChemBlender.reader_api` do not load `rdkit`, `bpy`, `ase`, `cclib` or `pymatgen`.

- [ ] **Step 3: Verify fixture hashes**

Run existing fixture/hash assertions without rewriting fixtures.

**Minimal implementation:** Tests only unless a regression is found.

**Compatibility verification:** Exact existing fixture/canonical hashes.

**Commit boundary:** Gate implementation commit if tests require additions.

**Stop boundary:** No version bump.

---

### Task 8: Full and Blender verification

**Files:**
- Modify if responsibility changes: `.agents/reference/code-architecture-guide.md`
- Test: `tests/blender_smoke.py`

**Current failure:** Local review evidence does not cover the new binding path.

**Target invariant:** Focused/full suites, Blender bundled-Python tests, extension package and real lifecycle all pass without importing RDKit in pure-core paths.

- [ ] **Step 1: Run the required focused matrix**

Run the exact modules named in the approved Gate prompt, including `tests.test_molecular_record_staging`.

- [ ] **Step 2: Run full static verification**

```powershell
& $pythonBin -m unittest discover -s tests -p "test_*.py" -v
& $pythonBin -m compileall -q ChemBlender worker tests
git diff --check
git status --short
```

- [ ] **Step 3: Run Blender 5.1.2 validation**

Run native validate/build, ZIP audit, isolated install/register/unregister/reload and existing XYZ/extXYZ/Cube Quick Import smoke.

**Minimal implementation:** Reuse existing scripts and smoke harness.

**Compatibility verification:** RDKit-specific behavior remains unstarted; Remote CI is recorded `Not Run`.

**Commit boundary:** No verification-only runtime commit.

**Stop boundary:** Do not begin RDKit Task 2 if any Gate verification fails.

---

### Task 9: Independent review and checkpoint

**Files:**
- Modify: `.agents/active/2.3.0-wave-1-native-molecular-and-grid.md`
- Modify: this plan

**Current failure:** The reviewed baseline contains the Gate defects.

**Target invariant:** Separate specification and code-quality reviews report no unresolved Critical, Important or Gate-related Minor findings.

- [ ] **Step 1: Commit the implementation**

```powershell
git add `
  ChemBlender/core/import_pipeline/grouping.py `
  ChemBlender/core/import_pipeline/parse.py `
  ChemBlender/core/import_pipeline/transaction.py `
  ChemBlender/core/model/project.py `
  ChemBlender/core/model/records.py `
  ChemBlender/reader_api/builtin_bridge.py `
  ChemBlender/reader_api/conformance.py `
  ChemBlender/reader_api/import_pipeline_bridge.py `
  ChemBlender/reader_api/protocol.py `
  ChemBlender/reader_api/registry.py `
  worker/reader_operation.py `
  tests/test_chemical_identity_records.py `
  tests/test_molecular_record_staging.py `
  tests/test_project_transaction.py `
  tests/test_reader_api_import_bridge.py `
  tests/test_reader_api_registry.py
git commit -m "fix: bind molecular records to staged source revisions"
```

- [ ] **Step 2: Run two independent reviews**

Review the planning baseline through implementation HEAD. Fix findings in dedicated review-fix commits and rerun affected/full verification.

- [ ] **Step 3: Record completion evidence**

Record planning/implementation/review SHAs, RED/GREEN counts, Blender result, `Remote CI: Not Run`, and Task 2 as the next task.

- [ ] **Step 4: Commit checkpoint**

```powershell
git add .agents/active/2.3.0-wave-1-native-molecular-and-grid.md docs/superpowers/plans/2026-07-28-chemblender-2.3.0-wave-1-rdkit-pre-adapter-binding-gate.md
git commit -m "chore: checkpoint RDKit source-binding gate"
```

**Minimal implementation:** Evidence-only checkpoint.

**Focused verification:** `git diff --check` and clean worktree after checkpoint.

**Compatibility verification:** No push and RDKit Task 2 unstarted at the Gate checkpoint.

**Commit boundary:** Final Gate checkpoint commit.

**Stop boundary:** The Gate must be completed before the separate Tasks 2–8 master plan begins.
