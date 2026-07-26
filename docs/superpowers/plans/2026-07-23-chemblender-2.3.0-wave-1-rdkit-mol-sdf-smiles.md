# ChemBlender 2.3.0 Wave 1 RDKit MOL, SDF and SMILES Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build complete base-package readers and exporters for MOL V2000/V3000, multi-record SDF and SMILES using the bundled RDKit while preserving raw records, topology, charges, stereo and recovery state.

**Architecture:** RDKit is a parser/chemistry backend, not the project model. Reader adapters convert RDKit molecules and raw blocks into Structure, AtomicIdentity, TopologyRecord, record properties and ConformerSet. Each SDF record has an independent identity and diagnostic outcome.

**Tech Stack:** RDKit 2026.3.3, Python 3.13, existing import pipeline and sidecar, `unittest`.

## Global Constraints

- Do not use the legacy `read.py` path for new behavior.
- Do not silently sanitize or discard records.
- Preserve raw source block/envelope and writer version.
- 3D SMILES embedding is a derived operation with fixed seed and parameters.
- SDF record order and raw property strings survive round-trip where representable.
- Fix the existing V3000 bond ID defect with a regression test.

---

### Task 1: Add atom identity, record and property table models

**Files:**
- Create: `ChemBlender/core/model/chemical_identity.py`
- Create: `ChemBlender/core/model/records.py`
- Modify: `ChemBlender/core/model/structure.py`
- Modify: `ChemBlender/core/model/project.py`
- Modify: `ChemBlender/core/model_registry.py`
- Create: `tests/test_chemical_identity_records.py`

**Interfaces:**
- Produces: `AtomicIdentityData`, `MolecularRecord`, `RecordPropertyColumn`, `ConformerSet`.

- [ ] **Step 1: Write atomic identity tests**

Require arrays or categorical values matching atom count for isotope, formal charge, atom map, atom name and stereo label. Formal charge is integer; isotope is non-negative integer.

- [ ] **Step 2: Write record property tests**

A MolecularRecord binds exactly one structure and optional topology, raw block bytes, title, source record index and ordered raw properties. A typed RecordPropertyColumn binds a record set and contains a validity mask.

- [ ] **Step 3: Write ConformerSet tests**

Coordinates have `(conformer,atom,xyz)`, topology identity matches the reference, atom mappings are integer permutations, and record keys are unique.

- [ ] **Step 4: Implement and commit**

Run model/sidecar/project tests and commit.

### Task 2: Implement a shared RDKit molecule adapter

**Files:**
- Create: `ChemBlender/core/formats/rdkit_common.py`
- Create: `tests/test_rdkit_common_adapter.py`

**Interfaces:**
- Produces: `adapt_rdkit_molecule(mol, raw_block, context) -> PublicImportBatchFragment`.

- [ ] **Step 1: Write a molecule fixture matrix**

Use embedded blocks for charged, isotopic, aromatic, chiral, unsanitized and no-conformer molecules. Assert atoms, coordinates, explicit bonds, bond orders, aromatic flags, formal charges, isotopes and stereo.

- [ ] **Step 2: Implement safe parsing modes**

Parse raw records with sanitization disabled first. Attempt sanitization on a copy. Store explicit-file topology regardless. If sanitization succeeds, store `rdkit_sanitized` topology only when it materially adds/changes interpretation. If it fails, create `mol.sanitize_failed` diagnostic.

- [ ] **Step 3: Handle coordinates**

A 3D conformer creates Structure coordinates. A 2D conformer is valid but marked as planar source; no automatic 3D optimization for MOL/SDF import. Missing conformer rejects Structure only when coordinates cannot be recovered.

- [ ] **Step 4: Run and commit**

Run with the pinned RDKit in Blender Python and commit.

### Task 3: Implement MOL V2000/V3000 reader

**Files:**
- Create: `ChemBlender/core/formats/mol.py`
- Modify: `ChemBlender/core/reader_catalog.py`
- Deprecate: `ChemBlender/core/mol_v2000.py` through a compatibility import
- Create: `tests/test_mol_reader.py`
- Create: `tests/fixtures/mol/README.md`
- Add: V2000/V3000 real writer fixtures.

**Interfaces:**
- Produces: reader ID `mol`, version `2`, capabilities structure/topology/atomic_identity.

- [ ] **Step 1: Write sniff tests**

V2000 and V3000 content both match exact; `.mol` ordinary text does not. SDF with `$$$$` is routed to SDF reader, not MOL.

- [ ] **Step 2: Implement block-version detection and adapter call**

Read bytes, decode with replacement diagnostic if needed, reject multiple SDF records in MOL reader, and call RDKit common adapter.

- [ ] **Step 3: Preserve old reader ID compatibility**

Explicit `reader_id="mol-v2000"` may resolve to a deprecated alias that calls the new reader for V2000 only and reports the replacement. Built-in catalog advertises `mol` as primary.

- [ ] **Step 4: Run and commit**

Run old/new tests and update capability matrix.

### Task 4: Implement multi-record SDF reader and record recovery

**Files:**
- Create: `ChemBlender/core/formats/sdf.py`
- Create: `tests/test_sdf_reader.py`
- Create: `tests/fixtures/sdf/README.md`
- Add: valid multi-record, malformed middle record and mixed-property fixtures.

**Interfaces:**
- Produces: reader ID `sdf`, record identities, raw/typed properties and staged grouping candidates.

- [ ] **Step 1: Write record recovery tests**

A three-record file with a malformed second record under Balanced Recovery yields two MolecularRecords, one Invalid record diagnostic, original indices 0 and 2, and an import summary showing one failed record.

- [ ] **Step 2: Use an RDKit supplier without silent skipping**

Retain record boundaries and raw blocks before RDKit parsing so a `None` supplier result can be tied to source record index and raw bytes/hash.

- [ ] **Step 3: Preserve SD properties**

Record property order is read from raw record. Store raw strings. Build typed bool/int/float columns only when parsing is unambiguous; mixed values remain categorical/string with diagnostics only when a requested numeric semantic cannot be established.

- [ ] **Step 4: Stage every record independently**

Each valid record receives a stable source-local key derived from source revision, record index and raw record hash. Do not merge in the reader.

- [ ] **Step 5: Run and commit**

Run reader, preview, sidecar and record tests.

### Task 5: Implement intelligent SDF conformer grouping

**Files:**
- Create: `ChemBlender/core/import_pipeline/conformer_grouping.py`
- Create: `tests/test_sdf_conformer_grouping.py`

**Interfaces:**
- Produces: `suggest_conformer_groups(records) -> tuple[ConformerGroupSuggestion, ...]` and confirmation conversion to ConformerSet.

- [ ] **Step 1: Write acceptance tests**

Records with same chemistry but reordered atoms group after deterministic atom mapping. Different bond order, formal charge or stereo do not group. Same atom count alone never groups.

- [ ] **Step 2: Implement matching precedence**

Use atom-map numbers if complete and unique. Otherwise use RDKit canonical ranks and substructure isomorphism, then verify exact topology, formal charges, isotopes and stereochemistry. Record the mapping and evidence.

- [ ] **Step 3: Build ConformerSet only on user acceptance**

Reorder coordinates into reference atom order, preserve record keys and property columns, and create provenance describing grouping evidence.

- [ ] **Step 4: Run and commit**

Run grouping and project validation tests.

### Task 6: Implement SMILES source and 3D derivation

**Files:**
- Create: `ChemBlender/core/formats/smiles.py`
- Create: `ChemBlender/core/derivations/smiles_3d.py`
- Create: `tests/test_smiles_reader.py`
- Create: `tests/test_smiles_3d.py`

**Interfaces:**
- Produces: `parse_smiles_text()`, `derive_smiles_3d()` and provenance parameters.

- [ ] **Step 1: Test source preservation**

Input isomeric SMILES produces a topology/identity entity, canonical SMILES and isomeric canonical SMILES. Invalid input returns blocking diagnostic without a Structure.

- [ ] **Step 2: Implement deterministic embedding**

Use ETKDGv3, fixed default seed `0xC0FFEE`, one thread for reproducibility, optional AddHs and UFF/MMFF choice as canonical parameters. Return a derived Structure only on success.

- [ ] **Step 3: Handle optimization failure**

Embedding success plus optimization failure retains coordinates with Partial derivation status and diagnostic. Embedding failure leaves the source/topology valid.

- [ ] **Step 4: Run and commit**

Run with bundled RDKit and commit.

### Task 7: Implement MOL/SDF/SMILES exporters and fix V3000

**Files:**
- Create: `ChemBlender/core/exporters/rdkit_molecular.py`
- Modify or deprecate: `ChemBlender/output.py` helper functions
- Create: `tests/test_rdkit_molecular_export.py`
- Create: `tests/test_molecular_roundtrip.py`

**Interfaces:**
- Produces: `export_mol()`, `export_sdf()`, `export_smiles()`.

- [ ] **Step 1: Add V3000 bond ID regression**

```python
def test_v3000_bond_ids_start_at_one(self):
    text = export_mol(self.structure, self.topology, version="V3000").text
    self.assertIn("M  V30 1 1 1 2", text)
    self.assertNotIn("M  V30 0 ", text)
```

- [ ] **Step 2: Build RDKit molecule from project entities**

Set atoms, isotopes, formal charges, maps, stereo and explicit bonds. Add conformer coordinates. Reject or diagnose topology concepts not representable by target format.

- [ ] **Step 3: SDF export**

Write records in selected original order and SD properties in original order. Derived conformers get deterministic new titles/record IDs without pretending to be original records.

- [ ] **Step 4: SMILES export**

Allow canonical and isomeric modes and report loss of coordinates/properties.

- [ ] **Step 5: Round-trip tests and commit**

Compare chemistry, coordinates within writer precision, charges, isotopes, stereo, record order and SD strings. Commit.

### Task 8: Add UI and remove silent legacy failure paths

**Files:**
- Modify: `ChemBlender/ui/quick_import.py`
- Modify: `ChemBlender/ui/import_preview.py`
- Modify: `ChemBlender/ui/project_browser/`
- Modify: `ChemBlender/read.py`
- Modify: `tests/blender_smoke.py`

**Interfaces:**
- Produces: record browsing, conformer confirmation, SMILES input through unified pipeline and explicit legacy errors.

- [ ] **Step 1: Add record/SD property browser rows**

Show record count, failed records, group suggestions and property columns. Default view uses first valid record or accepted first conformer group.

- [ ] **Step 2: Route legacy SMILES and File actions**

Legacy UI constructs ImportRequest. Do not call old `read_MOL` for migrated types.

- [ ] **Step 3: Make remaining unsupported legacy inputs explicit**

Until MOL2 Wave 3, old MOL2 input returns a controlled unsupported diagnostic rather than using an uninitialized `mol`. All RDKit parse `None` cases return user-visible errors.

- [ ] **Step 4: Blender smoke and performance**

Import V2000, V3000, multi-record SDF and SMILES; accept a conformer group; create/save/reopen views; export. Benchmark 10k-record indexing without creating 10k objects.

- [ ] **Step 5: Commit**

Commit UI/legacy bridge and tests.
