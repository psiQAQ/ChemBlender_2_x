# Phase 1 Blender adapters 收口实现计划

> 依据：[设计文档](../specs/2026-07-22-phase1-blender-adapters-design.md)

## Goal

完成 normalized molecular results 到单一 Blender Mesh 的 atom scalar/vector、trajectory 和 stick-spectrum linked selection 闭环。

## Plan

1. 为 cclib atom charge/spin typed identity 与 schema 4 写失败测试，再改为 `AtomicProperty`。
2. 扩展 Blender smoke：structure view、stable atom ID、scalar missing mask/range/color 与非法输入。
3. 实现 `dataset_view.py` 的 structure/scalar contract。
4. 在 smoke 中先断言通用 vector attributes、单 modifier 与实例数量。
5. 实现 `vector_arrow_v1`，迁移 vibration adapter 并保持 phase 行为。
6. 先断言 trajectory current-frame、clamp、单 Mesh 和 handler 去重，再实现内存 manager。
7. 先断言 atom boolean selection 与 stick spectrum state/mode identity，再实现 linked selection；broadened selection 必须失败。
8. 更新 ADR、路线图、Blender/reader 计划与 active/completed 状态。
9. 运行两套 full tests、Ruff、compileall、Blender validate/build、短路径 isolated lifecycle、ZIP audit 与 `git diff --check`。
10. 创建阶段提交并快进合并本地 `main`，然后进入 Gemmi/spglib 周期结构基础设施。

## Success Criteria

- cclib charge/spin 可从真实 output 进入带 structure UUID 的 `AtomicProperty`。
- 一个 Mesh 同时保持 stable atom IDs、当前 scalar/vector/trajectory/selection metadata，不保存权威大数组。
- vibration 和一般 atomic vector 共享一个 Geometry Nodes modifier contract。
- Blender frame change 只更新当前 Mesh 坐标；disable/reload 不重复 handler。
- stick UV-Vis/ECD/IR/Raman selection 能定位 source state/mode；broadened sample 明确拒绝直接映射。

## Verify

- Blender Python 与 cclib 1.8.1 environment 完整 `unittest` suite。
- Blender 5.1.2 package smoke 检查真实 Mesh attributes、evaluated instances、handler 与 lifecycle。
- Extension native validate/build 和 ZIP contract audit。
