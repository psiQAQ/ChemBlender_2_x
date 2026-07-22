# Phase 4 Publication Scene Templates

## Goal

在现有 Blender adapters、linked selection、recipe views 和 report artifacts 上定义可重放的 publication scene preset，使常见结构、表面、光谱和周期结果拥有明确而可审计的显示参数。

## Success Criteria

- 定义 versioned、纯数据 scene preset，不保存 `bpy` 对象或任意 Python callable。
- 首批 preset 覆盖结构、signed isosurface、property-on-surface、vibration/spectrum 和 band/DOS linked view。
- preset 参数映射到已有 adapter contract；缺失 dataset/view capability 时明确拒绝。
- 相同 entity revisions 与 preset 产生稳定 render identity，可进入 analysis report artifacts。
- 不新增第三方依赖，不复制大型 Blender asset。

## Constraints

- 首版不自动控制相机艺术构图、灯光优化或最终渲染农场。
- 不声称所有体系共享同一最佳 isovalue/色域；preset 保存明确参数与单位。
- 不实现数据库 connector 或远程任务。

## Next Action

盘点现有 Blender adapter settings 与 recipe view kinds，以失败测试定义 scene preset v1、binding validation 和 render identity。

## References

- [Blender 可视化计划](../../docs/quantum-visualization/plans/blender-visualization.md)
- [Recipe contract v1](../../docs/quantum-visualization/specs/recipe-contract-v1.md)
- [Analysis report manifest v1](../../docs/quantum-visualization/specs/analysis-report-manifest-v1.md)
