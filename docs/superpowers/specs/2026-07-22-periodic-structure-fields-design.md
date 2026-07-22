# Phase 2 周期结构与 VASP 标量场设计

## Scope

本阶段只建立两条纯 core 数据路径：

1. `ASE Atoms/POSCAR/CONTCAR/extXYZ -> Structure + AtomicProperty`；
2. `pymatgen-core VolumetricData -> Structure + Grid3D`。

Blender 继续只消费 ChemBlender 自有实体。ASE 与 pymatgen-core 均为外部
worker/core 依赖，不加入 Extension manifest 或 ZIP。本阶段不实现 band、DOS、
Fermi surface 或 phonopy。

## Dependency baseline

| Package | Pin | Source | License |
| --- | --- | --- | --- |
| `ase` | 3.29.0 | `submodules/ase` at tag `3.29.0` | LGPL-2.1-or-later |
| `pymatgen-core` | 2026.7.16 | `submodules/pymatgen-core` at tag `v2026.7.16` | MIT |

`pymatgen==2026.5.4` is a metapackage and currently resolves a newer
`pymatgen-core`. ChemBlender pins the package that actually contains
`pymatgen.io.vasp` so the tested runtime and reviewed source stay identical.

## Structure mapping

ASE owns POSCAR/CONTCAR/extXYZ syntax. The adapter creates:

- Cartesian coordinates and lattice in angstrom;
- fractional coordinates, PBC and unit occupancies;
- deterministic site labels derived from element occurrence order;
- `fixed_axes`, a boolean `AtomicProperty(atom, xyz)`, when supported ASE
  constraints are present;
- known scalar/vector per-atom arrays as typed `AtomicProperty` values only when
  their units are defined; every other non-core array or unsupported constraint
  becomes a `ParserReport` issue.

ASE `FixScaled.mask=True` and `FixAtoms` mean a fixed degree of freedom. The
normalized semantic role is therefore `fixed_axes`, not the inverted VASP `T/F`
spelling.

## Volumetric mapping

pymatgen-core owns VASP volumetric syntax. Each physical component becomes its own
`Grid3D`; component names and normalization are recorded in provenance.

| Source | pymatgen key | Semantic role | Stored unit | Normalization |
| --- | --- | --- | --- | --- |
| CHGCAR | `total` | `electron_density` | `inverse_cubic_angstrom` | raw value divided by cell volume |
| CHGCAR | `diff` | `spin_density` | `inverse_cubic_angstrom` | raw value divided by cell volume |
| CHGCAR SOC | `diff_x/y/z` | `magnetization_density_x/y/z` | `inverse_cubic_angstrom` | raw value divided by cell volume |
| PARCHG | same keys | `partial_charge_density` / partial spin roles | `inverse_cubic_angstrom` | raw value divided by cell volume |
| ELFCAR | `total` | `electron_localization_function_alpha` | `dimensionless` | none |
| ELFCAR | `diff` | `electron_localization_function_beta` | `dimensionless` | none |
| LOCPOT | one dataset | `local_potential` | `electron_volt` | none |
| LOCPOT | two datasets | `local_potential_alpha/beta` | `electron_volt` | none |
| LOCPOT SOC | four datasets | scalar plus `magnetic_potential_x/y/z` | `electron_volt` | none |

VASP CHGCAR/PARCHG values integrate as `sum(raw) / ngrid`; division by the cell
volume converts them to the physical spatial density used by `Grid3D`. PAW
augmentation occupancies remain source-only and are reported as unsupported in
this visualization adapter rather than silently discarded.

The grid origin is `(0, 0, 0)`. For shape `(nx, ny, nz)`, step vectors are the
three full lattice vectors divided by `nx`, `ny`, and `nz`. This preserves sheared
and triclinic cells. Every periodic grid stores `structure_id`; project commit
rejects dangling structure references.

## Blender contract

`create_structure_view()` stores the periodic cell matrix and PBC flags as object
metadata while retaining the existing point-mesh contract. `create_grid_volume()`
stores the optional structure UUID beside the dataset UUID. No third-party object
crosses into Blender and no external dependency is imported at extension enable.

## Failure and reporting policy

- missing ASE/pymatgen-core raises a backend-specific dependency error;
- invalid or non-periodic cells fail before entity creation;
- unsupported constraints, per-atom arrays and augmentation data create explicit
  issues;
- unknown volumetric component counts or keys fail rather than guessing spin
  semantics;
- all source hashes, package versions, normalization factors and source keys are
  provenance parameters.
