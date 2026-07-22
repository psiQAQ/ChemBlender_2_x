# Grid3D LOD 与 render cache contract

## 科学派生

`derive_grid_lod(grid, strides, dataset_index)` 从权威 `Grid3D` 生成单一 scalar LOD：

```text
source[..., ::sx, ::sy, ::sz]
```

- 三个 stride 必须是正整数且至少一个大于 1；
- `(dataset,x,y,z)` source 必须显式选择 dataset index；
- origin 不变，第 i 个 step vector 乘对应 stride；
- semantic role、value/coordinate unit、status、source calculation 和 structure ID 保留；
- output dims 固定为 `(x,y,z)`；
- revision 由 source UUID/revision、dataset index、strides 和 `grid_lod@1` 计算；
- provenance 记录 source grid parent 与完整参数。

派生通过 tuple slice 直接访问 lazy source，不先调用整体 `numpy.asarray(source)`。LOD 是可删除
派生 dataset，不修改 source values。

## Render cache

OpenVDB key：

```text
grid UUID/revision + dataset index + openvdb adapter/version
```

Volume-to-Mesh surface key：

```text
OpenVDB identity + isovalue + surface adapter/version
```

`volume_cache_path(root, ...)` 使用 `<root>/volume/<render-key>.vdb`。颜色、透明度和可见性
不进入 key；它们不改变 VDB 数值或 surface geometry。

## 非目标

- 不做插值滤波、Gaussian smoothing 或误差估计；v1 是确定性 stride decimation。
- 不引入 marching-cubes/mesh simplifier 依赖。
- 不把 OpenVDB 作为权威数组。
- 不自动混合或平均多个 dataset。
