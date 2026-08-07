# QCSchema v2 AtomicResult 合同样例

## 用途与选择理由

这个仓库合同覆盖 QCSchema v2 的 AtomicResult 包装层、输入/输出 molecule、gradient、properties、provenance、extras 和 native_files。它用于验证字段映射与原始 envelope 保留，不是实际量化计算结果。

## 来源与许可

- 取得日期：`2026-08-07`。

- 来源标识：`tests/fixtures/qcschema/atomic_result_v2.json@3e1d02e046851c6c89a81ac8dce42b435bb25509`。
- 来源路径：仓库测试夹具 `tests/fixtures/qcschema/atomic_result_v2.json`，逐字节复制。
- 许可：`GPL-3.0`。

## 规模与分辨率

文件大小 `1390` bytes，含 H₂ 两个原子、v2 AtomicResult 和一个 2×3 gradient。它足以验证 schema 分派和数值数据集形状，但方法、能量与坐标是测试值，不能用于科研结论。

## 字段说明

| JSON 字段 | 本文件内容 | 含义 |
| --- | --- | --- |
| `schema_name/version` | `qcschema_atomic_result` / 2 | 顶层类型和版本 |
| `input_data` | H₂、B3LYP/def2-svp、gradient | 计算输入与 specification |
| `molecule` | 两个 H、输出 geometry | 结果关联的分子 |
| `properties` | return energy、电子数 | 标量结果摘要 |
| `return_result` | 6 个 gradient 分量 | driver 的主要返回值 |
| `provenance/extras/native_files` | 测试来源与扩展数据 | 可追溯信息和原始附件 envelope |

## ChemBlender 支持边界

ChemBlender 读取 v2 AtomicResult，生成 Structure、gradient/energy 等可识别数据集，并保留完整 raw envelope。不是每个任意 `extras` 或 native file 都会成为可视化控件；未映射字段仍可留在项目记录中，导出须检查版本与字段损失。

## 操作流程

1. 用 `Quick Import` 选择 [`atomic-result.json`](atomic-result.json)。
2. 在 Preview 核对 schema v2、2 atoms、driver `gradient` 和数值数据集。
3. 确认后检查输入与输出 geometry、gradient、energy 和 provenance；不要把 fixture 数值当计算证据。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，先读取 Operator RNA，再用 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/qcschema/atomic-result.json 的绝对路径。只使用公开的 bpy.ops.chemblender.*；先报告 qcschema_atomic_result/2、两个 H、gradient driver、输入/输出 molecule、properties、raw envelope 和 Preview 诊断，等我确认后调用 bpy.ops.chemblender.confirm_import。明确说明这是合成合同而非真实计算；有损导出停下请求确认。保存 .blend 与相邻 .cbq。
```

## 完整性与验证

- SHA-256：`8261281b7211576fcafa619ad1c20863ff2e91f226307413553490a695e332f5`
- 精确大小：`1390` bytes
- 自动检查：2 atoms、schema version 2、gradient driver。

## 参考资料

- [QCElemental v2 AtomicResult API](https://molssi.github.io/QCElemental/dev/api/qcelemental.models.v2.AtomicResult.html)
- [QCSchema 文档](https://molssi-qc-schema.readthedocs.io/en/latest/)
- [ChemBlender 许可证](https://github.com/psiQAQ/ChemBlender_2_x/blob/main/LICENSE)
