# Quantum Visualization Foundation

## Goal

依次批准五项架构决策，并形成可以直接进入最小实现的量子化学数据契约。

## Success Criteria

- 每项 ADR 都记录选择、拒绝方案、后果和可运行验证。
- 最小接口规格能由普通 CPython 测试，不依赖 Blender runtime。
- 对象身份、数组维度、单位、reader report 和边车职责在五项决策间一致。
- 后续实现计划可以给出准确文件位置、接口和失败测试。

## Constraints

- 当前任务不安装依赖，不创建完整 core scaffold。
- 不修改 Blender UI、parser 或运行时代码。
- 不添加 Git submodule；参考仓库保持空占位。
- ADR 一次完成一项，后一项引用已批准术语，不并行定义冲突模型。

## Confirmed Facts

- `ChemBlender/scaffold.py` 接受 `.mol2`，但 `ChemBlender/read.py::read_MOL()` 没有 MOL2 分支。
- `ChemBlender/read.py` 顶层 import `bpy` 和 `bpy.props`，现有解析路径不能直接作为普通 CPython core。
- 2.2.0 是首个 Blender Extension 版本；`ChemBlender/` 是扩展根目录，仓库根目录是开发工作区。
- 当前依赖和 release gate 只批准现有 Extension/RDKit 范围；cclib、IOData、Gemmi、spglib 等仍是候选依赖。

## Next Action

起草 `.agents/decisions/0003-quantum-chemistry-semantic-model.md`，只确定 P0 对象、身份、数组元数据、缺失/歧义状态和 provenance 边界。数据类库、存储后端和完整领域对象留给后续决策。

## Verification

- 检查 ADR 与数据边界议程、语义核心计划之间的术语和链接。
- 使用标准库 `unittest` 验证示例 schema 和失败案例。
- 运行 `git diff --check`，确认新增 Markdown 为 UTF-8 无 BOM。

## References

- [文档体系设计](../../docs/superpowers/specs/2026-07-21-quantum-visualization-development-system-design.md)
- [持续开发路线图](../../docs/quantum-visualization/roadmap.md)
- [Phase 0 数据边界议程](../../docs/quantum-visualization/architecture/data-boundary.md)
- [语义核心计划](../../docs/quantum-visualization/plans/semantic-core.md)
- [Reader 与格式能力计划](../../docs/quantum-visualization/plans/readers-and-formats.md)
