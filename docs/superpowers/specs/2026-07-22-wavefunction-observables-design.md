# DensityMatrix、spin density 与 ESP 设计

## Goal

将 IOData 的 AO-basis 一阶密度矩阵与有效核电荷归一化为 ChemBlender 权威实体，并复用 GBasis/affine grid 后端派生 electron density、spin density 与 electrostatic potential。

## Semantic Model

### DensityMatrix

`DensityMatrix` 是独立实体，不作为无标签 `PropertyDataset`：

| 字段 | 约定 |
| --- | --- |
| `structure_id` | 所属结构 UUID |
| `basis_set_id` | 矩阵 AO basis UUID |
| `level` | `scf` 或 `post_scf` |
| `spin_role` | `total` 或 `spin` |
| `data` | dims `(basis_function_row, basis_function_column)`，dimensionless |
| `source_calculation` | 可选 CalculationRecord UUID |
| `provenance_ids` | 解析/派生来源 |

矩阵必须为有限实数方阵；`QCProject.commit()` 再验证宽度等于 `BasisSet.basis_function_count`，并原子检查 structure/basis/calculation 引用。

### Nuclear charge

IOData `atcorenums` 归一化为：

```text
PropertyDataset(
  semantic_role="nuclear_charge",
  domain="atom",
  dims=("atom",),
  unit="elementary_charge",
)
```

它与 atomic number 分离，以保留 ECP/赝势的有效核电荷。ESP 求值必须消费该 dataset，不能默认把 atomic number 当成所有文件的核电荷。

## IOData Mapping

| IOData key | level | spin_role |
| --- | --- | --- |
| `scf` | scf | total |
| `scf_spin` | scf | spin |
| `post_scf`, `post_scf_ao` | post_scf | total |
| `post_scf_spin`, `post_scf_spin_ao` | post_scf | spin |

未知 key 产生 `unsupported` issue，不猜测。缺失 `one_rdms` 不阻止 basis/orbital 导入，但不声明 `density_matrix` parsed capability。`atcorenums` 缺失时 IOData 自身以 `atnums` 派生；adapter 仍保存显式 dataset。

## Public Derivation Contract

```python
evaluate_density_matrix_grid(
    structure,
    basis_set,
    density_matrix,
    *, origin, step_vectors, shape,
) -> ImportBatch

evaluate_electrostatic_potential_grid(
    structure,
    basis_set,
    density_matrix,
    nuclear_charges,
    *, origin, step_vectors, shape,
    nuclear_exclusion_radius=1e-8,
) -> ImportBatch
```

total matrix 输出 `electron_density`；spin matrix 输出 `spin_density`。ESP 只接受 total matrix，输出 `electrostatic_potential`，单位 `hartree_per_elementary_charge`。所有函数验证 entity references、basis width、单位和 GBasis 固定版本。

## Convention Handling

normalized RDM 与 `BasisConvention` 使用同一 AO 顺序。GBasis pure convention 由 shell transformation 原生处理；Cartesian leading sign 需要显式对角符号矩阵 `S`：

```text
AO values in stored convention = S * AO_gbasis
RDM for GBasis integrals = S * D_stored * S
```

density/spin density 路径先求 stored-convention AO values，再执行一般 RDM contraction；因此 spin density 可以为负，不调用会强制非负的 `evaluate_density()`。

## ESP and Singularities

ESP 为核势与电子势之和。每个 grid point 到任一核的距离小于等于 `nuclear_exclusion_radius` 时整次派生失败，并指出奇点；不得用 GBasis `threshold_dist` 静默置零该核贡献。半径、核电荷 dataset revision 和全部 grid 参数进入 derivation hash/provenance。

ESP grid 与 density grid 是两个独立 dataset。后续“ESP mapped on density surface”必须：

```text
density Grid3D -> density isosurface
ESP Grid3D -> sample at surface vertices -> color attribute
```

不能把 ESP 正负等值面冒充 density surface 着色。

## Numerical Baselines

固定 IOData fixture、0.1-bohr spacing、每轴 6-bohr margin：

- water total RDM density integral：`10.00972518995233` electrons；
- water RDM 与 occupation-MO density 最大逐点差：`8.3482376567e-8`；
- CH3 total density integral：`8.999748772940842` electrons；
- CH3 spin density integral：`0.9999988480353136` electrons；
- CH3 spin density range：`[-0.030883563377, 0.256968296283]`。

water ESP 在 bohr 点 `(3,2,1)`、`(-2.5,1.5,3.5)`、`(0.2,-3,2)` 的总势分别为 `0.0297531414634`、`0.00731589779107`、`0.00512994996413` hartree/e。

## Non-goals

- complex/generalized spinor RDM、2-RDM 和 transition density；
- density gradient、Laplacian、kinetic-energy density、RDG/ELF；
- surface interpolation/material/colorbar；
- chunking、worker IPC 和 adaptive grid。
