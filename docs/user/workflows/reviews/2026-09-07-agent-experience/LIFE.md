# LIFE — 配对保存、Save As、冷重开与恢复

## R25 最终复核

执行者：**Agent 模拟用户**。2026-09-08，Blender **5.1.1** / Python **3.13.9**。源码 `039bde7e1bf028b4b691d888d51460ae331ff678`；ZIP SHA-256 `661c58f82ae0a5564d37e713eca281e992ad24fd5b5b81fe2b2aee321862368b`。

UI 与 MCP 各使用独立的干净测试副本。按用户授权，重复动作从 [UI → MCP 命令目录](../../../../../tests/blender_review_commands.py) 读取公开命令；原生首测证据保留在下方阶段记录，重放不记为新的原生 UI 首测。

本次范围：重开既有 revision 比较项目、Save As 新配对，UUID/manifest 一致；Connected 状态拒绝不适用的 Verify。

| 路径 | 最终结果 | 状态与耗时证据 | 配对文件 |
| --- | --- | --- | --- |
| UI | Passed（上述复核范围） | [操作结果](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-LIFE-UI-actions-summary.json)；[加载状态](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-LIFE-UI-loaded.json) | [最终副本](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25/LIFE/UI/LIFE-UI-saveas.blend) |
| MCP | Passed（上述复核范围） | [操作结果](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-LIFE-MCP-actions-summary.json)；[加载状态](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-LIFE-MCP-loaded.json) | [最终副本](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25/LIFE/MCP/LIFE-MCP-saveas.blend) |

所有最终副本的安装 Python 字节与 R25 ZIP 匹配，Reader API、Scene RNA、公开 poll 通过；原始配对文件及其权威数组未被本轮复核改写。[完整性核查](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25-integrity.json)与[逐项范围索引](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25-review.json)记录 UUID、manifest hash 和数组检查。每条命令的 JSON 留有实际 `seconds`，不将观察间隔计入产品等待。

最终 [14 集合展示文件](../../../../../.blend-analysis/2026-09-07-review/outputs/final-gallery/ChemBlender-R25-14-cases.blend)含本项同名 Collection 和 UI/MCP 子集合；[总览渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/FINAL-R25-gallery.png)与[真实窗口](../../../../../.blend-analysis/2026-09-07-review/screenshots/FINAL-R25-gallery-window-14-collections.png)已查看。展示模型按单体缩放，不用于科学距离比较；科学操作使用上表配对文件。

## 阶段验收记录（保留当时状态）

以下版本、失败和“待最终复核”描述对应当时检查点；当前结果以上方 R25 复核为准。

执行者：**Agent 模拟用户**。UI **Passed（R16 完整路径、R17 revision 重测）**；MCP **Passed（R16 保存恢复、R17 revision 重测）**。最终同包全项复核待完成。

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

R16 / 2d55e0d 的干净 UI 完整路径通过：Select Files 导入 21-atom MOL，Save Project 一次配对，Save As 跨目录配对，正常退出 PID33140 后以 PID2156 冷重开，启用键与 saved UUID/hash 一致。两个独立恢复副本分别完成 Missing→Verify 拒绝→恢复原目录→Verify 成功，以及 Missing→选择 relocated.cbq/manifest.json→Relink 成功。

受控 water.xyz 工作副本重新导入 +1 Å X 平移版本时，UI Preview 提示 New Revision；确认后旧 View 坐标保持不变，Comparison 建立新 View。最终 LIFE/UI 集合含 21-atom aspirin 和两个 3-atom water Views，蓝色旧版本、红色新版本；展示位置偏移不写入科学数组。

- [R16 UI 最终配对](../../../../../.blend-analysis/2026-09-07-review/outputs/LIFE-R16-UI-final/LIFE-UI.blend)
- [R16 UI 渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/LIFE-R16-UI-render-final.png)
- [冷重开](../../../../../.blend-analysis/2026-09-07-review/outputs/LIFE-R16-UI-cold.json)
- [Verify 恢复截图](../../../../../.blend-analysis/2026-09-07-review/screenshots/LIFE-R16-21-verify-restored.png)
- [Relink 身份](../../../../../.blend-analysis/2026-09-07-review/outputs/LIFE-R16-UI-relinked.json)
- [Comparison 科学坐标](../../../../../.blend-analysis/2026-09-07-review/outputs/LIFE-R16-UI-revision-comparison.json)

MCP 独立空场景导入 Preview 0.365 s、确认 0.337 s；公开 wm Save/Save As、Missing Verify 拒绝与原位恢复、Relink directory 均通过。冷重开最终 PID11352 的启用键、21 atoms、UUID/hash 一致。MCP weak_sandbox 禁止 wm.quit_blender；进程关闭由外部原生输入测试脚本完成，产品操作仍走 MCP。脚本曾在确认退出失败前多开 PID10484，两份自建进程正常关闭后才重启；不把该重复启动记作通过。

MCP 的 New Revision 确认在 Blender collection→RNA 转换时失败：动态 conflict_action 尚看不到 allowed_actions，new_revision 被拒绝。High：阻断合法 revision，未改变源科学数据；完整失败配对与 Preview 冻结于 outputs/failures/LIFE-revision-rna/。旧 ZIP 原生回归也复现 reuse_existing 被拒绝。R17 最小修复把 allowed_actions 放在动态枚举之前；新增真实 RNA 复用/新 revision 回归。第一次新 smoke 的数值断言写错 Structure 字段，已改用 coordinates.values，保留该测试错误日志。完整验证及双路径重测仍在执行。

R17 自动验证：99 专项、2308 全量（26 skips）、隔离 smoke 104.89 s、compile/docs/native build/ZIP audit/verifier 均通过。包 319de78bf3f4d27c3df5e8864cc3f67d3f2f7b02d72216f8aeb47c26331e3f91，29,987,802 packed / 32,106,657 unpacked；只有 import_preview.py +151 unpacked / +77 packed，allowance 为零。

R17 / 4b280c3 两个测试 profile 已安装并逐字节核对全部 packaged Python。UI 从原 aspirin 配对干净副本经真实 Open、Select Files、Preview、Reuse Existing、新 revision 无默认 View、Comparison 完成；MCP 从独立 aspirin 配对干净副本经公开 Operators 完成同样流程。MCP Preview/confirm：original 0.682/0.374 s，reuse 0.351/0.363 s，new 0.653/0.549 s。复用保持两个 mesh，Comparison 后三个 mesh；两个 water 的原子 X 分别为 [0, 0.758602, -0.758602] 与 [1, 1.758602, 0.241398]，旧数据不变。蓝/红颜色与摆位仅为展示。

测试脚本曾因语法错误未打开干净副本却继续下一步；这些 LIFE-R17-MCP-original/reuse/new 前缀记录无效，说明在 outputs/LIFE-R17-MCP-invalid-prestate.json。已增加本地 compile 与 RPC 非零退出码，重新打开并验证单 aspirin 前置，仅 LIFE-R17-MCP-final-* 计入上述通过。

- [UI 最终配对](../../../../../.blend-analysis/2026-09-07-review/outputs/LIFE-R17-UI/LIFE-UI-saveas.blend) / [渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/LIFE-R17-UI-render-final.png)
- [MCP 最终配对](../../../../../.blend-analysis/2026-09-07-review/outputs/LIFE-R17-MCP/LIFE-MCP-saveas.blend) / [渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/LIFE-R17-MCP-render-final.png)
- [UI 包绑定](../../../../../.blend-analysis/2026-09-07-review/outputs/LIFE-R17-UI-final-package.json) / [MCP 包绑定](../../../../../.blend-analysis/2026-09-07-review/outputs/LIFE-R17-MCP-final-package.json)

体验评价：Save Project 入口易找到；Relink 明确选择 manifest 后可恢复；Preview 有 staged/committed 反馈和取消；revision 选择清楚，失败未改变旧数据。保存和确认通常小于一秒，文件选择输入时间另见 ui-actions.jsonl。集合均为 LIFE 下的 UI 或 MCP。完整冷重开/恢复证据属于 R16，未冒称已在 R17 全路径重走。
