# 0034：原始科学实体不可变，拓扑按来源版本化

## Status

Proposed for Wave 1; user direction approved.

## Context

在Blender中编辑导入结构会使轨道、振动、密度和电荷与几何失配。缺键格式又需要推断拓扑，但推断不能伪装成文件事实。

## Decision

Object变换和显示设置不改变科学实体。坐标、元素、原子、键、晶胞、occupancy或Uij变化通过显式Apply Scientific Edits生成派生Structure/Topology和provenance。

拓扑来源按explicit_file、rdkit_sanitized、distance_inferred、user_edited版本化。一个Structure可关联多套TopologyRecord；View明确选择。

## Consequences

- 原结果只绑定原Structure revision。
- 推断参数和可信状态可检查、重算和拒绝。
- 周期/金属连接不强行赋普通共价键级。

## Rejected Alternatives

- 结构完全只读。
- 编辑直接覆盖原Structure。
- 轻微编辑原地更新、重大编辑派生的模糊规则。

## Verification Contract

编辑预览、派生提交、cancel和rollback有测试；父Structure及结果保持不变；导出明确选择原始或派生实体。
