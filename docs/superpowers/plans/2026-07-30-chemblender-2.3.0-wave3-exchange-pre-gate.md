# ChemBlender 2.3.0 Wave 3 Exchange Pre-Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze the native exchange-data boundary for MOL2, PDB, PQR and CJSON before any Wave 3 reader is implemented.

**Architecture:** Reuse `Structure`, `TopologyRecord`, `FrameSet`, `PropertyDataset`, `CategoricalData` and existing provenance. Add only the missing scalar annotation, external-reference and biological-hierarchy entities. These entities participate in the existing project transaction, sidecar and Reader API flows; no third-party parser object or format-specific structure class enters the core model.

**Tech Stack:** Python 3.13, NumPy, standard-library `dataclasses` and `unittest`, existing sidecar/canonical infrastructure, Blender 5.1.2 Extensions.

## Global Constraints

- Baseline is `c5fd3be27f8570a247d0b5e4e145a939b0e0dcbf`.
- Preserve sidecar schema `1.0` and Reader API `1.0-rc1`.
- Do not implement MOL2, PDB, PQR or CJSON readers, exporters or UI.
- Do not add Open Babel, Biopython or any other dependency.
- Do not modify manifest version, workflows, tags or releases.
- Do not push without explicit authorization.

---

### Task 1: Activate Wave 3 and persist the gate

**Files:**
- Create: `docs/superpowers/plans/2026-07-30-chemblender-2.3.0-wave3-exchange-pre-gate.md`
- Move: `.agents/active/2.3.0-wave-2-native-crystal.md` → `.agents/completed/2.3.0-wave-2-native-crystal.md`
- Move: `.agents/queued/2.3.0-wave-3-exchange-mol2-pdb-pqr.md` → `.agents/active/2.3.0-wave-3-exchange-mol2-pdb-pqr.md`
- Modify: `.agents/README.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Interfaces:** The active cursor is the single recovery authority. Wave 2 becomes immutable completion evidence; Wave 4 remains queued.

- [x] Record branch, worktree, baseline, design commit, required subgoals, stop boundary and `Remote CI: Not Run`.
- [x] Update the documentation contract so exactly Wave 3 is active.
- [x] Run `tests.test_quantum_visualization_docs`, `git diff --check` and commit `docs: start Wave 3 exchange pre-gate`.

### Task 2: Add the minimal exchange model contracts

**Files:**
- Create: `ChemBlender/core/model/exchange.py`
- Modify: `ChemBlender/core/model/__init__.py`
- Modify: `ChemBlender/core/model_registry.py`
- Modify: `ChemBlender/core/__init__.py`
- Create: `tests/test_exchange_models.py`
- Modify: `tests/test_model_registry.py`
- Modify: `tests/test_model_public_surface.py`
- Modify: `tests/test_core_public_api.py`

**Interfaces:** Add immutable `ChemicalAnnotation`, `ExternalReference`, `BiologicalModel`, `BiologicalChain`, `BiologicalResidue`, `BiologicalAtomSiteData` and `BiologicalHierarchy`.

- [x] **RED:** prove the model classes are absent, then specify exact validation for scalar values, identifiers, hierarchy indexes and atom-aligned arrays.
- [x] Implement the smallest frozen dataclasses by reusing existing model validators, `ArrayData` and `CategoricalData`.
- [x] Reject mutable/nested annotation values, invalid confidence, duplicate hierarchy keys and inconsistent atom-site array lengths.
- [x] Export only the native types; import no optional parser dependency.
- [x] Run the focused model/public-surface tests and commit `feat: add exchange data contracts`.

### Task 3: Integrate exchange entities into project transactions

**Files:**
- Modify: `ChemBlender/core/model/project.py`
- Modify: `ChemBlender/core/import_pipeline/parse.py`
- Modify: `ChemBlender/core/import_pipeline/grouping.py`
- Modify: `ChemBlender/core/import_pipeline/transaction.py`
- Modify: `ChemBlender/reader_api/builtin_bridge.py`
- Modify: `ChemBlender/reader_api/conformance.py`
- Modify: `ChemBlender/reader_api/import_pipeline_bridge.py`
- Modify: `worker/reader_operation.py`
- Modify only additional existing static entity-group lists found by repository search.
- Create: `tests/test_exchange_project_contract.py`
- Modify relevant import-pipeline and worker protocol tests.

**Interfaces:** `ImportBatch` and `QCProject` gain `biological_hierarchies`, `annotations` and `external_references`. Existing all-or-nothing commit semantics remain authoritative.

- [x] **RED:** cover valid commit, missing target/provenance, duplicate `(target, namespace, key)`, duplicate external identity, duplicate hierarchy per Structure, atom-count mismatch and transaction rollback.
- [x] Add the three registries once to each existing generic entity-group pipeline.
- [x] Keep annotations/references pointed at pre-existing scientific/source entities; prevent self-referential metadata graphs.
- [x] Preserve created-entity reporting, grouping, worker payload and project-graph revalidation behavior.
- [x] Run focused transaction/worker tests and commit `feat: integrate exchange project entities`.

### Task 4: Persist and publish the frozen boundary

**Files:**
- Modify: `ChemBlender/core/sidecar_migrations.py`
- Modify: `ChemBlender/core/sidecar_migrations.py`
- Modify: `ChemBlender/reader_api/public_model.py`
- Modify: `ChemBlender/reader_api/__init__.py`
- Modify: `ChemBlender/reader_api/canonical_document.py`
- Modify: `tests/fixtures/reader-api/public-schema-v1-rc1.json`
- Modify: `tests/fixtures/reader-api/public-schema-v1-rc1.sha256`
- Create: `tests/test_exchange_persistence.py`
- Modify relevant sidecar, canonical and Reader API tests.

**Interfaces:** New entity groups round-trip through sidecar schema `1.0`, canonical documents and `PublicImportBatch`; legacy documents default all new groups to empty.

- [x] **RED:** cover model codec, sidecar save/open, canonical round-trip, legacy missing-group defaults, public batch conversion and deterministic schema snapshot.
- [x] Register the exact types and three groups in existing codecs and bridges; do not create a second serializer.
- [x] Regenerate the locked Reader API snapshot and SHA deterministically while keeping `1.0-rc1`.
- [x] Prove cold imports of `ChemBlender.core` and `ChemBlender.reader_api` do not load Open Babel, Biopython, RDKit, Gemmi or spglib.
- [x] Run focused persistence/API tests and commit `feat: persist exchange reader contracts`.

### Task 5: Freeze format mapping policy and checkpoint

**Files:**
- Create: `.agents/decisions/0043-wave3-exchange-data-boundary.md`
- Modify: `.agents/README.md`
- Modify: `.agents/reference/code-architecture-guide.md`
- Modify: `docs/superpowers/plans/2026-07-23-chemblender-2.3.0-wave-3-mol2.md`
- Modify: `docs/superpowers/plans/2026-07-23-chemblender-2.3.0-wave-3-pdb-pqr.md`
- Modify: `docs/superpowers/plans/2026-07-23-chemblender-2.3.0-wave-3-cjson-reader-plugin-v1.md`
- Modify: `tests/test_quantum_visualization_docs.py`
- Modify: `.agents/active/2.3.0-wave-3-exchange-mol2-pdb-pqr.md`

**Interfaces:** ADR 0043 fixes MOL2 annotation/property mapping, PDB hierarchy/frame/topology mapping, PQR charge/radius datasets and CJSON whitelist/envelope policy.

- [x] **RED:** add documentation contracts for the ADR, architecture inventory and downstream-plan references.
- [x] Document the approved mappings without implementing format code.
- [ ] Run focused tests, then the full suite, `compileall` and `git diff --check`.
- [ ] Run Blender 5.1.2 native validate/build and ZIP safe-path/duplicate/CRC/wheel audit.
- [ ] Perform separate specification-compliance and code-quality review passes; fix all in-scope findings and rerun affected verification.
- [ ] Mark the gate completed, record exact RED/GREEN/Blender evidence and next task `Wave 3 Task 1 — MOL2 adapter`.
- [ ] Commit documentation as `docs: freeze Wave 3 exchange mappings`, then commit the final cursor/plan as `chore: checkpoint exchange pre gate`.
- [ ] Stop with a clean worktree; no reader implementation and no push.
