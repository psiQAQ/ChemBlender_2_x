# Progress

## 2026-09-10

- 创建 `release/2.5.0`。
- 保留用户 `.gitignore` 修改。
- 按绝对路径与父子链清理 10 套重复 MCP 链，共 30 个进程；保留 Blender 与 Codex。
- routed worker 改用目标环境 `python -I -m`，移除主环境源码和 `site-packages` 注入。
- `chemblender_prepare-0.1.0` wheel 以 `--no-deps` 安装到 gbasis/scientific/fermi route，包路径来自各自环境，NumPy 版本保持不变。
- `tests.test_prepare_runtime` 6 项 Passed；三个真实 route 配置下 `tests.test_processor_operations` 9 项 Passed。
- 下一步：Standard `uv tool`、准确能力诊断、GUI 9 个入口与 Blender Test Processor。
- GUI 改为 Windows GUI entry point，并增加只读 `capabilities`、`doctor`；现有进程控制器可读取诊断 JSON。
- capability 校验 route 内同版本 prepare 包；未配置 provider/QCEngine/专业 route 明确 unavailable。doctor 将 Standard NumPy/RDKit/Gemmi 作为必需项，逐项报告可选缺失。
- 全新临时 uv-tool/Python 3.12 从当次 wheel `[formats]` 安装成功；两个 launcher、help、capabilities、doctor、实际依赖路径、强制重装和卸载均 Passed。GUI launcher PE subsystem=2，无控制台窗口；CLI subsystem=3。
- prepare/runtime/controller 51 项 Passed、1 项有原因 skip；`uv build --no-cache` wheel/sdist Passed。PyPI 来源尚未发布，Not Run。
- 下一步：旧 SOP 版本化归档与中英双语 2.5 日常教程、离线 HTML。
- 建立 README、`docs/user/{en,zh-CN}`、`docs/prepare/{en,zh-CN}` 与自包含离线 HTML；旧 2.4 工作流保留稳定 URL 并明确归档，2026-09-09 scientific SOP 冻结为资格证据。
- 公开接口清单从 CLI parser、GUI command、Worker registry 和 Reader catalog 生成：10 CLI、9 GUI、21 operation、22 reader、13 export，Reader API `1.0-rc1`。
- 文档专项 82 项 Passed；Edge headless 以 1440x1000 分别加载中英离线 HTML 并生成截图，均 Passed。
- 下一步：2.5.0 构建、私有 Blender 实装并从新实例采集当前 UI 截图；完成后再关闭文档阶段。
- 私有 2.5.0 实装完成，采集 Blender 5.1.1 当前 UI 截图并嵌入中英离线 HTML；生成器与 manifest 记录图片 SHA-256，Edge headless 复核 Passed，文档阶段关闭。
- 最终干净 uv-tool 检查发现 `chemblender-prepare --version` 被 required subparser 拒绝；共享 parser 已增加 argparse 原生 version action，最小测试和源码命令 Passed。下一步重建 wheel/sdist 并从全新 tool 目录复验两个 launcher。
- 最终 prepare wheel/sdist 已重建；全新 Python 3.12 uv-tool 的 version、help、formats、capabilities、doctor、GUI mapped/viewable、实际包路径和许可证均 Passed，另一个全新目录的安装/强制重装/卸载生命周期 Passed。
- 版本升级遗留的发布契约失败已修复；专项 91 项 Passed/1 skip。最终全量 2531 项 Passed/36 skips/0 failures/0 errors，148.846 秒；processor modal 8.8–11.9 微秒、进入 running 9.4–11.1 毫秒、取消 0.326 秒。
- Blender 5.1.1 私有资源目录下 native validate/build Passed；最终 ZIP 2,830,577 bytes、109 members、无 wheel，package-CI 五件套审计 Passed，权威 SHA-256 `8e92b3439e92be8f90e3e63fd25e935a2592148d464d010ee1ca3a87e85ea6eb`。
- 中英离线 HTML 最终浏览器 QA Passed，HTML SHA-256 分别为 `4a388851b757e55ee3a8b5a9439885d09652fd74af79d69b82acccd48a118ea8` 与 `ad01d1de4226a32b7d7ff921706cce6bc0991118291e18ee54105efe024189e5`；离线资源 ZIP SHA-256 分别为 `3284d3c1d4c384c9ab3b48f91d65ec50001192d13e98730acc620152762285d3` 与 `cf108d85e64beef105f765f52ea88faf16038b6f605f62bad29aa9d519e94a8a`。
- 当前唯一剩余本机门槛是受保护的真实 `user_default` 安装；Blender PID 36516 仍在运行，等待用户正常保存并退出，不强制终止。
- 连续三次目标回合均通过系统进程状态确认 Blender 5.1.1 PID 36516 仍运行；为保护未保存内容，真实 `user_default` 备份/升级、最终资格文档和第 4 个稳定提交保持未执行。目标按阻塞规则暂停，用户正常退出 Blender 后可直接恢复。
- 用户确认退出后，系统复核 Blender 进程为 0。真实 `user_default` 的 2.4.0 扩展（375 文件、35,887,906 bytes）与 `userpref.blend` 已备份到 `.blend-analysis/2.5.0-public-delivery/user-default-backup-final-02`；偏好备份 SHA-256 为 `01ddc8544d7af885b6c7dad8dbbe5ceb5d00294936433563ac248cad6ccc376c`。
- Blender 5.1.1 原生 Extension API 已在真实 `user_default` 覆盖安装 2.5.0，并成功调用外部 processor：Worker Protocol 1、prepare 0.1.0、21 operations/10 Standard available、22 readers/16 available，外部环境 NumPy 2.5.3、RDKit 2026.3.3、Gemmi 0.7.5。首次同进程安装后保存的处理器路径在下一次启动为空；独立冷进程重新设置并保存后已确认写入，待再开一个冷进程完成持久化、reload 与联动复测。
- 最终真实-profile 冷复测 Passed：启动即读取完整 processor 绝对路径，2.5.0 自动启用，47 个注册类两轮 reload 通过，Blender 内 RDKit/Gemmi/prepare 不可导入，prepare 0.1.0 / Worker Protocol 1 capability 请求成功。日志中的 `right_mouse_navigation` keymap 与 DepthGenius 缺依赖为已有第三方扩展问题，不影响 ChemBlender 返回码。
- 最终进程审计确认 Blender 为 0；发现 Codex 宿主再生 3 套 blender-mcp 根/uv Python 子链，经 PID、父子关系及绝对路径复核后只终止 3 个根进程，6 个目标 PID 均退出。2.5.0 对外交付计划全部关闭，等待第 4 个逻辑提交。
- 提交前 prepare/docs/release/repository/processor 专项 120 项 Passed、1 项有原因 skip、0 failures/0 errors；`git diff --check` Passed。首次沙箱运行因用户 uv cache 初始化 `os error 183` 未进入测试，使用本机既有 uv 环境重跑成功。
