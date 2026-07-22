# Lazy Trajectory Frame Manager Implementation Plan

## Goal

让 `.cbq` FrameSet 在 Blender 中按帧读取并有界缓存，消除绑定时完整 materialization。

## Tasks

1. 用拒绝整体 `numpy.asarray`、记录 `__getitem__` 的 fixture 写 lazy-access 失败测试。
2. 实现 frame validation、LRU hit/eviction、相邻 prefetch、interpolation、streaming mean 和 close。
3. 让 `trajectory_view` binding 使用 manager；重复配置、clear、stale Object 和 unregister 释放 manager。
4. 调整 deferred-invalid-frame smoke：绑定不扫描未来帧，真正访问坏帧时才报错。
5. 验证普通 CPython core tests、完整 suite、native extension build 和隔离 Blender lifecycle。

## Verification

- manager 初始化的 access log 为空；读取一个 frame 不触发 `__array__`。
- cache 永远不超过配置上限，重复读取记录 hit。
- interpolation/mean 数值正确，complex/NaN 只在访问对应 frame 时拒绝。
- Blender smoke 继续只维护一个 Mesh 和一个 frame handler。
