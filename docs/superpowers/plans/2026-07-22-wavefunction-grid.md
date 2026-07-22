# 波函数派生 Grid3D 实现计划

> 依据：[波函数派生 Grid3D 设计](../specs/2026-07-22-wavefunction-grid-design.md)

## Goal

以 GBasis 0.1.0 实现 restricted/unrestricted MO 与电子密度的 affine `Grid3D` 派生，并接入现有 OpenVDB adapter。

## Plan

1. 固定 GBasis v0.1.0 submodule，记录 Python 3.12/3.13、NumPy、许可证和候选后端比较。
2. 先写 grid 参数、引用、依赖延迟加载、MO channel/index、occupation 与 generalized 拒绝测试。
3. 实现 normalized basis 到 GBasis segmented shell 的 convention-preserving bridge。
4. 实现 affine points、MO/density 求值、单位、deterministic derivation hash 和 provenance。
5. 用真实 restricted FCHK 做轨道 norm 与 10-electron 密度守恒集成测试。
6. 将派生 density/MO grid 送入现有 OpenVDB adapter，验证 metadata、Extension build 和 Blender lifecycle。
7. 更新 dependency/reference/capability 文档，提交并 fast-forward 合并 main。

## Verification

```powershell
& '<Blender Python>' -m unittest tests.test_wavefunction_grid
& '<Blender Python>' -m unittest discover -s tests -p 'test_*.py'

& .agents/cache/gbasis-py312/Scripts/python.exe -m unittest tests.test_wavefunction_grid

& '<Blender Python>' -m compileall -q ChemBlender tests
git diff --check
git status --short
```

## Exit Criteria

- 标准环境导入 core 不加载 GBasis/SciPy；缺依赖时给出专用错误。
- 真实 FCHK 通过 MO norm 与电子数守恒检查。
- convention、non-orthogonal steps、channel/index、单位、parent IDs 和 derivation hash 均有测试。
- generalized、缺 occupation、非法引用和错误单位均不产生部分结果。
- Extension ZIP 不包含 GBasis/IOData submodule 或外部 dependency。
