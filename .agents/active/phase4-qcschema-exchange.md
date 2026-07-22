# Phase 4 QCSchema Exchange

## Goal

建立与内部 versioned schema 解耦的 QCSchema adapter，优先支持可验证的 AtomicResult/Molecule 本地导入导出及 provenance/error 映射。

## Success Criteria

- QCSchema version 由 adapter 显式识别，不把内部模型锁定到某个 QCElemental release。
- molecule geometry、symbols、charge、multiplicity、model、driver、properties、success/error 和 provenance 不静默丢失。
- atomic units 与 ChemBlender unit token 映射明确；未知或不兼容字段进入 ParserReport/raw envelope。
- 至少一个 v1 fixture 完成 import/export 字段级 round-trip；v2 若上游稳定 schema/fixture 可用则加入独立 adapter。
- QCElemental 是 core/worker 可选依赖，不进入 Blender Extension ZIP。

## Constraints

- 不在本阶段通过 QCEngine 启动量子化学程序。
- 不让 Pydantic/QCElemental object 成为内部权威模型。
- 未能无损表达的 extras/native_files 保留 raw envelope 或显式 issue。
- 不伪造尚未稳定的 QCSchema v2 字段。

## Next Action

固定并审阅 QCElemental 当前源码、schema models 与 fixtures，以失败测试定义 v1 AtomicResult/Molecule adapter 和 raw envelope 边界。

## References

- [Reader 与格式能力计划](../../docs/quantum-visualization/plans/readers-and-formats.md)
- [语义核心计划](../../docs/quantum-visualization/plans/semantic-core.md)
- [计算记录与 provenance 调研](../../docs/quantum-visualization/references.md)
