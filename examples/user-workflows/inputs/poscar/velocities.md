# CONTCAR selective dynamics 与速度合同样例

## 用途与选择理由

这个合同集中覆盖普通 POSCAR 没有的可选块：Selective dynamics、lattice velocities/vectors 和 ion velocities。它用于确认这些数据不会在导入时被静默丢弃。

## 来源与许可

- 取得日期：`2026-08-07`。

- 来源标识：`tests/fixtures/poscar/velocities.CONTCAR@3e1d02e046851c6c89a81ac8dce42b435bb25509`。
- 来源路径：仓库测试夹具 `tests/fixtures/poscar/velocities.CONTCAR`，逐字节复制。
- 许可：`GPL-3.0`。

## 规模与分辨率

文件大小 `289` bytes，含 Na/Cl 两个位点、Selective dynamics 标志和 2 行 ion velocity。数值是为格式合同编写的确定性数据，不是一次 VASP 计算结果。

## 字段说明

| 字段组 | 本文件内容 | 含义 |
| --- | --- | --- |
| species / counts | Na Cl / 1 1 | 两种元素、两个位点 |
| `Selective dynamics` | `T F T`、`F F F` | 每个坐标方向是否允许弛豫 |
| `Cartesian` positions | 2 行 | 离子笛卡尔坐标 |
| `Lattice velocities and vectors` | 速度标志、3+3 行 | 晶格速度与晶格向量块 |
| ion velocities | 2 行 | 每个原子的速度向量 |

## ChemBlender 支持边界

ChemBlender 保留 Structure、cell、selective dynamics 和 velocity data。显示 View 不会自动模拟离子运动；这些速度是数据属性，只有显式创建相应可视化或分析时才会被使用。跨格式导出可能无法表达选择标志或速度。

## 操作流程

1. 用 `Quick Import` 选择 [`velocities.CONTCAR`](velocities.CONTCAR)。
2. 在 Preview 核对 Na/Cl、两个位点、Selective dynamics 和两行 ion velocity。
3. 确认导入并在属性区检查布尔约束和速度数组；导出时核对损失报告。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，先读取 Operator RNA，再用 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/poscar/velocities.CONTCAR 的绝对路径。只使用公开的 bpy.ops.chemblender.*；先报告 Na/Cl 两个位点、Selective dynamics 标志、lattice velocity block、2 行 ion velocity、项目实体和 Preview 诊断，等我确认后调用 bpy.ops.chemblender.confirm_import。不要把速度数据自动解释成动画；有损导出必须停下请求确认。保存 .blend 与相邻 .cbq。
```

## 完整性与验证

- SHA-256：`7cba0e025bf1a5f5930ff41b6069470e192dd05c9154955c552d44c5b8ea451a`
- 精确大小：`289` bytes
- 自动检查：2 sites、2 species、Selective dynamics、2 ion-velocity rows。

## 参考资料

- [VASP Wiki：CONTCAR](https://vasp.at/wiki/CONTCAR)
- [VASP Wiki：POSCAR](https://www.vasp.at/wiki/index.php/POSCAR)
- [ChemBlender 许可证](https://github.com/psiQAQ/ChemBlender_2_x/blob/main/LICENSE)
