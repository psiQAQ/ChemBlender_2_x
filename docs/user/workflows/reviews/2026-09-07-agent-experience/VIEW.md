# VIEW — Structure、Grid、力属性与轨迹

执行者：**Agent 模拟用户**。UI **Failed（修复后重测中）**；MCP **Not Run**。本项尚未完成，不能作为最终候选包通过证据。

## 前置与输入

独立空文件 VIEW UI，VIEW/UI 集合；使用本轮 `inputs/VIEW-grid-trajectory/` 中的不可变副本 `aspirin-rmd17-32.extxyz` 和 `two-datasets.cube`。前者为 32×21 坐标及 force/energy；后者为两个 2×2×1 数据集，原始语义/值单位需确认。副本哈希见本轮 `inputs/VIEW-grid-trajectory-copies.json`。

## UI 已执行

1. N → ChemBlender → Select Files，多选两个文件。Preview 中保留 aspirin 的默认 View，取消 Cube 的默认 View，确认独立来源导入。
2. Browser → By Data → 搜索 Grid → 选择 Ambiguous Scalar Field。选择 dataset index 1、generic_scalar、dimensionless，点击 Resolve。
3. 在修复后的 R9 包中，Browser 保持选中 Complete 派生 Grid；点击 Volume、Signed Surface，生成一个 Volume 和正负表面两个对象。公开绑定均指向新 Grid，输出显示坐标 Å、源坐标 bohr，比例为 0.529177210903。正值数据的负表面为空是预期结果。
4. Outliner 选择 aspirin Structure；Browser 搜索 force → Atomic Force → Show Force Vectors，窗口显示箭头。选择 Coordinates → Configure Trajectory Playback，时间轴结束帧变为 32。
5. 通过时间轴输入 32，坐标由首帧变为末帧，但 `cbq_vector` 与首帧完全相同。科学显示不一致，停止验收并保存失败现场。

R9 实际窗口操作约 22:29–22:41；Volume、Surface 和播放配置均在 1 秒等待后已有可见结果。每个原生输入批次的精确耗时见 `logs/ui-actions.jsonl`。尚未执行完整播放/暂停、丢失缓存恢复、最终渲染和独立 MCP 流程。

入口评价：相关按钮可找到，但 Import Diagnostics 固定展开且很长，数据操作需要反复滚动；已解决的 Grid 旁仍显示原始导入的 Ambiguous 诊断，容易与当前 Complete 状态混淆。短操作有状态栏完成提示。科学错误的恢复尚待重测。

## 失败与修复链

| 问题 | 严重程度与科学影响 | 失败证据 | 修复与重测 |
| --- | --- | --- | --- |
| Resolve 后重新选回旧 Grid | High；后续 View 可能使用未确认语义的源数据 | `outputs/failures/VIEW-grid-selection/`；旧 ZIP 的实际 smoke 断言失败 | `0a0a2af`；R9 UI 已重新导入并选中新 Complete Grid，完整自动验证通过；MCP 待测 |
| 力箭头没有随坐标帧更新 | High；第 32 帧坐标配第 1 帧力值，界面未提示 | `outputs/failures/VIEW-force-frame/`；frame1/frame32 状态 JSON；旧 ZIP smoke 的 `force vectors did not follow the trajectory frame` 失败 | 修复绑定当前 force 数据集到播放，缺失力帧隐藏箭头并显示原因；最终包 UI/MCP 重测中 |

R9 来源 `0a0a2af`；包 SHA-256 `6e4d0216843663325c8f6a44f2b7accdb67e0c86a7d96c4b1d2e6d8f955c88d8`。失败配对目录保存后已冻结，后续不在其中导入或保存。

- [已解析 Grid 截图](../../../../../.blend-analysis/2026-09-07-review/screenshots/VIEW-R9-03-resolved.png)
- [Volume 截图](../../../../../.blend-analysis/2026-09-07-review/screenshots/VIEW-R9-04-volume.png)
- [Signed Surface 截图](../../../../../.blend-analysis/2026-09-07-review/screenshots/VIEW-R9-05-surface.png)
- [力箭头与播放入口](../../../../../.blend-analysis/2026-09-07-review/screenshots/VIEW-R9-08-trajectory-controls.png)
- [末帧失败截图](../../../../../.blend-analysis/2026-09-07-review/screenshots/VIEW-R9-10-frame32.png)
- [首帧状态](../../../../../.blend-analysis/2026-09-07-review/outputs/VIEW-R9-UI-frame1.json)、[末帧状态](../../../../../.blend-analysis/2026-09-07-review/outputs/VIEW-R9-UI-frame32.json)、[旧包回归失败日志](../../../../../.blend-analysis/2026-09-07-review/logs/isolated-force-before.log)
