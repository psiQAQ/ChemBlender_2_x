# Grid semantic presets v1

## 目标

Cube 不能可靠声明 scalar field 的科学语义和值单位。ChemBlender 保留 raw
`Grid3D` 为 `AMBIGUOUS`，只有用户明确选择 dataset、preset 和 value unit 后，
才生成新的 `COMPLETE` `Grid3D` revision。该操作不修改原 grid，也不改动任何
voxel 数值。

## Preset 契约

| Preset ID | Semantic role | Value units | Signed | Default view | Isovalue policy | Colormap |
| --- | --- | --- | --- | --- | --- | --- |
| `generic_scalar` | `scalar_field` | `dimensionless`、density 或 ESP unit | 是 | `grid_volume` | `0.1 * max(abs(value))` | `diverging` |
| `molecular_orbital` | `molecular_orbital` | `inverse_bohr_to_three_halves` | 是 | `signed_isosurface` | `0.05 * max(abs(value))` | `phase` |
| `electron_density` | `electron_density` | `electron_per_cubic_bohr`、`electron_per_cubic_angstrom` | 否 | `grid_volume` | `0.001` | `sequential` |
| `spin_density` | `spin_density` | density units | 是 | `signed_isosurface` | `0.05 * max(abs(value))` | `diverging` |
| `electrostatic_potential` | `electrostatic_potential` | `hartree_per_elementary_charge` | 是 | `signed_isosurface` | `0.05 * max(abs(value))` | `diverging` |
| `reduced_density_gradient` | `reduced_density_gradient` | `dimensionless` | 否 | `grid_volume` | `0.5` | `sequential` |
| `sign_lambda2_rho` | `sign_lambda2_rho` | density units | 是 | `signed_isosurface` | `0.05 * max(abs(value))` | `diverging` |

`fraction_of_max_abs` 与 `absolute` 是 v1 唯一 isovalue policy。相对 policy
遇到非有限或全零数据时 fail closed。默认值只用于创建 view plan；view 必须保存
实际使用的 numeric isovalue，不能在 source revision 改变后静默重算。

## 派生身份和 provenance

`resolve_grid_semantics()` 的 identity 包含 source grid UUID/revision、
dataset index、preset ID、semantic role、value unit、isovalue policy 和
parameter。相同输入产生相同 Grid/provenance UUID 与 revision。

新 provenance 的 parents 包含 raw grid 和 raw grid 的 provenance IDs。
派生 grid 保留原来的 structure、source calculation、origin、step vectors 和
coordinate unit，只把所选 dataset 变成 `("x", "y", "z")` 数据。raw grid
继续保存在项目中，OpenVDB 和 mesh 仍只是可删除的 derived cache。
