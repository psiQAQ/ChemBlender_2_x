# IOData 波函数闭环实现计划

> 依据：[IOData 波函数语义与 adapter 设计](../specs/2026-07-22-iodata-wavefunction-design.md)

## Goal

建立 `BasisSet`/`OrbitalSet` 权威模型，并通过 IOData 1.0.1 完成 restricted FCHK、unrestricted FCHK 与 Molden 导入。

## Constraints

- core 与 adapter 顶层不得 import IOData、NumPy、SciPy、attrs 或 `bpy`。
- 不修改 Blender manifest wheels。
- basis convention 和 generalized spinor 不得静默压缩。
- fixture 只引用固定 submodule。
- 先写模型与 adapter 失败测试。

## Plan

1. 固定 IOData v1.0.1 submodule，记录许可证、依赖、用途、更新和移除方式。
2. 为 `BasisShell`、`BasisConvention`、`BasisSet`、`OrbitalChannel`、`OrbitalSet` 及 `QCProject` 原子提交写失败测试。
3. 最小扩展 model、`ImportBatch` 和 `QCProject` registries，验证引用、shape、kind/channel 与 basis 宽度。
4. 为 FCHK/Molden sniff、restricted/unrestricted/generalized 映射、可选字段 issue 和 lazy dependency 写失败测试。
5. 实现 `iodata_adapter` 和 reader descriptor；公开 API 由 `ChemBlender.core` 导出。
6. 在隔离 uv 环境安装固定 submodule，真实解析三份 fixture；在无 IOData 的 Blender Python 中运行全量标准测试。
7. 更新依赖、reference、capability 和活动任务文档；执行 compile、Extension validate/build、隔离 lifecycle smoke、ZIP 审计和 `git diff --check`。

## Verification

```powershell
& '<Blender Python>' -m unittest tests.test_wavefunction_model tests.test_iodata_adapter
& '<Blender Python>' -m unittest discover -s tests -p 'test_*.py'

uv venv .agents/cache/iodata-venv --python 3.13
uv pip install --python .agents/cache/iodata-venv/Scripts/python.exe ./submodules/iodata
& .agents/cache/iodata-venv/Scripts/python.exe -m unittest tests.test_iodata_adapter

& '<Blender Python>' -m compileall -q ChemBlender tests
git diff --check
git status --short
```

## Exit Criteria

- 三份真实 fixture 的结构、basis 数、轨道 kind/count、系数 shape、energy/occupation 单位与 upstream 对照一致。
- generalized synthetic fixture 保持一个 spin-basis channel。
- `QCProject.commit()` 拒绝 dangling structure/basis、非法 center、错误 channel 和系数宽度，且失败时不部分写入。
- IOData 与 submodule 不进入 Extension ZIP。
