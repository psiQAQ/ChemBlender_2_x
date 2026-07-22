# Lazy Trajectory Frame Manager

## Result

- 新增纯 core `TrajectoryFrameManager`，按 `values[index]` 读取、验证并缓存单帧。
- 提供有界 LRU、相邻 prefetch、linear interpolation、streaming mean 和显式 close。
- Blender trajectory binding 不再 materialize 完整 FrameSet；重复配置和 lifecycle 会关闭旧 manager。
- `.cbq` LazyNpyArray 实测在 manager close 后解除 mmap 文件锁。

## Evidence

- full suite：218 tests passed，27 optional-dependency skips。
- indexed-only fixture 证明初始化零访问且不调用整体 `__array__`。
- Blender 5.1.2 native validate/build passed。
- 隔离 install、单 Mesh frame update、cache metadata、两轮 reload、RDKit runtime 与 disable lifecycle passed。

## Decision

`.agents/decisions/0017-lazy-trajectory-frame-manager.md`

## Known Limitations

- prefetch 在当前线程同步读取，默认关闭；没有后台 I/O。
- v1 不做 PBC unwrap 或真实时间轴插值。
