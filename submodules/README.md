# 参考仓库

此目录按开发主题保存已经进入实现并固定 commit 的参考仓库。候选项目及用途见 [`docs/quantum-visualization/references.md`](../docs/quantum-visualization/references.md)。

只有已批准任务需要逐行审阅、运行对照测试或固定上游 commit 证据时，才添加对应仓库。添加前记录上游 URL、用途、许可证、固定 commit、更新方式和移除方式。

```bash
git submodule add <upstream-url> submodules/<name>
git -C submodules/<name> checkout <reviewed-commit>
git add .gitmodules submodules/<name>
```

当前仓库与候选：

| 项目 | 已知上游 | 触发主题 | 固定版本 / 状态 |
| --- | --- | --- | --- |
| cclib | `https://github.com/cclib/cclib.git` | Gaussian/ORCA output adapter、parser capability、integration fixture | `v1.8.1` / `07260dd0394cb1a2381d4d897746d727a12ad6ce`；BSD-3-Clause；只用于审阅和测试 |
| xyzrender | `https://github.com/aligfellow/xyzrender` | reader/Cube | 未拉取 |
| quantum-chem-skills | `https://github.com/silico-quantum/quantum-chem-skills` | recipe/workflow | 未拉取 |
| Molecular Blender | 添加前核实 | 波函数/适应性表面 | 未拉取 |
| Beautiful Atoms | 添加前核实 | volume/周期渲染 | 未拉取 |
| Molecular Nodes | 添加前核实 | 轨迹/session/选择 | 未拉取 |

更新 cclib 时先审阅新 release、许可证、字段变化和两份 integration fixture，再执行 `git -C submodules/cclib checkout <reviewed-commit>`。如移除，使用 `git submodule deinit` 和 `git rm submodules/cclib`，并同步删除 `.git/modules/submodules/cclib` 的本地缓存。不要为保持目录结构创建空仓库目录，也不要在未固定 reviewed commit 时提交 `.gitmodules`。
