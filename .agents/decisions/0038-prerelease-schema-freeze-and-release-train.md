# 0038：2.3.0 采用 Wave 预发布列车并在 beta 冻结 schema/API

## Status

Proposed for 2.3.0; user direction approved.

## Context

一次性开发到final缺少真实反馈；每Wave独立正式小版本又使2.3.0价值过低。当前release scripts仅接受三段数字，需要先验证Blender原生规则。

## Decision

alpha.1对应Wave0、alpha.2 Wave1、beta.1 Wave2、beta.2 Wave3、rc.1 Wave4、最后2.3.0。Beta.1冻结sidecar schema和Reader API v1 RC；RC后只修阻断问题。

任何tag前用Blender 5.1.2原生validator验证prerelease版本字符串。若不接受，在修改tag/release前形成替代数字映射ADR。

## Consequences

- package/release workflow动态派生artifact名。
- prerelease GitHub Release不设latest。
- exact-tag artifact是唯一发布源。

## Rejected Alternatives

- 全部Wave完成后才首次发布。
- 每Wave升级一个正式minor。
- 未验证就修改manifest/tag规则。

## Verification Contract

预发布probe、tag regex、changelog extraction、artifact selection和GitHub prerelease状态均由自动测试覆盖。
