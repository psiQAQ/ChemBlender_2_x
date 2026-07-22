# Excited States and Spectra

## Goal

将 cclib 激发态数据归一化为 ChemBlender `ExcitedStateSet`，从同一权威态数据派生 UV-Vis/ECD stick 与 broadened spectrum，并为 transition contribution、transition dipole 和 NTO/hole-electron dataset references 建立稳定身份。

## Success Criteria

- excitation energy、oscillator strength、state symmetry/multiplicity、rotatory strength 和 configuration contribution 具有明确 dims、unit、state identity、source calculation 与 provenance。
- cclib Gaussian/ORCA fixture 的 `etenergies`、`etoscs`、`etsyms`、`etsecs` 及可用 ECD 字段按真实 coverage 映射；缺失和 parser 差异显式报告。
- UV-Vis/ECD stick 与 Gaussian/Lorentzian spectrum 复用通用 `Spectrum` 约定，但不把振动 mode ID 与 excited-state ID 混用。
- configuration coefficients 的含义与自旋/占据-虚轨道索引明确；不把 coefficient 当概率，派生权重规则写入 provenance。
- `transition_density`、NTO hole/particle、hole-electron grids 以可选 dataset UUID references 表达，缺失时不创建空数组。
- core 不 import `bpy`，cclib 不进入 Extension。

## Constraints

- 本切片先覆盖 cclib 可稳定提供的垂直激发态；不自行执行 TDDFT、EOM-CC 或 NTO 分解。
- 不从 oscillator strength 推断 ECD rotatory strength，也不从 configuration 列表伪造 transition density。
- 能量输入单位必须依据 cclib contract 显式转换或保留，不能从数值范围猜测。
- Blender linked selection/panel 仅消费 state/dataset ID，不成为权威激发态模型。

## Next Action

核对 cclib 1.8.1 官方 attributes、parser coverage 与 Gaussian/ORCA TD fixture 中 `etenergies`、`etoscs`、`etsyms`、`etsecs`、`etrotats` 的实际 shape、unit 和自旋索引 convention，建立真实数值基线。

## References

- [持续开发路线图](../../docs/quantum-visualization/roadmap.md)
- [语义核心计划](../../docs/quantum-visualization/plans/semantic-core.md)
- [Blender 可视化计划](../../docs/quantum-visualization/plans/blender-visualization.md)
- [已完成的振动与光谱](../completed/vibrations-and-spectra.md)
