# ChemBlender 2.3.0 Wave 2 Native POSCAR and CONTCAR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a dependency-free POSCAR/CONTCAR reader and exporter that preserves lattice scaling, species order, coordinate mode, Selective Dynamics and supported velocity data.

**Architecture:** A strict line-oriented parser recognizes basename and content, produces periodic Structure plus typed constraints/metadata, and reports VASP 4 element ambiguity. Export is deterministic and semantically round-trippable.

**Tech Stack:** Python 3.13, NumPy, existing periodic models/import pipeline, `unittest` and Blender smoke.

## Global Constraints

- No ASE/pymatgen dependency for base POSCAR.
- Support files named exactly POSCAR or CONTCAR with no suffix.
- Do not invent elements for count-only VASP 4 files.
- Preserve species ordering and Selective Dynamics.
- Bonds/symmetry are not POSCAR data and are not exported.
- All coordinate and scale conversions record provenance.

---

### Task 1: Implement content sniffing and low-level parser

**Files:**
- Create: `ChemBlender/core/formats/poscar.py`
- Create: `tests/test_poscar_syntax.py`
- Create: `tests/fixtures/poscar/negative-scale.vasp`
- Create: `tests/fixtures/poscar/vasp4-counts.POSCAR`
- Create: `tests/fixtures/poscar/velocities.CONTCAR`

**Interfaces:**
- Produces: `sniff_poscar()`, `parse_poscar_document()` and `PoscarDocument`.

- [ ] **Step 1: Write sniff tests**

Exact basename POSCAR/CONTCAR plus valid lattice/count/coordinate structure yields EXACT. `.vasp` valid content yields EXACT/PROBABLE. Ordinary numeric text yields NONE.

- [ ] **Step 2: Parse scale and lattice**

Positive scale multiplies lattice and Cartesian coordinates according to VASP convention. Negative scale specifies target cell volume; compute factor `(-scale / abs(det(lattice))) ** (1/3)` and diagnose invalid zero/singular values.

- [ ] **Step 3: Parse species/count variants**

VASP 5: element symbols then counts. VASP 4: counts only; document contains missing element identities and cannot create a complete Structure until user supplies elements. Preview still shows counts/lattice.

- [ ] **Step 4: Parse modes and flags**

Recognize optional Selective Dynamics, Direct/Cartesian/K, case-insensitive first character, exact coordinate count and T/F triplets. Parse supported velocity blocks only when line counts and numeric fields are valid.

- [ ] **Step 5: Run and commit**

Run parser syntax/error tests; commit.

### Task 2: Map POSCAR into project entities

**Files:**
- Modify: `ChemBlender/core/formats/poscar.py`
- Modify: `ChemBlender/core/reader_catalog.py`
- Create: `tests/test_poscar_reader.py`
- Modify: `docs/quantum-visualization/reader-capability-matrix.json`

**Interfaces:**
- Produces: reader ID `poscar`, Structure, PeriodicSiteData, Selective Dynamics AtomicProperty and optional velocities.

- [ ] **Step 1: Add reader tests**

Assert cell/coordinates in angstrom, fractional coordinates, species order, site labels, PBC true and Selective Dynamics dims `(atom,xyz)` boolean/dimensionless.

- [ ] **Step 2: VASP 4 recovery**

Under Balanced mode, create a source preview with lattice/count metadata and Ambiguous diagnostic. User-supplied species assignment is a parse parameter; reparse creates a complete Structure and records assignment provenance.

- [ ] **Step 3: Preserve source mode**

Store original scale, coordinate mode, comment and species order in a POSCAR envelope or source metadata for export. Cartesian/Direct normalized coordinates coexist with original convention metadata.

- [ ] **Step 4: Register and conform**

Handle basename paths in registry selection independent of suffix. Run Reader API conformance.

- [ ] **Step 5: Commit**

Commit reader, tests and capability matrix.

### Task 3: Implement POSCAR/CONTCAR exporter

**Files:**
- Create: `ChemBlender/core/exporters/poscar.py`
- Create: `tests/test_poscar_exporter.py`
- Create: `tests/test_poscar_roundtrip.py`

**Interfaces:**
- Produces: `export_poscar(structure, settings) -> ExportResult`.

- [ ] **Step 1: Define exporter settings**

Settings include comment, Direct/Cartesian mode, scale policy (`unit`, `preserve_source`, `target_volume`) and include Selective Dynamics. Validate target format and entity completeness.

- [ ] **Step 2: Write source-preserving tests**

Imported POSCAR exported with preserve settings retains species ordering, Direct/Cartesian semantic coordinates and Selective flags. Negative scale may normalize to equivalent positive scale only if ExportReport states it; preserve mode retains source scale when coordinates/cell unchanged.

- [ ] **Step 3: Write derived-structure tests**

Derived periodic structure exports unit scale and explicit lattice. Missing species or nonperiodic structure is rejected. Velocities export only when a matching supported dataset is selected.

- [ ] **Step 4: Implement semantic comparator**

Parse output and compare lattice, atom identities, fractional coordinates modulo 1, flags and optional velocities.

- [ ] **Step 5: Run and commit**

Run exporter/round-trip tests and commit.

### Task 4: Add POSCAR product UI and legacy bridge

**Files:**
- Modify: `ChemBlender/ui/import_preview.py`
- Modify: `ChemBlender/ui/properties.py`
- Modify: `ChemBlender/ui/export.py`
- Modify: `ChemBlender/read.py`
- Modify: `tests/blender_smoke.py`

**Interfaces:**
- Produces: species-assignment recovery UI, constraint view controls and unified legacy import.

- [ ] **Step 1: Preview fields**

Show comment, scale convention, cell volume, species/counts, coordinate mode, Selective Dynamics and velocity availability. For VASP 4, provide ordered element assignment fields and block commit until counts match.

- [ ] **Step 2: Visualize constraints**

Write `cbq_selective_x/y/z` or a vector/boolean contract to structure view and add a Geometry Nodes or overlay marker that can be toggled. Scientific data remains in project.

- [ ] **Step 3: Route old crystal import**

Legacy POSCAR/CONTCAR file action invokes the new reader and StructureViewBuilder. Keep old parser callable only for migration regression until Wave 4.

- [ ] **Step 4: Blender smoke**

Import Direct and Cartesian fixtures, display constraints, save/reopen and round-trip export.

- [ ] **Step 5: Commit**

Commit UI/bridge/tests.
