# wwPDB CCD 三分子 SDF 代表样例

## 用途与选择理由

这个 SDF 依次收录 AIN（阿司匹林）、CFF（咖啡因）和 TA1（紫杉醇）的 CCD 理想构象，用于一次检查多记录流、不同分子规模、显式氢、三维坐标和拓扑。三个来源记录原样串接，没有重新优化结构。

## 来源与许可

- 取得日期：`2026-08-08`。

- 来源标识：`CCD AIN, CFF and TA1 ideal-coordinate SDF records in that order`。
- 源文件分别来自 [AIN](https://files.rcsb.org/ligands/download/AIN_ideal.sdf)、[CFF](https://files.rcsb.org/ligands/download/CFF_ideal.sdf) 和 [TA1](https://files.rcsb.org/ligands/download/TA1_ideal.sdf)，按该顺序逐字节拼接。
- 许可：`CC0-1.0`，见 [PDB Archive 使用政策](https://www.rcsb.org/pages/policies)。

## 规模与分辨率

文件大小 `11111` bytes，共 3 records；原子数为 21、24、113，键数为 21、25、119。源头部把记录标成 2D，但存在非零 z 坐标，RDKit 会提示并按 3D 构象处理；这条提示属于来源数据特征，应保留记录。

## 字段说明

| 字段组 | 本文件内容 | 含义 |
| --- | --- | --- |
| mol block header | AIN、CFF、TA1 | 每条化学组分 ID |
| counts / atom / bond blocks | V2000 CTAB | 每个分子的显式原子、坐标和连接 |
| `M  END` | 每记录 1 行 | CTAB 结束 |
| property fields | CCD 记录属性 | 名称、标识和来源元数据 |
| `$$$$` | 3 个记录分隔符 | SDF 流边界 |

## ChemBlender 支持边界

ChemBlender 流式拆分 SDF，为每个有效 record 建立 Structure、Topology、AtomicIdentity、MolecularRecord，并把可统一的属性映射为 record datasets。单条损坏可报告并保留其他记录；任意属性、V2000 扩展和维度头不保证无损映射到所有导出格式。

## 操作流程

1. 用 `Quick Import` 选择 [`ccd-3d-showcase.sdf`](ccd-3d-showcase.sdf)。
2. 在 Preview 核对 AIN/CFF/TA1、3 records、原子/键数和 2D-tag/3D-coordinate 警告。
3. 确认后分别创建 View，比较小分子与 113 原子 TA1；导出前核对记录属性与立体信息损失。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，先读取 Operator RNA，再用 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/sdf/ccd-3d-showcase.sdf 的绝对路径。只使用公开的 bpy.ops.chemblender.*；先报告 AIN/CFF/TA1 三个 record、原子数 21/24/113、键数 21/25/119、源 2D 标记与非零 z 坐标警告、项目实体和 Preview 诊断，等我确认后调用 bpy.ops.chemblender.confirm_import。不要删除来源警告；有损导出停下请求确认。保存 .blend 与相邻 .cbq。
```

## 完整性与验证

- SHA-256：`e94ea5e57e9491fcb1e47b725446f9663a484354e7516ad40a9219888f0328a2`
- 精确大小：`11111` bytes
- 自动检查：3 records（AIN/CFF/TA1）、atoms 21/24/113、bonds 21/25/119、3D coordinates。

## 参考资料

- [wwPDB Chemical Component Dictionary](https://www.wwpdb.org/data/ccd)
- [BIOVIA SDfile / CTfile 规范入口](https://3dswym.3dexperience.3ds.com/post/biovia-laboratory-informatics/can-i-store-molfiles-of-chemical-structures-in-my-database_FXvWcYPER3KN7sxun8F6SA)
- [PDB Archive 数据政策](https://www.rcsb.org/pages/policies)
