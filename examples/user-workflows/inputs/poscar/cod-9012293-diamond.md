# COD 9012293 金刚石 POSCAR 代表样例

## 用途与选择理由

这个样例把 COD 的金刚石非对称位点按 `Fd-3m` 展开为常规晶胞，再写成 VASP POSCAR。它用真实晶体来源检查晶胞、元素计数和 Direct 分数坐标，同时保持 8 位点的小规模。

## 来源与许可

- 取得日期：`2026-08-08`。

- 来源标识：`COD 9012293 expanded by Fd-3m symmetry`；源记录为 [COD 9012293 CIF](https://www.crystallography.net/cod/9012293.cif)。
- 派生方式：用 Gemmi 按源声明的 `Fd-3m` 对称性展开，确定性写出 8 个常规晶胞位点。
- 许可：`CC0-1.0`，见 [COD 数据提交与公共领域说明](https://www.crystallography.net/cod/new.html)。

## 规模与分辨率

文件大小 `180` bytes，含 1 种元素、8 个位点，立方晶胞边长 3.5669 Å，坐标模式为 `Direct`。文本很小是因为高对称晶体可用少量数字表达，并不等于晶格显示精度不足。

## 字段说明

| 行组 | 本文件内容 | 含义 |
| --- | --- | --- |
| comment | COD 9012293 diamond | 来源说明 |
| scale | `1` | 晶格整体比例 |
| lattice vectors | 3 个正交向量 | 3.5669 Å 立方晶胞 |
| species / counts | `C` / `8` | 元素顺序与位点数 |
| coordinate mode | `Direct` | 后续为分数坐标 |
| positions | 8 行 | 常规晶胞位点 |

## ChemBlender 支持边界

ChemBlender 导入 periodic Structure、cell 和分数坐标。POSCAR 不携带原 CIF 的空间群、实验元数据或 occupancy；这些信息无法从本文件无损恢复。需要对称性来源时应同时查原 CIF，导出前查看 loss preview。

## 操作流程

1. 用 `Quick Import` 选择 [`cod-9012293-diamond.POSCAR`](cod-9012293-diamond.POSCAR)。
2. 在 Preview 核对 C · 8、Direct 和晶胞体积约 45.3809 Å³，再确认导入；保存数据中核对 3.5669 Å 晶胞矩阵和全部坐标。
3. 创建周期 View；需要核查对称性时与源 CIF 对照，而不是把推断当源字段。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，先读取 Operator RNA，再用 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/poscar/cod-9012293-diamond.POSCAR 的绝对路径。只使用公开的 bpy.ops.chemblender.*；先报告 8 个 C 位点、3.5669 Å 晶胞、Direct 坐标、POSCAR 不含源空间群这一边界和 Preview 诊断，等我确认后调用 bpy.ops.chemblender.confirm_import。创建周期 View；先读取 UI 的 spglib dependency reason，只在按钮可用时调用 bpy.ops.chemblender.derive_crystal_symmetry，并把结果标为派生值；缺失时记录禁用原因且不绕过。保存 .blend 与相邻 .cbq。
```

## 完整性与验证

- SHA-256：`67c040a37159c5f7ba618f6ce264efc24308f50ed982bd0b80035733278bdb5c`
- 精确大小：`180` bytes
- 自动检查：8 sites、1 species、3.5669 Å cell、Direct mode。

## 参考资料

- [COD 9012293 原始 CIF](https://www.crystallography.net/cod/9012293.cif)
- [VASP Wiki：POSCAR](https://www.vasp.at/wiki/index.php/POSCAR)
- [COD 数据库说明](https://www.crystallography.net/cod/)
