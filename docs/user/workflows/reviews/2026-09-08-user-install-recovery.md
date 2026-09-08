# 实际用户配置安装恢复：2026-09-08

执行者：**Agent 模拟用户**。实际 `user_default` 安装、冷启动、完整 smoke 和 MCP 恢复均为 **Passed**。本次记录补充[上一轮体验报告](2026-09-07-agent-experience-review.md)中的安装阻断；保留旧报告、14 项明细和历史人工验收的原始状态。

## 范围与构建身份

- 用户明确授权修复实际安装问题；使用 Blender **5.1.1**、bundled Python **3.13.9**，实际用户配置，未使用远端 CI 或历史 5.1.2 结果。
- 分支 `fix/quantum-input-units-experience-review`，本轮开始时 HEAD `365b7ab767b1eaaf034a93dfe49fdd52d8bf51ac`。
- 安装原 R25 ZIP，产品源码 commit `039bde7e1bf028b4b691d888d51460ae331ff678`，版本仍为 **2.4.0**。
- ZIP SHA-256：`661c58f82ae0a5564d37e713eca281e992ad24fd5b5b81fe2b2aee321862368b`。本轮未改产品源码、依赖声明或包内容，无需重新构建。
- 本轮证据目录：`D:/workspace/ChemBlender_2_x/.blend-analysis/2026-09-08-user-install-recovery/`。下表文件名均相对此目录；这些本地文件不随 Git 分发。

## 原因与处置

旧失败涉及共享 wheel 清理及 Windows DLL 占用，日志曾出现 `numpy.testing` 缺失。本次实时预检发现环境已经变化：Quantum Cloud Studio 0.2.0 正式声明 NumPy 2.4.6，NumPy 和 `numpy.testing` 均完整；旧 `ChemBlender` 仍启用，而新扩展未启用、Gemmi 缺失。因此本轮没有重装 NumPy，也没有清空共享 `.local`。

开始时没有运行中的 Blender。先备份实际 profile 的 `config/`、`extensions/` 和 `scripts/`，共 6782 个文件，校验逐文件 SHA-256 与 ZIP CRC。备份 `Blender-5.1-user-profile-before.zip` 为 3,481,106,465 字节，SHA-256 为 `8a4a6141a16ccba2578b7bcaf72b3620524bf52f23c7715d4787b6886a5d5878`；索引见 `backup-manifest.json`。未自动恢复或删除备份。

安装使用正常用户 Preferences，保留其他扩展的启用和 wheel 声明，不加 `--factory-startup`。按[已验证 UI 操作目录](../../../../tests/blender_review_commands.py)重放公开 Operator：禁用旧 `ChemBlender` → `extensions.package_install_files` 安装同一 ZIP 到 `user_default` → 检查依赖 → `wm.save_userpref`。旧插件文件保留。启用集合的唯一变化是用 `bl_ext.user_default.chemblender` 替换 `ChemBlender`。

## 复验结果

| 检查 | 状态与实测结果 | 证据 |
| --- | --- | --- |
| 原生安装重放 | Passed；新扩展启用，RDKit 2026.03.3 / Gemmi 0.7.5 来源为实际扩展共享目录 | `install-result.json` |
| 第一次冷依赖检查 | Passed；独立新进程，2.367 秒；两个 wheel 的 Python/Pyd/DLL 文件逐一匹配 ZIP | `cold-result.json`、`cold-dependencies.json`、`cold.log` |
| 完整实际用户 smoke | Passed；103.811 秒；注册、注销、重复 reload、Scene RNA、Reader API、blend 资源及完整产品回归脚本 | `smoke-result.json`、`smoke.log` |
| smoke 后再次冷启动 | Passed；独立新进程，2.451 秒；保存的启用状态及 wheel 文件仍正确 | `cold-after-smoke-result.json`、`cold-after-smoke-dependencies.json` |
| 现有文件保护 | Passed；5723 个既有非缓存文件未改变；安装目录与 R25 ZIP 无差异 | `audit-after.json` |
| 可见窗口 | Passed；新进程 PID 29784，原生鼠标/键盘打开 ChemBlender 侧栏；可见 RDKit available、Project Browser、Quick Import | `window-final.png`、`logs/ui-actions.jsonl` |
| MCP 冷启动恢复 | Passed；9876 自动监听，三个真实请求返回 ok；环境、公开状态和已安装 Python 字节一致 | `mcp-after-cold.json`、`mcp-environment-after-cold.json`、`mcp-package-after-cold.json` |
| 共享数值依赖 | Passed；NumPy testing / 线性方程求解，SciPy、h5py、PySCF 导入；H2 RHF/STO-3G（0.74 Å）收敛，能量 -1.1167593073964255 Hartree | `postflight-live.json`、`postflight-blender.log` |
| 文档与任务治理 | Passed；37 项文档合约测试，0 失败/错误；`git diff --check` 通过 | `verification.json` |

5723 文件比对覆盖原 `scripts/`、其他扩展及共享依赖，排除本次目标扩展和缓存，不声称 Preferences 完全未变。原有 QCS、MCP 和其数值依赖仍启用；没有安装额外可选后端，也没有写 Blender 全局 `site-packages`。

UI 操作后再次 MCP 读取成功，证据为 `mcp-after-ui.json`。窗口仍为本轮新建的未保存默认场景；点击引起 dirty 标记，不是用户工作文件。文件 hash 与本轮记录提交身份见 `delivery-manifest.json`。本轮是环境恢复和操作文档修正，复用现有真实安装回归；未增加镜像式单元测试，也未重复无源码变更的全量 2315 项测试。

## 限制与后续

后台全量加载还出现既有 `right_mouse_navigation` 的 `3D View` keymap 错误，以及扫描其他插件时缺少 torch 的提示；这些插件不属于本轮修复范围。最终可见冷启动进程的 stderr 文件为空。本轮通过完整 ChemBlender smoke 和已有 PySCF 数值用例验证相关依赖，未宣称所有第三方插件功能都已测试。

原生安装 UI 已在上一轮执行；本次安装使用用户允许的公开 Operator 重放，不能记作新的逐弹窗 UI 首测。本次只复核实际安装和相关回归，不覆盖旧报告中的同步 MCP render 取消 `Not Run`，也不改写历史人工记录。独立测试窗口保留供用户使用；本轮未打开或覆盖用户工作文件。合并、PR CI、推送、tag 和 Release 均未在本轮执行。
