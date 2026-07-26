# 0039：旧 `.blend` 采用检测与显式迁移向导

## Status

Proposed for Wave 4; user direction approved.

## Context

旧scaffold、CIF properties和Geometry Nodes不能直接删除，但打开文件时自动迁移可能破坏场景和科学语义。

## Decision

打开旧场景只检测并提示。用户执行Migrate to Project后，扫描、预览、暂存QCProject、创建新View、验证并确认保存。旧对象移入隐藏`ChemBlender Legacy Backup` collection，默认保留。无法证明来源的字段标记legacy_unverified。

## Consequences

- 2.3.0继续兼容读取旧对象。
- 旧解析代码仅作为bridge，不再扩展。
- 迁移有报告和原子rollback。

## Rejected Alternatives

- 自动原地迁移。
- 两套路径长期并存。
- 不承诺旧项目升级。

## Verification Contract

固定2.1/2.2 `.blend` fixtures覆盖分子、晶体、键、occupancy/Uij和显示设置；失败不改变原文件或旧对象。
