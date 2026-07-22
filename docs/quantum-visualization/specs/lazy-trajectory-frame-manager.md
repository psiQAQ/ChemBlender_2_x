# Lazy trajectory frame manager

## 问题

`.cbq` 可以把 `FrameSet.data.values` 恢复为 memory-mapped lazy array，但现有
`configure_trajectory_view()` 立即执行 `numpy.asarray(values)` 并扫描全部帧。这会在绑定
Blender Object 时触发完整读取，抵消 sidecar 的价值。

## Contract

`TrajectoryFrameManager` 是不依赖 `bpy` 的纯 core 对象：

- 初始化只读取 shape/dtype metadata，不读取 frame values；
- `frame(index)` 只调用一次 `values[index]`，检查 `(atom, xyz)`、real、finite，并缓存只读
  float array；
- LRU `cache_size` 为正整数，任何时刻最多保留指定数量的 frame；
- `prefetch_around()` 只加载有效相邻索引；
- `interpolate()` 对两个已验证 frame 做线性插值；
- `mean()` 按 frame 流式累计，不 materialize frame axis；
- `close()` 清空 LRU，并调用 lazy source 的 `close()`（若存在），释放 Windows mmap。

返回数组为只读，防止 Blender 或调用方修改权威轨迹缓存。

## Blender binding

每个绑定保存 Object、manager、frame start/step 和 prefetch-ahead。frame-change handler：

1. 将 scene frame 映射并 clamp 到 trajectory index；
2. 读取 manager 当前 frame；
3. 换算到 Å 并 `foreach_set` 更新同一个 Mesh；
4. 可选预取后续有限帧。

重复 configure、clear、Object stale、unregister 都先关闭旧 manager。`.blend` 仍只保存
dataset UUID/revision、frame mapping 和 cache settings，不保存完整 frame arrays。

## 非目标

- 不插入隐式 PBC unwrap；
- 不增加 MDAnalysis/MDTraj；
- 不做后台线程预取；
- 不保存 Blender 每帧 Object 或 shape key；
- 不对 interpolation 赋予真实动力学时间含义。
