# ChemBlender 2.3.0 Wave 2 Crystal Pre-Gate Design

## Goal

Freeze the native crystal scientific contract before any Wave 2 format or UI
implementation, while preserving the unified Wave 1 project graph and current
sidecar schema.

## Existing Authority

`Structure` is format-neutral. A periodic structure uses:

- `cell`: three lattice vectors as `(cell_vector, xyz)` `ArrayData`;
- `coordinates`: Cartesian atom coordinates in the same known length unit;
- `periodic.fractional_coordinates`: dimensionless fractional coordinates;
- `periodic.pbc`: the three explicit periodic axes;
- `topology_ids`: references to independent `TopologyRecord` entities.

This remains the only persisted crystal identity. `Grid3D`, calculation
records, properties and Blender views continue to reference the same
`Structure.id`.

## Unit-Cell Contract

The authoritative representation is the finite, non-singular lattice matrix.
Its row order is the crystallographic `a`, `b`, `c` vector order. Only
`angstrom` and `bohr` are valid stored length units.

The public pure-core helper `unit_cell_parameters()` derives
`(a, b, c, alpha, beta, gamma)`. Lengths remain in the lattice unit; angles
are degrees. The six parameters are never persisted beside the matrix, so
there is no second value that can drift.

## Coordinate Contract

`fractional_to_cartesian()` computes `fractional @ cell`.
`cartesian_to_fractional()` computes `cartesian @ inverse(cell)`.
Both preserve atom order, reject non-finite or dimensionally invalid arrays
and have no optional dependency.

`validate_periodic_coordinate_consistency()` is the reader/adaptor boundary:
it rejects a non-periodic structure or a Cartesian/fractional mismatch above
the explicit absolute tolerance. It does not run automatically while opening
legacy sidecars, preserving current compatibility and the existing
Cartesian-authoritative topology inference policy.

## Symmetry Contract

File-declared operation strings remain on `PeriodicSiteData`, because exact
source syntax belongs to the source record. Derived symmetry remains
`SymmetryResult`: each rotation is a finite integer unimodular 3 by 3 matrix,
and each translation is a finite dimensionless three-vector. Gemmi or spglib
objects never cross the adapter boundary.

## Periodic Topology Contract

No `PeriodicTopology` registry is added. `TopologyRecord` already represents
`(atom_i, atom_j, cell_offset)` through canonical endpoints and
`bond_lattice_shifts`. Duplicate edges, zero-shift self edges, non-canonical
reversals and out-of-range atom references remain fail-closed.

## Persistence and Reader API

No project or sidecar schema version changes. Existing `Structure`,
`PeriodicSiteData`, `TopologyRecord` and `SymmetryResult` tags remain stable.
Tests serialize a periodic batch through both `.cbq` and the canonical Reader
API document and reopen the committed v0.1 fixture.

The Pre-Gate adds model validation and pure helpers only. CIF/Gemmi, POSCAR,
crystal UI, symmetry expansion and export remain later Wave 2 tasks.

## Error Handling

Type, shape, unit, finiteness, singular-cell and tolerance failures raise
stable `TypeError` or `ValueError` before publication. `QCProject.commit()`
must remain atomic: a rejected crystal/topology batch cannot mutate any
registry.

## Verification

- Focused crystal, topology, project, sidecar, canonical and public API tests.
- Full Blender-Python unit-test discovery.
- `compileall`, documentation contracts and `git diff --check`.
- A fresh process proves importing `ChemBlender.core` does not load `bpy`,
  `gemmi`, `spglib`, `ase` or `pymatgen`.
- Native extension validate/build and ZIP audit; no reader/product smoke is
  added in this gate.
