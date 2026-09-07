# ENV — 安装与入口

执行者：Agent 模拟用户。UI：**Failed，修复后待重测**；MCP：**Passed**（独立隔离安装/生命周期；面板显示待修复后重测）。真实用户目录的额外安装资格验证：**Blocked**，不能将隔离通过替代它。

- 前置：两个独立 factory-startup profile，初始均未安装 ChemBlender。Blender 5.1.1，English，1920×1080 屏幕，1.0 UI scale。
- 输入：源码 `bed5cab`、资格记录 `03604d3`，ZIP SHA-256 `63bc260e465132ad9ea45ee7e2060dfa16a45c87331e118d09dc2f6f232449b3`。
- UI：Edit → Preferences → Get Extensions → Install from Disk → User Default → 选择 ZIP；Add-ons 搜索 ChemBlender；两次勾选禁用/启用；保存测试设置；N → ChemBlender。
- MCP：全新 mcp-profile，公开 `extensions.package_install_files`；读取启用键与依赖来源；两次 `preferences.addon_disable/addon_enable`；核对 RNA 移除/恢复、Quick Import poll、Reader API handle。
- 预期：本地离线安装，正确启用键，重注册后入口与属性恢复，RDKit/Gemmi 来自本轮 profile、NumPy 来自 Blender。
- 可见实际：安装成功提示、ChemBlender 勾选；Quick Import、Project Browser、Legacy Migration 均可找到；RDKit available。所有公开状态符合预期。
- 耗时：UI 约 19:13–19:31，包含本轮原生输入脚本调试；独立 MCP 安装 2.62 s、两次生命周期检查 1.99 s。小操作立即返回，安装有状态提示。
- 体验：入口需要知道 N 侧栏；Quick Import 位于旧 Build Molecules 下方，发现成本中等。安装弹窗可取消；错误可回到选择步骤。依赖 DLL 在 Windows 重启用时输出锁定清理提示，功能恢复。

## 证据

[截图目录](../../../../../.blend-analysis/2026-09-07-review/screenshots/)：`ENV-07-install-menu.png`、`ENV-09-repository.png`、`ENV-13-install.png`、`ENV-14-addon-enabled.png`、`ENV-17-chemblender-panel.png`。

[ENV.blend](../../../../../.blend-analysis/2026-09-07-review/outputs/ENV.blend) 含 `ENV/UI` 集合；[MCP 安装状态](../../../../../.blend-analysis/2026-09-07-review/outputs/ENV-MCP-install.json)、[MCP 生命周期](../../../../../.blend-analysis/2026-09-07-review/outputs/ENV-MCP-lifecycle.json)。原生输入记录与 MCP 日志保留请求和结果。

## 问题与恢复

- 测试工具问题：64 位 HWND 声明、键盘扫描码与中文输入法干扰原生输入，修复本轮工具后重走安装通过。未修改产品代码。
- 真实用户目录首次 smoke：Blender wheel manager 清理原有第三方 NumPy 后，已加载 NumPy 缺失 `numpy.testing`，完整 smoke Failed；存在旧依赖文件锁。日志 `logs/actual-user-smoke.log` 保留失败。
- 自动审批拒绝再次向真实用户目录安装/清理，原因是可能影响已有 MCP 依赖。没有绕过审批。修复 commit：无；实际目录冷重装重测：Blocked。本轮隔离环境重测通过，但不替代该项。

- 后续 IMP 真实绘制发现 ENV 同样受影响：Project Browser.draw 写 Scene RNA 被 Blender 拒绝。先前看到面板标题不足以证明内容正常；UI 结果已更正为 Failed。失败日志及 `IMP-05-water-view.png` 保留，代码修复与全量重测正在进行。


## 新包重测

修复 commit `7764e83`；新 ZIP `7579c1541eb242cb9220d3c7ff40296446d3f083641cf5c0c50c3f1fb9dc2112`。UI 新 profile 原生重新安装、启用循环与实际绘制通过（`ENV-R2-04-browser.png`）；MCP 新 profile 独立安装与生命周期通过（`outputs/ENV-R2-MCP-state.json`）。非空列表也由 `IMP-R2-04-water-browser.png` 和 `IMP-R2-water-UI.json` 核对通过。UI/MCP 最终隔离结果均 Passed；真实用户额外安装资格仍 Blocked。旧失败状态和证据保留于上文。

默认 F3 菜单搜索未找到 Select Files；N 侧栏入口可用，发现成本仍为中等。

## 22b654d / 最终导入反馈包复核

ZIP SHA-256 `c5e438aefeb200e32dfcb5a09b73825acdc5dc6971a3acd64d9f85349c7c4207`。新 UI profile 显式 User Default 安装，`ENV-R3-07-repository-choice.png`、`ENV-R3-09-addon.png` 记录原生选择与启用；两次 UI 勾选重载及 MCP 独立重载后，Scene RNA、Reader API、公开 Quick Import poll 均正确。状态记录为 `outputs/ENV-R3-UI-install.json`、`ENV-R3-UI-reload.json`、`ENV-R3-MCP-reload.json`。`ENV-R3-UI.blend` 与 `ENV-R3-MCP.blend` 各含 ENV 集合。完整隔离 smoke 通过，102.91 s。

测试环境事故：20:20 UI 安装器默认选择 Existing MCP 仓库，导致本轮新建另一份扩展并重复注册；该尝试 Failed，不计作通过。核对创建时间和原用户进程未启用后，将刚生成目录移至本轮 quarantine；原 MCP 目录保留。新 UI profile 的 MCP 源也复制到本轮目录，重新显式选择 User Default 安装通过。完整记录见 `test-environment-incidents.json`。原用户窗口核对仍为 `1.blend`、Cube/Light/Camera、dirty=false。

## 保存项目 reload 修复

R5 中重新安装扩展后，已保存项目的 in-memory session 未恢复；另存展示文件只写 blend。旧 ZIP 的真实 smoke 重复启用后 project UUID 断言失败（isolated-reload-before.log），P1：项目操作不能正确延续；原 sidecar 未损坏，冷重开恢复。同步恢复的中间实现被原生安装器以 `_RestrictData` 拒绝，随后改成一次性 timer，保留已有 dirty session，unregister 取消回调。

R6 ZIP `b655ad3f6a1cbd1c542b072eeaf857d25b1954d4e67a6c7de0fc6621f8d25dcf` 通过 2,296 tests / 26 skips、隔离 smoke 105.5 s、原生 build 与五文件审计。实际 UI 安装到本轮 user_default 后，Browser 的 Structures/topologies/provenance 自动恢复，模块 SHA 一致（outputs/ENV-R6-UI-restored.json）。MCP 独立 profile 也已安装同包；尚需继续最终 UI/MCP 文件保存与复核。
