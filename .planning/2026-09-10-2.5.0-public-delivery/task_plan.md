# ChemBlender 2.5.0 对外交付

## Goal

交付可本机真实安装、可重复验证、文档口径统一的 ChemBlender 2.5.0 Viewer 与 `chemblender-prepare 0.1.0` Standard `uv tool`，完成双语新 SOP、旧 SOP 归档、全部公开面回归和稳定逻辑提交。

## Constraints

- 保留用户 `.gitignore` 修改，不纳入提交。
- 不 push、tag、创建 Release 或发布 PyPI。
- Blender 只配置一个外部 executable；不在 Blender Python 中安装依赖。
- Standard 只自动安装 NumPy、RDKit、Gemmi；专业 route 仅手动配置。
- 公开 API 为 CLI、Worker Protocol v1、Reader API `1.0-rc1`；不新增 Python SDK。
- 进程只按 PID、父子链和绝对路径处理。

## Plan

- [x] 从 `d8f0306` 创建 `release/2.5.0`；清理 10 套重复 blender-mcp/Python 链并保留 Blender。
- [x] P0：修复 routed worker 环境注入，真实隔离环境验证包路径和 NumPy 版本。
- [ ] 完成 Standard uv-tool、准确 capabilities/doctor、GUI 诊断与 Blender Test Processor。
- [ ] 归档旧 SOP，建立完整中英双语安装/API/GUI/Blender/故障/发布文档和离线 HTML。
- [ ] 升级 2.5.0、构建唯一权威 ZIP/wheel/sdist，完成 private 与 user_default 实装。
- [ ] 跑专项、全量、构建和文档回归；形成四个逻辑提交并关闭目标。

## Verification

- 专项单元回归与 route 安装态回归 0 failures / 0 errors。
- 干净 `uv tool` Standard 安装不依赖 checkout、`.venv` 或 `PYTHONPATH`。
- Blender 5.1.1 validate/build、私有 profile、真实 `user_default`、冷启动、reload、编辑、View、Cycles、保存重开通过。
- 双语文档、离线 HTML、图片、链接、清单和哈希一致。
- 完整测试 0 failures / 0 errors；`git diff --check` 通过。

## Progress Notes

2026-09-10：执行开始。当前 HEAD `d8f0306`，仅用户 `.gitignore` 为未提交修改。进程审计发现 10 套同一 Codex 宿主生成的 blender-mcp/uv Python 链，按 10 个已验证根 PID 停止后仅保留 Blender 5.1.1 PID 36516。

2026-09-10：P0 关闭。routed worker 只通过目标环境的 `python -I -m chemblender_prepare.worker.runner` 运行；gbasis/scientific/fermi 均安装同版本 prepare wheel 且保留各自 NumPy。runtime 专项 6 项、processor operation 全组 9 项均 Passed。
