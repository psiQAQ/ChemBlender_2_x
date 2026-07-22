# ADR 0009: Phase 1 Blender Dataset Contract

## Status

Accepted on 2026-07-22.

## Context

Phase 1 已有结构、原子属性、轨迹、振动、激发态和光谱语义，但缺少统一的 Blender 身份与属性契约。旧路径会让每种物理量各自创建对象或节点，并可能把权威数组写入 `.blend`。

## Decision

- normalized `Structure.id` 是 Mesh 与所有 atom-domain dataset 的关联键；`cbq_atom_id` 使用稳定的 zero-based integer POINT attribute。
- 原子标量使用 `cbq_atom_scalar`、`cbq_atom_scalar_valid` 与 `colour`；dataset UUID、revision、unit、semantic role 和显示范围保存在 object metadata。
- 原子矢量和振动共享 `cbq_vector`、`cbq_vector_magnitude` 与 `vector_arrow_v1`，一个 Mesh 只挂一个 instanced-arrow modifier。
- `FrameSet` 保留在 Python binding 中，`frame_change_post` 只更新单个 Mesh 的当前坐标；完整轨迹不写入 Mesh 或 custom properties。
- 只有 stick spectrum sample 能一对一映射 state/mode；broadened sample 不被猜测为单一来源实体。
- cclib schema 4 将 charge/spin 归一化为带 `structure_id` 的 `AtomicProperty`。多帧 gradient 在 frame-aligned vector 语义确定前继续显式报告 unsupported。

## Consequences

- Blender adapters 可以组合复用 normalized datasets，并通过 UUID 拒绝跨结构误用。
- disable/reload 必须去重并移除 trajectory handler；重开恢复、lazy trajectory 和 sidecar session 延后到 Phase 3。
- 当前交付的是可调用 adapter 和真实 scene contract，不包含最终面板、2D plot widget 或持久 session manager。
