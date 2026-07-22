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
| IOData | `https://github.com/theochem/iodata.git` | FCHK/Molden basis、orbital convention、integration fixture | `v1.0.1` / `adab5813713ba64641565eb2a8c11803a4e9bba6`；GPL-3.0-or-later；只用于审阅和测试 |
| GBasis | `https://github.com/theochem/gbasis.git` | normalized Gaussian basis 的 MO/density 求值与 integration fixture | `v0.1.0` / `6440c84f3fcf8d42cbd9b5de53ae8d70bed4cd4f`；GPL-3.0-or-later；外部 worker 后端、审阅和测试 |
| Gemmi | `https://github.com/project-gemmi/gemmi.git` | CIF DOM、small-structure convention、raw envelope 与 integration fixture | `v0.7.5` / `5cc1c23c6007e0e6cbd69289c6f7c0bff50e943e`；MPL-2.0；只用于审阅和测试 |
| spglib | `https://github.com/spglib/spglib.git` | 空间群、Wyckoff、等价原子、标准化与变换 convention | `v2.7.0` / `12355c77fb7c505a55f52cae36341d73b781a065`；BSD-3-Clause；只用于审阅和测试 |
| ASE | `https://gitlab.com/ase/ase.git` | POSCAR/CONTCAR、extXYZ、PBC 与 selective-dynamics adapter | `3.29.0` / `f27c0005ae6a67ea419f996e728668865bfc1f86`；LGPL-2.1-or-later；外部 core adapter、审阅和测试 |
| pymatgen-core | `https://github.com/materialsproject/pymatgen-core.git` | CHGCAR/PARCHG、ELFCAR、LOCPOT 解析和周期 grid convention | `v2026.7.16` / `488ad74cc5ecaba5d24c1726e2762fb47f31f5ef`；MIT；外部 core adapter、审阅和测试 |
| phonopy | `https://github.com/phonopy/phonopy.git` | q-point frequency、complex eigenvector、group velocity 与 supercell phase convention | `v4.4.0` / `2df40f4865d477f44d3b5d1ebcafc0b4af878e35`；BSD-3-Clause；外部 core adapter、审阅和测试 |
| PyProcar | `https://github.com/romerogroup/pyprocar.git` | FermiSurface3D mesh、band identity、projection、spin texture 与 velocity contract | `v6.5.0` / `4a2ec9049af78fdd35b6214eef68fe40e5f356ed`；GPL-3.0；可选 worker adapter、审阅和测试 |
| quantum-chem-skills | `https://github.com/silico-quantum/quantum-chem-skills.git` | recipe 分类、工作流输入输出与 citation 要求 | `fbfb3c23f94dff29f8db64a3b49c8dc6c840a154`；MIT；只用于审阅，不复制模板脚本 |
| critic2 | `https://github.com/aoterodelaroza/critic2.git` | external adapter CLI、QTAIM/NCI 输入输出与 integration fixture | `4b5dec9131c3a035af1b421d68a227c47fd641db`；GPL-3.0；外部 worker 程序参考，不进入 Extension |
| QCElemental | `https://github.com/MolSSI/QCElemental.git` | QCSchema v1/v2 model、字段迁移和 exchange fixture | `v0.50.4` / `46034a0587e2e74426cb1ae2d4d7f66ad5cf6090`；BSD-3-Clause；只用于 schema 审阅和测试，不进入 Extension |
| avogadrolibs | `https://github.com/OpenChemistry/avogadrolibs.git` | CJSON 1 reader/writer、字段 convention 与 integration fixture | `1.103.0` / `5d5d11f4a9ca716f7fb9653eb92424f1714b68ac`；BSD-3-Clause；只用于交换格式审阅和测试，不进入 Extension |
| xyzrender | `https://github.com/aligfellow/xyzrender` | reader/Cube | 未拉取 |
| Molecular Blender | 添加前核实 | 波函数/适应性表面 | 未拉取 |
| Beautiful Atoms | 添加前核实 | volume/周期渲染 | 未拉取 |
| Molecular Nodes | 添加前核实 | 轨迹/session/选择 | 未拉取 |

更新已固定仓库时先审阅新 release、许可证、字段变化和 integration fixture，再执行 `git -C submodules/<name> checkout <reviewed-commit>`。如移除，使用 `git submodule deinit` 和 `git rm submodules/<name>`，并同步删除 `.git/modules/submodules/<name>` 的本地缓存。不要为保持目录结构创建空仓库目录，也不要在未固定 reviewed commit 时提交 `.gitmodules`。
