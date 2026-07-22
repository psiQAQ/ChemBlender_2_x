# 参考项目目录

本目录来自 2026 年 7 月 21 日调研，用于安排代码审阅和对照测试，不等同于依赖清单。URL、许可证、活跃分支和固定 commit 在真正集成前重新核实。

| 项目 | 参考用途 | 对应主题 | 计划优先级 | 复用方式 | 许可证状态 | 添加 submodule 的触发条件 |
| --- | --- | --- | --- | --- | --- | --- |
| [xyzrender](https://github.com/aligfellow/xyzrender) | reader 分派、轻量中间模型、Cube/显示配置、测试 | reader；波函数/网格 | P0 | 架构与测试对照，必要时移植小段实现 | 集成前复核 | 开始 registry/Cube 实现且需要固定代码证据 |
| [quantum-chem-skills](https://github.com/silico-quantum/quantum-chem-skills) | 分析功能分类与 workflow recipe | workflow | P1 | 转写 schema，不复制占位脚本 | 集成前复核 | recipe 设计需要逐文件核对模板和引用 |
| Molecular Blender | Molden、轨道求值、适应性等值面 | 波函数/网格 | P0/P1 | 算法和 convention 对照 | 集成前复核 | Molden/MO 求值 benchmark 启动 |
| Beautiful Atoms | ASE/Blender 桥接、周期体系、体数据表面着色 | Blender；周期 | P0/P1 | adapter 与渲染模式对照 | 集成前复核 | volume 或 ASE adapter 进入实现 |
| Molecular Nodes | 长轨迹、session、选择、属性编码 | Blender；存储 | P0/P1 | session/manager/Geometry Nodes 契约参考 | 集成前复核 | 轨迹或 sidecar 恢复进入实现 |
| [cclib](https://github.com/cclib/cclib) | 通用量化输出与 parser capability | reader | P0 | 外部 core adapter；submodule 固定 v1.8.1 供审阅和测试 | BSD-3-Clause 已复核 | 已触发；`07260dd0394cb1a2381d4d897746d727a12ad6ce` |
| [IOData](https://github.com/theochem/iodata) | FCHK/Molden/WFN/WFX、basis、MO、RDM、Cube | reader；波函数 | P0 | 外部 core adapter；submodule 固定 v1.0.1 供审阅和测试 | GPL-3.0-or-later 已复核 | 已触发；`adab5813713ba64641565eb2a8c11803a4e9bba6` |
| QCElemental/QCSchema | 单位、计算记录、provenance、交换 | 语义核心；reader | P0/P1 | schema adapter 与单位参考 | 集成前复核 | 单位/QCSchema ADR 需要代码对照 |
| [ASE](https://gitlab.com/ase/ase) | 结构、轨迹、周期 I/O 与 calculator 交换 | reader；周期 | P0/P1 | 外部 core adapter；submodule 固定 3.29.0，当前用于 POSCAR/CONTCAR、extXYZ、PBC 与约束映射 | LGPL-2.1-or-later 已复核 | 已触发；`f27c0005ae6a67ea419f996e728668865bfc1f86` |
| [Gemmi](https://github.com/project-gemmi/gemmi) | CIF/mmCIF 词法、语法与 raw envelope | reader；周期 | P0 | 外部 core adapter；submodule 固定 v0.7.5 供审阅和测试 | MPL-2.0 已复核 | 已触发；`5cc1c23c6007e0e6cbd69289c6f7c0bff50e943e` |
| [spglib](https://github.com/spglib/spglib) | 空间群、Wyckoff、标准化与变换 | reader；周期 | P0 | 外部 core adapter；submodule 固定 v2.7.0 供审阅和测试 | BSD-3-Clause 已复核 | 已触发；`12355c77fb7c505a55f52cae36341d73b781a065` |
| ORBKIT | MO、密度、导数和网格求值 | 波函数/网格 | P1 | 仅保留未来对照候选；Python 3.13 实测因未声明 Cython 构建依赖失败 | LGPL-3.0-or-later 已复核 | 当前不触发；GBasis 已满足规则网格 MVP |
| [GBasis](https://github.com/theochem/gbasis) | Gaussian basis、MO、密度、ESP、导数与积分 | 波函数/网格 | P1 | 外部 worker 主后端；submodule 固定 v0.1.0 供审阅和真实 FCHK 测试 | GPL-3.0-or-later 已复核 | 已触发；`6440c84f3fcf8d42cbd9b5de53ae8d70bed4cd4f` |
| [Grid](https://github.com/theochem/grid) | 规则/原子中心/自适应网格、积分与 Cube | 波函数/网格 | P1 | 原子中心积分或自适应网格候选；当前 affine 点阵由 NumPy 生成 | GPL-3.0-or-later 已复核 | 当前不触发；规则网格不需要额外依赖 |
| CuGBasis | GPU 上的 MO、密度、ESP、RDG | 波函数/网格 | P2 | 可选 NVIDIA 加速 | 集成前复核 | P1 后端已形成可测性能瓶颈 |
| [pymatgen-core](https://github.com/materialsproject/pymatgen-core) | BandStructure、DOS、VASP 和材料数据 | 周期 | P1 | 外部 core adapter；submodule 固定 v2026.7.16，当前用于 VASP scalar grids | MIT 已复核 | 已触发；`488ad74cc5ecaba5d24c1726e2762fb47f31f5ef` |
| [PyProcar](https://github.com/romerogroup/pyprocar) | 投影能带、费米面、自旋纹理 | 周期 | P2 | 可选 worker adapter；submodule 固定 v6.5.0，输出转为中立 mesh，不把 PyVista/VTK 带入 Blender | GPL-3.0 已复核 | 已触发；`4a2ec9049af78fdd35b6214eef68fe40e5f356ed` |
| sumo | 能带/DOS/光学 publication plot 规范 | 周期；Blender | P1/P2 | 绘图语义与默认值参考 | 集成前复核 | 2D plot 联动进入实现 |
| [phonopy](https://github.com/phonopy/phonopy) | q-point、复数 eigenvector、声子数据 | 周期 | P1 | 外部 core adapter；submodule 固定 v4.4.0，保留完整复数相位并派生 supercell frames | BSD-3-Clause 已复核 | 已触发；`2df40f4865d477f44d3b5d1ebcafc0b4af878e35` |
| Avogadro/CJSON | 项目交换和 orbital/vibration/spectrum UI | reader；Blender | P1 | 交换 adapter 与工作流参考 | 集成前复核 | CJSON round-trip 进入实施 |
| critic2 | QTAIM、临界点、basin、NCI、ELF | workflow | P2 | 外部进程 adapter | 集成前复核（调研记录为 GPLv3） | TopologyGraph 与许可边界已批准 |
| Multiwfn | 电荷、键级、NCI、hole-electron、DOS、光谱 | workflow | P2 | 外部进程 adapter | 集成前复核 | 稳定非交互 recipe 和输出 fixture 已确认 |
| MDAnalysis/MDTraj | DCD/XTC/TRR 等长轨迹 | Blender；存储 | P2 | 可选 trajectory adapter | 集成前复核 | ASE/基础 trajectory 不能满足真实输入 |
| QCArchive | 计算记录数据库 | workflow | P2 | connector | 集成前复核 | 用户确认数据库导入与鉴权需求 |
| AiiDA | provenance 与计算工作流 | workflow | P2 | connector | 集成前复核 | 本地 recipe/worker 已稳定 |
| NOMAD | parser、raw archive、normalization、metainfo | workflow；语义核心 | P2 | 架构参考或 connector | 集成前复核 | code-independent quantity 或归档导入进入实施 |

## 使用规则

- 阅读官方 API 或论文足以回答问题时，不添加 submodule。
- 计划进入实现并需要逐行审阅、运行对照测试或保存固定 commit 证据时，才在 `submodules/` 添加仓库。
- submodule 只固定参考源码；运行时依赖仍由 Python/Blender 依赖决策、锁定版本和打包验证管理。
- 复制或改写代码前核对许可证、NOTICE、文件头和兼容边界，并在实现提交中保留来源。
