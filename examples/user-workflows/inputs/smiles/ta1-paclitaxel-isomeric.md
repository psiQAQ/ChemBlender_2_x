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

1. 用 `Quick Import` 选择 [`ta1-paclitaxel-isomeric.smi`](ta1-paclitaxel-isomeric.smi)。
2. 在 Preview 核对 62 graph atoms、68 bonds、stereo 和 planar 2D generated 诊断。
3. 确认后创建分子 View；与 V3000 MOL 比较可表达的重原子拓扑，不比较来源坐标。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，先读取 Operator RNA，再用 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/smiles/ta1-paclitaxel-isomeric.smi 的绝对路径。只使用公开的 bpy.ops.chemblender.*；先报告 1 条记录、62 个 graph atoms、68 条 bonds、51 个隐式氢、芳香性、stereochemistry、来源无坐标和 planar 2D generated 诊断，等我确认后调用 bpy.ops.chemblender.confirm_import。不得把 2D 派生坐标当 CCD 三维坐标；保存 .blend 与相邻 .cbq，有损导出停下请求确认。
```

## 完整性与验证

- SHA-256：`fc9c3aa78dc395d60448b2ed188691ddb7dd70cebe051b6f3123731943edc40e`
- 精确大小：`398` bytes
- 自动检查：1 record、source atoms 113、graph atoms 62、implicit H 51、68 bonds、0 source coordinate dimensions；与同源 V3000 的可表达重原子拓扑一致。

## 参考资料

- [RCSB CCD TA1](https://www.rcsb.org/ligand/TA1)
- [Daylight SMILES theory](https://www.daylight.com/dayhtml/doc/theory/theory.smiles.html)
- [PDB Archive 数据政策](https://www.rcsb.org/pages/policies)
