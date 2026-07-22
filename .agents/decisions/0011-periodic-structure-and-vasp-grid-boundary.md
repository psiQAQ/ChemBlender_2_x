# 0011：周期结构与 VASP 标量场边界

## Status

Accepted for Phase 2 periodic structure and scalar-field ingestion.

## Context

Gemmi/spglib 已建立 CIF 与对称性基础，但 POSCAR/CONTCAR、extXYZ 和 VASP
volumetric outputs 仍需要外部 parser。周期标量场还必须与结构共享 identity，
并明确 CHGCAR raw values、ELFCAR spin channels 和 LOCPOT components 的物理语义。

## Decision

- ASE 3.29.0 负责 POSCAR/CONTCAR 与 extXYZ syntax；selective dynamics 归一化为
  `fixed_axes(atom, xyz)`。
- pymatgen-core 2026.7.16 负责 CHGCAR/PARCHG、ELFCAR 与 LOCPOT syntax。
- CHGCAR/PARCHG raw values 除以 cell volume，保存为
  `inverse_cubic_angstrom`；ELFCAR 保持 dimensionless，LOCPOT 保持 eV。
- 每个物理 component 是独立 `Grid3D`；SOC vector components 不与 pymatgen
  派生的 magnitude 混为一个 dataset。
- `PeriodicSiteData.pbc` 明确保存三个方向；`Grid3D.structure_id` 建立 grid 到
  periodic structure 的 project-level reference。
- ASE/pymatgen-core late import，只存在于外部 core/worker 环境。

## Consequences

- triclinic grid 使用完整 lattice rows / grid shape 作为 step vectors。
- PAW augmentation、未知 ASE arrays 和 constraint types 进入 `ParserReport`，不静默丢弃。
- Blender structure/volume object 可以共享 structure UUID，但大型数组仍不写进 `.blend`。
- band/DOS、phonopy 与 Fermi surface 可复用同一 periodic structure identity。

## Verification Contract

1. POSCAR selective-dynamics 与 extXYZ partial PBC fixture 通过。
2. CHGCAR 数值积分恢复 raw `sum / ngrid` 的电子数。
3. collinear/SOC、ELFCAR α/β 和 LOCPOT spin semantics 有独立断言。
4. project 拒绝 dangling periodic grid structure reference。
5. Extension ZIP 不包含 ASE、pymatgen-core 或 submodules，Blender lifecycle 真实通过。
