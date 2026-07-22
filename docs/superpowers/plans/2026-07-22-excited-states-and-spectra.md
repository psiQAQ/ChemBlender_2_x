# 激发态、UV-Vis/ECD 与 transition reference 实现计划

> 依据：[设计文档](../specs/2026-07-22-excited-states-and-spectra-design.md)

## Goal

完成 cclib excited-state ingestion、typed configuration/reference model 和 UV-Vis/ECD spectrum 派生闭环。

## Plan

1. 用 cclib 1.8.1 属性表、parser 源码和四个真实 fixture 固化 shape、unit、spin/configuration 与缺失基线。
2. 先为 `ExcitationContribution`、`ExcitedStateReferences`、`ExcitedStateSet` 与项目引用写失败测试。
3. 实现最小模型，并把 `Spectrum` source/selection contract 泛化到振动和电子激发。
4. 为完整、partial、invalid cclib excited-state data 写失败测试。
5. 实现 adapter，升级 schema version，保留 unknown rotatory unit 为 ambiguous。
6. 为 UV-Vis/ECD stick、Gaussian、Lorentzian、signed intensity、FWHM 与 provenance 写失败测试。
7. 抽取/复用通用 peak-normalized spectrum kernel，不增加依赖。
8. 更新 ADR、semantic/reader/Blender/roadmap、active/completed 文档。
9. 运行两套 full tests、Ruff、compileall、Extension validate/build、短路径 isolated lifecycle、ZIP audit 与 `git diff --check`；提交并快进合并 `main`。

## Success Criteria

- Gaussian 16/09 与 ORCA TD/ADC2 fixture 的 state count、energy、configuration 和 optional coverage 与 cclib 一致。
- unknown ECD unit 明确产生 ambiguous dataset；UV-Vis 保持 dimensionless complete dataset。
- configuration coefficient 不被当作 probability；spin/index/reference 均可验证。
- 通用 `Spectrum` 不混淆 mode/state source UUID。
- cclib、SciPy 和 submodule 不进入 Extension ZIP。

## Verify

- Blender Python 与隔离 cclib 1.8.1 environment 的完整 `unittest` suite。
- `compileall`、Ruff、`git diff --check`。
- Blender 5.1.2 native validate/build、短路径 isolated lifecycle 和 ZIP contract audit。
