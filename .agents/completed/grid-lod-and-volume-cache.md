# Grid3D LOD and Volume Cache Identity

## Result

- 新增纯 core `derive_grid_lod`，以 lazy stride slice 生成保留 affine grid 语义的 scalar LOD。
- LOD revision 和 provenance 覆盖 source identity、dataset index、stride 与 algorithm version。
- OpenVDB 与 surface cache key 分离科学数据、几何参数和 adapter version。
- Blender Volume adapter 可从 cache root 自动定位稳定 VDB 路径，并避免整体读取多 dataset source。

## Evidence

- full suite：222 tests passed，27 optional-dependency skips。
- lazy indexed fixture、斜网格、multi-dataset 和 cache invalidation tests passed。
- Blender 5.1.2 native validate/build passed。
- 隔离 Extension install、full/LOD VDB 数值与 transform、两轮 reload、RDKit runtime 和 disable lifecycle passed。

## Decision

`.agents/decisions/0018-grid-lod-and-render-cache-identity.md`

## Known Limitations

- v1 是 stride decimation，不做抗混叠滤波或误差估计。
- surface cache 只定义 identity；没有在本阶段新增 marching-cubes 依赖。
