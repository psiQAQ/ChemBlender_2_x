# ChemBlender 2.3.0 Wave 1 Native Molecular and Grid Design

## Status

Approved direction for `2.3.0-alpha.2`, dependent on Wave 0.

## 1. Goal

Deliver base-package workflows for XYZ/extXYZ, MOL V2000/V3000, SDF, SMILES and Cube, and unify structure/topology Blender views with existing Geometry Nodes.

## 2. Native extXYZ

### Grammar

Parse the comment line as key/value metadata with quoted values and a required or optional `Properties` descriptor. Support property triples:

```text
name:type:columns
```

Types:

- `S`: categorical/string.
- `I`: integer.
- `R`: floating point.
- `L`: boolean.

Known names normalize to standard semantics; unknown names retain a normalized `extxyz_custom_{normalized_name}` role and original name metadata.

### Frame data

- Each frame can have Lattice and pbc.
- Frame-level energy, time, stress, virial and temperature become frame properties.
- Force, velocity, charge and other atom data become atom-frame properties.
- Multiple frames require stable atom count and identity; otherwise create separate structures/sets with diagnostics.

### Export

Reconstruct a deterministic `Properties` schema, quote metadata safely and preserve original unknown property order where possible. Round-trip compares semantics, not whitespace.

## 3. RDKit-backed molecular readers

### MOL V2000/V3000

Read without discarding raw block. Capture:

- atomic numbers and coordinates;
- explicit bonds and orders;
- aromatic flags;
- formal charge;
- isotopes;
- atom map;
- stereo/chirality;
- sanitize outcome.

Sanitize failure does not destroy raw topology. It produces diagnostics and an ambiguous explicit topology.

### SDF

Each record is staged independently. A bad record does not abort valid records under Balanced Recovery. Preserve:

- record index and title;
- original mol block version;
- SD property names, raw strings and order;
- typed columns only when all selected values parse consistently.

Intelligent grouping occurs after all records exist as structures. A ConformerSet requires validated topology, charge, stereo and atom mapping equivalence. The grouping explanation is visible and user-confirmed.

### SMILES

Store source text, canonical SMILES, isomeric SMILES, formal charge and embedding parameters. 3D generation is a derived operation with fixed random seed recorded in provenance. Failed embedding still retains the 2D/topological source and diagnostic.

## 4. Topology

Introduce TopologyRecord and source/quality metadata. File topology wins. RDKit sanitized topology is a separate interpretation if it differs. Distance inference is invoked only when no selected usable topology exists or the user requests recomputation.

## 5. Unified StructureViewBuilder

Create one mesh with vertices and edges, stable atom/bond IDs, scientific identity and existing ball-and-stick node groups. It supports:

- topology switching;
- atom scalar/vector attributes;
- selection;
- periodic cell metadata;
- old scaffold bridge during migration;
- reconstructible ViewRecord.

View creation never writes scientific edits back automatically.

## 6. Cube product UX

Use the existing strong parser and add:

- source structure and grid listing;
- multi-dataset selector;
- semantic role and unit confirmation;
- presets for MO, density, spin density, ESP and generic field;
- default isovalue policy with user-visible source;
- positive/negative signed surfaces;
- property-on-surface binding;
- cache/LOD controls;
- quality badge and report eligibility.

Nuclear charge and dataset IDs should be preserved in a typed field or envelope rather than only reported unsupported.

## 7. Exporters and round-trip

- XYZ/extXYZ semantic round-trip.
- MOL V2000/V3000 with charges/isotopes/stereo within RDKit writer capabilities.
- SDF record order, titles and SD fields.
- SMILES canonical/isomeric text export.
- Cube only exports derived files through an explicitly new artifact action; no lossless source rewrite promise.

## 8. Performance

- Stream/index SDF rather than creating all Blender objects.
- ExtXYZ and Cube large arrays stage to NPY.
- Topology inference uses spatial partitioning.
- Quick Import returns preview status within 0.5 s for ordinary files or starts a cancellable operation.

## 9. Exit criteria

Every format uses Quick Import and Project Browser, creates a default view, persists to `.cbq`, reopens, and exports where promised. Real fixtures cover normal, partial, ambiguous and invalid cases. The old direct read path is not expanded.
