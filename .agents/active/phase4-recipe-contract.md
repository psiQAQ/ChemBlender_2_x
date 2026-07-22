# Phase 4 Recipe Contract

## Goal

建立不依赖 `bpy` 的可验证 recipe schema，把量子化学分析工作流描述为语义输入、参数、执行步骤、输出、视图、验证和引用，而不是绑定 UI 按钮或外部程序菜单编号。

## Success Criteria

- recipe 具有稳定 ID/version，并显式声明输入 semantic role、domain、dims 和 unit 约束。
- 参数有类型、默认值与边界；未知参数、缺失输入和单位不兼容会在执行前失败。
- 输出声明、默认 view、validation 和 citation 信息可序列化并严格 round-trip。
- planner 只解析和绑定已有 datasets；不在 Blender 进程内执行外部程序。
- 至少以频率光谱、TDDFT 光谱和 wavefunction field 三类 recipe 验证模型可复用。

## Constraints

- 不直接复制 `quantum-chem-skills` 脚本，也不依赖 Multiwfn 交互菜单编号。
- 不在本阶段提交远程任务、运行外部可执行程序或新增 Python 依赖。
- recipe schema 不替代 `CalculationRecord`、`PropertyDataset` 或 provenance 权威模型。
- 先支持确定性单步派生；DAG 调度、重试和分布式执行后置。

## Next Action

审阅现有 spectrum、wavefunction worker 和 provenance 契约，先写 recipe schema、严格 codec、输入绑定及内置 recipe 的失败测试。

## References

- [工作流、recipe 与 connector 计划](../../docs/quantum-visualization/plans/workflows-and-connectors.md)
- [本地 worker protocol](../../docs/quantum-visualization/specs/local-worker-protocol-v1.md)
- [量子化学语义模型 ADR](../decisions/0003-quantum-chemistry-semantic-model.md)
