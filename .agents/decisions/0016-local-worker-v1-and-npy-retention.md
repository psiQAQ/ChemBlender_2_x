# 0016：本地 worker v1 与 `.npy` 保留决策

## Status

Accepted for Phase 3 local worker foundation.

## Context

GBasis、PyProcar 等任务包含重型可选依赖和长时间数值计算，不应在 Blender UI 进程中
同步运行。`.cbq` v0.1 已提供原子 sidecar 边界，但尚缺任务协议、取消和失败语义。

同时，是否需要 Zarr/HDF5 必须以当前数组 workload 为依据，不能因“可能很大”同时引入
两套 backend。

## Decision

- worker v1 使用严格 JSON request/result 和一次一进程模型。
- request 只传 sidecar locator、project/entity UUID/revision、operation/version 与 JSON 参数。
- operation 由固定 registry 注册，request 不能指定 module/class 或触发动态 import。
- operation 返回内存中的 `ImportBatch`；runner 在取消复查后 commit，并通过 `.cbq` 原子
  manifest 发布。重开并复验输出后才原子写 `success` result。
- Blender client 使用显式外部 Python 启动隐藏子进程，日志和协议文件保存在任务目录；
  Extension import/register 不探测、不安装也不启动 worker。
- worker v1 注册 `project.verify@1`、`wavefunction.mo_grid@1` 和
  `wavefunction.electron_density_grid@1`。GBasis 仍为 worker-only optional dependency。
- 2026-07-22 Windows benchmark 的四类 `.npy` sample 全部通过预设门槛，因此 v1 保留
  `.npy`，不增加 Zarr/HDF5。

## Consequences

- Python exception、取消与输出 mismatch 有结构化非成功结果；interpreter crash 不留下结果。
- 不响应取消的 native call 仍需由 client 终止其专属进程，但不会带崩 Blender。
- worker package/environment 的安装和发现 UI 尚未定义；client 必须接收显式 Python path。
- `.npy` 仍无 compression/chunking；真实数组超过触发门槛后必须重新 benchmark。

## Rejected Alternatives

- **Blender 内线程运行计算**：Python/native 库可能阻塞 UI，崩溃域也未隔离。
- **常驻 daemon/queue**：本地一次一任务尚不需要服务生命周期和并发锁。
- **request 指定 Python callable**：形成代码执行边界，无法稳定 version negotiation。
- **立即采用 Zarr/HDF5**：当前 benchmark 没有显示足以承担新依赖的瓶颈。

## Verification Contract

1. protocol round-trip 严格拒绝 unknown field、NaN、重复 input 与不安全 artifact path。
2. success 只在 output entity UUID/revision 重开复验后发布。
3. failure、执行前/执行后 cancel、output mismatch 和 BaseException crash 有独立测试。
4. `project.verify@1` 在普通 CPython subprocess 中运行。
5. 默认 registry 和 Blender client import 不加载 GBasis/PyProcar/pymatgen。
