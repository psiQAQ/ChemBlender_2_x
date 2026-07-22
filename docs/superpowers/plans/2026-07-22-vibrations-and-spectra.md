# 振动、IR/Raman 光谱与 Blender 模态实现计划

> 依据：[设计文档](../specs/2026-07-22-vibrations-and-spectra-design.md)

## Goal

完成 cclib vibration ingestion、normalized mode/spectrum model、确定性谱线展宽和 Blender 当前模态动画闭环。

## Plan

1. 用 cclib 1.8.1 官方属性表和 Gaussian/ORCA 真实 fixture 固化字段、shape、unit 与缺失基线。
2. 先为 `VibrationalModeSet`、`Spectrum`、项目引用和非法 shape/unit 写失败测试。
3. 以最小 `PropertyDataset` 子类实现两个模型，不增加独立 registry。
4. 为 cclib frequency/displacement/IR/Raman/reduced-mass/force-constant/symmetry mapping 写失败测试。
5. 实现 adapter，更新 calculation dataset IDs、capability 和逐字段 `ParserReport`。
6. 为 stick、Gaussian、Lorentzian、signed frequencies、FWHM 和 provenance 写失败测试。
7. 用 NumPy 实现 peak-normalized spectrum derivation，不增加依赖。
8. 为 Blender named-vector attributes、单一 instance node group 与正弦坐标更新增加 runtime smoke。
9. 更新语义、reader、Blender、roadmap、active/completed 文档。
10. 运行 core/worker tests、Ruff、compileall、Extension validate/build、短路径隔离 lifecycle、ZIP audit 与 `git diff --check`；提交并快进合并 `main`。

## Success Criteria

- 四个真实 Gaussian/ORCA fixture 均映射 54 modes，parser coverage 与真实字段一致。
- 负频率不被取绝对值或静默过滤；所有数组有明确 unit/dims。
- IR/Raman stick 与 broadened spectrum 可从同一 mode set 重建，FWHM 数值测试通过。
- Blender 不创建 per-arrow/per-frame Object，权威结构坐标不被修改。
- cclib/Scipy 不进入 Extension manifest 或 ZIP。

## Verify

- Blender Python 与隔离 cclib environment 的完整 `unittest` suite。
- `compileall`、Ruff、`git diff --check`。
- Blender 5.1.2 native Extension validate/build、短路径 isolated lifecycle 和 ZIP contract audit。
- 真实 `user_default` 仅在交互 Blender 未加载 ChemBlender/RDKit 时覆盖。
