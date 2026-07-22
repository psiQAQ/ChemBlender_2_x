# 0018：Grid3D LOD 与渲染缓存身份

## Status

Accepted for Phase 3 large-grid preview and rendering.

## Context

权威 `Grid3D` 可以来自 lazy sidecar，但 Blender Volume 生成路径原先会整体 materialize
多 dataset 数组，且调用者自行指定 VDB 文件名，无法可靠区分 source revision、LOD 和 adapter 版本。

## Decision

- LOD 是从权威 grid 以三个正整数 stride 派生的可删除 scalar dataset。
- 多 dataset source 必须显式选择 dataset index；不隐式混合或平均。
- origin 保持不变，每个完整 step vector 乘对应轴 stride，支持非正交网格。
- LOD revision/provenance 包含 source UUID/revision、dataset index、stride 和 algorithm version。
- lazy source 先执行 tuple slice，再 materialize 被选中的子数组。
- OpenVDB cache identity 包含 grid identity、dataset index 和 adapter version。
- surface identity 在 OpenVDB identity 上增加 isovalue 与 surface adapter version。
- 材质颜色、透明度和可见性不改变数值或几何，不进入 cache identity。

## Consequences

- 预览不会修改或替换 full-resolution dataset，缓存可安全删除重建。
- source revision、LOD 参数或 adapter version 变化会生成新路径，不会误用旧 VDB。
- v1 只做确定性 stride decimation；插值、误差估计和 mesh simplification 后置。

## Verification Contract

1. 非正交 step vectors 在不同 stride 下保持 affine mapping。
2. indexed-only lazy fixture 不触发 source 整体 `__array__`。
3. source revision、dataset index、stride、isovalue或 adapter version 变化使对应 key 失效。
4. Blender 隔离安装生成 full/LOD 两个 VDB，并验证 cache path、值和 transform。
