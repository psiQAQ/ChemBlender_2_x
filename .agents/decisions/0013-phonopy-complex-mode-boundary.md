# 0013：phonopy 复数周期模态边界

## Status

Accepted for Phase 2 periodic phonon visualization.

## Context

非 Γ 点 phonon eigenvector 是复数，并以 primitive atoms 表达。若只取实部或直接复制
到 supercell，会丢失晶胞间相位，生成物理错误的动画。

## Decision

- phonopy 4.4.0 作为外部 worker/core adapter，固定参考 submodule，不进入 Extension。
- `PhononModeSet` 保存 frequency `(qpoint, mode)`、complex eigenvector
  `(qpoint, mode, atom, xyz)`、q-point、mass、可选 group velocity/weight。
- 负 frequency 原样保存，代表 imaginary mode，不取绝对值。
- phonopy `(qpoint, 3N, 3N)` 的 eigenvector 列按 mode 转换，convention 显式记录为
  `phonopy_mass_weighted_dynamical_matrix`。
- supercell animation 使用
  `amplitude/sqrt(m) * Re[e * exp(i(2πq·R - phase + user_phase))]`。
- 派生结果是普通 `FrameSet`，复用 trajectory manager；不创建逐帧 Blender Object。
- 首批 adapter 接受已执行 `run_qpoints(..., with_eigenvectors=True)` 的内存对象；
  standalone YAML/HDF5 result reader 等待稳定配对结构 fixture。

## Consequences

- 数据层完整保留复数相位，Blender 只接收派生的实坐标帧。
- primitive-to-supercell atom index 和 integer translation 是派生 API 的必填输入，不能猜测。
- group velocity/weight 缺失进入 `ParserReport`。

## Verification Contract

1. `q=(1/2,0,0)` 的相邻 translation 位移严格反相。
2. `phase=π/2` 的结果包含 eigenvector imaginary component。
3. mass scaling、negative frequency provenance 和 axis transpose 有数值断言。
4. Blender trajectory handler 在单一 Mesh 上播放派生帧。
5. Extension ZIP 不包含 phonopy、h5py、matplotlib 或 submodules。
