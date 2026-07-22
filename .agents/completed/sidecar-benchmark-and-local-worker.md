# Sidecar Benchmark and Local Worker v1

## Result

- 用 trajectory、Grid3D、MO coefficients 和 projections 四类 representative arrays 完成 `.npy` benchmark；全部通过预设门槛，v1 保留 `.npy`。
- 定义严格 JSON worker protocol v1、entity UUID/revision 输入、结构化 success/error/cancel result 与固定 operation registry。
- runner 在取消复查后提交 `ImportBatch`，原子保存 `.cbq`，重开验证输出后才发布 success。
- 注册 `project.verify@1`、`wavefunction.mo_grid@1` 与 `wavefunction.electron_density_grid@1`。
- Blender client 使用显式外部 Python 启动隐藏子进程，非阻塞 poll/cancel/wait，主扩展不打包 worker 或重型后端。

## Evidence

- core/protocol suite：213 tests passed，27 optional-dependency skips。
- plain CPython subprocess `project.verify@1` 与 extension client launch passed。
- failure、pre/post-operation cancel、output mismatch、atomic replace failure 与 BaseException crash contracts passed。
- Blender 5.1.2 native validate/build passed；隔离 install、worker client import、两轮 reload、RDKit runtime 与 disable lifecycle passed。
- benchmark 环境与数据见 `docs/quantum-visualization/benchmarks/2026-07-22-npy-sidecar-windows.md`。

## Decision

`.agents/decisions/0016-local-worker-v1-and-npy-retention.md`

## Known Limitations

- v1 是一次一进程，不含 daemon、远程 transport 或并发 writer。
- 外部 worker 环境发现/安装 UI 尚未实现，client 接收显式 Python path。
- 不响应取消的 native call 需要终止其专属进程。
