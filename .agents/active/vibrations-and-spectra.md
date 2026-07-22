# Vibrations and Spectra

## Goal

将 cclib 振动数据归一化为 ChemBlender `VibrationalModeSet` 与 `Spectrum`，提供可验证的 IR/Raman stick 与 broadened spectrum，并建立 Blender 原子位移箭头和正弦模态动画的最小闭环。

## Success Criteria

- 振动频率、位移、reduced mass、force constant、IR intensity 与 Raman activity 具有明确 dims、unit、mode identity、source calculation 与 provenance。
- cclib Gaussian/ORCA fixture 的已提供字段被映射；parser 未提供的字段和失败/不完整计算被显式报告。
- 虚频保持有符号频率并可在 UI/材质语义中区分，不被自动丢弃或取绝对值。
- stick spectrum 与 Gaussian/Lorentzian broadened spectrum 使用同一权威 mode/intensity 数据，坐标轴单位和归一化规则明确。
- Blender 端用单一 instanced-arrow node contract 表达位移，并按 `sin(phase)` 更新当前结构位置；不为每个箭头或每帧创建 Object。
- core 不 import `bpy`；纯 Python 模型、parser 和 spectrum tests 不启动 Blender。

## Constraints

- 本切片先覆盖谐振动和分子 IR/Raman；声子、复数 q-point eigenvector、VCD 与非谐频率留到对应阶段。
- cclib 缺失 Raman activity 时不得从 IR intensity 推断。
- 动画不得修改权威结构坐标；Blender Mesh 只保存当前显示帧。
- 不引入新的运行时依赖；谱线展宽使用 NumPy 或标准库实现。

## Next Action

核对 cclib 官方 attributes contract 与当前 Gaussian/ORCA fixtures 中 `vibfreqs`、`vibdisps`、`vibirs`、`vibramans`、`vibrmasses`、`vibfconsts` 的实际 shape、unit 和 parser coverage，建立真实数值基线。

## References

- [持续开发路线图](../../docs/quantum-visualization/roadmap.md)
- [解析与格式计划](../../docs/quantum-visualization/plans/readers-and-formats.md)
- [Blender 可视化计划](../../docs/quantum-visualization/plans/blender-visualization.md)
- [已完成的波函数 observables](../completed/wavefunction-observables.md)
