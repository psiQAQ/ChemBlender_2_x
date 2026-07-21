# 参考仓库占位

此目录暂不包含 Git submodule。候选项目及用途见 [`docs/quantum-visualization/references.md`](../docs/quantum-visualization/references.md)。

只有已批准任务需要逐行审阅、运行对照测试或固定上游 commit 证据时，才添加对应仓库。添加前记录上游 URL、用途、许可证、固定 commit、更新方式和移除方式。

```bash
git submodule add <upstream-url> submodules/<name>
git -C submodules/<name> checkout <reviewed-commit>
git add .gitmodules submodules/<name>
```

初始候选：

| 项目 | 已知上游 | 触发主题 | 当前状态 |
| --- | --- | --- | --- |
| xyzrender | `https://github.com/aligfellow/xyzrender` | reader/Cube | 未拉取 |
| quantum-chem-skills | `https://github.com/silico-quantum/quantum-chem-skills` | recipe/workflow | 未拉取 |
| Molecular Blender | 添加前核实 | 波函数/适应性表面 | 未拉取 |
| Beautiful Atoms | 添加前核实 | volume/周期渲染 | 未拉取 |
| Molecular Nodes | 添加前核实 | 轨迹/session/选择 | 未拉取 |

不要为保持目录结构创建空仓库目录，也不要在未固定 reviewed commit 时提交 `.gitmodules`。
