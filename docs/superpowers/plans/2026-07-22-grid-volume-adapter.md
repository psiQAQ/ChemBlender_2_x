# Grid3D OpenVDB Volume Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将选定的 `Grid3D` dataset 写成带完整 affine transform 的 VDB cache，并在 Blender 中创建可恢复身份的 Volume object。

**Architecture:** 一个顶层 Blender adapter 使用 bundled NumPy 与 `openvdb`；调用方提供 cache path。adapter 只选取数组、换算坐标、原子写 cache、创建 Volume 和写 custom properties，不承担项目存储或 UI。

**Tech Stack:** Blender 5.1 `bpy`、bundled `numpy`/`openvdb`、Python 标准库、现有 `Grid3D`。

## Constraints

- 不新增 wheel、backend registry、material、surface、UI 或 cache manager。
- 只支持 `("x", "y", "z")` 与 `("dataset", "x", "y", "z")`。
- 权威数据不写入 `.blend`；VDB 明确是可重建 cache。

### Task 1: Blender 失败检查

**Files:**
- Modify: `tests/blender_smoke.py`
- Modify: `tests/test_repository_contract.py`

- [ ] 在 installed Extension smoke 中构造斜 `Grid3D`，调用 `create_grid_volume()` 并验证 VDB、transform、Volume grid 和 custom properties。
- [ ] 增加 manifest file permission 文案契约。
- [ ] 使用当前不含 adapter 的 build 运行 smoke，确认 import/call 失败。

### Task 2: 最小 adapter

**Files:**
- Create: `ChemBlender/grid_volume.py`
- Modify: `ChemBlender/blender_manifest.toml`

- [ ] 验证 Grid3D shape、dataset index、coordinate unit、cache suffix 和父目录。
- [ ] 将选择数组转为 float32，写入 `FloatGrid` 和 4×4 affine transform。
- [ ] 通过同目录临时文件与 `os.replace()` 原子更新 VDB。
- [ ] 创建并链接 Volume object，加载 `density` grid，写 dataset/cache/单位 properties。
- [ ] 失败时清理本次 Blender datablock。
- [ ] 更新 file permission，运行 source Blender test 与 repository contracts，提交实现。

### Task 3: 完整验证与状态

**Files:**
- Modify: `.agents/active/molecular-quantum-chemistry-closure.md`

- [ ] 运行 70+ 标准库 tests、Blender 3.13 compileall 与 core `bpy` 隔离检查。
- [ ] 运行 native Extension validate/build 和临时 `BLENDER_USER_RESOURCES` lifecycle smoke。
- [ ] 更新 active：Volume adapter 进入 Completed，Next Action 指向 cclib adapter 的依赖决策与 fixture 选择。
- [ ] `git diff --check`、提交、本地合并 main，并删除 worktree/branch。
