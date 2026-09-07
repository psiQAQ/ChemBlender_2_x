# rMD17 阿司匹林 32 帧 extXYZ 代表轨迹

## 用途与选择理由

这个 `representative` 文件提供可实际播放的多帧分子轨迹，并同时带能量、逐原子力和源索引。32 帧足以检查时间轴与 property 映射，文件仍只有约 60 KiB，适合纳入仓库。

## 来源与许可

- 来源标识：`10.6084/m9.figshare.12672038.v3 member rmd17_aspirin.npz; array rows 0..3100 stride 100`
- 2026-08-08 从 [rMD17 v3 数据集](https://doi.org/10.6084/m9.figshare.12672038.v3) 的 aspirin NPZ 派生。
- 许可：`CC0-1.0`，见 [Figshare 记录](https://figshare.com/articles/dataset/Revised_MD17_dataset_rMD17_/12672038)。
- 选取 NPZ array rows `0,100,...,3100`；`old_indices` 写为 `source_index`。原 kcal/mol 和 kcal/mol/Å 数值除以 `23.060547830619`，写成 eV 与 eV/Å。

## 规模与分辨率

文件大小 `61621` bytes，32 帧、每帧 21 个原子，坐标保留 10 位小数。它是从时间序列等间隔抽取的演示子集，不保证各帧统计独立，也不应直接当作训练/验证划分。

## 字段说明

| 字段 | 内容 | 含义 |
| --- | --- | --- |
| `Properties` | `species:S:1:pos:R:3:forces:R:3` | 元素、Å 坐标、eV/Å 原子力 |
| `energy` | 每帧一个实数 | 总能，单位 `electron_volt` |
| `step` | 0 到 3100，步长 100 | 本 NPZ 中选取的 array row |
| `source_index` | rMD17 `old_indices` 值 | 原时间序列索引，不保证单调 |
| `*_unit` | eV、eV/Å、dimensionless | 显式单位声明 |

## ChemBlender 支持边界

ChemBlender 2.4.0 创建 21-atom Structure、32-frame FrameSet、`atomic_force` AtomFrameProperty、`energy` 和索引 FrameProperty。`source_index` 是额外元数据，语义需用户检阅；插件不把这 32 帧解释为独立统计样本，也不执行机器学习训练。

## 操作流程

1. 导入 [`aspirin-rmd17-32.extxyz`](aspirin-rmd17-32.extxyz)，在 Preview 核对32frames、atomic_force及energy/source_index/step摘要。确认后再从项目数据核对单位和每帧21原子，不能把未显示的字段说成Preview已显示。
2. 确认后在 Project Browser 选中 FrameSet，激活匹配的 Structure View，运行 `Configure Trajectory Playback`，再抽查第 0、15、31 帧。
3. 选择 property 显示或导出 extXYZ，确认 32 帧与单位没有丢失。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，先读取 Operator RNA，用 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/extxyz/aspirin-rmd17-32.extxyz 的绝对路径。只使用公开 bpy.ops.chemblender.* 和 UI RNA。报告实际Preview的32帧、atomic_force和energy/source_index/step摘要；经我确认再调用bpy.ops.chemblender.confirm_import，然后核对21atoms/frame、energy=electron_volt、atomic_force=electron_volt_per_angstrom与来源索引。选中 FrameSet、激活匹配 Structure View，再调用 bpy.ops.chemblender.configure_trajectory_playback，然后用公开时间轴检查第 0、15、31 帧，不能把子集说成独立训练集。任何有损导出停在确认边界。保存相邻 .blend/.cbq 并报告大小。
```

## 完整性与验证

- SHA-256：`95ad7342776441a9ce2d524a65351dad8b8e29ab40857b4ed858d17ab71a409a`
- 精确大小：`61621` bytes
- 源 NPZ SHA-256：`6efe3d2454c1a9215efe2bf271c58084ae556afa188a740ae06955bf43456ee8`
- 自动检查：32 × 21 × 3 坐标和力均有限；单位、能量、逐帧 `source_index` 与文件文本一致；二次生成逐字节一致。

## 参考资料

- [rMD17 v3 数据集与时间序列警告](https://figshare.com/articles/dataset/Revised_MD17_dataset_rMD17_/12672038)
- [libAtoms extXYZ 规范](https://github.com/libAtoms/extxyz)
- [派生脚本](../../scripts/prepare_representative_inputs.py)
