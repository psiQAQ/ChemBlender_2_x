# 0033：核心身份严格、可选数据宽容的质量边界

## Status

Proposed for Wave 0; user direction approved.

## Context

科学文件常含未结束计算、损坏record、未知Cube语义和部分属性。全拒绝降低兼容性；静默恢复会误导用户。现有ParserIssue信息不足。

## Decision

提供Strict、Balanced、Maximum三种模式，默认Balanced。核心结构身份不可恢复时拒绝对应实体；可选物理量缺失时保留可信数据并标记Partial/Ambiguous/Incomplete。新增详细ImportDiagnostic，包含稳定code、原值、规范化值、恢复动作、科学后果和建议。

## Consequences

- UI显示分层badge和摘要，不对普通成功导入弹无意义对话框。
- Ambiguous数据可预览，但不默认进入最终报告。
- 导出Partial/Ambiguous需明确确认。

## Rejected Alternatives

- 任一错误取消整个批次。
- 尽可能导入但只写日志。
- 各reader自行定义不一致状态。

## Verification Contract

每种格式至少有partial/ambiguous/invalid fixture；诊断JSON/Markdown稳定；质量状态传播到View和报告。
