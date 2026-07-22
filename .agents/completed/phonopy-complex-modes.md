# Phase 2 Phonopy Complex Modes

## Result

- 固定 phonopy v4.4.0 / `2df40f4865d477f44d3b5d1ebcafc0b4af878e35` 参考 submodule。
- 新增 `PhononModeSet`，保留 q-point、negative frequency、complex eigenvector、mass、group velocity 和 weight 语义。
- 完成真实 `Phonopy.run_qpoints` object adapter 与 explicit missing-field report。
- 完成包含 `2πq·R`、mass scaling、animation phase 和 user phase 的 supercell frame derivation。
- 派生结果复用现有 `FrameSet`/trajectory handler，Blender 中只有一个活动 Mesh。

## Verification Evidence

- phonopy 4.4.0 worker 环境：184 tests passed，27 skipped。
- Blender Python：184 tests passed，27 skipped。
- real phonopy object 的 frequency、q-point 和 complex eigenvector transpose 数值一致。
- Blender 5.1.2 Extension validate/build passed；短路径 isolated lifecycle 与复数 q-point animation smoke passed。
- ZIP 仍只包含 pinned RDKit wheel，不包含 phonopy/h5py/matplotlib/submodules。

## Known Limits

- 首批不直接读取 standalone `qpoints.yaml`/HDF5；这些结果必须与 primitive/supercell
  identity 配对后才能安全进入项目。
- supercell mapping 由调用者提供并严格验证；后续可由 phonopy object adapter 自动导出。
- phonon dispersion publication plot、thermal properties 和 NAC 计算未实现。
