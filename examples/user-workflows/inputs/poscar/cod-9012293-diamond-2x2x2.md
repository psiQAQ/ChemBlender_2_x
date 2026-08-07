# COD 9012293 金刚石 2×2×2 CONTCAR 代表样例

## 用途与选择理由

这个文件把 8 位点金刚石常规晶胞扩成 2×2×2、64 位点 supercell，并附 64 行零速度。它用于检查更接近可视化工作的周期规模、坐标与速度数据，不需要引入大型外部数据集。

## 来源与许可

- 取得日期：`2026-08-08`。

- 来源标识：`COD 9012293 expanded by Fd-3m symmetry, then 2x2x2 supercell`。
- 源记录：[COD 9012293 CIF](https://www.crystallography.net/cod/9012293.cif)；Gemmi 展开常规晶胞后由仓库脚本确定性复制 2×2×2，并写入零速度。
- 许可：`CC0-1.0`，见 [COD 数据提交与公共领域说明](https://www.crystallography.net/cod/new.html)。

## 规模与分辨率

文件大小 `1494` bytes，含 64 个 C 位点、7.1338 Å 立方 cell 和 64 行速度。64 位点足以观察周期复制、选择和显示性能；文件仍小，是因为没有轨迹和体素场。

## 字段说明

| 行组 | 内容 | 含义 |
| --- | --- | --- |
| scale / lattice | `1`、7.1338 Å 立方向量 | supercell 晶格 |
| species / counts | `C` / `64` | 元素和位点数 |
| coordinate mode | `Direct` | 64 行分数坐标 |
| positions | 2×2×2 复制 | 原 8 位点常规晶胞的 supercell |
| velocity mode | `Cartesian` | 随后的速度坐标系 |
| velocities | 64 行 `0 0 0` | 确定性静止原子速度 |

## ChemBlender 支持边界

ChemBlender 导入 periodic Structure、cell、64 个位点和 atomic velocity property。零速度是为验证 CONTCAR 可选块而生成，不是分子动力学结果；POSCAR/CONTCAR 也不保留源 CIF 的实验和空间群元数据。

## 操作流程

1. 用 `Quick Import` 选择 [`cod-9012293-diamond-2x2x2.CONTCAR`](cod-9012293-diamond-2x2x2.CONTCAR)。
2. 在 Preview 核对 64 sites、Direct positions 和 64×3 velocity 数据，再确认导入。
3. 创建周期 View，检查 2×2×2 空间分布；速度应全部为零。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，先读取 Operator RNA，再用 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/poscar/cod-9012293-diamond-2x2x2.CONTCAR 的绝对路径。只使用公开的 bpy.ops.chemblender.*；先报告 64 个 C 位点、7.1338 Å cell、Direct 坐标、64 行零 atomic velocity 和 Preview 诊断，等我确认后调用 bpy.ops.chemblender.confirm_import。创建周期 View 并确认速度数据全零；不要把零速度描述成模拟结果。保存 .blend 与相邻 .cbq。
```

## 完整性与验证

- SHA-256：`7cf52f6c2473adad5f32f65bfb97c0d1f6d57f6788802abcc7cb4d05b16f0693`
- 精确大小：`1494` bytes
- 自动检查：64 sites、base 8 sites、2×2×2、7.1338 Å cell、64 velocity rows、Direct mode。

## 参考资料

- [COD 9012293 原始 CIF](https://www.crystallography.net/cod/9012293.cif)
- [VASP Wiki：POSCAR](https://www.vasp.at/wiki/index.php/POSCAR)
- [VASP 输入输出简介](https://vasp.at/wiki/index.php/Input_and_Output_-_a_short_Intro)
