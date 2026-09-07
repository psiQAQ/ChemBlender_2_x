# LIFE — 配对保存、Save As、冷重开与恢复

执行者：**Agent 模拟用户**。UI **Failed（修复后重测中）**；MCP **Not Run**。

前置：独立空 LIFE UI，导入本轮不可变 ain-aspirin-v2000.mol，21 atoms / 21 bonds。原生点击 Select Files、Preview、确认；Quick Import 的 Save Project 首次仅保存 blend，第二次保存产生 cbq。随后 Ctrl+Shift+S 另存新目录，界面显示 Connected、clean，却没有新 cbq，locator 仍为 LIFE-UI.cbq。原配对完整，科学数组未改变。

| 问题 | 严重程度与影响 | 证据 / 修复 |
| --- | --- | --- |
| Save As 忽略目标路径 | High；新文件不能独立重开，clean 状态误导 | R14/ffce8ff、03cf499a；两个单测及旧 ZIP 原生回归失败。使用 save_pre 传入的 filepath；首次保存和 Save As 一次发布正确配对 |

失败现场冻结于 outputs/failures/LIFE-saveas-status/，包含原配对和缺失 sidecar 的另存文件。后续 handler 诊断在工作副本创建 handler-probe.blend，并可能补出了 sidecar；不将后来的副本状态混作原失败。原生诊断记录证实保存回调收到新路径而 bpy.data.filepath 仍旧；官方 Blender 3.6 API 变更也说明保存 handler 接收 filepath：[Blender Python API](https://developer.blender.org/docs/release_notes/3.6/python_api/)。

- [失败截图](../../../../../.blend-analysis/2026-09-07-review/screenshots/LIFE-R14-06-saveas.png)
- [保存状态](../../../../../.blend-analysis/2026-09-07-review/outputs/LIFE-R14-UI-saveas-first.json)
- [回调实测](../../../../../.blend-analysis/2026-09-07-review/outputs/LIFE-save-handler-observation.json)
- [失败文件](../../../../../.blend-analysis/2026-09-07-review/outputs/failures/LIFE-saveas-status/LIFE-R14-UI-saveas/LIFE-UI-saveas.blend)
- [旧包回归失败](../../../../../.blend-analysis/2026-09-07-review/logs/isolated-save-destination-before.log)

修复后 42 项 session 专项通过。完整 smoke 的新增跨目录用例第一次使后续 Relink 原有“同目录 basename”假设失效；把 Relink fixture 放在新 blend 同目录后，保持其原有相对 locator 校验。第二个隔离 profile 安装时 Windows 拒绝重命名目录，未启用插件；新的隔离 profile 完整 smoke 104.49 秒通过。Windows 已加载 RDKit DLL 清理警告保留在日志，不触及真实用户目录。

R15 包 8d8e7ed5e870f23a038dad8fbe7638f110a9c98820f4c5c4451019c6b13abe75；29,987,310 packed / 32,104,077 unpacked。只有 ui/session.py +167 unpacked / +86 packed，allowance 为零。完整单测及干净 UI/MCP、冷重开、Verify/Relink、revision 仍在执行，不把自动验证替代体验结果。

R15 完整单测 2305 / 26 skips / 零失败；UI 首次 Save 和跨目录 Save As 一次产生正确配对。原生保存 Preferences 后关闭原测试进程，以 Blender 5.1.1 新进程 PID33140 冷重开：启用键、project UUID、link 和 21 atoms/21 bonds 恢复。早先未保存测试 profile 的启用首选项导致一次无插件启动，属于测试前置错误，不记通过。

- [R15 单次保存](../../../../../.blend-analysis/2026-09-07-review/screenshots/LIFE-R15-01-first-save.png)
- [冷重开状态](../../../../../.blend-analysis/2026-09-07-review/outputs/LIFE-R15-UI-cold-final.json)

随后在工作副本移动 sidecar，Missing 和 Verify 拒绝符合预期；Relink 原生选择器不能确认目录，选 manifest.json 会重复拼接路径。直接公开 Operator 诊断即使传目录也因 Missing 会话的临时空 project UUID 而拒绝。失败冻结于 outputs/failures/LIFE-relink-selector/。这是 High 恢复缺陷，原权威数组未改变。

R16 修复选择器、保存身份校验和状态刷新；候选必须匹配已有 Scene 的 UUID/schema/manifest hash，冲突或残缺 link 不采用。完整测试最初暴露三个旧迁移回归，已在原有可回滚事务内显式发布新 generation，保留失败回滚及重开检查。最终 120 专项、2308 全量/26 skips、隔离 smoke 105.12 s 均通过。包 e79c84cdb18c6e4345e48a42747689137b82d55191a33d4baff3c27a0568b9f2，29,987,725 packed / 32,106,506 unpacked；相对 R15，project_service.py +1355/+177、migration.py +325/+94、Browser panel +749/+144。

R16 原生输入脚本曾在未打开文件选择器时误输路径，影响了测试视图。未保存这些误操作，通过 File > Open > Don't Save 重开原测试副本；已增加文件选择器状态保护。这些截图属于测试执行故障，不是产品流程通过证据。修复后的完整 UI/MCP LIFE 仍待完成。
