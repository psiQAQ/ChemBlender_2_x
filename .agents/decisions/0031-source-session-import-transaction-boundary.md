# 0031：来源 revision、会话项目与导入事务

## Status

Proposed for Wave 0; user direction approved.

## Context

当前 reader以source hash作revision、UUID4作实体ID，无法表达重复导入、路径移动和内容更新。Quick Import需要预检、用户确认和原子提交。

## Decision

新增SourceRecord、SourceRevision、确定性parse identity、ImportRequest、ImportPreview和ProjectTransaction。首次导入建立会话项目和临时sidecar；保存`.blend`或Save Project时固化为同名`.cbq`并记录相对locator、project UUID、schema和manifest hash。

重复和revision冲突由用户确认，不静默覆盖或复制。批量导入统一预检，确认后一次提交。

## Consequences

- 已有View不会自动跳转到新revision。
- 文件移动可按content hash重链接。
- 数据提交与View创建分开回滚。

## Rejected Alternatives

- 每次导入永远创建副本。
- 相同路径静默覆盖。
- 每个文件直接在源目录旁创建sidecar。

## Verification Contract

同内容、同路径变化和同内容异路径三类冲突均有测试；cancel和失败不改变项目；保存后重开恢复相同source/revision身份。
