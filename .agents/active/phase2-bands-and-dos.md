# Phase 2 Phonopy Complex Modes

## Goal

建立 phonopy q-point、frequency 与 complex eigenvector 语义，并按完整相位公式生成周期超胞位移动画。

## Success Criteria

- 复数 eigenvector 不丢弃虚部，q-point 使用 reciprocal fractional coordinates。
- 动画实现 `Re[e_j(q) exp(i(q·R_j - ωt + φ))]`，支持用户相位与振幅。
- primitive/supercell、atom mapping、frequency 与 group velocity 具有明确单位和 shape。
- phonopy late import，不进入 Blender Extension。

## Constraints

- 本阶段不实现 PyProcar Fermi surface。
- 不把 phonopy/h5py 加入 Blender Extension。
- 不将 complex mode 简化为仅使用 eigenvector 实部的静态箭头。

## Next Action

固定并拉取 phonopy 参考 submodule，核对 YAML/HDF5 schema 与 eigenvector normalization；先写 complex mode 相位和 supercell mapping tests，再实现 adapter。

## References

- [周期电子结构计划](../../docs/quantum-visualization/plans/periodic-electronic-structure.md)
- [能带与 DOS 决策](../decisions/0012-periodic-band-dos-boundary.md)
