# 参考项目目录

本目录汇总量子化学可视化的源码审阅和对照测试参考；2026-09-08 核实并新增工作台首期三个子模块，运行时依赖仍由独立依赖决策管理。其余候选在真正集成前重新核实 URL、许可证和固定 commit。

| 项目 | 参考用途 | 对应主题 | 计划优先级 | 复用方式 | 许可证状态 | 添加 submodule 的触发条件 |
| --- | --- | --- | --- | --- | --- | --- |
| [xyzrender](https://github.com/aligfellow/xyzrender) | reader 分派、轻量中间模型、Cube/显示配置、测试 | reader；波函数/网格 | P0 | 架构与测试对照，必要时移植小段实现 | 集成前复核 | 开始 registry/Cube 实现且需要固定代码证据 |
| [quantum-chem-skills](https://github.com/silico-quantum/quantum-chem-skills) | 分析功能分类与 workflow recipe | workflow | P1 | 已固定 `fbfb3c2`，转写 schema，不复制模板脚本 | MIT | 更新 recipe 分类或引用要求时审阅新 commit |
| Molecular Blender | Molden、轨道求值、适应性等值面 | 波函数/网格 | P0/P1 | 算法和 convention 对照 | 集成前复核 | Molden/MO 求值 benchmark 启动 |
| Beautiful Atoms | ASE/Blender 桥接、周期体系、体数据表面着色 | Blender；周期 | P0/P1 | adapter 与渲染模式对照 | 集成前复核 | volume 或 ASE adapter 进入实现 |
| [Molecular Nodes](https://github.com/BradyAJohnston/MolecularNodes) | 密度网格/VDB、session、选择、Geometry Nodes | Blender；存储 | P0/P1 | 仅参考 `entities/density/grids.py`、`nodes/geometry.py`、`session.py`；不嵌套安装插件或移植 pickle 存储 | GPL-3.0 已复核；`LICENSE.OLD` 的 MIT 非当前许可 | 已触发；`b3ab6b7a2e484f9b3a0d0a7192943700ebf183b0` |
| [MOrbVis](https://github.com/Yasuaki-Ito/morbvis) | 轨道浏览/比较、截面、Cube 导出、GPU 降级交互 | Blender；波函数/网格 | P0/P1 | 仅参考 `src/core/` 与 `src/shaders/mo_eval.wgsl`，不将 TypeScript/WebGPU 移入 Python worker | BSD-3-Clause 已复核 | 已触发；`724f43c6d6f25cc979e58c6848499e1a65d76d53` |
| [PySCF](https://github.com/pyscf/pyscf) | MO/密度/ESP 网格、AO/RDM 与 Cube 数值对照 | 波函数/网格；worker | P0/P1 | 固定 `v2.14.0`，参考 `pyscf/tools/cubegen.py`、`pyscf/dft/numint.py`；不新增运行时依赖 | Apache-2.0 已复核，保留 `NOTICE` 和文件头 | 已触发；`c63a953ba603a5ad8c1d65d88da72aaf05ede4d8` |
| [cclib](https://github.com/cclib/cclib) | 通用量化输出与 parser capability | reader | P0 | 外部 core adapter；submodule 固定 v1.8.1 供审阅和测试 | BSD-3-Clause 已复核 | 已触发；`07260dd0394cb1a2381d4d897746d727a12ad6ce` |
| [IOData](https://github.com/theochem/iodata) | FCHK/Molden/WFN/WFX、basis、MO、RDM、Cube | reader；波函数 | P0 | 外部 core adapter；submodule 固定 v1.0.1 供审阅和测试 | GPL-3.0-or-later 已复核 | 已触发；`adab5813713ba64641565eb2a8c11803a4e9bba6` |
| [QCElemental/QCSchema](https://github.com/MolSSI/QCElemental) | 单位、计算记录、provenance、交换 | 语义核心；reader | P0/P1 | 已固定 `v0.50.4` / `46034a0`；v1/v2 分离 adapter 与 raw envelope，不作为内部模型 | BSD-3-Clause 已复核 | 已触发；升级时复核 schema name/version、conversion loss 与 fixtures |
| [QCEngine](https://github.com/MolSSI/QCEngine) | QCSchema compute、program harness、failure/provenance | workflow；worker | P1 | 已固定 `v0.50.0` / `d1842c4`；`qcschema.compute@1` 仅在外部 worker 延迟导入，PySCF 使用独立受限 adapter | BSD-3-Clause 已复核 | 已触发；升级时复核 v1/v2 conversion、harness discovery 与 FailedOperation |
| [ASE](https://gitlab.com/ase/ase) | 结构、轨迹、周期 I/O 与 calculator 交换 | reader；周期 | P0/P1 | 外部 core adapter；submodule 固定 3.29.0，当前用于 POSCAR/CONTCAR、extXYZ、PBC 与约束映射 | LGPL-2.1-or-later 已复核 | 已触发；`f27c0005ae6a67ea419f996e728668865bfc1f86` |
| [Gemmi](https://github.com/project-gemmi/gemmi) | CIF/mmCIF 词法、语法与 raw envelope | reader；周期 | P0 | 外部 core adapter；submodule 固定 v0.7.5 供审阅和测试 | MPL-2.0 已复核 | 已触发；`5cc1c23c6007e0e6cbd69289c6f7c0bff50e943e` |
| [spglib](https://github.com/spglib/spglib) | 空间群、Wyckoff、标准化与变换 | reader；周期 | P0 | 外部 core adapter；submodule 固定 v2.7.0 供审阅和测试 | BSD-3-Clause 已复核 | 已触发；`12355c77fb7c505a55f52cae36341d73b781a065` |
| ORBKIT | MO、密度、导数和网格求值 | 波函数/网格 | P1 | 仅保留未来对照候选；Python 3.13 实测因未声明 Cython 构建依赖失败 | LGPL-3.0-or-later 已复核 | 当前不触发；GBasis 已满足规则网格 MVP |
| [GBasis](https://github.com/theochem/gbasis) | Gaussian basis、MO、密度、ESP、导数与积分 | 波函数/网格 | P1 | 外部 worker 主后端；submodule 固定 v0.1.0 供审阅和真实 FCHK 测试 | GPL-3.0-or-later 已复核 | 已触发；`6440c84f3fcf8d42cbd9b5de53ae8d70bed4cd4f` |
| [Grid](https://github.com/theochem/grid) | 规则/原子中心/自适应网格、积分与 Cube | 波函数/网格 | P1 | 原子中心积分或自适应网格候选；当前 affine 点阵由 NumPy 生成 | GPL-3.0-or-later 已复核 | 当前不触发；规则网格不需要额外依赖 |
| [cuGBasis](https://github.com/theochem/cuGBasis) | GPU 上的 MO、密度/导数、ESP | 波函数/网格 | P2 | 未来 NVIDIA/CUDA worker 候选；参考 `src/eval_*.cu` 和 `src/pybind.cpp` | 存在冲突：`LICENSE` 为 LGPLv3，`HEADER` 为 GPL-3-or-later；`f39b7b7` 已核实 | 暂不下载；CPU 性能瓶颈实测且许可冲突澄清后再评估 |
| [pymatgen-core](https://github.com/materialsproject/pymatgen-core) | BandStructure、DOS、VASP 和材料数据 | 周期 | P1 | 外部 core adapter；submodule 固定 v2026.7.16，当前用于 VASP scalar grids | MIT 已复核 | 已触发；`488ad74cc5ecaba5d24c1726e2762fb47f31f5ef` |
| [PyProcar](https://github.com/romerogroup/pyprocar) | 投影能带、费米面、自旋纹理 | 周期 | P2 | 可选 worker adapter；submodule 固定 v6.5.0，输出转为中立 mesh，不把 PyVista/VTK 带入 Blender | GPL-3.0 已复核 | 已触发；`4a2ec9049af78fdd35b6214eef68fe40e5f356ed` |
| sumo | 能带/DOS/光学 publication plot 规范 | 周期；Blender | P1/P2 | 绘图语义与默认值参考 | 集成前复核 | 2D plot 联动进入实现 |
| [phonopy](https://github.com/phonopy/phonopy) | q-point、复数 eigenvector、声子数据 | 周期 | P1 | 外部 core adapter；submodule 固定 v4.4.0，保留完整复数相位并派生 supercell frames | BSD-3-Clause 已复核 | 已触发；`2df40f4865d477f44d3b5d1ebcafc0b4af878e35` |
| [Avogadro/CJSON](https://github.com/OpenChemistry/avogadrolibs) | 项目交换和 orbital/vibration/spectrum UI | reader；Blender | P1 | 已固定 `1.103.0` / `5d5d11f`；稳定字段进入语义层，扩展字段保留 raw envelope | BSD-3-Clause 已复核 | 已触发；升级时复核 `CjsonFormat` reader/writer 与 fixtures |
| [critic2](https://github.com/aoterodelaroza/critic2) | QTAIM、临界点、basin、NCI、ELF | workflow | P2 | 已固定 `4b5dec9`；外部进程 adapter，后续解析为 `TopologyGraph` | GPL-3.0 | 更新 CLI/output parser 时审阅新 commit 与 fixture |
| Multiwfn | 电荷、键级、NCI、hole-electron、DOS、光谱 | workflow | P2 | 外部进程 adapter | 集成前复核 | 稳定非交互 recipe 和输出 fixture 已确认 |
| [TheoDORE](https://github.com/plasser-lab/theodore) | 跃迁密度、电子/空穴、fragment CT 与 exciton | workflow；波函数 | P2 | 未来 worker 分析候选；参考 `theodore/lib_tden.py`、`lib_sden.py`、`lib_exciton.py` | GPL-3.0；`e7ddc34` 的 `LICENSE.txt`/`COPYRIGHT.txt` 已核实 | 暂不下载；进入激发态分析且需要可复现实例时添加；旧 `theodore-qc` URL 已重定向 |
| [NCIPLOT 4.4](https://github.com/juliacontrerasgarcia/NCIPLOT-4.4) | NCI/RDG、密度 Hessian 色映射对照 | workflow | P2 | 作者发布的 Fortran 程序；参考 `src_4.4/props.f90`，优先对照现有 critic2 结果 | GPL-3.0-or-later；`e7a113c` 源码头已核实 | 暂不下载；进入 NCI 数值验证时添加，不重复建设现有分析后端 |
| [moldenViz](https://github.com/Faria22/moldenViz) | 球谐 Molden、轨道求值、自适应采样对照 | 波函数/网格 | P2 | 参考 `src/moldenViz/parser.py`、`tabulator.py`、`_adaptive_grid.py`；不替换 IOData/GBasis | MIT；`16968dd` 已核实 | 暂不下载；当前 2.3.1 parser 拒绝 Cartesian 轨道基函数，core 依赖 NumPy>=2.2 |
| [IboView](https://www.iboview.org/_bgBqyRo.html) / [KoehnLab 维护 fork](https://github.com/KoehnLab/iboview) | IAO/IBO、局域轨道、反应路径轨道呈现 | 波函数；Blender | P2 | C++/Qt 源码参考：`src/IboView/IvIao.cpp`、`src/MicroScf/CtOrbLoc.cpp`；维护 fork 非官方上游 | GPL-3.0；维护 fork `69da0fc` 的 `iboview-license.txt` 已核实，第三方组件单独授权 | 暂不下载；进入局域轨道工作流时再选定源码来源 |
| MDAnalysis/MDTraj | DCD/XTC/TRR 等长轨迹 | Blender；存储 | P2 | 可选 trajectory adapter | 集成前复核 | ASE/基础 trajectory 不能满足真实输入 |
| QCArchive | 计算记录数据库 | workflow | P2 | connector | 集成前复核 | 用户确认数据库导入与鉴权需求 |
| AiiDA | provenance 与计算工作流 | workflow | P2 | connector | 集成前复核 | 本地 recipe/worker 已稳定 |
| NOMAD | parser、raw archive、normalization、metainfo | workflow；语义核心 | P2 | 架构参考或 connector | 集成前复核 | code-independent quantity 或归档导入进入实施 |

## 使用规则

- 阅读官方 API 或论文足以回答问题时，不添加 submodule。
- 计划进入实现并需要逐行审阅、运行对照测试或保存固定 commit 证据时，才在 `submodules/` 添加仓库。
- submodule 只固定参考源码；运行时依赖仍由 Python/Blender 依赖决策、锁定版本和打包验证管理。
- 复制或改写代码前核对许可证、NOTICE、文件头和兼容边界，并在实现提交中保留来源。
