# Cube Reader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 Python 标准库将单、多 dataset Cube 无损归一化为现有 `Structure` 与 `Grid3D`。

**Architecture:** 新增一个与 `xyz.py`、`mol_v2000.py` 同级的 reader。读取 Cube whitespace token stream，保留三条 step vector，将 voxel-major 多值去交错为 dataset-first `ArrayData`；语义和值单位保持 ambiguous。

**Tech Stack:** Python 标准库 `array`、`hashlib`、`math`、`pathlib`、`uuid`、`unittest`。

## Constraints

- 不新增依赖、模型字段、Blender UI、surface 或 lazy storage。
- 不从 comment、文件名或 dataset ID 猜物理语义。
- 非法或截断输入不返回部分 batch。

### Task 1: Golden fixtures 与失败测试

**Files:**
- Create: `tests/fixtures/cube/sheared.cube`
- Create: `tests/fixtures/cube/two-datasets.cube`
- Create: `tests/test_cube_reader.py`

- [ ] 创建单 dataset 斜网格 fixture 和负 `NATOMS` 双 dataset fixture。
- [ ] 测试 sniff、registry、结构/网格/provenance/report、索引坐标和 dataset 去交错。
- [ ] 用内联 fixture 测试 `NVAL=2`、截断、奇异网格、无效组合、非有限值和 data count。
- [ ] 运行 `uv run --no-project python -m unittest tests.test_cube_reader -v`，确认因模块不存在而失败。

### Task 2: 最小 Cube reader

**Files:**
- Create: `ChemBlender/core/cube.py`
- Modify: `ChemBlender/core/__init__.py`

- [ ] 实现 header/axis/atom、`NVAL`、`DSET_IDS` 和严格 data count 解析。
- [ ] 构造共享 provenance 的 `Structure` 与 `Grid3D`；多 dataset 去交错为前导 dataset 维。
- [ ] 定义并导出 `CUBE_READER`、`sniff_cube()` 与 `parse_cube()`。
- [ ] 运行 Cube、core 和 reader tests，提交 `feat: add Cube grid reader`。

### Task 3: 运行时与状态

**Files:**
- Modify: `tests/blender_smoke.py`
- Modify: `.agents/active/molecular-quantum-chemistry-closure.md`

- [ ] 在 smoke 中断言 Extension 实际导入 `core.cube`。
- [ ] 运行全量 unittest、CPython `bpy` 隔离、compileall 和 `git diff --check`。
- [ ] 运行 native Extension validate/build 与干净 profile lifecycle smoke。
- [ ] 更新 active：Cube 进入 Completed，Next Action 指向 grid 到 Blender 可重建视图的最小设计。
- [ ] 提交状态和运行时测试。
