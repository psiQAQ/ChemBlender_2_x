# 0014：费米面与 PyProcar worker 边界

## Status

Accepted for Phase 2 Fermi-surface visualization.

## Context

PyProcar 能生成带投影、自旋和速度属性的费米面，但其核心对象继承 PyVista，并依赖
VTK、scikit-image、matplotlib 与 `numpy<2.0`。直接嵌入 Blender 会扩大二进制冲突面。

## Decision

- ChemBlender 权威类型是 `FermiSurfaceMesh`，不保存 PyVista object。
- mesh 顶点使用包含 `2π` 的 Cartesian reciprocal coordinates，单位 `inverse_angstrom`。
- triangle faces、face-domain band index、spin index、Fermi energy 与 band/structure UUID 必须显式保存。
- `SurfaceProperty` 统一 vertex/face scalar/vector；首批 allow-list 为 orbital contribution、spin texture、Fermi velocity/speed。
- PyProcar local isosurface index 必须通过 `band_isosurface_index_map` 恢复为原 band index。
- PyProcar v6.5.0 只属于隔离 worker extra；adapter 使用 PyVista-compatible data contract，不 eager import PyProcar/PyVista。
- Blender 创建单一 Mesh 和 named attributes，selection 写回 face/band identity。

## Consequences

- worker 可替换 PyProcar 或升级 mesh 后端，而 Blender contract 不变。
- unknown PyProcar arrays 进入 `ParserReport`，不自动复制含义不明的数据。
- Brillouin-zone clipping 与高级 glyph/style 延后。

## Verification Contract

1. flattened PyVista triangles 和 local→original band mapping 有数值断言。
2. project 验证 structure/band/spin/band-index references。
3. Blender face/point attributes 与 selection metadata 真实通过。
4. Extension ZIP 不包含 PyProcar、PyVista、VTK 或 submodules。
