# Phase 2 周期结构与 VASP 标量场实施计划

## Goal

用固定版本 ASE/pymatgen-core 完成 POSCAR/CONTCAR/extXYZ 与
CHGCAR/PARCHG/ELFCAR/LOCPOT 的 normalized core 和 Blender identity 闭环。

## Plan

1. 固定 ASE 3.29.0 与 pymatgen-core 2026.7.16 子模块、依赖和许可证记录。
2. 先为 `Grid3D.structure_id`、project dangling-reference 和 Blender metadata
   写失败测试，再做最小模型扩展。
3. 先写 ASE late-import、POSCAR selective dynamics、extXYZ/PBC/array 报告测试，
   再实现 adapter 与 reader descriptors。
4. 先写 pymatgen-core CHGCAR/PARCHG/ELFCAR/LOCPOT、spin/SOC、单位归一化、
   augmentation 报告和非正交 step-vector 测试，再实现 adapter。
5. 更新 core exports、格式能力矩阵、路线图、参考项目和当前任务状态。
6. 运行普通 CPython 无依赖/有依赖测试，验证不 eager import 第三方栈。
7. 运行 Blender Extension validate/build、隔离安装生命周期和 ZIP 审计。
8. 创建阶段提交，快进合并本地 `main`，再进入 Phase 2 band/DOS schema。

## Verify

- `python -m unittest discover -s tests -p "test_*.py"`
- `.agents/cache/periodic-py313/Scripts/python.exe -m unittest discover -s tests -p "test_*.py"`
- CHGCAR 数值积分、triclinic affine endpoint 与 spin/SOC component assertions
- Blender 5.1.2 `validate_extension.py`、`build_extension.py` 和
  `tests/blender_smoke.py --python-exit-code 1`
- ZIP 不包含 `ase`、`pymatgen`、submodules、tests 或 worker environment
- `git diff --check` 和最终 worktree 状态
