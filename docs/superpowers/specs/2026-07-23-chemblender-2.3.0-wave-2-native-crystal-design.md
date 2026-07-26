# ChemBlender 2.3.0 Wave 2 Native Crystal Design

## Status

Approved direction for `2.3.0-beta.1`, dependent on Wave 1.

## 1. Goal

Make CIF and POSCAR/CONTCAR base-package features, provide crystal data/view/export closure, and freeze sidecar schema plus Reader API v1 RC.

## 2. Gemmi packaging

Gemmi is a pinned manifest wheel. The dependency ADR records version, source URL, SHA-256, wheel size, unpacked size, license and notices. The import is delayed until CIF sniff/parse. Blender package smoke checks a representative parse and two lifecycle cycles.

No code downloads or installs Gemmi at runtime.

## 3. CIF reader

Gemmi owns lexical and structural parsing. The reader selects a data block explicitly when a file contains multiple blocks; Quick Import proposes the first structure-capable block and Project Browser exposes all blocks.

Capture:

- original bytes and block name;
- all tag names and raw envelope;
- cell;
- atom/site labels and elements;
- fractional/cartesian coordinates;
- occupancy;
- disorder group/assembly where available;
- Uiso/Ueq and complete Uij rows;
- declared space-group name/number;
- symmetry operations;
- chemical metadata;
- diagnostics for uncertainty and missing/contradictory fields.

Gemmi parse errors are record/block diagnostics; unrelated blocks may remain available.

## 4. Symmetry boundary

File-declared symmetry is source data. Optional spglib derives a `SymmetryResult` with explicit parameters. UI shows:

```text
Declared: P 21/c, IT 14
Derived:  P 21/c, IT 14, symprec 1e-5
Status: match
```

or a discrepancy with transformation and tolerance information. Derivation cannot overwrite the CIF envelope or declared fields.

## 5. Native POSCAR/CONTCAR

The reader supports:

- comment;
- positive scale and negative target-volume scale;
- three lattice vectors;
- VASP 5 element line and VASP 4 count-only ambiguity;
- Direct/Cartesian and case-insensitive leading character;
- Selective Dynamics flags;
- optional velocities/lattice velocity block when valid;
- no-extension basename sniff for POSCAR/CONTCAR;
- finite values and count validation.

VASP 4 without element information is Ambiguous and requires user element assignment; it cannot silently invent elements.

## 6. Crystal topology and views

Periodic topology inference uses cell and PBC and produces a derived coordination topology. ViewBuilder supports:

- asymmetric unit vs expanded cell;
- cell edges and axis arrows;
- supercell;
- occupancy-aware rendering;
- Uij thermal ellipsoids;
- Selective Dynamics markers;
- topology source indicator;
- file vs standardized structure comparison.

## 7. Controlled export

### CIF

Prefer envelope-preserving export. Apply a known-field patch plan to a copy of the source document. Unknown tags/loops remain unless the user explicitly creates a normalized new CIF. Export report lists modified, preserved and omitted fields.

### POSCAR

Round-trip lattice, species order, coordinate mode and Selective Dynamics. Do not write symmetry or bonds because POSCAR does not represent them.

## 8. API/schema freeze

Before beta.1:

- finalize Source/Diagnostic/Topology/Conformer/Categorical/View models;
- increment `.cbq` manifest/schema and implement migration from v0.1;
- publish Reader API v1 RC;
- prohibit breaking changes after tag without a user-approved release-blocking ADR.

## 9. Exit criteria

A clean official ZIP with no spglib or external worker imports real CIF/POSCAR, displays crystal data, saves/reopens and exports under policy. Gemmi wheel and artifact size gates pass. API and schema compatibility tests are frozen.
