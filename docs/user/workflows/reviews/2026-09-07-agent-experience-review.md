# ChemBlender 本轮体验验收

执行者：**Agent 模拟用户**。日期：2026-09-07，Asia/Shanghai。
本轮独立记录，不改写历史人工验收。当前仍在执行，未完成项目不能视为通过。

## 当前检查点

最近完成自动验证的 R22 ZIP `82529f5564f8b4f9b319785c35094700c431747ff2daa3b438312c6a2b3a8e56`（1c290ee）：2,313 tests，26 skips，无失败/错误；隔离smoke104.33s，两配置独立冷依赖检查Passed。REP-MOLECULAR完整UI/MCP重测Passed。以下旧包结果保留为失败—修复链，最终仍需全项复核。

| 项目 | UI | MCP |
| --- | --- | --- |
| ENV | 隔离安装与 reload 已验证；实际用户安装 Blocked | 隔离安装已验证；待最终复核 |
| IMP | f2cbd41 通过；待最终包复核 | f2cbd41 通过；待最终包复核 |
| DATA | R8 Passed；待全轮最终复核 | R8 Passed；待全轮最终复核 |
| VIEW | R13 Passed；待全轮最终复核 | R13 Passed；待全轮最终复核 |
| EXP | R14 Passed；待全轮最终复核 | R14 Passed；待全轮最终复核 |
| LIFE | R16/R17 Passed；待最终包复核 | R16/R17 Passed；待最终包复核 |
| MIG | R20 Passed；待全轮最终复核 | R20 Passed；待全轮最终复核 |
| AGENT | R21 Passed；待全轮最终复核 | R21 Passed，冷依赖已修复；待最终复核 |
| OUTSIDE | R21 Passed；待全轮最终复核 | R21 Passed；同步渲染中途取消Not Run；待最终复核 |
| REP-MOLECULAR | R22 Passed；待全轮最终复核 | R22 Passed；待全轮最终复核 |
| REP-TRAJECTORY | R22 Passed；待全轮最终复核 | R22 Passed；待全轮最终复核 |
| [REP-BIOLOGICAL](2026-09-07-agent-experience/REP-BIOLOGICAL.md) | Passed（原生首测，R24 按授权 MCP 重放复核） | Passed（独立 R24） |
| [REP-CRYSTAL](2026-09-07-agent-experience/REP-CRYSTAL.md) | Passed（按授权重放及窗口检查） | Passed（独立 R24） |
| [REP-GRID](2026-09-07-agent-experience/REP-GRID.md) | Passed（R25 干净重放、原生修复检查、新进程冷恢复） | Passed（独立 R25、真实 Cycles、冷恢复） |

## 源码、环境与证据

- 独立分支：`fix/quantum-input-units-experience-review`；首阶段修复：`bed5cab`。
- Blender **5.1.1**，bundled Python **3.13.9**，Windows；不引用历史 5.1.2 或远端 CI 作为本轮通过证据。
- 已构建 ZIP：`63bc260e465132ad9ea45ee7e2060dfa16a45c87331e118d09dc2f6f232449b3`，29,983,410 bytes。
- 证据目录：[本轮文件](../../../../.blend-analysis/2026-09-07-review/)。原生输入及 MCP 请求分别记录在 `logs/ui-actions.jsonl`、`logs/mcp-actions.jsonl`。
- 用户自存的根目录 `1.blend` 不属于本轮产物；测试窗口独立 profile，MCP 端口 9877。
- 2,289 项 unittest：零失败/错误、26 skips；详见 `logs/unit-final.log`。compileall、生成文档检查、原生 validate/build、五文件 artifact verifier 已通过。

## 包体归因

历史预算为 29,977,165 bytes / 32,066,803 unpacked bytes。当前为 29,983,410 / 32,088,516；增加 6,245 packed / 21,713 unpacked bytes。资源与两个固定 wheel 的内容和大小保持一致。

| 成员 | 相对历史预算的 unpacked bytes 变化 | 原因 |
| --- | ---: | --- |
| core/formats/gaussian_input.py | +9,601 | 既有 Gaussian reader 加入后未更新预算，本轮加入单位校正 |
| core/formats/orca_input.py | +9,161 | 既有 ORCA reader 加入后未更新预算，本轮加入单位校正 |
| core/formats/__init__.py | +359 | 已提交的 reader 导出 |
| core/reader_catalog.py | +286 | 已提交的 reader 注册 |
| core/__init__.py | +396 | 已提交的公开 core 导出 |
| core/import_pipeline/conflicts.py | +92 | 相同文件的 reader 版本变化触发 revision 冲突 |
| core/storage/publication.py | +199 | 发布前关闭 Windows lazy array 映射 |
| ui/project_browser/panel.py | +1,619 | 历史包使用 LF；当前标准 Git checkout 为 CRLF，共 1,619 行 |

在独立历史 checkout `255cdce` 原生重建得到 29,977,234 bytes；仅将该 panel 恢复 LF，即重现历史包的 29,977,165 bytes 和 32,066,803 unpacked bytes。ZIP 时间戳不同，因此不宣称复现历史 SHA。详细成员对比与重建记录见 `package-native-delta.json` 和 `baseline-reconstruction.json`。本轮相对开始时源码的实际增加为 4,214 unpacked bytes；其余是已提交 reader 与历史换行基线的补齐。全部 unexplained-growth allowance 保持 **0**。

## 体验进度

14 项将分别保存明细，UI 和 MCP 使用独立前置状态。真实 UI 通过原生鼠标、键盘、菜单和弹窗操作；公共 MCP 仅使用公开 Operator 与公开状态。测试脚本的 HWND/键盘扫描码问题已修正，不能归为产品缺陷。

## UI 现场修复：Project Browser

`IMP-05-water-view.png` 与 `logs/ui-blender-error.log` 记录了真实 draw 上下文禁止写 Scene RNA 的失败，导致 Browser 空白。保存失败现场为 `outputs/failures/IMP-before-browser-fix.blend` 及其 `.cbq`。新增回归先失败；修复将投影更新延后到一次性主线程 timer，合并重复请求，并在文件切换/卸载时取消 timer。源码全量重测 2,290 tests / 26 skips / 0 failures or errors；仍需新包 UI/MCP 复核。

修复 ZIP：`7579c1541eb242cb9220d3c7ff40296446d3f083641cf5c0c50c3f1fb9dc2112`，29,983,926 bytes；只有 `ui/project_browser/panel.py` 相对首包增加 2,087 unpacked bytes，压缩包增加 516 bytes。源码 section 2,695,847 bytes、总解压 32,090,603 bytes。新的五文件审计位于 `package-browser-fix/`，旧包保留在 `package/`，通过记录不会混用。

新包 UI 安装/重启用后，`ENV-R2-04-browser.png` 已实际显示 `No project data`、By Source/By Data 与筛选，错误日志没有 draw traceback。完整隔离 smoke 通过，耗时 103.48 s；仍需重跑有数据的 IMP 与 MCP 复核。


## 导入体验补充修复

`22b654d` 修复取消摘要与预览标签；ZIP `c5e438aefeb200e32dfcb5a09b73825acdc5dc6971a3acd64d9f85349c7c4207` 为 29,983,936 bytes，相对 Browser 修复包只有 `ui/import_preview.py` 增加 185 unpacked / 10 packed bytes。完整隔离 smoke 通过，102.91 s。

逐项记录：[ENV](2026-09-07-agent-experience/ENV.md)、[IMP](2026-09-07-agent-experience/IMP.md)。IMP UI 已保存六个 Structure View、IMP/UI 集合、配对 sidecar 与渲染。MCP 检查复现强制 Preview 残留及显式确认值被默认值覆盖，当前修复正在进行最终包复测；其余 12 项尚未执行，不能视为通过。

新增构建 `c206b53e5cb94c8c9a568740b1297d710d001d43175ecca64f2045f8457dd311` 为 29,984,397 bytes，解压 32,092,532 bytes。相对上一包：import_preview.py +369 unpacked / +84 packed，properties.py +1287 / +353，quick_import.py +88 / +24。只有三处公开导入反馈实现变更，所有未解释增长 allowance 仍为 0；审计五文件保存在 package-mcp-preview/。

R6 仅 ui/session.py 增加 742 unpacked / 209 packed bytes，用于注册后恢复已保存 session；包 29,984,722 bytes，总解压 32,093,564 bytes。资源/wheel 未变，所有未解释增长 allowance 为 0。中间同步注册失败包 99234f3f 已淘汰，失败日志仍保留。


R8 DATA 双路径完成，详见 [DATA 独立报告](2026-09-07-agent-experience/DATA.md)。该报告保留生物不可见缺陷、dc1ff3d 修复、回归与 UI/MCP 结果，以及旧证据副本被测试脚本继续使用后的状态纠正。最终配对文件按 DATA/UI 与 DATA/MCP 集合保存。其他 11 项仍未执行。

VIEW 的 Grid 选择和力箭头缺陷链见 [VIEW 独立报告](2026-09-07-agent-experience/VIEW.md)。b05dd5c 对应当前最终自动验证包；相对 R9，trajectory_view.py 增加 1716 unpacked / 473 packed bytes，Browser panel 增加 1487 / 288，总包增加 761 bytes，unexplained allowance 为零。窗口重新安装后从空文件重跑 UI；MCP 仍等待 UI 完整结束后独立执行。

R13 VIEW 双路径完整重测通过，详见 [VIEW](2026-09-07-agent-experience/VIEW.md)。配对文件各有 VIEW/UI 或 VIEW/MCP 集合，截图与渲染均保留。此阶段文件重开为同进程，不代替 LIFE 的冷启动。其余 10 项继续执行。

迁移独立报告：[MIG](2026-09-07-agent-experience/MIG.md)。两条路线有独立集合、渲染、完整配对和冷重开证据。继续 AGENT、OUTSIDE 和五类代表输入；最终同包复核与总展示文件尚未完成。

[AGENT独立报告](2026-09-07-agent-experience/AGENT.md)包含单位诊断修复、原生连接恢复与MCP测试profile冷依赖修复的完整证据。还剩OUTSIDE与五类代表输入，以及最终同包复核和14集合总展示文件。

[OUTSIDE独立报告](2026-09-07-agent-experience/OUTSIDE.md)：真实Eevee双路径渲染、材质作用范围、集合、配对与重开通过。剩五类代表输入、最终同包复核和14集合总展示文件。

[REP-MOLECULAR独立报告](2026-09-07-agent-experience/REP-MOLECULAR.md)：八类输入两路线各保存集合、八张独立渲染和配对文件；59个数组hash相同。MOL2误标修复后完整重测通过。剩四类REP、最终同包全项复核和14集合总展示文件。

[REP-TRAJECTORY独立报告](2026-09-07-agent-experience/REP-TRAJECTORY.md)：32×21坐标/力、energy/step/source_index数值与文本一致；双路径1/16/32帧、播放暂停、集合、六张渲染与配对保存通过。剩三类REP、最终同包复核和14集合总文件。
