# Grid3D LOD and Render Cache Implementation Plan

## Goal

为大型体数据提供可复现预览 LOD，并使 OpenVDB/surface cache 按科学与渲染参数可靠失效。

## Tasks

1. 用拒绝整体 `__array__` 的四维 source 写 multi-dataset stride failure test。
2. 实现 stride validation、lazy tuple slice、affine step scaling、stable UUID/revision/provenance。
3. 实现 volume 与 surface render cache key；surface key 包含 isovalue，颜色不进入 API。
4. 让 Blender `create_grid_volume()` 接受 cache root，生成 identity-based VDB path，并写 metadata/custom properties。
5. 在 Blender smoke 中验证斜网格 transform、content、LOD/path/key 和现有显式 `.vdb` 兼容。
6. 运行完整 suite、native validate/build 与隔离 Extension lifecycle。

## Verification

- source access log 只有一个 tuple slice。
- stride/source revision/dataset index/adapter/isovalue 变化分别使正确层级 key 变化。
- origin、非正交 step vectors、units 与 structure ID 保留。
- full-resolution source 未修改，cache 可删除重建。
