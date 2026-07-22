# Phase 3 Sidecar and Cache Foundation

## Goal

确定 `.cbq` project manifest、array sidecar 和 source/parser/derivation/render hash 契约，
使大型轨迹、网格、轨道和周期数据不再依赖 `.blend` 保存权威数组。

## Success Criteria

- manifest 可以重开并恢复 structure/dataset/provenance identity。
- 大数组通过 lazy reference 保存，`.blend` 只保留 project/dataset UUID 与 display settings。
- source、parser、derivation、render hash 分层且能可靠失效缓存。
- 第一版使用最小可验证后端，不同时实现 Zarr 与 HDF5。

## Constraints

- 不在选定存储格式前添加两个并行 backend。
- 不把 worker server、远程 IPC 与 storage schema 混在同一切片。
- 不覆盖用户源文件，所有缓存可删除并重建。

## Next Action

审阅现有 model/provenance/hash 与 `.blend` metadata，比较 stdlib directory+`.npy`、Zarr、
HDF5 的实际需求；先确定最小 manifest 和 atomic-write contract。

## References

- [大型数据与交互计划](../../docs/quantum-visualization/plans/storage-and-workers.md)
- [费米面 worker 边界](../decisions/0014-fermi-surface-worker-boundary.md)
