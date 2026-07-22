# Phase 4 Surface Preset Application

## Goal

为 `signed_isosurface` 与 `property_on_surface` 实现可重建的 Blender surface application，沿用 Grid3D affine、render cache identity 与 scene plan 原子回滚契约。

## Success Criteria

- signed scalar field 生成独立正/负相位表面并使用明确颜色，不由法向猜相位。
- property-on-surface 在 surface vertices 采样第二个同 affine Grid3D，并写入命名 float/color attribute。
- 阈值、颜色、单位、dataset UUID/revision 与 render identity 保存在对象 metadata。
- 缓存与对象失败不污染源 sidecar；stale plan 和中途异常零残留。
- Blender 5.1 isolated smoke 覆盖非正交 affine、正负表面、属性采样、cleanup 与 reload。

## Constraints

- 优先复用 OpenVDB/Volume；若 Blender API 无法稳定得到所需 surface attributes，采用已有 NumPy 能力实现有限 fallback，不新增依赖。
- 不把 Grid3D values 写进 Mesh 作为权威存储。
- 不自动修改 camera、light、render output 或覆盖用户文件。

## Next Action

验证 Blender 5.1 Volume to Mesh 的可脚本化输出和属性传递；以最小 3D fixture 决定 OpenVDB 路径或纯 NumPy fallback。

## References

- [Scene preset v1](../../docs/quantum-visualization/specs/scene-preset-v1.md)
- [Grid3D 与单位 ADR](../decisions/0004-grid3d-and-units.md)
- [Grid LOD/cache ADR](../decisions/0018-grid-lod-and-render-cache-identity.md)
