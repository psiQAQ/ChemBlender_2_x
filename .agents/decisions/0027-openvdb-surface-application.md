# ADR 0027: OpenVDB Surface Application

## Status

Accepted — 2026-07-22.

## Decision

`signed_isosurface` 使用两个独立 OpenVDB cache：正相位保存原 Grid3D，负相位保存数值取负后的 Grid3D；两者均以正阈值进入 Blender `Volume to Mesh`。相位由数据与 metadata 明确表达，不从 mesh normals 推断。

`property_on_surface` 在同一 VDB 保存 `density` 与 `property` 两个共享 affine 的 float grid。Geometry Nodes 以 `density` 生成 mesh，用 `Get Named Grid`、`Sample Grid` 和 `Store Named Attribute` 在 surface vertices 写入 `cbq_surface_property`。材质通过固定 `coolwarm` 发散色表读取该属性。

## Consequences

- 完整非正交 step vectors 由 VDB transform 保留，Blender Object 保持 identity transform。
- `.blend` 保存可重建 Volume、Geometry Nodes、材质和 cache 引用；Grid3D values 仍以 sidecar 为权威。
- cache 文件名由 scene `render_identity` 与 phase/variant 派生；写入使用临时文件加 `os.replace()`。
- v1 只支持 `coolwarm`，未知 colormap 在 plan 阶段失败，不做静默替换。
