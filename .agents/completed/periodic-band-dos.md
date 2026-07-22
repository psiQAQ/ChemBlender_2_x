# Phase 2 Periodic Band Structure and DOS

## Result

- 新增 `BandStructure`、`DensityOfStates`、`BandPathBranch` 与 `EnergyReference` 模型。
- 完成 pymatgen-core `BandStructureSymmLine`、`CompleteDos` 和 `vasprun.xml` adapter。
- 保留 spin、kpoint、band、occupation、Fermi level、reciprocal lattice、branch、atom 与 orbital axes。
- band/DOS 与 periodic structure 共享 UUID；缺失 occupation/projection 显式报告。
- 新增 Blender Curve 映射、Fermi shift、β-DOS mirror 和 linked-selection metadata。

## Verification Evidence

- pymatgen-core 2026.7.16 worker 环境：175 tests passed，20 skipped。
- Blender Python：175 tests passed，25 skipped。
- Blender 5.1.2 Extension validate/build passed。
- 短路径隔离 profile lifecycle passed；band/DOS Curve、selection、RDKit 和重复 enable/disable 均通过。
- 在退出测试进程、冷恢复 shared wheel 并保存启用状态后，第二个全新 Blender 进程确认扩展、RDKit 与 electronic plot 模块可用。
- pinned RDKit wheel SHA-256 为 `f8bd59b24e128c9c70c975bfb1920cf610ba3096439a24ca2850eb861e767c48`。

## Known Limits

- 当前 reader 使用 regular-path `Vasprun.get_band_structure(line_mode=False)`；高对称 line-mode 需要匹配 KPOINTS 来源后再提供 UI 选项。
- 本阶段没有真实大型 `vasprun.xml` fixture；adapter 的轴与数值契约由真实 pymatgen 对象覆盖。
- PyProcar Fermi surface、publication styling 和 phonopy 属于后续切片。
