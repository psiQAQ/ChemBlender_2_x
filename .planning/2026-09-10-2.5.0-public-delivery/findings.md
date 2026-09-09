# Findings

- 当前真实用户 profile 安装的是旧公开 2.4.0，不含新的 `processor_executable` 设置。
- `runtime.run_worker()` 将主环境 `site-packages` 放入 routed Python 的 `sys.path[0]`，会覆盖专业环境锁定的 NumPy。
- `tests/test_processor_blender.py` 固定指向旧的 wheel-bearing `chemblender-2.4.0.zip`。
- 当前包已有 `chemblender-prepare` 与 `chemblender-prepare-gui` entry point；`uv tool` 只需正式安装/验收，不需要冻结成单文件 EXE。
- GUI 当前 7 个命令，缺 `capabilities`、`doctor`；顶层包没有通用 Python SDK。
- 当前公开文档混合 CBQ Viewer 与旧 Quick Import/Wavefunction Import 流程。
