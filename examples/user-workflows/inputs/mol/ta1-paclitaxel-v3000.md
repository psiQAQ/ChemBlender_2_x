# CCD TA1 紫杉醇 V3000 MOL 代表样例

## 用途与选择理由

这个样例使用较大的手性天然产物测试 V3000 CTAB、显式氢、环系和立体信息。RCSB TA1 记录列出 11 个手性原子，能覆盖三原子合同样例无法触及的结构复杂度。

## 来源与许可

- 取得日期：`2026-08-08`。

- 来源标识：`CCD TA1 ideal coordinates`；源文件为 [RCSB TA1 理想坐标 SDF](https://files.rcsb.org/ligands/download/TA1_ideal.sdf)。
- 派生方式：用仓库既有 RDKit 确定性输出 V3000 mol block，不重新优化坐标。
- 许可：`CC0-1.0`，见 [PDB Archive 使用政策](https://www.rcsb.org/pages/policies)。

## 规模与分辨率

文件大小 `7268` bytes，含 113 个原子（62 个重原子、51 个显式氢）、119 条键和 1 个三维构象。这里的“分辨率”是坐标与拓扑表达精度，不是衍射分辨率；该规模足以测试复杂分子的交互显示。

## 字段说明

| 字段 | 本文件内容 | 含义 |
| --- | --- | --- |
| `M  V30 BEGIN CTAB` | V3000 数据块开始 | V3000 容器边界 |
| `COUNTS` | 113 atoms、119 bonds | 结构规模 |
| `BEGIN ATOM` | 元素、坐标、映射和属性 | 原子记录 |
| `BEGIN BOND` | 键序、端点和立体属性 | 拓扑记录 |
| `CFG` 等属性 | 源记录的立体标记 | 手性或键立体语义 |

## ChemBlender 支持边界

ChemBlender 通过 RDKit 读取 V3000，并保留原始 `MolecularRecord`、来源拓扑、解释拓扑和原子身份。可显示三维结构与常见立体信息；并非所有 V3000 collection、query 或厂商扩展都可无损往返，导出必须以 loss preview 为准。

## 操作流程

1. 用 `Quick Import` 选择 [ta1-paclitaxel-v3000.mol](ta1-paclitaxel-v3000.mol)，在实际 Preview 检查 1 record、V3000、1 sanitized topology record 与 Complete。
2. 确认导入后，在 Project Browser 和保存项目中核对 113 原子、119 条键、立体信息及分别保留的来源/解释拓扑。
3. 查看默认 Structure View；默认原子视图不代表已接受显示拓扑。需要连接显示时明确选择并接受相应拓扑，导出前检查损失提示。

Preview只显示该格式当前实现的摘要。未出现的原子/键数、计算参数和详细诊断，应在确认后的项目实体或来源文件中核对，不能报告为Preview已显示。保存时让 `.blend` 与同名 `.cbq` 相邻。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，先读取 Operator RNA。用公开 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/mol/ta1-paclitaxel-v3000.mol 的绝对路径。先报告实际 preview_json 中的 reader、quality、可用摘要和诊断，等我确认再调用 confirm_import；不要把文档中的预期计数说成 Preview 已显示。确认后用公开状态和保存的项目核对：113 原子、119 条键、立体信息及分别保留的来源/解释拓扑。查看默认 View，并说明原子显示与科学拓扑的区别；有损导出停在确认边界。保存 .blend 与相邻 .cbq 并报告路径。
```

## 完整性与验证

- SHA-256：`9f2f24b82a04951b1b1e1193fbfbd0bd55c506919da951d62e4c284d94583c56`
- 精确大小：`7268` bytes
- 自动检查：1 record、113 atoms、119 bonds、1 conformer、V3000；与同源 SDF/XYZ 的原子序列一致。

## 参考资料

- [RCSB CCD TA1](https://www.rcsb.org/ligand/TA1)
- [BIOVIA CTfile / SDfile 规范入口](https://3dswym.3dexperience.3ds.com/post/biovia-laboratory-informatics/can-i-store-molfiles-of-chemical-structures-in-my-database_FXvWcYPER3KN7sxun8F6SA)
- [PDB Archive 数据政策](https://www.rcsb.org/pages/policies)
