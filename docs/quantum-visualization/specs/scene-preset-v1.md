# Scene preset v1

Scene preset 是 recipe view 与 Blender adapter 之间的纯数据计划。definition 声明 binding
类型、semantic role、默认显示参数和 adapter contracts；plan 将其绑定到 project 中的
entity UUID/revision，并计算稳定 `render_identity`。

## 内置 preset

| Preset | Binding | Adapter contract | 关键设置 |
| --- | --- | --- | --- |
| `structure_publication` | structure | `structure_view_v1` | display coordinate unit |
| `signed_isosurface` | Grid3D | `openvdb_volume_v1`、`volume_to_mesh_v1` | dataset index、正 isovalue、派生负 isovalue、phase color、opacity |
| `grid_volume` | Grid3D | `openvdb_volume_v1` | dataset index |
| `property_on_surface` v2 | surface/property Grid3D | `openvdb_volume_v1`、`grid_to_mesh_v1`、`property_surface_v2` | 两个 dataset index、surface isovalue、color range、colormap |
| `grid_slice` | Grid3D | `grid_sample_view_v1` | dataset index、origin、u/v 全幅跨度、counts、color range |
| `grid_profile` | Grid3D | `grid_sample_view_v1` | dataset index、start/end、sample count、显示曲线半径 |
| `grid_colorbar` | Grid3D | `grid_sample_view_v1` | dataset index、color range、宽高 |
| `vibration_spectrum_linked` | structure、modes、stick spectrum | structure/vibration/spectrum-curve/stick-selection | mode index、arrow/amplitude scale |
| `electronic_spectrum_linked` | structure、states、stick spectrum | structure/spectrum-curve/stick-selection | state index |
| `band_dos_linked` | BandStructure、DensityOfStates | 两种 curve v1 | energy reference、beta mirror |

Publication plan 只接受 `complete` dataset；Volume 允许 incomplete preview，signed surface
允许 Complete/Ambiguous preview，后者不能用于报告。linked datasets 必须共享 structure/source
identity；property-on-surface 的两个网格必须共享 shape、origin、完整 step vectors、坐标单位
和 structure。设置不做隐式字符串/数值转换。

`render_identity` 包含所有 binding UUID/revision、preset/version 与归一化设置。preset codec
严格拒绝 unknown field，不序列化 `bpy`、callable 或大型数组。

## Blender application

`apply_scene_preset()` 在创建 datablock 前调用 `validate_scene_plan()`，以当前 project 的
UUID/revision 重新生成并逐字段比较 plan。已支持 structure、vibration/spectrum、
electronic spectrum 与 band/DOS；创建的每个对象保存 preset ID/version、所有 binding
ID/revision、归一化 settings 和 `render_identity`。任一 adapter 失败时，本次新建的 Object
及其无用户 datablock 全部回滚。

## Surface application

`signed_isosurface` 创建明确的 positive/negative 两个 OpenVDB Volume，并由独立
`Volume to Mesh` Geometry Nodes modifier 生成表面。negative cache 保存取负后的 scalar
field，因此两相位都使用正阈值，绝不根据 mesh normal 推断相位。

`property_on_surface` v2 在一个 VDB 中保存 `density` 与 `property` grid。Geometry Nodes
通过 `Get Named Grid("density") → Grid to Mesh` 只为 density 生成几何，再在其顶点采样
property grid，写入 `cbq_surface_property`。旧 v1 View 需要显式 Rebuild View。
材质使用 `coolwarm` 和显式 color range；非对称跨零范围的中性色仍对应实际零值。

## 科学采样与色标

切片与剖面共用 NumPy 三线性采样，完整保留 Grid3D 的 origin/step vectors。科学坐标以
绑定 Grid 的 bohr/angstrom 为单位，显示对象转换为 angstrom；对象平移、旋转和缩放不改写
采样参数。有限越界点返回 NaN 与 False mask，Mesh 不生成跨越无效点的面，Curve 断线。
非有限坐标、退化平面和零长剖面直接拒绝。

平面 u/v vector 是两边的完整跨度，counts 包括两端点；剖面 start/end 也包括端点。
Blender View 最多 1,000,000 个采样点，因为完整显示网格仍驻留内存。纯 core 点采样按块
处理，不受该显示上限限制。CSV 从 View 保存的科学参数重新采样，记录 Grid UUID/revision、
dataset index、完整 affine、单位、来源与 validity mask；无效值留空，不伪造零值。

独立 `grid_colorbar` View 保存自己的范围，显示最小值、最大值、范围内的零点及数值单位。
它与表面和切片共用色图。更改表面范围时，应以相同范围重新创建色标。

## 当前边界

v1 不自动决定相机、灯光或物理阈值，不把生成的 Mesh 或 VDB 作为权威数值存储。
