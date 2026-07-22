# 0007：波函数规则网格采用 GBasis 外部 worker 后端

## Status

Accepted for the molecular wavefunction derived-field closure.

## Context

ChemBlender 已用 IOData 将 FCHK/Molden 归一化为 `Structure`、`BasisSet` 和 `OrbitalSet`。下一步需要从这些自有实体求 MO 与 density，但不能把大型科学依赖装入 Blender Extension，也不能绕回源文件重新解析。

候选为 GBasis+Grid 与 ORBKIT。真实 Windows/Python 3.13 探针显示 ORBKIT 1.1.0.dev2 的构建元数据缺少 Cython；GBasis 0.1.0 的代码在 NumPy 2.5.1 下可运行，但 Windows metadata 要求 NumPy<2，标准 Python 3.13 安装无法解析。GBasis 在 Python 3.12/NumPy 1.26.4 标准安装和真实 FCHK 数值测试通过。

## Decision

- 规则 affine 网格 MVP 使用 `qc-gbasis==0.1.0`，固定官方 tag `v0.1.0`。
- GBasis 在独立 worker/core 环境运行；当前推荐 Python 3.12，不加入 Blender manifest。
- 规则点阵由 NumPy 生成，不为当前功能引入 qc-grid。
- normalized basis 的 shell、normalization 和 convention 显式映射到 GBasis；求值器不依赖 IOData 对象。
- ORBKIT、qc-grid、adaptive grid 和 GPU 后端推迟到其独有能力有验收需求时再引入。

## Consequences

- Blender 5.1/Python 3.13 不承担 GBasis 当前 NumPy metadata 冲突。
- 同一 compute API 后续可放入本地或远程 worker，而 Blender 只接收 `Grid3D`/sidecar 引用。
- 首版不提供自适应采样和 generalized spinor，但失败是显式的。
- GBasis 为 GPL-3.0-or-later，与本仓库许可证兼容；submodule 不进入 Extension ZIP。

## Verification Contract

1. Python 3.12 标准依赖环境可从真实 FCHK 生成 MO/density grid。
2. 输入只包含 normalized entities；删除 IOData 对象后仍可求值。
3. 密度积分与 occupation 电子数一致到声明容差。
4. Extension validate/build/lifecycle 不需要 GBasis、SciPy 或 IOData。
5. 任何未来改用 Python 3.13 worker 的决定必须重新验证官方 dependency metadata，而不是依赖强制安装。
