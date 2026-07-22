# Phase 4 TopologyGraph and critic2 Parser

## Goal

定义分子与周期标量场拓扑的中立 `TopologyGraph`，并从固定 critic2 fixture 提取临界点和连接路径，供 Blender 以点、曲线和属性着色显示。

## Success Criteria

- critical point 具有稳定 ID、kind、position、field value、signature 和 source identity。
- topology path 以端点 ID 和有序 xyz samples 表达，不把曲线塞入 Mesh custom properties。
- parser 对缺失列、未知 CP 类型、非有限数值和悬空路径显式失败或报告 issue。
- 分子与周期坐标、单位和 cell identity 不混淆。
- 至少一个固定 critic2 官方 fixture 或最小摘录通过 golden test，输出可进入 `QCProject`。

## Constraints

- 不在本阶段构建或运行 critic2；只解析已固定版本的文本 fixture。
- 不实现 basin 积分或 surface mesh，除非 fixture 提供稳定、可验证格式。
- 不把 critic2 GPL 源码复制进 Extension；submodule 仅供审阅。
- Blender adapter 先映射 points/curves；高级标签与 basin surface 后置。

## Next Action

从 critic2 官方 tests 选择包含 CP 与 bond path 的小型 `.cro`，以失败测试定义 `TopologyGraph`、parser report 和单位/坐标约定。

## References

- [External adapter v1](../../docs/quantum-visualization/specs/external-analysis-adapter-v1.md)
- [critic2 固定源码](../../submodules/critic2/README.md)
- [语义核心计划](../../docs/quantum-visualization/plans/semantic-core.md)
