# ADR 0022: Versioned QCSchema exchange

## Status

Accepted on 2026-07-22.

## Decision

- 分别识别 `qcschema_output/1`、`qcschema_atomic_result/2` 与 Molecule 2/3，未知版本明确失败。
- 用 `CalculationMetadata` 承载 driver、model、charge/multiplicity、program 和 error 摘要。
- 用 `QCSchemaEnvelope` 保存完整 JSON；规范化失败或无单位映射的字段通过 `ParserReport` 报告。
- QCSchema geometry 使用 `bohr`，derivative 使用 atomic-unit token。
- QCElemental 固定源码仅用于对照，不进入 Extension 依赖或内部对象图。

## Consequences

同一 `.cbq` 项目可查询常用计算语义并无损保留外部文档。上游 schema 演进由新
adapter 版本处理，不要求迁移 ChemBlender 内部对象到 Pydantic/QCElemental model。
