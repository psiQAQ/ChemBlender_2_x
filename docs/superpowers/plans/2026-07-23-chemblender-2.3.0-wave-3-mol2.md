# ChemBlender 2.3.0 Wave 3 Native MOL2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement dependency-free, record-aware Tripos MOL2 import with atom types, substructures, partial charges, explicit topology and transparent unsupported-section diagnostics.

**Architecture:** A section tokenizer preserves raw records and maps common `MOLECULE`, `ATOM`, `BOND` and `SUBSTRUCTURE` sections into internal structures, topology and categorical properties. Multiple molecule blocks become independent MolecularRecords. Export remains P1 and is not a beta.2 release requirement.

**Tech Stack:** Python 3.13 standard library, NumPy, existing record/categorical/topology/import pipeline and `unittest`.

## Global Constraints

- No Open Babel or RDKit MOL2 parser dependency.
- Content markers, not extension alone, determine MOL2.
- Preserve raw atom type, substructure and charge type strings.
- Unsupported sections are reported, not silently discarded.
- Atom and bond IDs need not be contiguous, but references must resolve.
- Legacy MOL2 input must route to this reader after completion.

---

### Task 1: Add MOL2 source metadata models

**Files:**
- Create: `ChemBlender/core/model/mol2.py`
- Modify: `ChemBlender/core/model/project.py`
- Modify: `ChemBlender/core/model_registry.py`
- Create: `tests/test_mol2_models.py`

**Interfaces:**
- Produces: `Mol2Envelope`, `Mol2MoleculeMetadata`, `Mol2SubstructureData`.

- [ ] **Step 1: Write model tests**

Validate molecule type, charge type and status bits as categorical strings. Substructure IDs are integer per atom; names are categorical and can be missing. Envelope stores raw record bytes and present section names.

- [ ] **Step 2: Implement project references**

MolecularRecord may reference a Mol2Envelope and substructure dataset. Sidecar registry includes the new types with stable tags.

- [ ] **Step 3: Run and commit**

Run model/sidecar tests and commit.

### Task 2: Implement MOL2 tokenizer and molecule block parser

**Files:**
- Create: `ChemBlender/core/formats/mol2.py`
- Create: `tests/test_mol2_syntax.py`
- Create: `tests/fixtures/mol2/README.md`
- Add: small molecule, aromatic, substructure, multi-molecule and malformed fixtures.

**Interfaces:**
- Produces: `sniff_mol2()`, `iter_mol2_records()`, `parse_mol2_record()`.

- [ ] **Step 1: Write sniff tests**

Require `@<TRIPOS>MOLECULE` followed by plausible counts and `@<TRIPOS>ATOM`. `.mol2` ordinary text returns NONE. Complete source is EXACT; truncated valid prefix is PROBABLE.

- [ ] **Step 2: Tokenize sections**

Section headers are case-insensitive exact markers. Preserve unknown sections as raw lines and section names. A new `MOLECULE` begins the next record.

- [ ] **Step 3: Parse MOLECULE and ATOM**

Read name, counts, molecule type, charge type and status/comment lines. Atom fields include ID, name, x/y/z, atom type, optional substructure ID/name and charge. Determine element from Tripos atom type prefix with explicit fallback diagnostic; never default unknown element to hydrogen/carbon.

- [ ] **Step 4: Parse BOND and SUBSTRUCTURE**

Resolve arbitrary atom IDs to zero-based indices. Map bond type strings into bond order/aromatic/amide/unknown semantics. Unknown references invalidate topology but may preserve structure. Parse common substructure ID/name/root fields.

- [ ] **Step 5: Run and commit**

Run syntax tests and commit parser primitives.

### Task 3: Map MOL2 into project entities with record recovery

**Files:**
- Modify: `ChemBlender/core/formats/mol2.py`
- Modify: `ChemBlender/core/reader_catalog.py`
- Create: `tests/test_mol2_reader.py`
- Modify: `docs/quantum-visualization/reader-capability-matrix.json`

**Interfaces:**
- Produces: reader ID `mol2`, Structure, TopologyRecord, AtomicProperties, categorical atom/substructure data and MolecularRecords.

- [ ] **Step 1: Write mapping tests**

Assert coordinates, elements, atom types, partial charges, topology source explicit_file, aromatic/amide flags, substructure IDs/names and envelope.

- [ ] **Step 2: Implement partial recovery**

A malformed record does not invalidate other records under Balanced mode. A valid atom block with invalid bonds yields a Structure and Invalid topology diagnostic. Missing charge values produce Partial property, not zero Complete values.

- [ ] **Step 3: Register and conform**

Add execution mode built-in, capabilities structure/topology/atomic_property/substructure/multi_record. Run Reader API v1 conformance.

- [ ] **Step 4: Run and commit**

Run reader, catalog, sidecar, preview and record tests; commit.

### Task 4: Add MOL2 Project Browser and view behavior

**Files:**
- Modify: `ChemBlender/ui/import_preview.py`
- Modify: `ChemBlender/ui/project_browser/`
- Modify: `ChemBlender/ui/properties.py`
- Modify: `tests/blender_smoke.py`

**Interfaces:**
- Produces: molecule/record/substructure browsing and styling.

- [ ] **Step 1: Preview summary**

Show molecule count, atom/bond counts, molecule/charge types, partial-charge availability and unsupported sections.

- [ ] **Step 2: Browser and selection**

Expose atom type, substructure and charge datasets. Add substructure selection/coloring through categorical codes and existing selection attributes.

- [ ] **Step 3: Legacy bridge**

Route legacy `.mol2` file action to Quick Import. Remove the temporary unsupported diagnostic introduced in Wave 1.

- [ ] **Step 4: Blender smoke and commit**

Import aromatic/substructure fixture, create ball-and-stick view, color by substructure, save/reopen. Commit.

### Task 5: Establish MOL2 export P1 boundary

**Files:**
- Create: `docs/quantum-visualization/2.3.0/specs/mol2-export-p1.md`
- Create: `tests/test_mol2_export_readiness.py`

**Interfaces:**
- Produces: a machine-readable readiness check, not an exporter requirement.

- [ ] **Step 1: Define representability rules**

Document required atom names/types, charge type, substructure and bond type mappings for future export. Identify data that cannot be reconstructed from generic Structure/Topology alone.

- [ ] **Step 2: Add readiness report**

`mol2_export_readiness(project_entities)` returns Complete/Partial/Unsupported with missing fields. UI may display this but does not promise export.

- [ ] **Step 3: Test and commit**

Run readiness tests and commit the explicit P1 boundary.
