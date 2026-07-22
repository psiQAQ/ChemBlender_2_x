# Phase 1 Blender Adapter Closure

## Goal

用共享 dataset/entity ID 将 Phase 1 已有的结构、原子标量、原子矢量、优化轨迹和激发态选择映射到 Blender，形成从 Gaussian/ORCA normalized data 到可交互场景的最小闭环。

## Success Criteria

- 原子标量写入 POINT-domain named float attribute，并保留 dataset ID、unit、method、范围与缺失值策略。
- force/gradient/vibration 等原子矢量复用单一 instanced-arrow 节点契约，不为每个箭头创建 Object。
- `FrameSet` 只保留一个当前帧 Mesh，切帧更新 position；权威轨迹数组不写入 `.blend` Mesh。
- state/mode/atom selection 使用稳定整数/UUID 映射；光谱选择可定位对应 state，且不会混淆不同 dataset。
- Blender 5.1.2 隔离 lifecycle、真实 Geometry Nodes 求值和 core tests 通过。

## Constraints

- 本阶段先提供可调用 adapter 与最小 scene contract，不建立完整产品 UI 或大型 sidecar session manager。
- 不复制 parser 逻辑，不把 cclib/IOData/GBasis 加入 Extension。
- 轨迹缓存、插值、长轨迹 lazy loading 和重开恢复留给 Phase 3；当前先验证单 Mesh 当前帧原则。

## Next Action

盘点现有 structure Mesh、`atom_property`、`vibration_view`、`FrameSet` 与 scene custom-property 约定，写出原子标量/矢量/轨迹/linked-selection 的最小统一 adapter 设计和真实 Blender 验收场景。

## References

- [持续开发路线图](../../docs/quantum-visualization/roadmap.md)
- [Blender 可视化计划](../../docs/quantum-visualization/plans/blender-visualization.md)
- [已完成的激发态闭环](../completed/excited-states-and-spectra.md)
