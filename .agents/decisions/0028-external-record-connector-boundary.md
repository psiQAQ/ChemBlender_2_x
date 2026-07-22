# ADR 0028: External Record Connector Boundary

## Status

Accepted — 2026-07-22.

## Decision

QCArchive、AiiDA 与 NOMAD 通过 provider-neutral `chemblender_external_record_request/1` 和 worker operation `external_record.fetch@1` 接入。Blender Extension 不加载服务 SDK，不保存凭据值，不直接执行网络请求。

Connector 只负责定位和获取记录；返回的 QCSchema/CJSON 必须继续通过现有 adapter 归一化。provenance source 使用 redacted provider URI，endpoint、offline path 与 authentication value 不进入 `.cbq`。

## Consequences

- 缺凭据、缺 SDK、记录缺失与记录解析失败有不同稳定错误码。
- 离线 fixture transport 可完整验证 fetch→artifact→adapter→atomic project commit，无需账号或网络。
- 真正启用 provider SDK 前仍需用户选择服务、部署方式与认证策略；该选择不会改变 v1 request/result contract。
