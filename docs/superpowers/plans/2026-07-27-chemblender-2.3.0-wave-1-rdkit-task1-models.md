# ChemBlender 2.3.0 Wave 1 RDKit Task 1 Models Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add immutable atom identity, molecular record, typed record-column and conformer-set models, integrate them into the project graph, sidecar v0.2 and Reader API/canonical v0.1 without importing RDKit or starting any reader.

**Architecture:** Reuse `ArrayData`, `CategoricalData`, `PropertyDataset`, `DatasetStatus`, `ImportBatch`, `QCProject` and the existing strict tagged encoders. `MolecularRecord` gets one new top-level project registry; `RecordPropertyColumn` and `ConformerSet` remain dataset-like entities. Compatibility is bounded to two known additive fields and is applied to an in-memory copy only after the original sidecar/canonical envelope has passed its existing integrity checks.

**Tech Stack:** Python 3.13 standard library, Blender-bundled NumPy 2.3.4, dataclasses, existing `.cbq` v0.2 and Reader API canonical v0.1, `unittest`.

## Global Constraints

- Do not import or call RDKit and do not create MOL/SDF/SMILES readers, exporters, grouping, UI or Cube runtime.
- Do not change `manifest_version`, `project_schema_version`, `READER_API_VERSION`, canonical document schema version, manifest version, CHANGELOG, workflow, tag or Release.
- Do not add or upgrade dependencies.
- Preserve strict unknown-field/type/enum rejection and exact original manifest/canonical hashing.
- Preserve the exact alpha.1 sidecar fixture and canonical artifact/hash rules.
- Keep `ChemBlender.core` and `ChemBlender.reader_api` importable without `bpy`, `rdkit`, `ase`, `cclib` or `pymatgen`.
- Complete only RDKit parent-plan Task 1; Task 2 remains unstarted.

---

### Task 1: Atomic identity value model

**Files:**
- Create: `ChemBlender/core/model/chemical_identity.py`
- Modify: `ChemBlender/core/model/structure.py`
- Test: `tests/test_chemical_identity_records.py`

**Existing contracts reused:**
- `ArrayData` shape/dims/unit metadata and immutable dataclass pattern.
- `CategoricalData` integer codes, unique categories and explicit `missing_code`.

**New interfaces:**
- `AtomicIdentityData(isotopes, formal_charges, atom_map_numbers, atom_names, stereo_labels)`.
- `Structure.atomic_identity: AtomicIdentityData | None = None`.

- [ ] **Step 1: Write the RED tests**

Cover a complete identity; wrong dims; inconsistent atom axes; float isotope; bool formal charge; negative isotope/map; categorical shape mismatch; object dtype rejection; `Structure` atom-count mismatch; and an unchanged `Structure` without identity.

**Expected RED:** `ImportError` for `AtomicIdentityData` and missing `Structure.atomic_identity`.

- [ ] **Step 2: Run RED**

Run:

```powershell
& $pythonBin -m unittest tests.test_chemical_identity_records -v
```

Expected: non-zero exit caused only by the missing Task 1 model.

- [ ] **Step 3: Implement minimally**

Use one frozen, slotted dataclass. Require all five values to be `ArrayData`/`CategoricalData`, exact `("atom",)` dims, one shared positive-or-zero atom axis, `"dimensionless"` units, integer non-bool isotope/charge/map arrays, non-negative isotope/map values and no object dtype. Append the optional field to `Structure` and compare its atom count with `atomic_numbers`.

- [ ] **Step 4: Verify focused behavior**

Run the Task 1 tests and existing structure/model tests.

**Compatibility verification:** Existing positional and keyword `Structure` construction remains valid because the field is last and defaults to `None`.

**Commit boundary:** Include in `feat: add molecular identity and record models`.

**Stop boundary:** Do not add RDKit molecule conversion.

---

### Task 2: Molecular record and ordered raw property model

**Files:**
- Create: `ChemBlender/core/model/records.py`
- Test: `tests/test_chemical_identity_records.py`

**Existing contracts reused:**
- UUID/text validators from `core.model.common`.
- Frozen, slotted ID-bearing project entities.

**New interfaces:**
- `RawRecordProperty(name: str, value: str)`.
- `MolecularRecord(id, revision, source_revision_id, record_key, structure_id, topology_id, raw_block, title, source_record_index, block_version, writer_name, writer_version, ordered_raw_properties, provenance_ids)`.

- [ ] **Step 1: Write the RED tests**

Cover exact CRLF/LF bytes, empty title/value, duplicate ordered property names, tuple normalization, invalid record index including bool, empty record key, optional topology, writer metadata types and immutable order.

**Expected RED:** imports fail because `RawRecordProperty` and `MolecularRecord` do not exist.

- [ ] **Step 2: Run RED**

Run the single new test module and retain the expected failure summary.

- [ ] **Step 3: Implement minimally**

Keep `raw_block` as one exact `bytes` field. Normalize only sequence containers to tuples; never decode, normalize or deduplicate properties. Accept `block_version` as `str | None`, with current producers expected to use `V2000` or `V3000`; this Task does not infer it.

- [ ] **Step 4: Verify focused behavior**

Run raw-evidence and immutability tests.

**Compatibility verification:** No reader or exporter is added and no RDKit object can enter either dataclass.

**Commit boundary:** Same Task 1 implementation commit.

**Stop boundary:** Do not parse SDF properties or infer typed columns.

---

### Task 3: Typed record property columns

**Files:**
- Modify: `ChemBlender/core/model/records.py`
- Test: `tests/test_chemical_identity_records.py`

**Existing contracts reused:**
- `PropertyDataset`, `ArrayData`, `CategoricalData`, `DatasetStatus`.
- Frame-property mask rules as the closest established pattern.

**New interfaces:**
- `RecordPropertyColumn(PropertyDataset)` with `record_ids: tuple[UUID, ...]` and `validity_mask: ArrayData | None = None`.

- [ ] **Step 1: Write the RED tests**

Cover complete numeric; partial numeric with/without mask; complete numeric with mask; categorical missing codes; categorical redundant mask; complete categorical missing code; duplicate/non-UUID record IDs; data length mismatch and wrong domain/dims.

**Expected RED:** missing `RecordPropertyColumn`.

- [ ] **Step 2: Run RED**

Run the new test module and confirm contract failures are model failures, not fixture errors.

- [ ] **Step 3: Implement minimally**

Call `PropertyDataset.__post_init__()`, require `domain == "record"`, leading `("record",)`, unique UUID tuple matching the first data axis. Complete numeric/logical forbids a mask; partial numeric/logical requires an exact dimensionless bool `("record",)` mask; categorical uses only `missing_code`, forbids a mask and forbids missing codes when Complete.

- [ ] **Step 4: Verify focused behavior**

Run record-column and existing frame-property tests.

**Compatibility verification:** Raw record properties remain unchanged; typed columns are additive datasets.

**Commit boundary:** Same Task 1 implementation commit.

**Stop boundary:** Do not add SDF type inference.

---

### Task 4: ConformerSet structural model

**Files:**
- Modify: `ChemBlender/core/model/records.py`
- Test: `tests/test_chemical_identity_records.py`

**Existing contracts reused:**
- `PropertyDataset` dataset identity/status/provenance fields.
- `FrameSet` coordinate validation style.

**New interfaces:**
- `ConformerSet(PropertyDataset)` with `reference_structure_id`, optional `reference_topology_id`, ordered unique `record_ids`/`record_keys` and `atom_mappings`.

- [ ] **Step 1: Write the RED tests**

Cover valid coordinates and mappings; wrong dims/unit; zero axes; bool mappings; duplicate/missing/out-of-range mapping entries; duplicate record ID/key and length mismatches.

**Expected RED:** missing `ConformerSet`.

- [ ] **Step 2: Run RED**

Run the new test module and retain the expected missing-model failure.

- [ ] **Step 3: Implement minimally**

Require coordinates `("conformer","atom","xyz")`, positive axes, xyz length 3 and a known dimensional length unit. Require integer non-bool mappings with exact `("conformer","atom")` shape and each row equal to a permutation of `range(atom_count)`. Normalize record IDs/keys to tuples and require unique values matching conformer count.

- [ ] **Step 4: Verify focused behavior**

Run permutation, identity and dataset base-contract tests.

**Compatibility verification:** This model accepts already-normalized conformer data only and stores no suggestion or RDKit object.

**Commit boundary:** Same Task 1 implementation commit.

**Stop boundary:** Do not implement conformer grouping.

---

### Task 5: Project registry and graph validation

**Files:**
- Modify: `ChemBlender/core/model/project.py`
- Modify: `ChemBlender/core/model/__init__.py`
- Test: `tests/test_chemical_identity_records.py`
- Modify: `tests/test_project_graph_integrity.py`

**Existing contracts reused:**
- `ImportBatch` tuple groups.
- `QCProject.commit()` pre-mutation final-graph validation.
- One global UUID namespace and `validate_project_graph()`.

**New interfaces:**
- `ImportBatch.molecular_records: tuple[MolecularRecord, ...] = ()`.
- `QCProject.molecular_records: dict[UUID, MolecularRecord]`.

- [ ] **Step 1: Write the RED tests**

Cover empty registry, successful record commit, cross-registry duplicate UUID, dangling source revision/structure/topology/provenance, topology owned by another structure, dangling record-column/conformer record IDs, conformer structure/topology/atom/unit mismatch, `SourceRevision.created_entity_ids`, and zero mutation after each failure.

**Expected RED:** constructor/commit reject unknown new fields or omit required graph checks.

- [ ] **Step 2: Run RED**

Run `tests.test_chemical_identity_records` and `tests.test_project_graph_integrity`.

- [ ] **Step 3: Implement minimally**

Add exactly one registry. Include it in incoming entity groups, final IDs, mutation, `_all_entity_ids`, registry validation and graph reconstruction. Validate each record against the final source/structure/topology/provenance graph before any mutation. Validate record datasets against final records; validate conformer references, atom count and coordinate unit against their reference structure/topology.

- [ ] **Step 4: Verify focused behavior**

Run project transaction, graph integrity and source model tests.

**Compatibility verification:** Existing registries and report ID equality retain their current order/semantics; new record IDs are ordinary created entities.

**Commit boundary:** Same Task 1 implementation commit.

**Stop boundary:** Do not add additional top-level registries for columns/conformers.

---

### Task 6: Sidecar alpha.1 compatibility migration

**Files:**
- Modify: `ChemBlender/core/model_registry.py`
- Modify: `ChemBlender/core/sidecar_migrations.py`
- Modify: `tests/test_sidecar_storage.py`
- Test: `tests/test_chemical_identity_records.py`

**Existing contracts reused:**
- Strict tagged `_Encoder`/`_Decoder`.
- `migrate_manifest()` post-hash, in-memory `deepcopy` path.
- Existing bounded current-v0.2 topology migration.

**New interfaces:**
- Model tags for `AtomicIdentityData`, `RawRecordProperty`, `MolecularRecord`, `RecordPropertyColumn`, `ConformerSet`.
- Current-v0.2 additive defaults only for missing `QCProject.molecular_records` and `Structure.atomic_identity`.

- [ ] **Step 1: Write the RED tests**

Cover save/open of every new model; exact raw bytes and duplicate properties; lazy conformer arrays; synthetic pre-Task1 current-v0.2 missing both fields; malformed existing fields; unknown future field/type; unchanged alpha.1 fixture/hash.

**Expected RED:** strict decoder reports invalid fields/model tags and old v0.2 documents fail due to the new exact dataclass field set.

- [ ] **Step 2: Run RED**

Run new tests plus sidecar storage and model registry.

- [ ] **Step 3: Implement minimally**

Register the five exact types. In `migrate_manifest()`, only when the source is a valid current-v0.2 `QCProject`, deep-copy and inject encoded empty `molecular_records` and `atomic_identity=None` where absent. Never overwrite a present field, never delete unknown fields, and leave original document/hash bytes untouched.

- [ ] **Step 4: Verify focused behavior**

Run sidecar/model registry tests and explicitly close reopened lazy arrays.

**Compatibility verification:** Alpha.1 fixture bytes and expected hash stay unchanged; schema versions remain `0.2`.

**Commit boundary:** Same Task 1 implementation commit.

**Stop boundary:** Stop and report if bounded additive migration cannot preserve strict unknown-field rejection.

---

### Task 7: Reader API and canonical-document additive compatibility

**Files:**
- Modify: `ChemBlender/reader_api/public_model.py`
- Modify: `ChemBlender/reader_api/builtin_bridge.py`
- Modify: `ChemBlender/reader_api/canonical_document.py`
- Modify: `ChemBlender/reader_api/__init__.py`
- Modify: `tests/test_public_import_batch.py`
- Modify: `tests/test_reader_canonical_document.py`

**Existing contracts reused:**
- Exact public type allowlist and immutable recursive value validation.
- `_BATCH_FIELDS` internal/public bridge.
- Strict canonical type/enum registries and canonical JSON/artifact hashes.

**New interfaces:**
- Public exports for all five new model types.
- `PublicImportBatch.molecular_records: tuple[MolecularRecord, ...] = ()`.

- [ ] **Step 1: Write the RED tests**

Cover exact public names, molecular-record group acceptance, internal/public/internal round-trip, dataset subclasses, mutable/RDKit-like object rejection, new canonical round-trip, and old canonical v0.1 documents missing only the two approved additive fields.

**Expected RED:** missing public types/group/bridge field/type tags and strict decoder field mismatches.

- [ ] **Step 2: Run RED**

Run public batch and canonical tests.

- [ ] **Step 3: Implement minimally**

Extend explicit imports, `_GROUP_TYPES`, `_PUBLIC_MODEL_TYPES`, `_BATCH_FIELDS` and canonical `_TYPE_NAMES`. Before canonical model decode, apply a narrow in-memory compatibility projection only to `PublicImportBatch.molecular_records` and nested `Structure.atomic_identity`; keep every other exact-field check unchanged.

- [ ] **Step 4: Verify focused behavior**

Run public batch, bridge, canonical bundle and worker-reader bundle tests.

**Compatibility verification:** Do not change `READER_API_VERSION` or `_SCHEMA_VERSION`; old canonical 0.1 artifact hashes remain validated before decoding.

**Commit boundary:** Same Task 1 implementation commit.

**Stop boundary:** Stop for an ADR decision if strict bounded compatibility proves impossible.

---

### Task 8: Public API and documentation contract

**Files:**
- Modify: `ChemBlender/core/__init__.py`
- Modify: `tests/test_model_modules.py`
- Modify: `tests/test_model_public_surface.py`
- Modify: `tests/test_model_registry.py`
- Modify: `tests/test_core_public_api.py`
- Modify: `docs/quantum-visualization/2.3.0/public-core-api.md`
- Modify: `.agents/reference/code-architecture-guide.md`
- Modify: `tests/test_quantum_visualization_docs.py`

**Existing contracts reused:**
- Exact `core.__all__`, Reader API `__all__`, model origins and architecture inventory tests.

**New interfaces:**
- `AtomicIdentityData`, `RawRecordProperty`, `MolecularRecord`, `RecordPropertyColumn`, `ConformerSet` from `ChemBlender.core` and `ChemBlender.reader_api`.

- [ ] **Step 1: Write the RED tests**

Add the five names to exact public/model/module-origin expectations and optional-stack import isolation.

**Expected RED:** exact public surfaces and architecture inventory differ.

- [ ] **Step 2: Run RED**

Run model/public/document contract tests.

- [ ] **Step 3: Implement minimally**

Re-export the exact types without importing RDKit. Document only implemented model/storage/Reader API responsibilities and explicitly state that RDKit is not a project model and readers/grouping/export/UI are not yet implemented.

- [ ] **Step 4: Verify focused behavior**

Run all public-surface and documentation tests.

**Compatibility verification:** Pure imports leave `bpy`, `rdkit`, `ase`, `cclib` and `pymatgen` absent from `sys.modules`.

**Commit boundary:** Same Task 1 implementation commit.

**Stop boundary:** No UI or format capability documentation.

---

### Task 9: Full verification and checkpoint

**Files:**
- Modify: `.agents/active/2.3.0-wave-1-native-molecular-and-grid.md`
- Modify: this plan only to record evidence/check completion.

**Existing contracts reused:**
- Repository verification commands and Blender bundled-Python baseline.

**New interfaces:** None.

- [ ] **Step 1: Run focused verification**

Run the exact focused modules named in the goal, adjusted only for files that truly exist.

**Expected RED:** Not applicable; implementation must already be green.

- [ ] **Step 2: Run compatibility verification**

Run alpha.1 sidecar, canonical 0.1, optional-stack isolation and Blender bundled-Python model/sidecar/Reader API tests.

- [ ] **Step 3: Run full verification**

Run full `unittest`, `compileall`, `git diff --check` and inspect `git status --short`. Run extension validate/build/ZIP/lifecycle only if package contract is affected.

- [ ] **Step 4: Independent review**

Run separate specification-compliance and code-quality reviews over `e00ee4039dea6b7497c80a98611e32446300e592..HEAD`; fix every Critical, Important and Task-related Minor finding and repeat verification.

- [ ] **Step 5: Commit**

Commit implementation as `feat: add molecular identity and record models`, then update cursor evidence and commit `chore: checkpoint RDKit molecular models`.

**Focused verification:** New model/project/sidecar/public/canonical suites all pass.

**Compatibility verification:** Versions/hashes unchanged; Remote CI recorded `Not Run`.

**Commit boundary:** Final checkpoint commit only contains cursor/plan evidence.

**Stop boundary:** Stop with RDKit Task 2 unchecked and do not push.
