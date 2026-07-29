# ChemBlender 2.3.0 Wave 3 Exchange Pre-Gate Design

## Goal

Freeze the compatible model boundary needed by MOL2, PDB, PQR and CJSON
before implementing any Wave 3 reader, exporter or Blender workflow.

Wave 3 continues to use the existing `Structure`, `TopologyRecord`,
`AtomicIdentityData`, `PropertyDataset`, provenance and project graph. It does
not introduce a parallel molecular, biological or exchange structure model.

## Existing Authority

- `Structure` remains the scientific atom and coordinate identity.
- `AtomicIdentityData` remains limited to isotope, formal charge, atom-map,
  atom-name and stereochemical identity.
- Numeric and categorical arrays remain `PropertyDataset`,
  `AtomicProperty`, `ArrayData` or `CategoricalData`.
- Exact source syntax and unknown source fields remain in a format envelope.
- Project UUIDs remain internal identities; external database identifiers do
  not replace them.

## Chemical Annotation Contract

`ChemicalAnnotation` is a first-class immutable project entity with:

- `id` and `revision`;
- `target_entity_id`;
- normalized `namespace` and `key`;
- one exact scalar `value`: `str`, `int`, finite `float` or `bool`;
- non-empty `source`;
- optional finite `confidence` from 0 through 1;
- `provenance_ids`.

Annotations are entity-level metadata. They do not contain arrays, nested
JSON, mutable containers, callables or third-party objects. One project may
not contain two annotations with the same
`(target_entity_id, namespace, key)` identity. Repeated or structurally
unknown source data stays in the source envelope instead of being collapsed.
Targets must be ordinary project scientific/source entities, not another
annotation, external reference, provenance record or diagnostic.

Atom-, bond- or record-aligned values do not create one annotation per item.
They use the existing columnar dataset contracts.

## External Reference Contract

`ExternalReference` is a first-class immutable project entity with:

- `id` and `revision`;
- `target_entity_id`;
- normalized `namespace`;
- non-empty `identifier` and `source`;
- `provenance_ids`.

The project rejects duplicate
`(target_entity_id, namespace, identifier)` references and dangling target or
provenance UUIDs. Targets follow the same non-recursive restriction as
annotations. An external identifier never becomes a `Structure`, project or
source UUID. References contain no credentials, endpoint configuration,
network cache or provider SDK object.

## Biological Hierarchy Contract

`BiologicalHierarchy` is one immutable entity per `Structure`. It stores a
compact hierarchy rather than duplicating atoms:

- one `BiologicalModel` source identity;
- ordered chain records;
- ordered residue records referencing a chain index;
- atom-site data aligned to the `Structure` atom axis and referencing a
  residue index;
- `id`, `revision`, `structure_id` and `provenance_ids`.

`BiologicalModel`, chain and residue records are immutable value objects.
Atom sites use the `Structure` atom index as their identity; they do not store
coordinates or atomic numbers again. Atom-site serial number, alternate
location, record kind and residue mapping are columnar typed values. Atom
names continue to use `AtomicIdentityData`.

Compatible PDB MODEL coordinates use the existing `FrameSet`; source model
numbers are a frame property and share the hierarchy of the reference atom
identity. Incompatible MODEL records become separate Structures and separate
hierarchies. The hierarchy therefore never duplicates one atom-site table per
coordinate frame.

Validation rejects empty required identifiers, invalid parent indices,
duplicate chain/residue keys, an atom-site length different from the
referenced `Structure`, and multiple hierarchies for one structure.

No `BiologicalStructure` subclass, ribbon/cartoon model, secondary structure,
biological assembly or large-trajectory hierarchy is added.

## Format Mapping Policies

### MOL2

- Coordinates and elements map to `Structure`.
- Explicit bonds map to `TopologyRecord`.
- Tripos atom type and substructure columns use categorical
  `AtomicProperty` datasets.
- Partial charge uses numeric `AtomicProperty`.
- Molecule type, charge type and other supported scalar flags use
  `ChemicalAnnotation`.
- Repeated sections and unsupported exact syntax remain in a future MOL2
  envelope and diagnostics.

### PDB

- ATOM/HETATM coordinates and elements map to `Structure`.
- MODEL, chain and residue nesting maps to `BiologicalHierarchy`.
- Explicit CONECT edges map to `TopologyRecord`.
- Occupancy and B-factor use numeric `AtomicProperty`.
- CRYST1 uses the existing periodic `Structure` contract.
- Header-like supported scalar metadata may use `ChemicalAnnotation`;
  unrecognized records remain in a future PDB envelope.

### PQR

PQR reuses the PDB hierarchy boundary. Charge and radius are numeric
`AtomicProperty` datasets with explicit units and provenance. Neither value
changes atomic identity.

### CJSON

CJSON continues to use its existing whitelist and `CJSONEnvelope`. Stable
known fields map to existing scientific models. Unknown or structurally
arbitrary JSON never becomes a generic annotation and remains in the
envelope with diagnostics.

## Project, Sidecar and Reader API

`ImportBatch`, `QCProject` and `PublicImportBatch` gain explicit groups for
annotations, external references and biological hierarchies. Project commit
validates all target, structure and provenance references before mutating any
registry.

Sidecar schema remains `1.0` and Reader API remains `1.0-rc1`. New model tags
and batch groups are compatible additions. Sidecar and canonical decoders
provide explicit empty-group defaults for documents written before this
gate; no legacy entity is reinterpreted.

The public Reader API exposes only these neutral immutable types. It does not
expose `QCProject`, internal registries, parser internals, Blender state,
Open Babel, Biopython or RDKit objects.

## Error Handling

Model construction raises stable `TypeError` for wrong exact types and
`ValueError` for invalid values or relationships. Non-finite floats,
unregistered nested values, mutable containers, dangling references and
duplicate semantic keys fail before publication.

`QCProject.commit()` remains atomic. Rejected exchange batches leave all
registries unchanged. Sidecar and canonical failures close any lazy arrays
through their existing ownership paths.

## Verification

- RED tests first for immutable model validation, hierarchy graph integrity,
  duplicate and dangling references, project rollback and public surfaces.
- Sidecar save/open and canonical document round trips, including legacy
  empty-group defaults.
- Existing Wave 1 molecular and Wave 2 crystal fixtures continue to open.
- A fresh-process import audit proves `ChemBlender.core` and
  `ChemBlender.reader_api` do not load Open Babel, Biopython, Gemmi, spglib or
  RDKit.
- Focused tests, full `unittest` discovery, `compileall`, documentation
  contracts and `git diff --check`.
- Blender 5.1.2 native extension validate/build and ZIP audit.

## Stop Boundary

This gate ends after the contracts, persistence/public boundaries, tests and
checkpoint are complete. It does not implement MOL2, PDB, PQR or CJSON reader
changes, Reader ecosystem work, exporters, UI, hierarchy visualization,
version changes, tags or releases.
