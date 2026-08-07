# H2 解析 LCAO 密度 Cube 代表样例

## 用途与选择理由

这个 `representative` Cube 用于实际走 Volume、Signed Surface、LOD 和导出流程。数据由仓库脚本解析生成：两个 H 核相距 1.4 bohr，标量场是归一化的双电子 1s bonding LCAO 密度。它是教学模型，不是 HF 或 DFT 计算。

## 来源与许可

- 取得日期：`2026-08-08`。

- 来源标识：`analytic-h2-lcao-density-v1; R=1.4 bohr; extent=-6..6 bohr; grid=64x64x64`
- 平台：ChemBlender deterministic generator，实现在 [`prepare_representative_inputs.py`](../../scripts/prepare_representative_inputs.py)。
- 许可：`GPL-3.0`，见 [仓库许可证](https://github.com/psiQAQ/ChemBlender_2_x/blob/main/LICENSE)。
- 公式：`rho=(phi_A+phi_B)^2/(1+S)`，`phi=exp(-r)/sqrt(pi)`，`S=exp(-R)*(1+R+R^2/3)`。

## 规模与分辨率

文件大小 `3932577` bytes，网格 `64 × 64 × 64`，共 262144 点；范围是每轴 `[-6,6]` bohr，间距约 `0.19047619047619047` bohr。离散积分为 `1.9996717588440331` electrons，最小/最大值为 `7.75746861e-10` / `0.229296377`。这是可视化采样分辨率，不是实验分辨率。

## 字段说明

| 字段 | 本文件内容 | 含义 |
| --- | --- | --- |
| 两行标题 | analytic H2；`Not HF or DFT` | 模型和限制 |
| atom count / origin | `2`，origin `(-6,-6,-6)` bohr | 两个核与网格起点 |
| axis records | 每轴 64 点 | 采样数和 step vector |
| atom records | Z=1、nuclear charge=1、z=±0.7 bohr | H 核位置 |
| scalar block | 262144 个非负值 | 解析 LCAO 密度，atomic units |

## ChemBlender 支持边界

ChemBlender 2.4.0 读入 Structure、Grid3D 和 nuclear-charge 属性，并可创建 Volume/Signed Surface。Cube 本身没有可靠的标准字段声明“电子密度”，因此插件仍要求用户显式解决 semantic/unit；标题只是证据，不能绕过确认。Cube 导出支持选定的单 dataset，不承诺保留源排版。

## 操作流程

1. 导入 [`h2-lcao-1s-density-64.cube`](h2-lcao-1s-density-64.cube)，核对 `64³`、bohr 网格和两颗 H。
2. 把 semantic 设为 electron density、unit 设为 atomic unit，并记录这是人工确认。
3. 创建 Volume 和 Signed Surface，调整 isovalue；保存项目后冷重开检查缓存重建。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，读取 Operator RNA，用 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/cube/h2-lcao-1s-density-64.cube 的绝对路径。只用公开 bpy.ops.chemblender.*。先报告 64x64x64 网格、两颗 H、数值范围、Grid3D 的 ambiguous semantic/unit 和诊断；经我确认后调用 bpy.ops.chemblender.confirm_import。再用 bpy.ops.chemblender.resolve_grid_semantics 明确标记“解析 H2 LCAO 密度，atomic units，非 HF/DFT”，随后调用 bpy.ops.chemblender.create_grid_view 分别建 Volume 与 Signed Surface。遇任何确认或取消边界就停下。保存相邻 .blend/.cbq 并冷重开验证。
```

## 完整性与验证

- SHA-256：`51fcb06343132c4b75f340aa5824434c9c622b51df7ea1ad3742920c78af66b4`
- 精确大小：`3932577` bytes
- 生成参数描述 SHA-256：`4852c6958c17be640f9aafad6fb0b92b97780812b3c73464cc2f22a943ad9012`
- 自动检查：shape 64³、有限且非负、最大值大于最小值、离散积分在 0.001 精度内为 2 electrons；二次生成逐字节一致。

## 参考资料

- [h5cube Gaussian Cube 字段说明](https://h5cube-spec.readthedocs.io/en/latest/cubeformat.html)
- [派生脚本](../../scripts/prepare_representative_inputs.py)
- [ChemBlender 网格展示流程](../../../../docs/user/workflows/03-visualize.md)
