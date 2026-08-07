# MolSSI 水分子 HF gradient QCSchema v1 代表样例

## 用途与选择理由

这是 MolSSI QCSchema 仓库中的真实规范示例，用来验证官方 v1 顶层标识 `qc_schema_output/1`、水分子 HF/cc-pVDZ gradient 和多组计算属性。它直接覆盖旧版别名之外的官方 schema 路径。

## 来源与许可

- 取得日期：`2026-08-08`。

- 来源标识：`MolSSI/QCSchema@5390e6f11d21847e4e7ca2ad14a97594f957cb2d:tests/simple/water_gradient_HF_output.json`。
- 源文件：[MolSSI 固定提交中的 water gradient output](https://raw.githubusercontent.com/MolSSI/QCSchema/5390e6f11d21847e4e7ca2ad14a97594f957cb2d/tests/simple/water_gradient_HF_output.json)，逐字节取得。
- 许可：`BSD-3-Clause`，见该提交的 [LICENSE](https://github.com/MolSSI/QCSchema/blob/5390e6f11d21847e4e7ca2ad14a97594f957cb2d/LICENSE)。

## 规模与分辨率

文件大小 `1378` bytes，含 3 个原子、9 个 gradient 分量和 13 组可识别数值数据。量化结果的可信度由方法、基组和程序 provenance 决定，不由 JSON 文件大小决定。

## 字段说明

| JSON 字段 | 本文件内容 | 含义 |
| --- | --- | --- |
| `schema_name/version` | `qc_schema_output` / 1 | 官方 v1 输出类型 |
| `molecule` | O/H/H、geometry、molecule schema v2 | 计算结构，QCSchema 默认原子单位 |
| `driver` | `gradient` | 主计算目标 |
| `model` | HF / cc-pVDZ | 电子结构方法和基组 |
| `return_result` | 3×3 gradient | 主返回数组 |
| `properties` | energy、basis/MO/electron counts、dipole、iterations | 计算摘要 |
| `provenance/success` | 程序信息、成功状态 | 结果来源与执行状态 |

## ChemBlender 支持边界

ChemBlender 接受官方 `qc_schema_output/1`，同时保留旧拼写别名的兼容性。已知 molecule、gradient、energy 和 properties 会映射为项目实体/数据集，完整 JSON 作为 raw envelope 保留；它不会在导入时重新运行 HF 计算或验证第三方数值正确性。

## 操作流程

1. 用 `Quick Import` 选择 [`molssi-water-gradient-hf.json`](molssi-water-gradient-hf.json)。
2. 在 Preview 核对 `qc_schema_output/1`、3 atoms、HF/cc-pVDZ、gradient 和 13 个 numeric datasets。
3. 确认后查看 Structure、gradient/energy 数据和 provenance；导出 v2 或其他格式时检查版本转换损失。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，先读取 Operator RNA，再用 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/qcschema/molssi-water-gradient-hf.json 的绝对路径。只使用公开的 bpy.ops.chemblender.*；先报告 qc_schema_output/1、O/H/H、HF/cc-pVDZ、gradient、13 个 numeric datasets、provenance 和 Preview 诊断，等我确认后调用 bpy.ops.chemblender.confirm_import。不要重新计算或改写 raw envelope；版本转换或有损导出必须停下请求确认。保存 .blend 与相邻 .cbq。
```

## 完整性与验证

- SHA-256：`73b28251edde763490937d303cee0b4c2cf4bf55c566d4139c5e33220ffae451`
- 精确大小：`1378` bytes
- 自动检查：3 atoms、`qc_schema_output` v1、gradient driver、13 numeric datasets。

## 参考资料

- [QCSchema v1 示例](https://molssi-qc-schema.readthedocs.io/en/latest/examples.html)
- [固定版本 qc_schema_output/1 schema](https://github.com/MolSSI/QCSchema/blob/5390e6f11d21847e4e7ca2ad14a97594f957cb2d/qcschema/data/v1/qc_schema_output.schema)
- [MolSSI QCSchema 源文件](https://github.com/MolSSI/QCSchema/blob/5390e6f11d21847e4e7ca2ad14a97594f957cb2d/tests/simple/water_gradient_HF_output.json)
