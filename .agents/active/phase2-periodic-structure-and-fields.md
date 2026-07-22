# Phase 2 Periodic Structure and Scalar Fields

## Goal

用 ASE/pymatgen adapters 将 POSCAR/CONTCAR 与 VASP 周期标量场归一化到现有 `Structure.periodic`、`Grid3D` 和 provenance 契约，并建立周期结构到 Blender structure/volume view 的最小闭环。

## Success Criteria

- ASE adapter 支持 POSCAR/CONTCAR 与 extXYZ 的 lattice、species、fractional/cartesian coordinates、PBC 和 selective-dynamics/原子数组报告。
- pymatgen adapter 支持 CHGCAR/PARCHG、ELFCAR、LOCPOT 的物理语义、单位、spin/dataset 维和完整周期网格轴。
- 周期 grid 与 structure 共享稳定 UUID；网格 origin/step vectors 与晶胞严格一致，不假设正交晶胞。
- Blender 可加载周期 structure 与 OpenVDB volume，并保留 source dataset identity；Extension 不打包 ASE/pymatgen。
- 真实小型 VASP fixtures、普通 CPython tests、Blender 5.1.2 lifecycle 与 ZIP audit 通过。

## Constraints

- 先完成 structure/grid adapter，不提前实现 band/DOS、phonopy 或 PyProcar。
- ASE 与 pymatgen 只在独立 core/worker 环境 late import；新增依赖、许可证和固定 submodule 必须同步记录。
- selective dynamics 与来源专属字段不能静默丢弃；未归一化字段进入 `ParserReport`。

## Next Action

核对 ASE、pymatgen 当前官方版本/API/许可证和 VASP fixture 许可，评估以 ASE 还是轻量自有 POSCAR reader 作为首选结构入口；随后先写 periodic structure 与 scalar-grid 字段映射测试。

## References

- [持续开发路线图](../../docs/quantum-visualization/roadmap.md)
- [周期电子结构计划](../../docs/quantum-visualization/plans/periodic-electronic-structure.md)
- [已完成的晶体基础设施](../completed/crystal-foundation.md)
