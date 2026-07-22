# Phase 2 Phonopy Complex Modes 实施计划

## Goal

完成 phonopy complex q-point modes 的 normalized model、adapter、相位求值与 Blender
trajectory 复用闭环。

## Plan

1. [x] 固定 phonopy 4.4.0 submodule，核对 eigenvector、frequency、group velocity 与 mapping contract。
2. [x] 先写 `PhononModeSet` complex dtype、shape、unit、structure reference tests，再实现模型。
3. [x] 先写纯函数的 phase、mass scaling、supercell translation tests，再实现 mode frames 派生。
4. [x] 先写真实 phonopy object mapping tests，再实现 late-import adapter 与 ParserReport。
5. [x] 扩展 Blender smoke，证明复数 q-point frames 复用 trajectory view。
6. [x] 更新 ADR、依赖、路线图和 active/completed 文档。
7. [x] 运行两套 Python tests、Blender validate/build、isolated lifecycle、ZIP audit 与 diff check。
8. [x] 创建阶段提交、快进合并本地 `main`，继续 Phase 2 Fermi-surface/PyProcar 评估。

## Verify

- eigenvector transpose 数值逐项一致；
- `q=(1/2,0,0)` 的相邻 primitive translations 产生相反位移；
- `phase=π/2` 保留 imaginary component 的贡献；
- negative frequency 不改变位移相位求值，仅作为虚频语义保留；
- Blender Extension 不包含 phonopy、h5py 或 submodules。
