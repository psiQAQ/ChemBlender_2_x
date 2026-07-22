# Phase 2 Fermi Surface 实施计划

## Goal

完成中立费米面 mesh schema、PyProcar worker adapter 与 Blender Mesh/selection 闭环。

## Plan

1. [x] 固定 PyProcar v6.5.0 submodule，核对许可证、依赖和 `FermiSurface3D` mesh/property contract。
2. [x] 先写 `FermiSurfaceMesh`、`SurfaceProperty` 与 project reference tests，再实现模型。
3. [x] 先写 synthetic PyVista/PyProcar mapping tests，再实现无 eager import 的 worker adapter。
4. [x] 先写 Blender triangle mesh、attributes 与 selection smoke，再实现 display adapter。
5. [x] 更新 ADR、依赖、reference catalog、路线图和 active/completed 文档。
6. [x] 运行 Python tests、Blender validate/build、isolated lifecycle、ZIP audit 与 diff check。
7. [x] 创建阶段提交并快进合并本地 `main`；Phase 2 关闭后进入 Phase 3 sidecar/cache。

## Verify

- vertices/faces、spin/band/Fermi identity 不丢失；
- PyProcar local-isosurface index 恢复为 normalized band index；
- scalar/vector 的 domain、shape 和 unit 有明确断言；
- Blender named attributes 与 selected face/band 一致；
- Extension 只保留 RDKit wheel，不含 PyProcar/PyVista/VTK。
