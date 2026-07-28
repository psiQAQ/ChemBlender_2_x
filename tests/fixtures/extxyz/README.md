# extXYZ syntax fixtures

- `properties-mixed.extxyz`: ChemBlender mixed `S/I/R/L` descriptor coverage.
- `multiframe-cell.extxyz`: changing per-frame Lattice metadata.
- `invalid-property.extxyz`: invalid zero-column `Properties` descriptor.
- `libatoms-typed.extxyz`: libAtoms-style typed scalar/vector/matrix comment values.
- `libatoms-legacy-array.extxyz`: backward-compatible whitespace-separated `{}` array.
- `ase-lattice.extxyz`: ASE-style quoted Lattice and pbc values.
- `ovito-properties.extxyz`: OVITO-compatible named particle columns.

The compatibility files are test data only. ChemBlender does not import or
depend on ASE, libAtoms/extxyz, or OVITO at runtime.
