# Scene preset v1

Scene preset 是 recipe view 与 Blender adapter 之间的纯数据计划。definition 声明 binding
类型、semantic role、默认显示参数和 adapter contracts；plan 将其绑定到 project 中的
entity UUID/revision，并计算稳定 `render_identity`。

## 内置 preset

| Preset | Binding | Adapter contract | 关键设置 |
| --- | --- | --- | --- |
| `structure_publication` | structure | `structure_view_v1` | display coordinate unit |
| `signed_isosurface` | Grid3D | `openvdb_volume_v1`、`volume_to_mesh_v1` | 正 isovalue、派生负 isovalue、phase color、opacity |
| `property_on_surface` | surface/property Grid3D | volume/mesh + `surface_property_plan_v1` | surface isovalue、color range、colormap |
| `vibration_spectrum_linked` | structure、modes、stick spectrum | structure/vibration/stick-selection | mode index、arrow/amplitude scale |
| `electronic_spectrum_linked` | structure、states、stick spectrum | structure/stick-selection | state index |
| `band_dos_linked` | BandStructure、DensityOfStates | 两种 curve v1 | energy reference、beta mirror |

Publication plan 只接受 `complete` dataset。linked datasets 必须共享 structure/source
identity；property-on-surface 的两个网格必须共享 shape、origin、完整 step vectors、坐标单位
和 structure。设置不做隐式字符串/数值转换。

`render_identity` 包含所有 binding UUID/revision、preset/version 与归一化设置。preset codec
严格拒绝 unknown field，不序列化 `bpy`、callable 或大型数组。

## 当前边界

v1 定义和验证 scene plan，不自动决定相机、灯光或物理阈值。`surface_property_plan_v1`
明确表示尚待 Blender application adapter 实现；不会把未生成的表面声称为已完成 artifact。
