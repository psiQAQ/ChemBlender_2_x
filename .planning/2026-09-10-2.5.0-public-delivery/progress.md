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
