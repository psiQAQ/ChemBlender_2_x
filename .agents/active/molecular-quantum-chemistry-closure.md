# Molecular Quantum Chemistry Closure

## Goal

完成 Phase 1 分子量子化学最小闭环：量化输出、波函数和体网格进入 normalized model，并由 Blender 视图消费。

## Success Criteria

- Cube 多 dataset 与非正交网格完整进入 `Grid3D`，不静默截断。
- Gaussian 或 ORCA fixture 经 cclib adapter 进入结构、能量和至少一种计算属性。
- FCHK 或 Molden fixture 经 IOData adapter 进入 basis/orbital 语义对象。
- 至少一个 normalized grid 在 Blender 中生成可重建视图，并保留来源与派生关系。

## Constraints

- 先完成无第三方依赖的 Cube reader 契约，再申请新增 cclib/IOData 依赖。
- 不在 Blender import、`register()` 或 enable 时安装包。
- 第三方对象只能由 adapter 转换，不能成为权威模型。
- 大型数组和依赖打包方案分别经过后续决策，不提前实现 worker 或 sidecar backend。

## Next Action

按已批准的实施计划实现最小 Cube reader：完整三个 step vectors、`NVAL`/`DSET_IDS` 多 dataset、bohr 坐标和显式 grid semantic/value-unit ambiguity。

## Completed

- 已选择标准库原生 Cube parser，不提前引入 IOData 或扩展 `Grid3D` 轴标签模型。

## References

- [持续开发路线图](../../docs/quantum-visualization/roadmap.md)
- [波函数与体网格计划](../../docs/quantum-visualization/plans/wavefunction-and-grids.md)
- [Reader 与格式能力计划](../../docs/quantum-visualization/plans/readers-and-formats.md)
- [Grid3D 与单位约定 ADR](../decisions/0004-grid3d-and-units.md)
- [Reader capability contract ADR](../decisions/0005-reader-capability-contract.md)
- [Cube reader 设计](../../docs/superpowers/specs/2026-07-22-cube-reader-design.md)
- [Cube reader 实现计划](../../docs/superpowers/plans/2026-07-22-cube-reader.md)
