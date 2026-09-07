# EXP — 导出选择、损失与重新导入

执行者：**Agent 模拟用户**。UI **Passed（R14）**；MCP **Passed（R14）**。下文保留原失败与修复链。

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


## R14 独立重测

执行时间：2026-09-08 00:06–00:21 UI，00:22–00:26 MCP；逐批操作耗时记录于 `logs/ui-actions.jsonl`、`logs/mcp-actions.jsonl`。来源 commit `ffce8ffb09714ae697823198ec8d0a46cc800151`，ZIP SHA-256 `03cf499abf22e0ba1dd3dcbaace19e6b9c73103bd738f373528cad2d23cd9bd8`，Blender 5.1.1。

UI 从空文件重新导入同一不可变样例；Coordinates 的默认 extXYZ 无损失，切换 XYZ 即显示 FrameSet 格式拒绝，取消不写文件。导出 roundtrip.extxyz 后，选 Structure 切换 XYZ，预览立即列出 cell/PBC 和 associated datasets 遗漏，文件后缀同步。未确认的 unconfirmed.xyz 被拒绝且不存在；勾选确认后 confirmed.xyz 成功。两份导出均通过 Select Files、Preview、确认再导入。

MCP 在另一个空文件独立 quick_import/confirm_import，通过公开 Browser RNA 选择数据。export_project_entity INVOKE_DEFAULT 打开预览，读取 active_operator.loss_preview 并切换格式，file.cancel 取消；随后公开 EXEC 导出 extXYZ，未确认 XYZ 返回错误，显式 confirm_loss=True 成功，公开导入两份结果。首次 file.cancel 的测试脚本漏传临时文件窗口，返回 Area not found in screen；补齐公开 window+area context 后恢复，与插件无关。MCP 预览截图聚焦失败，09 图片不作为该预览证据；公开 JSON 和 10 最终截图有效。

| 检查 | UI | MCP | 实际结果 |
| --- | --- | --- | --- |
| 选择、格式预览、取消 | Passed | Passed | FrameSet→XYZ 明确拒绝，取消不输出 |
| 有损确认和错误恢复 | Passed | Passed | 未确认不输出，确认后恢复成功 |
| extXYZ round-trip | Passed | Passed | 2×1 坐标、4/5 Å 晶胞、PBC=T T T 完全一致 |
| XYZ round-trip | Passed | Passed | 保留 C/坐标；预览声明的 cell/PBC 缺失符合输出格式 |
| 视觉与保存 | Passed | Passed | 每条路径 3 个原子 View，EXP/UI 或 EXP/MCP 集合、配对文件与渲染 |

入口依赖先在 Browser 选对实体，初次使用需辨认 Structure 与 Coordinates；修复后文案和格式后缀一致。小文件导出立即完成，未观察到足够长的 worker 等待窗口，因此此样例只验证文件选择器取消，不声称实际中途打断导出 worker。三个 View 的 world location 为截图展示错开，科学坐标保持不变。

- [UI 损失确认截图](../../../../../.blend-analysis/2026-09-07-review/screenshots/EXP-R14-05-loss-confirmed-preview.png)
- [UI extXYZ 再导入预览](../../../../../.blend-analysis/2026-09-07-review/screenshots/EXP-R14-06-roundtrip-preview.png)
- [MCP 公开损失预览](../../../../../.blend-analysis/2026-09-07-review/outputs/EXP-R14-MCP-loss-preview.json)
- [MCP 最终窗口](../../../../../.blend-analysis/2026-09-07-review/screenshots/EXP-R14-10-MCP-final.png)
- [UI 渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/EXP-R14-UI-render-final.png) / [MCP 渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/EXP-R14-MCP-render-final.png)
- [UI 配对项目](../../../../../.blend-analysis/2026-09-07-review/outputs/EXP-R14-UI/EXP-UI.blend) / [MCP 配对项目](../../../../../.blend-analysis/2026-09-07-review/outputs/EXP-R14-MCP/EXP-MCP.blend)
- [科学数组、单位与文件 hash 核对](../../../../../.blend-analysis/2026-09-07-review/outputs/EXP-R14-science-check.json)

三个产品问题由 ffce8ff 修复，本项双方重测通过；最终全部 required case 同包复核仍待完成。
