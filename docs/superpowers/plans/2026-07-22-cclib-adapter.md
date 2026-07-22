# cclib 最小解析闭环实现计划

> 依据：[cclib 最小解析闭环设计](../specs/2026-07-22-cclib-adapter-design.md)

## Goal

以 cclib 1.8.1 为可选外部解析依赖，实现 Gaussian/ORCA 结构、SCF 能量和原子布居的 normalized import batch。

## Constraints

- `ChemBlender.core` 与 adapter 模块顶层不得 import cclib、NumPy、SciPy 或 `bpy`。
- 不修改 Extension wheel 清单，不在运行期安装包。
- fixture 只从固定 cclib submodule 读取。
- 先写失败测试，再写最小实现。

## Plan

1. 固定 `submodules/cclib` 到官方 v1.8.1，记录许可证、用途、更新和移除方式，并调整文档契约测试。
2. 为 Gaussian/ORCA sniff、`ccData` 字段映射、计算状态、缺失字段和未映射字段编写失败测试。
3. 实现延迟依赖入口、normalized adapter、`CCLIB_OUTPUT_READER` 与明确的 dependency/parser 错误。
4. 添加可选 integration test，真实解析固定 Gaussian/ORCA fixture，并验证 `QCProject.commit()`。
5. 在隔离 uv 环境安装 submodule 版本，运行 adapter integration test；再运行不带可选依赖的标准测试。
6. 更新 capability/依赖/当前任务文档，执行 `compileall`、全量单元测试、文档链接、`git diff --check` 和 worktree 审计。

## Verification

```powershell
# 标准 core 测试
& '<Blender Python>' -m unittest discover -s tests -p 'test_*.py'

# 可选 cclib integration 环境
uv venv .agents/cache/cclib-venv --python 3.13
uv pip install --python .agents/cache/cclib-venv/Scripts/python.exe ./submodules/cclib
& .agents/cache/cclib-venv/Scripts/python.exe -m unittest tests.test_cclib_adapter

# 静态检查
& '<Blender Python>' -m compileall -q ChemBlender tests
git diff --check
git status --short
```

## Exit Criteria

- Gaussian 和 ORCA fixture 均产生 structure、SCF energy、原子 charge 与成功状态。
- adapter 输出可原子提交到 `QCProject`，没有悬空引用。
- 无 cclib 环境仍可 import `ChemBlender.core` 并运行标准模型测试。
- cclib 未进入 Blender manifest 或 Extension ZIP 依赖。
