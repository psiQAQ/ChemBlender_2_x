# Phonopy Complex Modes Design

## Goal

把 phonopy q-point 结果归一化为不丢失复数相位的 ChemBlender 数据集，并在周期
supercell 上生成物理正确的位移帧。

## Data Contract

- `PhononModeSet.data`: frequency，dims `(qpoint, mode)`，unit `terahertz`；负值表示虚频。
- `qpoints`: reciprocal fractional coordinates，dims `(qpoint, reciprocal_axis)`。
- `eigenvectors`: complex，dims `(qpoint, mode, atom, xyz)`，按 phonopy
  dynamical-matrix convention 保存，不提前丢弃 phase。
- `masses`: primitive atom masses，unit `atomic_mass_unit`。
- `group_velocities`: optional `(qpoint, mode, xyz)`，unit `terahertz_angstrom`。
- `weights`: optional q-point weights，dimensionless。

phonopy 原始 eigenvector 为 `(qpoint, 3N, 3N)`，列是 mode。adapter 转换为
`(qpoint, mode, atom, xyz)`，即 `transpose(0, 2, 1).reshape(q, mode, atom, 3)`。

## Animation Contract

对 supercell atom `j`，给定其 primitive atom index `a_j` 和相对 primitive-cell
translation `R_j`：

`u_j(phase) = amplitude / sqrt(mass[a_j]) * Re[e(q,mode,a_j) * exp(i(2π q·R_j - phase + user_phase))]`

输入 `phase` 直接使用弧度，因此 Blender frame mapping 与实际秒数解耦。结果先形成
普通 `FrameSet`，再复用已有 trajectory frame handler；不为每帧创建 Object。

## Adapter Boundary

- 首批支持已经运行 `run_qpoints(..., with_eigenvectors=True)` 的 `Phonopy` object。
- phonopy YAML 负责 unit/primitive/supercell 输入，但 `band.yaml`/`mesh.yaml` 的独立
  结果解析推迟到有稳定 fixture 后。
- phonopy 4.4.0 late import，仅在 worker/core 环境；不进入 Extension ZIP。
- HDF5/h5py 不进入首批实现。

## Non-goals

- 不实现 phonon band publication plot、thermal properties、NAC 计算或 force constants。
- 不把 eigenvector 实部当作完整非 Γ 点模态。
- 不实现 PyProcar Fermi surface。

## Verification

- synthetic complex eigenvector 精确验证 `2πq·R`、mass scaling、phase 和 imaginary mode。
- real phonopy object 验证 axis transpose、primitive structure、frequency 和 group velocity。
- Blender smoke 复用单一 Mesh/FrameSet，验证两个 translation 的相位相反。
- 两套 Python tests、Extension validate/build、ZIP audit 和 isolated lifecycle 通过。
