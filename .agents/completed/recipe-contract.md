# Versioned Recipe Contract

## Result

- 新增纯 core recipe schema、严格 JSON codec、项目实体绑定和稳定 derivation identity。
- 输入可约束 entity kind、semantic role、domain、dims、unit 与必需字段。
- 参数具有严格类型、默认值、边界和 choices，不做隐式转换。
- 内置 IR、TDDFT UV-Vis 与 molecular-orbital-grid 三类 recipe。
- 固定 `quantum-chem-skills@fbfb3c2` 作为 workflow 分类与 citation 参考，不复制模板脚本。

## Evidence

- targeted recipe tests：7 passed。
- full suite：229 tests passed，27 optional-dependency skips。
- Blender 5.1.2 native validate/build 与隔离 Extension lifecycle smoke passed。

## Decision

`.agents/decisions/0019-versioned-recipe-contract.md`

## Known Limitations

- v1 只规划确定性单步 operation，不执行 DAG 或远程任务。
- 外部程序 preparation/execution/output validation 由下一阶段 adapter contract 提供。
