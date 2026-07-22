# Surface Preset Application

## Result

- signed scalar field 写为 positive/negative 两个独立 VDB，并以正阈值生成明确相位表面。
- property-on-surface 在单个 VDB 保存 `density`/`property` grids，在 evaluated mesh 顶点写入 `cbq_surface_property`。
- `coolwarm` 材质读取命名属性和显式 color range；未知 colormap 在 plan 阶段失败。
- scene application 要求 `cache_root`，保留 dataset/revision/unit/threshold/color/render identity metadata。
- surface Object、Volume、Geometry Nodes 与 Material 具有成组 cleanup，失败不残留 Blender datablock。

## Verification

- Blender 5.1.2 isolated smoke：非正交 affine、正负非空 evaluated mesh、property 非恒定采样、三份 VDB cache、cleanup 与 extension lifecycle 通过。
- 普通单测覆盖派生 signed setting 的 plan replay 及 unsupported colormap。

## Decision

[ADR 0027](../decisions/0027-openvdb-surface-application.md)
