# Scene Preset Application

## Result

- `validate_scene_plan()` 在 Blender 副作用前按当前 project UUID/revision 重建 plan，并拒绝 stale 或被修改的计划。
- `apply_scene_preset()` 支持 structure、vibration/stick spectrum、electronic stick spectrum 与 band/DOS。
- 新增 `spectrum_curve_v1`，stick spectrum 每个 sample 使用独立竖线 Curve spline。
- 每个对象保存 preset ID/version、view kind、render identity、settings 与 binding ID/revision。
- adapter 中途失败会删除本次新建 Object 和无用户 datablock；未实现的 surface view 在创建前显式失败。

## Verification

- Blender Python：273 tests passed，27 skipped。
- Blender 5.1.2：extension validate/build 通过；隔离安装 smoke 验证 apply、stale-plan、rollback、register/unregister/reload，退出码 0。

## Remaining Boundary

`signed_isosurface` 与 `property_on_surface` 仍为显式 unsupported；由下一 active phase 实现。
