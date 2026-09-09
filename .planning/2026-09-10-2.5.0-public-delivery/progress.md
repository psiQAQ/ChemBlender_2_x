# Progress

## 2026-09-10

- 创建 `release/2.5.0`。
- 保留用户 `.gitignore` 修改。
- 按绝对路径与父子链清理 10 套重复 MCP 链，共 30 个进程；保留 Blender 与 Codex。
- routed worker 改用目标环境 `python -I -m`，移除主环境源码和 `site-packages` 注入。
- `chemblender_prepare-0.1.0` wheel 以 `--no-deps` 安装到 gbasis/scientific/fermi route，包路径来自各自环境，NumPy 版本保持不变。
- `tests.test_prepare_runtime` 6 项 Passed；三个真实 route 配置下 `tests.test_processor_operations` 9 项 Passed。
- 下一步：Standard `uv tool`、准确能力诊断、GUI 9 个入口与 Blender Test Processor。
