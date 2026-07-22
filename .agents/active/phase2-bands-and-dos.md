# Phase 2 Band Structure and Density of States

## Goal

建立 ChemBlender 自有 `BandStructure`、`DensityOfStates` 与 projection schema，
用 pymatgen-core adapter 导入 VASP band/DOS 数据，并与 periodic structure 共享稳定 UUID。

## Success Criteria

- band energies 保留 spin、kpoint、band、occupancy、Fermi level、reciprocal lattice、
  labels 与 path branches。
- total DOS/PDOS 保留 spin、energy、atom、orbital 维和明确的能量参考。
- projections 不因缺字段而伪造；parser capability/issue 明确反映来源支持度。
- 最小 2D plot/linked-selection adapter 可在 Blender 内选择 band/kpoint 或 DOS
  component，并回写 dataset identity。
- 普通 CPython、真实 pymatgen objects/fixtures、Blender lifecycle 与 ZIP audit 通过。

## Constraints

- 本阶段不实现 PyProcar Fermi surface 或 phonopy。
- 不把 matplotlib/pymatgen-core 加入 Blender Extension；2D 输出先采用轻量自有数据/Curve contract。
- 先稳定 schema 与能量零点，再讨论 sumo 风格和 publication presets。

## Next Action

核对 pymatgen-core 2026.7.16 的 `BandStructureSymmLine`、`CompleteDos`、VASP
`Vasprun`/`BSVasprun` 字段约定；先写 spin/kpoint/band/projection 和 energy-reference
模型测试，再实现 adapters。

## References

- [周期电子结构计划](../../docs/quantum-visualization/plans/periodic-electronic-structure.md)
- [周期结构与标量场决策](../decisions/0011-periodic-structure-and-vasp-grid-boundary.md)
