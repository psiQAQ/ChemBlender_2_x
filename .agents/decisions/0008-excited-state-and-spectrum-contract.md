# 0008：激发态与电子光谱采用可追踪 state dataset 契约

## Status

Accepted for the Phase 1 molecular excited-state closure.

## Context

cclib 可以从 Gaussian、ORCA 等输出提取垂直激发能、振子强度、态标签、组态贡献和部分跃迁矩，但各 parser 的可选字段覆盖不同，`etrotats` 也没有统一公开单位。振动光谱已有 `Spectrum`，但其 source 与 selection 字段不能继续假设来源一定是振动 mode。

## Decision

- 用 `ExcitedStateSet` 保存 `(state,)` 激发能以及同一 state identity 下的可选强度、跃迁偶极、态标签、multiplicity 和 ragged configuration。
- `ExcitationContribution` 保留 zero-based 轨道索引、alpha/beta spin 和带符号 coefficient；`weight` 只作为 `coefficient**2` 的显式派生值。
- transition density、NTO hole/particle 和 hole/electron density 通过每态可选 dataset UUID 引用，不以空数组表示缺失。
- `etrotats` 保留原值与 `unknown` unit，并使 dataset/ECD spectrum 为 `ambiguous`；不跨 parser 猜测物理单位。
- `Spectrum` 通过 kind 校验来源类型，使用通用 `selection_policy`；电子展宽在 wavenumber 轴上执行。

## Consequences

- UV-Vis 与 ECD 可复用相同的 stick/Gaussian/Lorentzian kernel，同时不会混用 mode 与 state UUID。
- 缺失的 transition density 或 NTO 不阻止能量与强度进入项目；非法 configuration 进入 `ParserReport.INVALID`，不删除其他已解析态数据。
- wavelength 只适合作为后续 UI 派生显示；当前不会在非线性 wavelength 轴上错误套用 wavenumber FWHM。

## Verification Contract

1. Gaussian 16/09 与 ORCA TD/ADC2 fixture 固化 state count、首个能量、dipole/rotatory coverage 与 configuration 结构。
2. signed coefficient 与 signed ECD intensity 在模型和派生光谱中保持不变。
3. unknown rotatory unit 必须显式产生 ambiguous issue/status。
4. 项目提交拒绝 dangling structure、state-derived dataset 和错误类型的 spectrum source。
5. cclib、SciPy 与 fixture/submodule 不进入 Blender Extension ZIP。
