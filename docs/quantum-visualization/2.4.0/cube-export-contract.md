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
