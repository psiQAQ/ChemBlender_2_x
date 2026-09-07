# EXP — 导出选择、损失与重新导入

执行者：**Agent 模拟用户**。UI **Failed（修复后重测中）**；MCP **Not Run**。

前置：独立空文件 EXP UI，输入为本轮 `inputs/EXP/carbon-trajectory.extxyz` 不可变副本，2 帧、每帧 1 个碳原子，晶胞边长 4/5 Å，PBC=T T T。先保存 EXP/UI 集合及配对文件。

UI 步骤：Select Files → Preview → 确认；Browser By Data 选 Coordinates → Export Selected Data。默认 extXYZ；改为 XYZ，取消。再选 Structure → Export Selected Data，默认 CIF；改为 XYZ，保留未勾选的损失确认，写入本轮新文件 lost-cell.xyz。

实际结果：格式已变为 XYZ，公开 loss_preview 和窗口仍显示 CIF 计划；FrameSet 改 XYZ 时也未即时显示格式拒绝。XYZ 输出只有元素和坐标，晶胞/PBC 被省略，且没有要求确认。默认文件名曾为当前 EXP-UI.blend，已使用显式新路径避免覆盖。原始科学数组未修改。

| 问题 | 严重程度 / 影响 | 证据 / 修复 |
| --- | --- | --- |
| RNA 格式变化没有刷新 Python Operator 的预览 | High，确认依据与实际目标格式不一致 | `EXP-R13-10-xyz-stale-preview.png`、公开 preview JSON；回调实际收到 OperatorProperties，缺少 Python 方法 |
| XYZ 未列出晶胞/PBC 等科学数据损失 | High，用户可无确认导出有损数据 | `lost-cell.xyz`；新增 periodic loss 与未确认 worker 拒绝回归先失败 |
| 文件选择器沿用当前 blend 名称 | High，目标易选成当前项目 | `EXP-R13-04-export-preview.png`；新增默认数据文件名和拒绝覆盖当前 Blender 文件的回归 |

来源 `e42b16fcaf2a98447915c3310fb5b6662705a0df` / R13 ZIP `a478b65910fcfff44f02914935527131a33ba131c80b26bb199074a4ce627876`。失败配对目录完整冻结于 `outputs/failures/EXP-preview-loss/`，后续不在其中导入或保存。原生 UI 时间约 23:49–23:55；每批动作耗时见日志。取消文件选择器后场景仍可使用，未写输出；尚未完成正常 extXYZ round-trip、损失确认重测和独立 MCP。

- [失败截图](../../../../../.blend-analysis/2026-09-07-review/screenshots/EXP-R13-10-xyz-stale-preview.png)
- [失败配对文件](../../../../../.blend-analysis/2026-09-07-review/outputs/failures/EXP-preview-loss/EXP-UI.blend)
- [预览状态](../../../../../.blend-analysis/2026-09-07-review/outputs/EXP-R13-UI-xyz-preview.json)
- [回归失败日志](../../../../../.blend-analysis/2026-09-07-review/logs/export-preview-before.log)

修复后 64 项专项、2303 项完整单测（26 skips）、完整隔离 smoke 105.39 秒、原生构建、ZIP 审计和 verifier、compile/docs 检查均通过。R14 最终包 `03cf499abf22e0ba1dd3dcbaace19e6b9c73103bd738f373528cad2d23cd9bd8` 相对 R13 仅 ui/export.py 增加 2633 unpacked / 636 packed 字节，未解释 allowance 为零。真实窗口快速重测已显示 XYZ 的正确遗漏信息和同步 .xyz 后缀；完整干净 UI/MCP 仍待完成。中间包 78f15b9a 缺少后缀修复，仅保留历史证据。
