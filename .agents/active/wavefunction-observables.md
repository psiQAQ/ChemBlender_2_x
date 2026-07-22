# Wavefunction Observables

## Goal

将 IOData 一阶密度矩阵归一化为 ChemBlender `DensityMatrix`，并用 GBasis 从同一权威数据派生 electron density、spin density 与 electrostatic potential `Grid3D`。

## Success Criteria

- `DensityMatrix` 明确记录 basis、matrix role、spin semantics、dims、unit、source calculation 与 provenance，restricted/unrestricted 不靠 key 名字符串在 Blender 层推断。
- IOData FCHK 的 `one_rdms` 映射到 normalized model；缺失 total/spin/post-SCF matrix 时显式报告。
- 真实 restricted FCHK 的 RDM density 与 occupation-based density 在相同点阵上一致，并通过电子数守恒检查。
- 真实开放壳层 fixture 生成可正可负的 `spin_density`，其积分与 spin polarization 一致。
- ESP 同时包含电子与核贡献，在避开核坐标的固定点与 GBasis 官方接口/独立公式核对。
- density、spin density、ESP 保持独立 semantic role；ESP mapped on density surface 不被误写为 ESP 等值面。
- core 不依赖 `bpy`，worker 依赖仍不进入 Blender Extension。

## Constraints

- 先支持实 AO-basis 1-RDM；complex/generalized spinor 和 2-RDM 不进入本切片。
- 不从 Blender datablock 重建 density matrix。
- 不为 ESP 单独引入 Grid；复用现有 affine points 与 GBasis backend。
- 原子核奇点必须显式排除或报告，不能产生未标记的 infinity/NaN grid。

## Next Action

核对 IOData `one_rdms` key/基组 convention 与 GBasis `evaluate_density`、`electrostatic_potential` 的矩阵方向和核贡献契约；用 water/ch3 FCHK 建立 RDM、spin 与 ESP 数值基线。

## References

- [持续开发路线图](../../docs/quantum-visualization/roadmap.md)
- [波函数与体网格计划](../../docs/quantum-visualization/plans/wavefunction-and-grids.md)
- [已完成的波函数派生场](../completed/wavefunction-derived-fields.md)
- [GBasis worker 后端决策](../decisions/0007-wavefunction-grid-backend.md)
