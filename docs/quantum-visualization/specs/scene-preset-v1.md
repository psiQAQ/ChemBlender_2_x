# Scene preset v1

Scene preset 是 recipe view 与 Blender adapter 之间的纯数据计划。definition 声明 binding
类型、semantic role、默认显示参数和 adapter contracts；plan 将其绑定到 project 中的
entity UUID/revision，并计算稳定 `render_identity`。

## 内置 preset

| Preset | Binding | Adapter contract | 关键设置 |
| --- | --- | --- | --- |
| `structure_publication` | structure | `structure_view_v1` | display coordinate unit |
| `signed_isosurface` | Grid3D | `openvdb_volume_v1`、`volume_to_mesh_v1` | dataset index、正 isovalue、派生负 isovalue、phase color、opacity |
| `property_on_surface` | surface/property Grid3D | volume/mesh + `surface_property_plan_v1` | 两个 dataset index、surface isovalue、color range、colormap |
| `vibration_spectrum_linked` | structure、modes、stick spectrum | structure/vibration/spectrum-curve/stick-selection | mode index、arrow/amplitude scale |
| `electronic_spectrum_linked` | structure、states、stick spectrum | structure/spectrum-curve/stick-selection | state index |
| `band_dos_linked` | BandStructure、DensityOfStates | 两种 curve v1 | energy reference、beta mirror |

Publication plan 只接受 `complete` dataset。linked datasets 必须共享 structure/source
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

`property_on_surface` 在一个 VDB 中保存 `density` 与 `property` grid。Geometry Nodes 在
density isosurface 顶点采样 property grid，写入 `cbq_surface_property`，材质用 `coolwarm`
及显式 color range 映射。v1 不接受其他 colormap 名称。

## 当前边界

v1 不自动决定相机、灯光或物理阈值，不把生成的 Mesh 或 VDB 作为权威数值存储。
