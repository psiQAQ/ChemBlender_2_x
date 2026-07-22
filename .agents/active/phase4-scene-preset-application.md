# Phase 4 Scene Preset Application

## Goal

在 Blender application layer 重放已验证的 scene preset plan，先覆盖已有 adapter 能力，并为尚未实现的 surface/property contract 返回明确 unsupported 结果。

## Success Criteria

- structure、vibration/stick spectrum、electronic stick selection、band/DOS plan 可创建或配置实际 Blender objects。
- 每个对象保存 preset ID/version、render identity、entity IDs/revisions 与设置。
- 执行前复验 project binding；partial/stale plan 不创建对象。
- signed/property surface 若缺稳定 adapter，不静默降级或生成伪结果。
- Blender 5.1 isolated smoke 验证 apply、cleanup、register/unregister/reload。

## Constraints

- 不自动渲染、覆盖文件或修改用户相机/灯光。
- 不在 application layer 复制 core validation。
- 不新增模板引擎或量化依赖。

## Next Action

盘点 spectrum curve 缺口与现有 adapter 返回对象，先以 Blender smoke fixture 定义 plan application 的对象/metadata/rollback contract。

## References

- [Scene preset v1](../../docs/quantum-visualization/specs/scene-preset-v1.md)
- [Blender 可视化计划](../../docs/quantum-visualization/plans/blender-visualization.md)
- [Scene preset 决策](../decisions/0026-versioned-scene-presets.md)
