# DensityMatrix、spin density 与 ESP 实现计划

> 依据：[DensityMatrix、spin density 与 ESP 设计](../specs/2026-07-22-wavefunction-observables-design.md)

## Goal

完成 IOData one-RDM/nuclear-charge 导入及 GBasis electron-density、spin-density、ESP 派生闭环。

## Plan

1. 为 `DensityMatrix`、ImportBatch/QCProject registry、引用和矩阵宽度写失败测试。
2. 最小扩展 model；失败提交不得部分写入。
3. 为 IOData recognized/unknown RDM keys、effective nuclear charge、capability/report 写失败测试。
4. 实现 IOData RDM 与 nuclear-charge adapter，并用 water/ch3 FCHK 验证矩阵 shape/role。
5. 为 total/spin density、Cartesian sign、ESP total-only、核奇点、deterministic provenance 写失败测试。
6. 实现 RDM contraction 和 GBasis ESP adapter；复用已有 affine points/shell conversion/version gate。
7. 运行 water/ch3 守恒量、fixed-point ESP、pure-basis convention 与 Blender/OpenVDB 回归。
8. 更新路线图、依赖与活动任务，提交并 fast-forward 合并 main。

## Verification

```powershell
& '<Blender Python>' -m unittest tests.test_density_matrix_model tests.test_iodata_adapter tests.test_wavefunction_observables
& '<Blender Python>' -m unittest discover -s tests -p 'test_*.py'

& .agents/cache/observables-py312/Scripts/python.exe -m unittest tests.test_iodata_adapter tests.test_wavefunction_observables

& '<Blender Python>' -m compileall -q ChemBlender tests
git diff --check
git status --short
```

## Exit Criteria

- IOData raw objects are not retained by normalized entities。
- total/spin RDM、nuclear charge、semantic role、unit、UUID/revision 与 provenance 均可验证。
- water/ch3 数值满足设计基线与容差，spin density 保留负值。
- 核奇点和错误 matrix role 在调用 GBasis 前失败。
- Extension ZIP 不包含 GBasis/IOData/SciPy，Blender lifecycle 继续通过。
