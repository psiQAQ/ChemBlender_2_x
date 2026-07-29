# ChemBlender 2.3.0 Wave 3 Native PDB and PQR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement atom-level complete PDB/PQR import with hierarchy metadata, altlocs, multiple models, explicit CONECT topology, CRYST1 cell and PQR charge/radius, without expanding into full structural-biology rendering.

**Architecture:** PDB uses fixed-column records; PQR uses validated whitespace dialects. Atom identity and hierarchy are typed categorical/integer data. Compatible MODEL records form FrameSet; incompatible models remain separate structures. CONECT topology takes precedence over inference.

**Tech Stack:** Python 3.13 standard library, NumPy, existing categorical/frame/topology/import/view systems, `unittest` and Blender smoke.

## Wave 3 Pre-Gate Binding

ADR 0043 is authoritative. PDB/PQR must reuse `BiologicalHierarchy`,
`AtomicIdentityData`, `AtomicProperty`, `FrameSet`, `TopologyRecord` and
`Structure`; do not create `BiologicalAtomData`, `ModelIdentity`,
`SegmentData` or a PDB-specific Structure.

## Global Constraints

- No Biotite, MDAnalysis or external package in the base path.
- Do not implement ribbon/cartoon, secondary structure or biological assembly.
- Do not silently merge altlocs.
- Do not infer elements without a diagnostic and preserved original atom name.
- MODEL compatibility uses atom identity, not atom count alone.
- PDB/PQR export remains P1, with readiness reporting.

---

### Task 1: Lock PDB/PQR mapping to the exchange contracts

**Files:**
- Create: `tests/test_biological_atom_data.py`
- Modify: `docs/quantum-visualization/reader-capability-matrix.json`

**Interfaces:**
- Consumes: `BiologicalHierarchy`, `AtomicIdentityData`, `AtomicProperty` and
  `FrameSet`.
- Produces: executable mapping fixtures; no new core model.

- [x] **Step 1: Write shape and categorical tests**

`BiologicalAtomSiteData` stores serial, residue index, altloc and record kind;
`BiologicalChain`/`BiologicalResidue` store chain, segment, residue number,
insertion code and residue name; `AtomicIdentityData` stores atom names.
Occupancy/B-factor and PQR charge/radius remain atomic datasets. All atom
dimensions match Structure.

- [x] **Step 2: Verify identity key**

A stable atom identity tuple uses record kind, chain, residue number, insertion code, residue name, atom name and altloc. Serial is retained but not the sole identity across models.

- [x] **Step 3: Verify project/sidecar validation**

Each Structure has at most one BiologicalHierarchy. Compatible MODEL records
use FrameSet; incompatible identity sets create independent structures.
Run sidecar/canonical round-trip.

- [x] **Step 4: Commit**

Commit model and tests.

Completion evidence: `ac924e6`, `3eade23`; 22 focused tests passed,
`compileall` and `git diff --check` passed, and fix round 1 closed the only
Important review finding. The registered-reader capability matrix remains
unchanged until PDB/PQR reader registration in Tasks 3 and 4.

### Task 2: Implement fixed-column PDB parser

**Files:**
- Create: `ChemBlender/core/formats/pdb.py`
- Create: `tests/test_pdb_syntax.py`
- Create: `tests/fixtures/pdb/README.md`
- Add: atom/hetatm, altloc, multimodel, conect, cryst1 and malformed fixtures.

**Interfaces:**
- Produces: `sniff_pdb()`, `parse_pdb_records()` and record dataclasses.

- [x] **Step 1: Write column tests**

Test exact slices for serial, atom name, altloc, residue, chain, residue number, insertion, xyz, occupancy, B-factor, element and charge. Lines shorter than required generate record diagnostics.

- [x] **Step 2: Implement element resolution**

Use element columns when valid. Otherwise infer from atom name using PDB conventions and chemical context, preserving inferred flag and diagnostic. Unknown remains invalid atom identity; do not default.

- [x] **Step 3: Parse MODEL/ENDMDL and TER**

Maintain model number and segment index. ATOM/HETATM outside MODEL belong to model 1. Nested/mismatched model markers produce diagnostics and balanced recovery.

- [x] **Step 4: Parse CONECT and CRYST1**

CONECT serial references map after atoms are known. Repeated entries can encode bond multiplicity only when unambiguous; otherwise store connectivity/unknown order. CRYST1 maps cell and declared space group/source metadata.

- [x] **Step 5: Run and commit**

Run syntax tests and commit parser primitives.

Completion evidence: `22b566a`, `b848b0c`, `ed7b0e0`, `089f0c5`;
22 focused and 89 related tests passed, `compileall` and `git diff --check`
passed. Three review-fix rounds closed fixed-column element alignment,
malformed TER recovery, model-scoped CONECT, CRYST1 validation and sniff
confidence findings with no open Critical/Important issues.

### Task 3: Map PDB models, altlocs and topology into project entities

**Files:**
- Modify: `ChemBlender/core/formats/pdb.py`
- Modify: `ChemBlender/core/reader_catalog.py`
- Create: `tests/test_pdb_reader.py`
- Modify: `docs/quantum-visualization/reader-capability-matrix.json`

**Interfaces:**
- Produces: reader ID `pdb`, structures/models/frame sets, BiologicalAtomData, occupancy/B-factor properties and explicit topology.

- [x] **Step 1: Write model compatibility tests**

Two models with identical identity keys form a FrameSet. Reordered atoms are mapped deterministically by identity. Missing/different altloc or residue identity splits models and reports why.

- [x] **Step 2: Implement altloc policy**

All altloc atoms are imported. Default view policy selects blank then highest occupancy per site, but source Structure/records retain all alternatives. The selected-altloc view is a view filter, not data deletion.

- [x] **Step 3: Map properties**

Occupancy and B-factor are AtomicProperties with validity masks. Missing values are Partial. CONECT becomes explicit TopologyRecord. Without CONECT, no automatic reader topology; Import Preview may suggest distance inference.

- [x] **Step 4: Register and conform**

Capabilities include structure, topology partial, trajectory/model, hierarchy and atomic property. Run Reader API conformance.

- [x] **Step 5: Commit**

Run reader/sidecar/preview tests and commit.

Completion evidence: `e3cc301`, `348554e`; 42 focused, 156 related and
23 sidecar tests passed, `compileall` and `git diff --check` passed. Fix
round 1 closed all review findings for MODEL occurrence identity,
duplicate-identity topology recovery, serial/occupancy validation,
diagnostics and real PDB persistence.

### Task 4: Implement PQR parser and dialect detection

**Files:**
- Create: `ChemBlender/core/formats/pqr.py`
- Create: `tests/test_pqr_reader.py`
- Create: `tests/fixtures/pqr/README.md`
- Add: with-chain, no-chain and malformed fixtures.

**Interfaces:**
- Produces: reader ID `pqr`, Structure, BiologicalAtomData, charge/radius properties.

- [x] **Step 1: Write dialect tests**

Support validated forms with and without chain ID. Detect positions of xyz, charge and radius by allowed field counts and numeric validation, not by best-effort shifting. Ambiguous lines are rejected with field-level diagnostic.

- [x] **Step 2: Map identity and properties**

Partial charge uses elementary_charge; radius uses angstrom. Atom/residue/chain fields map to BiologicalAtomData. PQR does not imply bonds.

- [x] **Step 3: Register and conform**

Sniff distinguishes PQR from PDB by valid trailing charge/radius fields and content. Run conformance.

- [x] **Step 4: Commit**

Commit reader, fixtures, catalog and tests.

Completion evidence: `c528908`, `f0d4852`, `d43f7b4`; 12 focused and
175 related tests passed, `compileall` and `git diff --check` passed. Two
review-fix rounds closed padded PQR routing, token-only element ambiguity,
residue conflict isolation, Reader API metadata and conservative polymer
element inference with no open findings.

### Task 5: Add chain/residue/altloc selection and view controls

**Files:**
- Create: `ChemBlender/ui/biological.py`
- Modify: `ChemBlender/views/structure.py`
- Modify: `ChemBlender/ui/project_browser/`
- Modify: `ChemBlender/ui/properties.py`
- Modify: `tests/blender_smoke.py`

**Interfaces:**
- Produces: hierarchy attributes, selection operators, altloc filter, model playback and size-aware default representation.

- [ ] **Step 1: Write Blender attribute contract**

Point attributes contain chain/residue/altloc categorical codes, residue number, occupancy, B-factor, PQR charge/radius and record kind. Mapping metadata stores categories and hashes.

- [ ] **Step 2: Add selection operators**

Select by chain, residue range/name, atom name, altloc and property threshold. Selections write existing boolean named attributes and do not change source data.

- [ ] **Step 3: Model/frame playback**

Compatible models use existing trajectory manager. Altloc filtering is applied consistently across frames or reports incompatibility.

- [ ] **Step 4: Default view**

Small files use ball-and-stick when explicit/inferred topology selected; large files default to atoms/points with an explanation. No ribbon option is exposed.

- [ ] **Step 5: Blender smoke and commit**

Import PDB altloc/multimodel and PQR charge/radius; select chain/residue, switch altloc, play frames, save/reopen. Commit.

### Task 6: Define PDB/PQR export readiness P1

**Files:**
- Create: `ChemBlender/core/exporters/pdb_readiness.py`
- Create: `tests/test_pdb_export_readiness.py`
- Create: `docs/quantum-visualization/2.3.0/specs/pdb-pqr-export-p1.md`

**Interfaces:**
- Produces: readiness reports for future export.

- [ ] **Step 1: Define required identity fields and representability**

PDB readiness requires atom names, residue identity, serial allocation and coordinates. PQR additionally requires finite charge/radius. Report line-width/field overflow risks.

- [ ] **Step 2: Implement and test**

Complete imported entities report Ready; generic molecules report MissingHierarchy; long identifiers report FieldOverflow.

- [ ] **Step 3: Commit**

Commit readiness boundary without claiming exporter support.
