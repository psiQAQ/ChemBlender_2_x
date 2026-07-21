# Quantum Visualization Foundation

## Result

Phase 0 数据边界与最小语义核心已完成验收。

## Delivered

- ADR 0003–0006 确定语义模型、`Grid3D`/单位、reader capability 和 Blender/边车职责边界。
- `ChemBlender/core/` 可由普通 CPython 导入，不加载 `bpy`、RDKit 或 NumPy。
- `ArrayData`、`Structure`、`CalculationRecord`、`PropertyDataset`、`Grid3D`、`FrameSet`、`ParserReport`、`ProvenanceRecord` 与原子提交已实现。
- reader registry 支持 bounded sniff、capability、确定性选择与 `ImportBatch` 返回约束。
- `.mol2` 的错误能力声明已移除；XYZ 和 MOL V2000 可把同一水分子归一化为一致的原子序数、坐标、维度和单位。
- 多帧 XYZ 使用 `FrameSet` 保存共享原子身份、逐帧坐标和 comment；未映射字段通过 `ParserReport` 显式报告。

## Verification

- 标准库全量测试：64 tests passed。
- CPython 隔离检查：`ChemBlender.core` import 后 `bpy` 不在 `sys.modules`。
- Blender 5.1.2 native Extension validate/build：passed。
- 临时 `BLENDER_USER_RESOURCES` 中的安装、RDKit、`.blend` library、重复 enable/disable 和 `core.mol_v2000` 真实导入：passed。
- 已知非阻断警告：旧菜单 ID、旧正则转义，以及 Windows 上 RDKit DLL 卸载清理警告。

## References

- [量子化学语义模型 ADR](../decisions/0003-quantum-chemistry-semantic-model.md)
- [Grid3D 与单位约定 ADR](../decisions/0004-grid3d-and-units.md)
- [Reader capability contract ADR](../decisions/0005-reader-capability-contract.md)
- [Blender 与边车数据职责边界 ADR](../decisions/0006-blend-sidecar-boundary.md)
- [MOL V2000 reader 设计](../../docs/superpowers/specs/2026-07-22-mol-v2000-reader-design.md)
- [MOL V2000 reader 实现计划](../../docs/superpowers/plans/2026-07-22-mol-v2000-reader.md)
