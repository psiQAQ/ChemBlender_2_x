# NaCl CIF 合同样例

## 用途与选择理由

这是一个最小的 `contract` 样例，用来快速检查 CIF 的晶胞、空间群和分数坐标导入。它是仓库测试夹具，不是实验数据，也不适合衡量大晶体的性能。

## 来源与许可

- 取得日期：`2026-08-07`。

- 来源标识：`tests/fixtures/cif/nacl.cif@3e1d02e046851c6c89a81ac8dce42b435bb25509`
- 平台：ChemBlender repository；文件从仓库夹具逐字节复制。
- 许可：`GPL-3.0`，见 [仓库许可证](https://github.com/psiQAQ/ChemBlender_2_x/blob/main/LICENSE)。

## 规模与分辨率

文件有 1 个 data block、2 个非对称单元位点，大小为 `413` bytes。坐标写到 1 位小数，晶胞边长写为 `5.6402 Å`；这里的文件大小只反映文本编码，不是图像分辨率。

## 字段说明

| 字段 | 本文件的值 | 含义 |
| --- | --- | --- |
| `data_nacl` | `nacl` | CIF data block 名称 |
| `_cell_length_*` / `_cell_angle_*` | `5.6402 Å` / `90°` | 晶胞参数 |
| `_space_group_IT_number` | `225` | 国际空间群编号 |
| `_atom_site_*` loop | `Na1`、`Cl1` | 元素、分数坐标和 occupancy；两者 occupancy 均为 1 |

## ChemBlender 支持边界

ChemBlender 2.4.0 通过 Gemmi 读入 periodic `Structure`、晶胞、位点和 `CIFEnvelope`，并可受控导出 CIF。`Preserve` 与 `Normalized` 的语义不同；归一化可能改变标签、字段顺序或排版。导入 CIF 不会凭空生成化学键。

## 操作流程

1. 在 `Quick Import` 选择 [`nacl.cif`](nacl.cif)，查看 Import Preview 的 reader、晶胞和诊断。
2. 确认后在 Project Browser 选择 Structure，创建周期 Structure View。
3. 导出时先查看 loss preview，再选择 `Preserve` 或 `Normalized`。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，先读取 Operator RNA，再把仓库中的 examples/user-workflows/inputs/cif/nacl.cif 解析成绝对路径。只调用 UI 等价的 bpy.ops.chemblender.quick_import、bpy.ops.chemblender.confirm_import 和需要时的 bpy.ops.chemblender.export_project_entity，不导入私有 Python 模块。先报告 Import Preview 的 reader、诊断、晶胞、Structure 和 CIFEnvelope，再由我确认提交；有损导出必须停在确认界面，不得绕过。保存时让 .blend 与 .cbq 同目录，并报告实际文件路径。
```

## 完整性与验证

- SHA-256：`b5b14183e1ac9e5591fda5d9bfc57500344d20b5dd68b4fae54382ce4613b654`
- 精确大小：`413` bytes
- 自动检查：1 block、2 sites、space group 225，并按原字节校验。

## 参考资料

- [IUCr CIF 1.1 语法规范](https://www.iucr.org/resources/cif/spec/version1.1/cifsyntax)
- [ChemBlender 工作流格式矩阵](../../../../docs/user/workflows/formats.md)
