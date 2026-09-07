# ChemBlender 本轮体验验收

执行者：**Agent 模拟用户**。日期：2026-09-07，Asia/Shanghai。
本轮独立记录，不改写历史人工验收。当前仍在执行，未完成项目不能视为通过。

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
