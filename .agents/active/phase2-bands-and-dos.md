# Phase 2 Fermi Surface Evaluation

## Goal

评估并实现最小 reciprocal-space / Fermi-surface schema，确定 PyProcar 是否作为首选外部 adapter。

## Success Criteria

- Fermi surface mesh 保留 reciprocal coordinate convention、Fermi level、band/spin identity。
- vertex properties 可表达 orbital contribution、spin texture 与 Fermi velocity。
- Blender Mesh 与已有 band/DOS/Structure UUID 可联动。
- 明确 PyProcar 许可、版本、支持程序与直接依赖代价。

## Constraints

- 不实现完整 publication UI 或所有 PyProcar parser。
- 不把 PyProcar/pymatgen/scikit-image 打入 Blender Extension。
- 如果 PyProcar 数据模型不能稳定解耦，先实现中立 mesh schema 和 adapter boundary。

## Next Action

核对 PyProcar 最新稳定版本、许可证、核心 Fermi-surface mesh API 与依赖；仅在需要逐行实现证据时拉取 submodule。

## References

- [周期电子结构计划](../../docs/quantum-visualization/plans/periodic-electronic-structure.md)
- [phonopy 复数模态决策](../decisions/0013-phonopy-complex-mode-boundary.md)
