# Phase 3 Storage Benchmark and Worker Protocol

## Goal

用代表性 Phase 1/2 数组验证 `.npy` v0.1 的容量与访问边界，并定义本地 worker 的 versioned request/result/error/cancel 协议，使 GBasis、PyProcar 等重计算不阻塞或带崩 Blender。

## Success Criteria

- benchmark 记录 trajectory、Grid3D、MO coefficient 和 projection 的写入、顺序读取、切片访问与文件体积。
- 依据数据决定保留 `.npy` 或只选择 Zarr/HDF5 之一；无证据时不增加 backend。
- worker 请求只传 sidecar locator、UUID/revision、operation/version 和参数，不传可变 Python 对象。
- 成功结果原子发布，失败、取消和进程崩溃不会被标记为成功。
- 协议与 runner 可在普通 CPython 测试，Blender Extension 不以 worker 可用为启用前提。

## Constraints

- 不实现远程 worker、队列服务或计算集群。
- 不在 Blender import/register 时启动进程或安装依赖。
- 不将 GBasis、PyProcar、pymatgen 或 phonopy 打包进主扩展。
- 不把 benchmark 的大型生成数据提交到 Git。

## Next Action

确定可重复的 synthetic benchmark shapes 与记录格式；审阅现有 GBasis/PyProcar adapter 输入边界，然后先写 worker protocol 的失败测试。

## References

- [存储、缓存与 worker 计划](../../docs/quantum-visualization/plans/storage-and-workers.md)
- [`.cbq` v0.1](../../docs/quantum-visualization/specs/cbq-sidecar-v0.1.md)
- [ADR 0015](../decisions/0015-cbq-npy-sidecar-and-cache-identity.md)
