# 周期碳 extXYZ 合同轨迹

## 用途与选择理由

这是一个 `contract` 夹具，用两帧单原子数据检查 extXYZ 的 `Lattice`、`pbc`、多帧分组和变化晶胞。它不能代表真实分子动力学规模。

## 来源与许可

- 取得日期：`2026-08-07`。

- 来源标识：`tests/fixtures/extxyz/multiframe-cell.extxyz@3e1d02e046851c6c89a81ac8dce42b435bb25509`
- 平台：ChemBlender repository；从测试夹具逐字节复制。
- 许可：`GPL-3.0`，见 [仓库许可证](https://github.com/psiQAQ/ChemBlender_2_x/blob/main/LICENSE)。

## 规模与分辨率

文件仅 `170` bytes，2 帧、每帧 1 个 C 原子。第一/第二帧立方晶胞边长为 4/5 Å，位置从 `(0,0,0)` 变为 `(0.1,0,0)`。这里的“分辨率”是 2 个时间帧，不是空间图像分辨率。

## 字段说明

| 字段 | 本文件的值 | 含义 |
| --- | --- | --- |
| 首行 | `1` | 当前帧 atom count |
| `Lattice` | 3 × 3 矩阵，边长 4 或 5 | 每帧晶胞，按 extXYZ 约定展开 |
| `Properties` | `species:S:1:pos:R:3` | 每行是元素字符串和 3 个实数坐标 |
| `pbc` | `T T T` | 三方向周期 |
| atom 行 | `C x y z` | 元素与 Cartesian 坐标 |

## ChemBlender 支持边界

ChemBlender 2.4.0 把兼容帧组成 FrameSet，并保留逐帧 cell/PBC 属性。它不会从一个 C 原子推断键。若帧的 atom identity 不一致，导入器应拆组或报诊断，而不是强行拼成轨迹。

## 操作流程

1. 导入 [`carbon-trajectory.extxyz`](carbon-trajectory.extxyz)，核对 Preview 显示 2 帧和变化晶胞。
2. 确认后创建 Structure View，通过时间轴查看位置和 cell frame property。
3. 导出 extXYZ 时检查帧数、cell/PBC 和 property schema。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，先读取 Operator RNA，用 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/extxyz/carbon-trajectory.extxyz 的绝对路径。只用公开 bpy.ops.chemblender.* 和 UI RNA。报告 Preview 的 2 帧、每帧 1 个 C、两个晶胞、PBC、FrameSet 和所有诊断，等我确认后再调用 bpy.ops.chemblender.confirm_import。用公开时间轴/RNA切换两帧，不访问私有项目状态。导出前显示 loss preview；保存相邻 .blend/.cbq。
```

## 完整性与验证

- SHA-256：`c44eb9eacf3b4890f64bb2b633103f30bfb98b52638849a1caa7c6fd2e8453ff`
- 精确大小：`170` bytes
- 自动检查：2 frames、1 atom/frame、2 periodic frames，原字节受 manifest 约束。

## 参考资料

- [libAtoms extXYZ 规范](https://github.com/libAtoms/extxyz)
- [ChemBlender 导入流程](../../../../docs/user/workflows/01-import.md)
