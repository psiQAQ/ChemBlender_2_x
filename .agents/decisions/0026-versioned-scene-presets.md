# 0026：Versioned publication scene presets

## Status

Accepted for Phase 4 visualization automation.

## Context

现有 Blender adapters 各自保存 dataset metadata，但缺少跨结构、表面、光谱和周期 plot 的
可重放显示计划。直接保存 Blender objects 无法可靠验证输入 revision 和参数变化。

## Decision

- scene preset 是独立于 `bpy` 的 versioned definition/plan。
- binding 只引用 project entity UUID/revision；publication plan 只接受 complete datasets。
- settings 使用严格名称与类型，所有 bindings/settings 进入 render identity。
- recipe view 只通过显式映射选择 preset，不按名称猜测。
- preset 声明 adapter contracts；尚无 Blender 实现的 surface property 保持 plan-only。

## Consequences

- 同一 plan 可由 Blender application layer 重放，也可作为 report artifact 审计。
- revision、isovalue、色域、mode/state selection 或 energy reference 改变都会失效 render identity。
- preset 不包含相机美学决策，也不宣称默认 isovalue 对所有体系物理最优。

## Verification Contract

1. builtin definition 可严格 JSON round-trip，且不含 callable/Blender object。
2. stale/wrong/partial binding 与 unknown/invalid setting 被拒绝。
3. 双网格 affine、spectrum source 和 band/DOS structure linkage 有专门测试。
4. entity revision 或 setting 变化会改变 render identity。
