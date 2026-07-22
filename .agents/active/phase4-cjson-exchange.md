# Phase 4 CJSON Exchange

## Goal

建立 Avogadro CJSON 的轻量项目交换 adapter，将结构、键、选择以及已支持的轨道、振动、光谱和表面引用映射到 ChemBlender 语义对象，同时无损保留未知字段。

## Success Criteria

- 固定并审阅 Avogadro/OpenChemistry 当前 CJSON schema、reader/writer 与 fixture。
- 至少一个 CJSON fixture 完成结构、键和项目元数据 import/export round-trip。
- 可稳定映射的 vibration、spectrum、orbital/surface 引用进入现有对象；不稳定字段进入 raw envelope/ParserReport。
- CJSON 保持轻量交换格式，大型数组继续使用 `.cbq` sidecar，不复制进 `.blend`。
- Avogadro 及其依赖不进入 Blender Extension ZIP。

## Constraints

- 不在本阶段实现完整 Avogadro UI 或 Open Babel fallback。
- 不假设 CJSON 能承载大型轨道矩阵和体数据。
- 不伪造缺失的单位、basis 或 provenance。

## Next Action

核实 CJSON 权威仓库与当前 schema/fixtures，固定 reference submodule，以失败测试定义最小交换边界。

## References

- [Reader 与格式能力计划](../../docs/quantum-visualization/plans/readers-and-formats.md)
- [Blender 映射计划](../../docs/quantum-visualization/plans/blender-visualization.md)
- [参考项目目录](../../docs/quantum-visualization/references.md)
