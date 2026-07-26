# ChemBlender 2.3.0 Wave 3 MOL2, PDB/PQR, CJSON and Reader Ecosystem Design

## Status

Approved direction for `2.3.0-beta.2`, dependent on Wave 2.

## 1. Goal

Complete the remaining base-format surface and prove Reader API v1 through an independent extension reader and conformance kit.

## 2. MOL2

Implement a dependency-free parser for common Tripos sections:

- `MOLECULE`;
- `ATOM`;
- `BOND`;
- `SUBSTRUCTURE`;
- molecule type and charge type;
- atom type, substructure ID/name and partial charge;
- bond types `1`, `2`, `3`, `ar`, `am`, `du`, `un`, `nc` with explicit diagnostics for unsupported semantics.

Do not use extension alone to identify MOL2. Require section markers. Multiple molecule blocks create records. Export is P1 and not required for beta.2 release qualification.

## 3. PDB

Use a fixed-column parser for legacy PDB 3.30 records relevant to atom-level visualization:

- ATOM/HETATM;
- MODEL/ENDMDL;
- CONECT;
- CRYST1;
- TER;
- optional TITLE/HEADER/COMPND metadata;
- serial, atom name, altloc, residue, chain, insertion code, occupancy, B-factor, element, formal charge.

Element inference from atom name is explicit and diagnosed. Altlocs remain distinct source atoms or conformer choices according to user policy; they are not silently merged. MODEL frames require compatible atom identity, otherwise they become separate model structures.

## 4. PQR

Parse whitespace-oriented PQR atom records with charge and radius. Support variants with or without chain IDs by validating field count and coordinate/charge/radius positions. Preserve PDB-like identity fields and mark the exact dialect used.

## 5. Data mapping

Add `BiologicalAtomData` or equivalent typed identity attached to Structure:

- serial;
- atom name;
- residue name/number;
- insertion code;
- chain;
- altloc;
- segment/TER group;
- occupancy and B-factor datasets.

PQR charge and radius are AtomicProperties. String data use CategoricalData.

## 6. View behavior

- default ball-and-stick or atoms based on size;
- chain/residue coloring and selection;
- altloc filter;
- model/frame playback when valid;
- CRYST1 cell;
- explicit CONECT topology before inference.

No ribbon, cartoon, secondary structure or biological assembly generation is included.

## 7. CJSON

Refine existing CJSON adapter to the public API and project model. Preserve raw envelope, structures, topology, trajectories, scalar properties and lightweight spectra/orbital references supported by the format. Large arrays remain in `.cbq`; CJSON export references or omits them under an explicit report.

## 8. Reader plugin ecosystem

### Example plugin

Create a separate example Blender Extension package that reads a minimal text coordinate format. It depends only on Reader API v1 and never imports private `ChemBlender.core.*` modules.

### Conformance kit

Tests:

- manifest validation;
- sniff determinism and prefix bounds;
- parse type/reference/unit validation;
- canonical document round-trip;
- diagnostics;
- dependency unavailable behavior;
- exception isolation;
- plugin disable/missing sidecar recovery.

## 9. Exit criteria

MOL2, PDB, PQR and CJSON complete their promised workflows. The example plugin installs and unloads independently. API additions are backward compatible with beta.1 RC. Project reopening does not require reader plugins that originally produced the stored data.
