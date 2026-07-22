# Phase 4 QCEngine Execution

## Goal

在既有 local worker 与 QCSchema exchange 上建立可选 QCEngine/PySCF 计算入口，使 recipe 能提交受控的本地原子计算并将成功或失败结果统一回收到 QCSchema adapter。

## Success Criteria

- 固定并审阅 QCEngine 当前 procedure、program harness、provenance 与 failure model。
- 定义不 import `bpy` 的 worker task，请求只接受严格 QCSchema AtomicInput 与明确 program。
- `QCEngineResult` 成功、program 缺失、输入无效、计算失败和取消均有稳定协议测试。
- PySCF 首个 smoke 使用极小分子和轻量 HF/STO-3G；未安装可选依赖时明确返回 dependency error。
- QCEngine、PySCF 与其依赖不进入 Blender Extension ZIP。

## Constraints

- 不在 Blender 主进程执行 SCF。
- 不实现远程调度、队列或任意 shell 命令。
- 不自动安装 QCEngine/PySCF；真实计算测试仅在已批准外部 worker 环境可用时运行。

## Next Action

固定 QCEngine 官方 release，审阅 `compute`、harness discovery 和 FailedOperation 契约，以失败测试定义 worker request/result 边界。

## References

- [工作流与 connector 计划](../../docs/quantum-visualization/plans/workflows-and-connectors.md)
- [QCSchema 交换边界](../../docs/quantum-visualization/architecture/qcschema-exchange.md)
- [本地 worker 边界](../decisions/0016-local-worker-v1-and-npy-retention.md)
