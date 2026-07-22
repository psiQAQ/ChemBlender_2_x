# 0025：确定性 analysis report manifest

## Status

Accepted for Phase 4 local report output.

## Context

Project、recipe、provenance 与 worker artifact 已可追踪，但缺少一个适合审阅和归档的
轻量报告入口。报告不能复制大型数组，也不能把失败/歧义数据描述为有效结果。

## Decision

- 采用 `chemblender_analysis_report/1` 纯 JSON manifest 和确定性 Markdown renderer。
- calculation selection 自动纳入其 dataset；provenance 按 parent closure 收集。
- recipe plan、citations 和 artifact hash 进入报告，数组值不进入报告。
- 不写 timestamp、本机绝对路径或网络内容；目标 report bundle 不覆盖已有目录。
- failed calculation 使报告为 `failed`；其他 incomplete/ambiguous 数据使报告为 `incomplete`。

## Consequences

- 报告可以字段级 diff 和 content hash，适合自动化归档。
- 报告只陈述数据身份/状态，不替代领域解释或论文叙述。
- 图像与场景只作为外部 artifact 引用；文件移动后需重新生成报告。

## Verification Contract

1. 输入顺序变化不改变 JSON/Markdown。
2. stale recipe binding、未知 entity、缺失/越界 artifact 被拒绝。
3. failed/ambiguous 状态在 manifest 和 Markdown 中显式出现。
4. bundle 写入不覆盖已有结果；core import 不加载 `bpy`。
