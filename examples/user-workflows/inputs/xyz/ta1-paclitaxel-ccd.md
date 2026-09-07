# CCD TA1 紫杉醇 XYZ 代表样例

## 用途与选择理由

这个 XYZ 保留 TA1 的全部 113 个显式原子和 CCD 理想笛卡尔坐标，用于检查较大单构象和氢原子显示。它与同源 SMILES 形成清楚对照：XYZ 有几何，但没有键和立体字段。

## 来源与许可

- 取得日期：`2026-08-08`。

- 来源标识：`CCD TA1 ideal coordinates`；源文件为 [RCSB TA1 ideal SDF](https://files.rcsb.org/ligands/download/TA1_ideal.sdf)。
- 派生方式：按源原子顺序写出元素和理想坐标，统一为 8 位小数，不生成或猜测键。
- 许可：`CC0-1.0`，见 [PDB Archive 使用政策](https://www.rcsb.org/pages/policies)。

## 规模与分辨率

文件大小 `4222` bytes，含 1 帧、113 个原子（62 个重原子、51 个显式氢），坐标单位 Å、文本保留 8 位小数。小于 5 KB 已能完整保存这套离散坐标，但小数位不等于实验精度。

## 字段说明

| 行 | 本文件内容 | 含义 |
| --- | --- | --- |
| 第 1 行 | `113` | 本帧原子数 |
| 第 2 行 | CCD 来源与 source SHA | comment / provenance |
| 后续 113 行 | element x y z | 元素和 Å 笛卡尔坐标 |
| 未提供字段 | bond、charge、stereo、cell | XYZ 不能表达这些语义 |

## ChemBlender 支持边界

ChemBlender 为本文件生成单个 Structure，保留元素、坐标和注释，不生成来源 Topology。任何显示用键都不能宣称来自 XYZ；需要权威连接和立体信息时应使用同源 MOL/SDF。

## 操作流程

1. 用 `Quick Import` 选择 [ta1-paclitaxel-ccd.xyz](ta1-paclitaxel-ccd.xyz)，在实际 Preview 检查 XYZ reader、Complete 与默认 Structure View。
2. 确认导入后，在 Project Browser 和保存项目中核对 1 frame、113 atoms、Å坐标以及没有来源Topology；不能把显示推断连线当作来源键。
3. 查看默认 Structure View；默认原子视图不代表已接受显示拓扑。需要连接显示时明确选择并接受相应拓扑，导出前检查损失提示。

Preview只显示该格式当前实现的摘要。未出现的原子/键数、计算参数和详细诊断，应在确认后的项目实体或来源文件中核对，不能报告为Preview已显示。保存时让 `.blend` 与同名 `.cbq` 相邻。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，先读取 Operator RNA。用公开 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/xyz/ta1-paclitaxel-ccd.xyz 的绝对路径。先报告实际 preview_json 中的 reader、quality、可用摘要和诊断，等我确认再调用 confirm_import；不要把文档中的预期计数说成 Preview 已显示。确认后用公开状态和保存的项目核对：1 frame、113 atoms、Å坐标以及没有来源Topology；不能把显示推断连线当作来源键。查看默认 View，并说明原子显示与科学拓扑的区别；有损导出停在确认边界。保存 .blend 与相邻 .cbq 并报告路径。
```

## 完整性与验证

- SHA-256：`7246d8fcba48aa122ecc354e818be393faeb5c02c9cfde50ea884789860a9621`
- 精确大小：`4222` bytes
- 自动检查：1 frame、113 atoms、62 heavy atoms、51 explicit H、8 coordinate decimals、angstrom；与同源 V3000 原子序列一致。

## 参考资料

- [RCSB CCD TA1](https://www.rcsb.org/ligand/TA1)
- [Open Babel XYZ 格式说明](https://openbabel.org/docs/FileFormats/XYZ_cartesian_coordinates_format.html)
- [Atomsk XYZ 约定说明](https://atomsk.univ-lille.fr/doc/en/format_xyz.html)
