# Phase 2 Fermi Surface

## Result

- 固定 PyProcar v6.5.0 / `4a2ec9049af78fdd35b6214eef68fe40e5f356ed` 参考 submodule。
- 新增中立 `FermiSurfaceMesh` 与 `SurfaceProperty`，连接 periodic Structure 和 BandStructure UUID。
- 完成 PyVista-compatible PyProcar adapter，恢复原 band index 并筛选明确的 scalar/vector properties。
- 新增 Blender triangle Mesh、point/face named attributes 与 face→band linked selection。
- PyProcar/PyVista/VTK 保持在可选隔离 worker 边界外，不进入 Extension。

## Verification Evidence

- Blender Python：190 tests passed，27 skipped（可选外部 parser/worker 依赖未安装）。
- synthetic PyProcar surface 验证 triangles、band mapping、velocity、spin 与 projection values。
- Blender 5.1.2 Extension validate/build 与 isolated lifecycle passed；smoke 验证 face band attribute、vertex scalar/vector 与 selection metadata。
- Extension ZIP 只含 pinned RDKit wheel。

## Known Limits

- 当前 adapter 消费已生成的 `FermiSurface3D`/PyVista-compatible object，不负责解析 PROCAR。
- 未实现 Brillouin-zone wireframe、clipping、spin arrows 和 publication styling。
- PyProcar 的 NumPy 1.x worker extra 必须与 NumPy 2.x qc-core 环境隔离。
