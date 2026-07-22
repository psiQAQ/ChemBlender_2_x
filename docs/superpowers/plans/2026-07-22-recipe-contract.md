# Phase 4 recipe contract implementation plan

## Goal

建立 versioned recipe schema、严格 JSON codec、项目输入绑定和首批内置 recipe。

## Plan

1. 以失败测试固定 schema invariants、严格 codec、输入/单位校验和 derivation identity。
2. 实现纯 Python `recipe` module，不 import `bpy`，不执行外部程序。
3. 定义 vibration、TDDFT 与 wavefunction-grid 三类内置 recipe。
4. 固定 `quantum-chem-skills` reviewed commit，并更新 reference、ADR 和阶段文档。
5. 运行全量 core tests、Extension validate/build、Blender smoke 与 `git diff --check`。

## Verify

- `python -m unittest tests.test_recipe`
- `python -m unittest discover -s tests`
- Blender Extension validate/build 与隔离安装 smoke test
- `git diff --check`
