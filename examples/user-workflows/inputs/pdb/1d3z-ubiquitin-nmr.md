# PDB 1D3Z 泛素 NMR 多模型代表样例

## 用途与选择理由

1D3Z 是一套真实的溶液 NMR 泛素结构，适合同时检查 PDB 固定列、10 个 MODEL、蛋白层级和轨迹视图。它补足小型 PDB 合同在原子数、残基数和多构象方面的空白。

## 来源与许可

- 取得日期：`2026-08-08`。

- 来源标识：`PDB 1D3Z`；文件从 [RCSB PDB 1D3Z](https://files.rcsb.org/download/1D3Z.pdb) 逐字节取得。
- 条目描述 human ubiquitin solution NMR，实验温度 308 K；PDB 文件明确写有 `RESOLUTION. NOT APPLICABLE`。
- 许可：`CC0-1.0`，见 [PDB Archive 使用政策](https://www.rcsb.org/pages/policies)。

## 规模与分辨率

文件大小 `1015821` bytes，含 10 个模型，每个模型 1231 个原子、1 条链、76 个残基。NMR ensemble 没有晶体学 Å 分辨率；这里应检阅模型一致性和构象变化，不能把文件大小换算成实验分辨率。

## 字段说明

| record | 本文件内容 | 含义 |
| --- | --- | --- |
| `HEADER` / `TITLE` / `EXPDTA` | 1D3Z、ubiquitin、solution NMR | 条目与实验类型 |
| `MODEL` / `ENDMDL` | 10 组 | 构象边界和模型编号 |
| `ATOM` | 每模型 1231 行 | 固定列原子名、残基、链、坐标、occupancy、B-factor、元素 |
| `SEQRES` 等 | chain A、76 residues | 生物序列与层级元数据 |
| `REMARK` / `JRNL` | 实验、验证和文献信息 | 原始条目说明 |

## ChemBlender 支持边界

ChemBlender 把兼容的 MODEL 映射为一个 Structure 加 10 帧 trajectory，并保存 chain/residue/atom biological hierarchy 与原始记录。PDB 的通用 REMARK 不会全部变成 UI 控件；导出格式也未必保留所有实验元数据，必须查看 loss preview。

## 操作流程

1. 用 `Quick Import` → `Select Files` 选择 [`1d3z-ubiquitin-nmr.pdb`](1d3z-ubiquitin-nmr.pdb)，在 Preview 核对 pdb reader、Complete 和 Default view: Structure。
2. 确认后在 Project Browser → By Data 选择 BiologicalHierarchy，核对 1231 atoms、76 residues；选中对应 View，点击 `Configure 10 MODEL Frames` 后再拖动时间轴。10 个 NMR MODEL 是构象集合，不是有时间单位的动力学轨迹。
3. 可用 biological selection 按 chain/residue 筛选；导出前检查元数据损失。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，先读取 Operator RNA，再用 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/pdb/1d3z-ubiquitin-nmr.pdb 的绝对路径。只使用公开的 bpy.ops.chemblender.*；先报告实际 preview_json 的 reader、质量、能力和默认 View，等我确认后调用 bpy.ops.chemblender.confirm_import。提交后从公开 Browser 与保存项目核对 10 个 MODEL、每模型 1231 个原子、chain A 和 76 个残基；选中对应层级和 View，调用 bpy.ops.chemblender.play_biological_models 配置播放，并可通过 bpy.ops.chemblender.select_biological_atoms 做公开的层级选择。导出有损时停下；保存 .blend 与相邻 .cbq。
```

## 完整性与验证

- SHA-256：`21099cb88231455fdfab4095dddfadcc85cc4213e105cf5f9cfff2ca21993378`
- 精确大小：`1015821` bytes
- 自动检查：10 frames/models、1231 atoms/model、1 chain、76 residues。

## 参考资料

- [RCSB PDB 1D3Z 条目](https://www.rcsb.org/structure/1D3Z)
- [wwPDB PDB 格式 3.30](https://www.wwpdb.org/documentation/file-format-content/format33/sect1.html)
- [PDB Archive 数据政策](https://www.rcsb.org/pages/policies)

筛选反馈：Biological hierarchy 分行显示 MODEL、chain/segment entries、residue 和 atom 数；执行 Select Biological Atoms 后状态栏报告选中数量。筛选写入 View 的 `cbq_selected`，不改写来源坐标或层级，也不等同于隐藏其余原子。
