# Phase 3 Lazy Trajectory Frame Manager

## Goal

消除 Blender trajectory 配置阶段对完整 `FrameSet` 的 eager materialization，以按帧访问和有限缓存支持 `.cbq` 长轨迹，并提供可测试的插值与区间均值。

## Success Criteria

- `configure_trajectory_view()` 不调用 `numpy.asarray(frames.data.values)` 读取全部轨迹。
- frame manager 只读取请求帧，使用有界 LRU，并可预取相邻帧。
- 插值和区间均值保持 shape/unit、拒绝 non-finite/complex frame。
- frame-change handler 继续只更新一个 Mesh，不创建每帧 Object。
- lazy sidecar 关闭、对象删除、disable/reload 不留下 stale binding 或文件锁。

## Constraints

- 不在本切片加入 MDAnalysis/MDTraj 依赖或新轨迹格式。
- 不把所有帧复制进 Blender datablock。
- 不假设跨周期边界的最短路径；PBC unwrap 需要显式 cell/convention 后再加入。
- 缓存大小必须有界且由调用者可配置。

## Next Action

为不支持整体 `numpy.asarray`、只记录 `__getitem__` 的 array fixture 写失败测试；建立纯 core frame manager，再改造 Blender binding。

## References

- [存储、缓存与 worker 计划](../../docs/quantum-visualization/plans/storage-and-workers.md)
- [Blender 可视化计划](../../docs/quantum-visualization/plans/blender-visualization.md)
- [`.cbq` v0.1](../../docs/quantum-visualization/specs/cbq-sidecar-v0.1.md)
