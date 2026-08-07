# PDB MODEL 与 alternate location 轨迹合同样例

## 用途与选择理由

这个仓库合同把两个 MODEL 与 A/B alternate location 放在一个极小文件里，用于检查模型身份相容时的轨迹组装和 altLoc 字段保留。它是语义回归数据，不是实验结构。

## 来源与许可

- 取得日期：`2026-08-07`。

- 来源标识：`tests/blender_smoke.py@3e1d02e046851c6c89a81ac8dce42b435bb25509`。
- 来源路径：由仓库 Blender smoke test 中的固定文本逐字节保存。
- 许可：`GPL-3.0`。

## 规模与分辨率

文件大小 `360` bytes，含 2 帧，每帧 2 个原子记录，alternate location 为 A 与 B。坐标保留到 0.001 Å 的文本位数；规模只适合验证解析和动画连接。

## 字段说明

| 字段 | 内容 | 含义 |
| --- | --- | --- |
| `MODEL` | 1、2 | 帧/构象编号 |
| `ATOM` serial/name | 两个 `CA` 记录 | 原子身份字段 |
| altLoc | A、B | 同一位点的替代构象标签 |
| occupancy | 0.60、0.40 | 两个替代位置的占位 |
| xyz / B-factor | 每模型不同 | 坐标与温度因子 |

## ChemBlender 支持边界

ChemBlender 在原子身份一致时生成两帧 trajectory，并保留 biological hierarchy、altLoc、occupancy 和 B-factor 数据。这个合同没有真实序列或实验元数据，不能用来评价大型 PDB 性能。

## 操作流程

1. 用 `Quick Import` 选择 [`model-trajectory.pdb`](model-trajectory.pdb)。
2. 在 Preview 核对 2 帧、每帧 2 个记录和 A/B altLoc，再确认导入。
3. 创建轨迹 View，切换两帧并检查 occupancy 属性。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，先读取 Operator RNA，再用 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/pdb/model-trajectory.pdb 的绝对路径。只使用公开的 bpy.ops.chemblender.*；先报告两个 MODEL、每帧两个记录、A/B altLoc、0.60/0.40 occupancy、trajectory 和 Preview 诊断，等我确认后调用 bpy.ops.chemblender.confirm_import。创建轨迹 View 并切换帧；保存 .blend 与相邻 .cbq。
```

## 完整性与验证

- SHA-256：`b5b86a4dff1f21f1d8132be6dd64627d7b1cc23278f99cdff896b05f5859c6ff`
- 精确大小：`360` bytes
- 自动检查：2 frames、2 atoms/frame、2 alternate-location labels。

## 参考资料

- [wwPDB PDB 格式 3.30](https://www.wwpdb.org/documentation/file-format-content/format33/sect1.html)
- [ChemBlender 许可证](https://github.com/psiQAQ/ChemBlender_2_x/blob/main/LICENSE)
