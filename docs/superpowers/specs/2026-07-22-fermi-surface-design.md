# Fermi Surface Mesh Design

## Goal

建立独立于 PyVista/VTK 的 reciprocal-space surface 语义，使 PyProcar 生成的费米面
可以进入 ChemBlender、携带 band/spin/property identity，并与已有 band/DOS/structure 联动。

## Dependency Decision

PyProcar v6.5.0 / `4a2ec9049af78fdd35b6214eef68fe40e5f356ed` 使用 GPL-3.0，
`FermiSurface3D` 继承 `pyvista.PolyData`。其基础依赖含 PyVista/VTK、scikit-image、
scikit-learn、matplotlib、trimesh，并要求 `numpy<2.0`。因此它只能作为可选 worker
adapter，不能进入 Blender Extension 或通用 qc-core 环境。

## Model

`FermiSurfaceMesh(PropertyDataset)`：

- `data`: vertices `(vertex, xyz)`，unit `inverse_angstrom`；
- `faces`: triangle indices `(face, corner)`，unit `dimensionless`；
- `structure_id` 与 `band_structure_id`；
- `spin_index`、`fermi_energy`；
- `band_indices(face)`，指向 normalized BandStructure 的 band axis；
- `properties`: `SurfaceProperty` tuple，domain 是 `vertex` 或 `face`，数组第一维匹配；
- coordinate convention 固定 `cartesian_reciprocal_2pi`。

常见 property：`orbital_contribution(vertex)`、`spin_texture(vertex, xyz)`、
`fermi_velocity(vertex, xyz)`、`fermi_speed(vertex)`。

## PyProcar Mapping

- `surface.points` → vertices；
- flattened PyVista `surface.faces` → triangles；
- `cell_data['band_index']` 通过 `band_isosurface_index_map` 的逆映射恢复原始 band index；
- point/cell arrays 按显式 allow-list 进入 `SurfaceProperty`，未知数组报告但不静默复制；
- adapter 接收明确 `spin_index` 和 normalized `BandStructure`，不猜 spin。

## Blender Mapping

创建单一 triangle Mesh；point/face scalar/vector 写入 named attributes。Object 保存
dataset、band dataset、structure、spin 和 Fermi identity。selection 写回 selected face、
band 与最近 vertex，为后续 linked brushing 提供契约。

## Non-goals

- 不在 Blender 内生成费米面或导入 VASP PROCAR。
- 不实现 PyProcar 全部 plotting/config API。
- 不实现 Brillouin-zone clipping、spin glyph styling 或 publication preset。

## Verification

- synthetic PyVista-like object 验证 face 解码、原始 band 恢复与 point/vector properties。
- model/project 验证 structure/band references、face range 与属性 domain。
- Blender smoke 验证 mesh、named attributes 和 face selection metadata。
- Extension ZIP 不包含 PyProcar、PyVista、VTK 或 submodule。
