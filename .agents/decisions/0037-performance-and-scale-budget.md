# 0037：2.3.0 分层性能与规模预算

## Status

Proposed for 2.3.0; user direction approved.

## Context

现有lazy trajectory、LOD和sidecar提供基础，但没有产品时延和数据规模门。无目标无法判断UI和缓存是否可发布。

## Decision

即时交互目标：50k atoms、1k frames、128³、10k SDF records。延迟加载目标：250k atoms、100k frames、256³、100k records。启用2s、反馈0.5s、普通view3s、128³ Cube10s、cached frame100ms、browser filter200ms。超过1s操作必须进度、取消和非长期阻塞。

## Consequences

- reader和UI基准成为Wave退出门。
- 大SDF、轨迹和Grid不能全部物化为Object或Python tuple。
- CI追踪趋势，本地reference hardware验证绝对SLA。

## Rejected Alternatives

- 只保证正确性、不定义性能。
- 2.3.0直接承诺百万原子和GPU级数据。

## Verification Contract

固定生成器和真实fixture输出JSON benchmark；阈值回归有明确失败；cancel后无临时/handler泄漏。
