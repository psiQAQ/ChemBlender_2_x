# Phase 3 Grid LOD and Volume Cache

## Goal

为大型 `Grid3D` 建立可复现的多分辨率派生层和 render cache identity，使 Blender 可用低分辨率 Volume 预览并切换到完整质量，而不改变权威 grid。

## Success Criteria

- LOD 通过整数 stride 从权威 Grid3D 派生，保留 origin、完整非正交 step vectors、dataset axes、unit 和 structure identity。
- 每个 LOD 具有稳定 revision/provenance，stride、source revision 或 algorithm version 变化会失效。
- lazy source 只读取所需 stride slice，不要求整体 materialization。
- Blender Volume cache path 包含 render identity，不会把不同 LOD/isovalue 误认为同一缓存。
- full-resolution dataset 保持不变，LOD cache 可删除重建。

## Constraints

- 不加入新的 marching-cubes、Zarr/HDF5 或 mesh simplifier 依赖。
- 不把 LOD 写回 source parser 数据。
- 不把材质颜色纳入科学 derivation identity。
- 先覆盖 scalar Grid3D；多 dataset leading axes 必须显式选择 dataset index。

## Next Action

为斜网格、leading dataset axis、lazy stride access 和 cache invalidation 写失败测试，再实现纯 core LOD derivation 与 Blender cache locator。

## References

- [波函数、网格与表面计划](../../docs/quantum-visualization/plans/wavefunction-and-grids.md)
- [存储、缓存与 worker 计划](../../docs/quantum-visualization/plans/storage-and-workers.md)
- [Grid3D 与单位 ADR](../decisions/0004-grid3d-and-units.md)
