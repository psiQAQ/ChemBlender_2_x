# ChemBlender 2.3.0 Native Compatibility and Platform Foundation Design

## Status

Approved direction. This design consolidates all user decisions made before document generation. Implementation must still verify the live repository before changing code.

## 1. Goal

Build ChemBlender 2.3.0 as a Windows x64, Blender 5.1+ scientific visualization platform whose base installation can import, organize, inspect, visualize and export common chemistry and quantum-data files without requiring users to install external tools or Python environments.

The release allocates effort as follows:

```text
70% Native Compatibility
30% Platform Foundation
```

The product is result-first and program-neutral. Existing optional compute and analysis backends remain available through delayed imports and workers, but they do not define base-package success.

## 2. User outcomes

A user installs the official ZIP and can:

1. Import one or many supported files using a file chooser or drag-and-drop.
2. Review detected readers, capabilities, diagnostics, duplicates and grouping suggestions.
3. Commit confirmed data atomically to a session project.
4. Receive an appropriate default Blender view without losing access to other records or datasets.
5. Browse the project By Source or By Data.
6. Inspect quality, units, provenance, revisions and parser limitations.
7. Save a `.blend`; the project is solidified to a sibling `.cbq` sidecar and linked relatively.
8. Reopen the scene and recover project identity and views.
9. Export supported formats under explicit loss policies.
10. Create an editable scientific derivative without corrupting source-linked results.

## 3. Product boundaries

### Included in the base package

- Blender-provided Python, NumPy, Requests and OpenVDB.
- Pinned RDKit Windows CPython 3.13 wheel.
- Pinned Gemmi Windows CPython 3.13 wheel.
- ChemBlender native readers, exporters, models, UI, view adapters and sidecar support.

### Optional enhancements

- spglib for symmetry derivation and standardization.
- cclib for Gaussian/ORCA and other output parsing.
- IOData for FCHK/Molden and wavefunction containers.
- GBasis for orbital/density/ESP grid evaluation.
- ASE, pymatgen, phonopy and PyProcar.
- Multiwfn, critic2 and other external executables.
- QCArchive, AiiDA, NOMAD and remote services.

### Explicit non-goals

- A full quantum chemistry execution platform.
- Runtime package installation.
- A protein ribbon/cartoon ecosystem.
- Lossless Cube rewriting.
- Automatic directory scanning and silent grouping.
- Storing authoritative large arrays in Blender datablocks.
- Immediate extraction of `chemblender-core` into a separately released package.

## 4. Target architecture

```text
External files / optional readers / worker outputs
                         │
                         ▼
                Reader Plugin API
                         │
                PublicImportBatch
                         │
             Import Preview and Decision
                         │
              ProjectTransaction
                         │
                     QCProject
                         │
        Session or persistent .cbq sidecar
                         │
                  View Planning
                         │
       Mesh / Curve / Volume / Material / GN
```

### Target packages

```text
ChemBlender/
├── core/
│   ├── __init__.py
│   ├── model/
│   ├── import_pipeline/
│   ├── formats/
│   ├── exporters/
│   ├── storage/
│   └── services/
├── reader_api/
├── ui/
├── views/
├── legacy/
├── runtime/
└── assets/
```

`ChemBlender.core` remains a stable compatibility façade. Internal files can move only when re-exports, serialization tags, tests and the architecture guide are updated together.

## 5. Scientific data model additions

### Sources and revisions

- `SourceRecord`: logical source identity.
- `SourceRevision`: immutable content/reader/parameter combination.
- `parse_identity`: deterministic SHA-256 over source hash and canonical parse conditions.
- Source locator remains mutable metadata, not scientific identity.

### Imports and diagnostics

- `ImportRequest` captures user intent.
- `ImportPreview` captures staged output and decisions.
- `ProjectTransaction` performs validated project publication.
- `ImportDiagnostic` carries severity, quality, stable code, field path, recovery, consequence and suggested action.

### Structured collections

- `ConformerSet` is distinct from temporal `FrameSet`.
- `FrameProperty`, `AtomFrameProperty` and `CellFrameProperty` attach frame-indexed data.
- `CategoricalData` stores string categories without object arrays.
- `TopologyRecord` owns topology source, quality, inference parameters and provenance.
- `CalculationGroup` stores user-confirmed multi-source relationships.
- `ViewRecord` represents reconstructible views.

## 6. Quality and recovery

The default is Balanced Recovery:

```text
unrecoverable scientific identity → reject entity/record
recoverable optional data         → retain with quality status
```

Statuses:

- Complete
- Partial
- Ambiguous
- Incomplete
- Invalid

Ambiguous data may be previewed but is excluded from final reports until resolved. Export of partial or ambiguous data requires confirmation.

## 7. Format scope

### Wave 1

- XYZ and generic extXYZ.
- MOL V2000/V3000.
- SDF multi-record.
- SMILES.
- Cube.

### Wave 2

- CIF using bundled Gemmi.
- Native POSCAR/CONTCAR.

### Wave 3

- MOL2.
- PDB/PQR atom-level and hierarchy metadata.
- CJSON.

Format support is reported with F0–F5 maturity, not a boolean.

## 8. Topology and editing

Topology precedence:

```text
explicit_file
rdkit_sanitized
distance_inferred
user_edited
```

All inferred topology is a derived entity. Periodic and metal connections do not automatically acquire conventional single-bond semantics.

Imported scientific entities are immutable. Object transforms and appearance are view state. Atom, bond, cell, occupancy or ADP changes require an explicit edit preview and produce derived entities with provenance. Existing orbitals, grids and spectra remain bound to their source structure revision.

## 9. UI design

### N-panel

- Quick Import.
- Project state and dirty indicator.
- Recent sources.
- Active data/view controls.
- Workspace entry.

### Workspace

- By Source / By Data browser.
- 3D view.
- Entity and view properties.
- Diagnostic/numeric/spectrum region.
- Import, save, verify and export actions.

Quick Import and Project Browser share the same pipeline and project. The workspace is optional; core operations remain possible in the N-panel.

## 10. Reader API

Execution modes:

- Built-in.
- Extension Reader.
- Worker Reader.

Built-in and Extension readers return public Python dataclasses. Worker readers return canonical JSON plus safe relative NPY artifacts. Both represent the same schema and round-trip deterministically. Because installed Blender extension module names include a repository namespace, ChemBlender publishes a versioned API handle in `bpy.app.driver_namespace`; extension-reader bootstrap code resolves the actual `reader_api` module through that handle instead of hardcoding `bl_ext.user_default` or the source-tree `ChemBlender` name.

API timeline:

```text
alpha       0.x experimental
beta.1      v1 RC and schema freeze
beta.2      compatible additions and conformance kit
2.3.0       v1 stable
```

## 11. Storage

A session project writes to a Blender temporary root. On save it is atomically solidified into `{blend_stem}.cbq`. The Scene stores project UUID, schema, relative locator and manifest hash. Missing, incompatible, mismatch and invalid states never delete existing views.

Large arrays remain content-addressed NPY. The sidecar type registry becomes explicit and versioned so internal module splits do not change serialization unexpectedly.

## 12. Performance

Immediate and lazy scale budgets and user timing targets are defined in `docs/quantum-visualization/2.3.0/performance-budget.md`. Operations over one second require progress, cancellation and cleanup. Blender data mutation remains on the main thread.

## 13. Testing

Each vertical slice must prove:

```text
real fixture
→ reader
→ preview/diagnostics
→ project commit
→ default Blender view
→ save/reopen
→ export/round-trip where promised
```

Optional integrations receive dedicated CI that does not silently skip targeted tests. Package and release CI remain exact-artifact workflows.

## 14. Release train

- `2.3.0-alpha.1`: Wave 0.
- `2.3.0-alpha.2`: Wave 1.
- `2.3.0-beta.1`: Wave 2 and schema/API freeze.
- `2.3.0-beta.2`: Wave 3.
- `2.3.0-rc.1`: Wave 4, fixes only.
- `2.3.0`: final.

The manifest prerelease syntax is not assumed. An early Wave 0 task probes Blender 5.1.2 native validation. No prerelease tag is created before this result is recorded.

## 15. Wave decomposition

The master plan routes to five separate design/plan groups. Only one Wave is active at once. A Wave is rejected if it lands data models without a user-visible vertical closure or if it declares product completion based solely on synthetic adapter tests.
