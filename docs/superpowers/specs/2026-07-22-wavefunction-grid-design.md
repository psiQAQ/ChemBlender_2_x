# 波函数派生 Grid3D 设计

## Goal

从 normalized `Structure`、`BasisSet` 和 `OrbitalSet` 计算分子轨道与电子密度 `Grid3D`。求值层不重新读取 FCHK/Molden，不依赖 `bpy`，并把 convention、输入 revision、求值参数和 backend 版本写入 provenance。

## Backend Decision

MVP 采用固定 `qc-gbasis==0.1.0`（官方 tag `v0.1.0`，commit `6440c84f3fcf8d42cbd9b5de53ae8d70bed4cd4f`）。它可直接消费 Gaussian shell 并求 AO/MO，许可证为 GPL-3.0-or-later。

真实环境探针得到以下结论：

| 候选 | 结果 | 决策 |
| --- | --- | --- |
| GBasis 0.1.0 | Python 3.12/Windows 标准安装和真实 FCHK 计算通过；Python 3.13 可在 NumPy 2.5.1 下运行，但其 Windows metadata 固定 `numpy<2`，标准解析失败 | 外部 worker 主后端；不打入 Blender Extension |
| qc-grid 0.0.9.post1 | 提供通用网格、积分和插值，但规则 affine 点阵可用 NumPy 直接生成 | MVP 不引入；原子中心/自适应积分阶段再评估 |
| ORBKIT 1.1.0.dev2 | Python 3.13 构建因未声明 Cython 依赖失败，发行和构建链比 GBasis 陈旧 | 不作为主后端；不拉取 submodule |

GBasis 的 Python 3.13 metadata 不兼容是 worker 环境约束，不通过修改 Blender manifest 或忽略依赖来隐藏。推荐 worker 使用 Python 3.12；NumPy 2 的强制安装仅用于兼容性探针。

## Public Contract

```python
evaluate_molecular_orbital_grid(
    structure,
    basis_set,
    orbital_set,
    *,
    channel,
    orbital_index,
    origin,
    step_vectors,
    shape,
) -> ImportBatch

evaluate_electron_density_grid(
    structure,
    basis_set,
    orbital_set,
    *,
    origin,
    step_vectors,
    shape,
) -> ImportBatch
```

参数约定：

| 参数 | 约定 | 说明 |
| --- | --- | --- |
| `origin` | 3 个 bohr 浮点数 | 网格索引 `(0,0,0)` 的位置 |
| `step_vectors` | 3×3 bohr | 完整 affine step vectors，允许非正交 |
| `shape` | 3 个正整数 | `(x, y, z)` 采样点数 |
| `channel` | `restricted`/`alpha`/`beta` | MO 求值通道 |
| `orbital_index` | 零基整数 | 通道内轨道索引 |

两个函数返回仅包含一个 `Grid3D` 和一个 `ProvenanceRecord` 的 `ImportBatch`，可原子提交到已有 `QCProject`。输入实体 ID/revision 不匹配、坐标不是 bohr、basis 不是 L2 normalization、generalized spinor、缺 occupation 或非法 grid 时显式失败。

## Basis Conversion

求值器把每个 normalized shell 的 contraction 列拆成 GBasis segmented shell，但不改变数值：

- center 取 `Structure.coordinates[center_atom]`；
- exponent 和 coefficient 保持 atomic units；
- Cartesian/pure ordering 从 `BasisConvention` 显式传给 GBasis；
- pure function 的顺序与负号由 GBasis transformation 原生解释；
- contraction normalization 固定为 1，与 IOData `from_iodata` wrapper 一致，因为 IOData 系数已经保留来源 normalization。

因此 MO coefficient 的 basis-function 轴与求值后的 AO 轴保持同一顺序，不做隐式 Gaussian/ORCA convention 假设。

## Numerical Semantics

网格点按下式生成：

```text
r(i,j,k) = origin + i*step[0] + j*step[1] + k*step[2]
```

MO 值为 `psi_i(r) = sum_mu C[i,mu] chi_mu(r)`，输出 `semantic_role=molecular_orbital`、单位 `inverse_bohr_to_three_halves`。正负相位保留在同一标量 grid 的正负值中；后续表面 adapter 必须分别选择正、负 isovalue，不能从 mesh normal 猜相位。

restricted/unrestricted 密度统一按 channel occupation 求和：

```text
rho(r) = sum_channel sum_i occupation[channel,i] * psi[channel,i](r)^2
```

输出 `semantic_role=electron_density`、单位 `electron_per_cubic_bohr`。首版只支持实系数；generalized spinor 明确推迟。

## Derivation Identity

派生 SHA-256 包含：输入 UUID/revision、operation/version、backend/version、origin、step vectors、shape，以及 MO 的 channel/index。该 hash 同时作为 grid revision 和 provenance `source_hash`。provenance 的 `parent_ids` 包含 structure、basis 和 orbital set UUID。

## Numerical Baseline

固定 IOData `water_sto3g_hf_g03.fchk`，在每轴扩展 6 bohr、spacing 0.1 bohr 的规则网格上：

- occupation 总和为 10 electrons；
- 数值积分为 10.0097251825 electrons；
- 7 个 MO 的离散 norm 在约 0.9999997–1.0045726；
- Python 3.12/NumPy 1.26.4 与 Python 3.13/NumPy 2.5.1 的结果在显示精度内一致。

集成测试使用该守恒量验证整个 normalized-model-to-grid 路径，而不是只验证数组 shape。

## Non-goals

- 自适应网格、原子中心积分、GPU、导数、ESP、RDG 和 NCI；
- complex/generalized spinor；
- chunked/lazy 求值与 worker IPC；
- 把 GBasis、SciPy 或 IOData 加入 Blender Extension wheels。
