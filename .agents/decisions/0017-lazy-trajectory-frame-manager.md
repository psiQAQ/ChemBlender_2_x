# 0017：长轨迹按帧读取与有界 LRU

## Status

Accepted for Phase 3 trajectory playback.

## Context

`.cbq` 已能 lazy mmap FrameSet，但 Blender trajectory adapter 在配置时对完整 frame axis
执行 `numpy.asarray` 和 finite scan，导致长轨迹首次绑定即全部读取。

## Decision

- 纯 core `TrajectoryFrameManager` 只以 `values[index]` 读取请求帧。
- 每帧访问时验证 shape、real 和 finite，缓存只读 float copy；未来坏帧不阻塞当前有效帧。
- manager 使用调用者指定的正整数 LRU 上限，提供有限相邻预取、线性插值和流式区间均值。
- Blender binding 保存 manager 与 frame mapping，继续只更新一个 Mesh。
- 重复 configure、clear、stale Object 和 unregister 都关闭 manager；若 source 提供 `close()`，
  同时释放 mmap。
- v1 不做隐式 PBC unwrap；没有显式 image convention 时最短路径可能改变真实运动。

## Consequences

- 绑定成本与当前帧大小相关，不再与总 frame count 成正比。
- 完整轨迹 finite validation 改为按需 validation；批量审计需显式流式遍历。
- interpolation 是显示工具，不自动代表真实动力学时间插值。

## Verification Contract

1. indexed-only fixture 初始化零访问，读取单帧不调用 source `__array__`。
2. LRU hit/miss/eviction、prefetch、interpolation 和 streaming mean 有纯 CPython tests。
3. NaN/complex 只在相应 frame 访问时拒绝。
4. sidecar LazyNpyArray 在 manager close 后释放 Windows mmap。
5. Blender repeated configure/reload/unregister 保持一个 handler 和一个 Mesh。
