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

对 ORBKIT 与 IOData+GBasis/Grid 做最小可运行比较，选择首个 MO/density 网格求值后端，并设计 `OrbitalSet → Grid3D` 派生 provenance 与数值基准。

## Completed

- 已选择标准库原生 Cube parser，不提前引入 IOData 或扩展 `Grid3D` 轴标签模型。
- Cube reader 已实现斜网格、bohr 坐标、`NVAL`/`DSET_IDS` 多 dataset 去交错、dataset ID provenance，以及显式 semantic/value-unit ambiguity。
- Blender 5.1.2 bundled `openvdb` 已通过斜 transform、写入和 Volume 重新加载探针；首版不实现无证据需要的第二套 mesh backend。
- OpenVDB adapter 已实现显式 cache path、float32 派生 cache、斜 affine transform、bohr 到 angstrom 换算、Volume 创建和 dataset 身份恢复属性。
- Blender lifecycle smoke 现在使用 `--python-exit-code 1`，Python traceback 不再被 exit code 0 静默放过。
- cclib 1.8.1 已作为外部 core adapter 接入；Gaussian 16 与 ORCA 4.1 fixture 可归一化为结构、SCF 能量、原子布居、计算状态和 provenance。
- `submodules/cclib` 已固定官方 v1.8.1 commit，仅用于源码审阅与 integration fixture，不进入 Blender Extension。
- `BasisSet`/`OrbitalSet` 已支持 restricted、unrestricted 和 generalized channel，保留 shell contraction、Cartesian/pure convention、spin-basis 维度与原子单位。
- IOData 1.0.1 adapter 已通过 restricted FCHK、unrestricted FCHK 和 Molden fixture；上游 convention 修正警告进入 `ParserReport`。
- `submodules/iodata` 已固定官方 v1.0.1 commit，仅用于源码审阅与 integration fixture，不进入 Blender Extension。

## References

- [持续开发路线图](../../docs/quantum-visualization/roadmap.md)
- [波函数与体网格计划](../../docs/quantum-visualization/plans/wavefunction-and-grids.md)
- [Reader 与格式能力计划](../../docs/quantum-visualization/plans/readers-and-formats.md)
- [Grid3D 与单位约定 ADR](../decisions/0004-grid3d-and-units.md)
- [Reader capability contract ADR](../decisions/0005-reader-capability-contract.md)
- [Cube reader 设计](../../docs/superpowers/specs/2026-07-22-cube-reader-design.md)
- [Cube reader 实现计划](../../docs/superpowers/plans/2026-07-22-cube-reader.md)
- [Grid3D 到 OpenVDB Volume adapter 设计](../../docs/superpowers/specs/2026-07-22-grid-volume-adapter-design.md)
- [Grid3D OpenVDB Volume adapter 实现计划](../../docs/superpowers/plans/2026-07-22-grid-volume-adapter.md)
- [cclib adapter 设计](../../docs/superpowers/specs/2026-07-22-cclib-adapter-design.md)
- [cclib adapter 实现计划](../../docs/superpowers/plans/2026-07-22-cclib-adapter.md)
- [IOData 波函数语义设计](../../docs/superpowers/specs/2026-07-22-iodata-wavefunction-design.md)
- [IOData 波函数实现计划](../../docs/superpowers/plans/2026-07-22-iodata-wavefunction.md)
