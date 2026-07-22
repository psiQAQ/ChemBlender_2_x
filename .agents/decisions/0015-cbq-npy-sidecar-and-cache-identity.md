# 0015：`.cbq` v0.1 使用 content-addressed NumPy sidecar

## Status

Accepted for Phase 3 storage foundation.

## Context

Phase 1/2 已产生轨迹、轨道、体网格、能带和费米面数组。把这些数组写进 `.blend`
不符合 ADR 0006；同时当前没有足够 benchmark 支持在 Zarr 与 HDF5 之间做长期选择。

## Decision

`.cbq` v0.1 使用目录、JSON manifest 和 content-addressed `.npy` 数组。写入采用临时文件、
fsync 和同目录 `os.replace`，manifest 最后发布。读取使用固定 model type registry，禁止
manifest 触发动态 import，并以 `allow_pickle=False` 打开数组。

缓存身份分为 source、parser、derivation 和 render 四层。所有参数先 canonicalize；
NaN、Infinity、未知对象和不安全路径直接拒绝，不以 Python `repr` 形成不稳定身份。

Blender scene 仅保存 project UUID、schema version 和 locator。恢复错误映射为明确状态，
不修改或删除现有场景对象。

## Consequences

- 普通 CPython 与 Blender 可使用同一无服务本地格式。
- 数组可 memory-map，并按内容去重；manifest 很小且可审查。
- `.npy` 不提供 chunk/compression，超大数组的随机访问性能需在后续 benchmark 中衡量。
- v0.1 的 manifest type tags 属于内部 versioned schema，不承诺作为通用交换格式。

## Rejected Alternatives

- **立即加入 Zarr 和 HDF5**：增加两套依赖、打包和迁移面，且缺少规模证据。
- **NPZ 单文件**：压缩归档不适合独立数组的 lazy mmap 和原子增量发布。
- **pickle**：不安全、不可审查且跨版本脆弱。
- **隐藏 Mesh 保存数组**：语义不透明且不能被 worker 可靠共享。

## Verification Contract

1. structure/dataset/provenance UUID 与 revision 可完整 round-trip。
2. 重开项目后数组保持 lazy reference，首次数值访问才 memory-map。
3. 相同数组只保存一次；篡改、越界路径、UUID/schema mismatch 被拒绝。
4. manifest 替换失败不破坏上一次有效项目。
5. 四层 cache key 在输入变化时失效，在 map key 顺序变化时保持稳定。
6. Blender 的 missing/incompatible/mismatch 状态不会删除现有对象。
