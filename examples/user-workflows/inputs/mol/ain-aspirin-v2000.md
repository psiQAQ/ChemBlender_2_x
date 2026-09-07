# CCD AIN 阿司匹林 V2000 MOL 代表样例

## 用途与选择理由

这个样例把 wwPDB Chemical Component Dictionary 的 AIN 理想构象写成 V2000 MOL，用于检查带显式氢、键级和三维坐标的真实小分子。它比三原子水合同样例更适合观察环、羧基和芳香体系。

## 来源与许可

- 取得日期：`2026-08-08`。

- 来源标识：`CCD AIN ideal coordinates`；源记录为 [RCSB AIN](https://www.rcsb.org/ligand/AIN) 的理想坐标 SDF。
- 派生方式：用仓库既有 RDKit 读取源 SDF，并确定性输出一个 V2000 mol block。
- 许可：`CC0-1.0`，见 [PDB Archive 使用政策](https://www.rcsb.org/pages/policies)。

## 规模与分辨率

文件大小 `1818` bytes，含 21 个原子（13 个重原子、8 个显式氢）、21 条键和 1 个三维构象。坐标来自 CCD 理想构象，不是实验电子密度；小文件仍能完整表达这一离散分子结构。

## 字段说明

| 字段 | 本文件内容 | 含义 |
| --- | --- | --- |
| header | 名称、生成程序 | MOL 记录说明 |
| counts line | 21 atoms、21 bonds、`V2000` | CTAB 规模和版本 |
| atom block | 元素、x/y/z、原子属性 | 显式原子与笛卡尔坐标 |
| bond block | 两端原子、键级、立体标记 | 分子连接关系 |
| `M  END` | 1 行 | CTAB 结束标记 |

## ChemBlender 支持边界

ChemBlender 通过 RDKit 读取 V2000，保留原始 `MolecularRecord`，并分别保存来源拓扑与规范化解释拓扑。普通原子、键级、形式电荷和立体信息可进入项目；罕见 CTfile 扩展字段不保证都成为独立 UI 属性，导出时要看 loss preview。

## 操作流程

1. 用 `Quick Import` 选择 [ain-aspirin-v2000.mol](ain-aspirin-v2000.mol)，在实际 Preview 检查 1 record、V2000、1 sanitized topology record 与 Complete。
2. 确认导入后，在 Project Browser 和保存项目中核对 21 原子、21 条键、显式氢及分别保留的来源/解释拓扑。
3. 查看默认 Structure View；默认原子视图不代表已接受显示拓扑。需要连接显示时明确选择并接受相应拓扑，导出前检查损失提示。

Preview只显示该格式当前实现的摘要。未出现的原子/键数、计算参数和详细诊断，应在确认后的项目实体或来源文件中核对，不能报告为Preview已显示。保存时让 `.blend` 与同名 `.cbq` 相邻。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，先读取 Operator RNA。用公开 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/mol/ain-aspirin-v2000.mol 的绝对路径。先报告实际 preview_json 中的 reader、quality、可用摘要和诊断，等我确认再调用 confirm_import；不要把文档中的预期计数说成 Preview 已显示。确认后用公开状态和保存的项目核对：21 原子、21 条键、显式氢及分别保留的来源/解释拓扑。查看默认 View，并说明原子显示与科学拓扑的区别；有损导出停在确认边界。保存 .blend 与相邻 .cbq 并报告路径。
```

## 完整性与验证

- SHA-256：`32bd93a45508c66d28205bfd423068a41434022a7cc7c312cb0a983c17178bf4`
- 精确大小：`1818` bytes
- 自动检查：1 record、21 atoms、21 bonds、1 conformer、V2000。

## 参考资料

- [RCSB CCD AIN](https://www.rcsb.org/ligand/AIN)
- [BIOVIA CTfile / SDfile 规范入口](https://3dswym.3dexperience.3ds.com/post/biovia-laboratory-informatics/can-i-store-molfiles-of-chemical-structures-in-my-database_FXvWcYPER3KN7sxun8F6SA)
- [PDB Archive 数据政策](https://www.rcsb.org/pages/policies)
