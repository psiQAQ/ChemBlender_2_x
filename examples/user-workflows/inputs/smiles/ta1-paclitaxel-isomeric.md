# CCD TA1 紫杉醇 isomeric SMILES 代表样例

## 用途与选择理由

这个单记录 SMILES 来自 TA1 理想结构，保留紫杉醇较复杂的环、分支、芳香性和手性 token。它用于验证无来源坐标时，较复杂分子图和 stereochemistry 能否进入项目。

## 来源与许可

- 取得日期：`2026-08-08`。

- 来源标识：`CCD TA1 ideal coordinates converted to canonical isomeric SMILES`。
- 源文件：[RCSB TA1 ideal SDF](https://files.rcsb.org/ligands/download/TA1_ideal.sdf)；用 RDKit 2026.3.3 确定性生成 canonical isomeric SMILES，并附记录名。
- 许可：`CC0-1.0`，见 [PDB Archive 使用政策](https://www.rcsb.org/pages/policies)。

## 规模与分辨率

文件大小 `398` bytes，含 1 条记录、62 个图原子、68 条重原子图键和 51 个由来源显式氢转为隐式的氢。来源的 113 原子三维坐标被有意省略；SMILES 本身没有几何分辨率。

## 字段说明

| token 类型 | 本文件内容 | 含义 |
| --- | --- | --- |
| 元素与括号 | C/O/N/H、分支 | 原子和支链图 |
| 数字 | 多个环闭合编号 | 环连接配对 |
| `=` | 双键 | 键级 |
| 小写 `c` | 芳香碳 | 芳香图语义 |
| `@` / `@@` | 多处 | tetrahedral stereochemistry |
| Tab 后文本 | `TA1 paclitaxel` | 记录名称，不是图的一部分 |

## ChemBlender 支持边界

ChemBlender 当前 SMILES 文件入口只接受一条非空记录。RDKit 解析 graph、aromaticity、formal charge 和 stereo，并生成确定性的平面 2D Structure；源 CCD 3D 坐标不在该文件中，不能从 SMILES 无损恢复。需要来源三维几何时使用同目录 MOL/SDF/XYZ。

## 操作流程

1. 用 `Quick Import` 选择 [ta1-paclitaxel-isomeric.smi](ta1-paclitaxel-isomeric.smi)，在实际 Preview 检查 1 record、SMILES: 1 与 Complete；sanitized topology计数不等于图键数。
2. 确认导入后，在 Project Browser 和保存项目中核对 62 graph atoms、68 bonds、51个隐式氢与stereo；Import Diagnostics 的 planar 2D generated 说明这些是派生坐标。
3. 查看默认 Structure View；默认原子视图不代表已接受显示拓扑。需要连接显示时明确选择并接受相应拓扑，导出前检查损失提示。

Preview只显示该格式当前实现的摘要。未出现的原子/键数、计算参数和详细诊断，应在确认后的项目实体或来源文件中核对，不能报告为Preview已显示。保存时让 `.blend` 与同名 `.cbq` 相邻。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，先读取 Operator RNA。用公开 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/smiles/ta1-paclitaxel-isomeric.smi 的绝对路径。先报告实际 preview_json 中的 reader、quality、可用摘要和诊断，等我确认再调用 confirm_import；不要把文档中的预期计数说成 Preview 已显示。确认后用公开状态和保存的项目核对：62 graph atoms、68 bonds、51个隐式氢与stereo；Import Diagnostics 的 planar 2D generated 说明这些是派生坐标。查看默认 View，并说明原子显示与科学拓扑的区别；有损导出停在确认边界。保存 .blend 与相邻 .cbq 并报告路径。
```

## 完整性与验证

- SHA-256：`fc9c3aa78dc395d60448b2ed188691ddb7dd70cebe051b6f3123731943edc40e`
- 精确大小：`398` bytes
- 自动检查：1 record、source atoms 113、graph atoms 62、implicit H 51、68 bonds、0 source coordinate dimensions；与同源 V3000 的可表达重原子拓扑一致。

## 参考资料

- [RCSB CCD TA1](https://www.rcsb.org/ligand/TA1)
- [Daylight SMILES theory](https://www.daylight.com/dayhtml/doc/theory/theory.smiles.html)
- [PDB Archive 数据政策](https://www.rcsb.org/pages/policies)
