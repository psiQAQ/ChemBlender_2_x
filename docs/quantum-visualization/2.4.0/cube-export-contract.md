# Native Cube Export Contract

## Readiness

`cube_export_readiness(project_entities, *, dataset_index=None)` is a pure
core boundary. It requires one `Grid3D`, the `Structure` named by
`Grid3D.structure_id`, and one matching complete `nuclear_charge`
`AtomicProperty` in `elementary_charge`. Atom count must be positive. All
coordinates, charges and selected voxel values are finite real numeric arrays.

`CubeExportReadiness` is frozen and returns sorted tokens with one of:
`Ready`, `MissingEntity`, `MissingSelection`, `Ambiguous`, `Invalid` or
`UnsupportedUnit`.

## Dataset Selection

- `("x", "y", "z")` accepts only `dataset_index=None`.
- `("dataset", "x", "y", "z")` requires an exact in-range integer index;
  `bool` is invalid.
- Other leading dimensions are invalid.

Only the selected dataset slice must be finite. Selection does not resample or
alter the affine `origin`, `step_vectors` or spatial shape.

## Units and Loss Boundary

Structure coordinates and Grid geometry independently accept `bohr` or
`angstrom`; later serialization converts both into one bohr output frame.
Unknown, dimensionless and other coordinate units fail closed.

Readiness does not claim the Cube text can preserve semantic role, scalar-value
unit, project identity, provenance, topology, periodic/cell data or atomic
identity. The writer must report every present non-representable semantic before
publication and require explicit confirmation. OpenVDB, Blender Volume and mesh
caches remain derived data and are never export sources.

## Snapshot and Publication

Preview and export copy authoritative coordinates, nuclear charges and only the
selected scalar grid once. Exporter-owned mappings are closed after each read;
arrays already loaded by the caller remain loaded. Before an atomic destination
replacement, the live selected values are compared with the snapshot. A changed
input, cancellation or write failure leaves an existing destination unchanged.

Cube output uses normalized comments and cannot preserve Grid3D semantic/value
units, project UUID/revision/provenance, Structure cell/periodicity, molecular
charge/multiplicity, topology or atomic identity. Loss entries are sorted and
any entry requires exact `confirm_loss=True` before text is returned or written.
Re-import qualification compares atoms, nuclear charges, bohr geometry, affine
grid shape/steps, selected values and the preserved or normalized dataset ID.
