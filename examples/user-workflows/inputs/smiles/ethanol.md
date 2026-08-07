# 乙醇 SMILES 合同样例

## 用途与选择理由

单行 `CCO` 是最小的 SMILES 文件合同，用来验证文件识别、单条记录和无坐标分子图。它适合快速冒烟测试，不足以覆盖芳香性、环、形式电荷或立体化学。

## 来源与许可

- 取得日期：`2026-08-07`。

- 来源标识：`synthetic-ethanol-smiles@3e1d02e046851c6c89a81ac8dce42b435bb25509`。
- 来源路径：仓库中的确定性合成样例 `examples/user-workflows/inputs/smiles/ethanol.smi`。
- 许可：`GPL-3.0`。

## 规模与分辨率

文件大小 `4` bytes，含 1 条记录、3 个重原子和 0 维来源坐标。SMILES 编码分子图而不是几何，因此“文件只有 4 bytes”不表示坐标精度低，而是根本没有来源坐标。

## 字段说明

| token | 内容 | 含义 |
| --- | --- | --- |
| `C` | 两次 | 两个脂肪族碳 |
| `O` | 一次 | 一个氧 |
| 相邻 token | `C-C-O` | 默认单键连接 |
| 行尾 | 1 条非空行 | ChemBlender 文件读取器的单记录边界 |

## ChemBlender 支持边界

ChemBlender 当前 SMILES 文件入口接受恰好一条非空记录，RDKit 解析图并生成确定性的平面 2D 来源 Structure、Topology 和 AtomicIdentity。生成的平面坐标是派生显示坐标，不是实验或优化构象；批量多行 SMILES 不在当前文件入口范围。

## 操作流程

1. 用 `Quick Import` 选择 [`ethanol.smi`](ethanol.smi)，或在文本入口输入 `CCO`。
2. 在 Preview 核对 1 record、3 heavy atoms 和 planar 2D generated 诊断。
3. 确认后创建分子 View；需要三维构象时另做派生操作并保留 provenance。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，先读取 Operator RNA。可用 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/smiles/ethanol.smi 的绝对路径，或用公开的 bpy.ops.chemblender.import_smiles_text 输入 CCO；只使用 bpy.ops.chemblender.*。先报告 1 条记录、3 个重原子、来源无坐标和 planar 2D generated 诊断，等我确认后调用 bpy.ops.chemblender.confirm_import。不要把派生 2D 坐标写成实验构象；保存 .blend 与相邻 .cbq。
```

## 完整性与验证

- SHA-256：`5c9aa2a3024d56c903d547798cbd04ff743433ba0950dbfd8e19238e40651172`
- 精确大小：`4` bytes
- 自动检查：1 record、3 heavy atoms、0 source coordinate dimensions。

## 参考资料

- [Daylight SMILES theory](https://www.daylight.com/dayhtml/doc/theory/theory.smiles.html)
- [ChemBlender 许可证](https://github.com/psiQAQ/ChemBlender_2_x/blob/main/LICENSE)
