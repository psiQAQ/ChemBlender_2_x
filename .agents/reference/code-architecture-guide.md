# ChemBlender 代码架构导览

本文面向需要阅读、维护或扩展 ChemBlender 的开发者，说明当前代码分层、主要数据流，以及每个 Python 文件承担的职责和主要入口。它描述的是当前 `main` 的实际实现，不是未来路线图。

## 维护规则

- 新增、删除、移动源码文件，或者改变模块职责、跨层依赖、主要公开入口时，必须在同一提交中更新本文。
- 小型私有 helper、局部变量和不改变调用方式的内部重构无需逐项记录。
- `ChemBlender/core/` 必须保持可在普通 CPython 中导入，不得依赖 `bpy`。
- Blender datablock 是视图和缓存；`QCProject` 与 `.cbq` sidecar 才是量子化学数据的权威来源。
- `worker/` 是独立进程入口，不进入 Blender Extension ZIP；扩展通过 `ChemBlender/worker_client.py` 调用它。

`tests/test_quantum_visualization_docs.py` 会比较本文列出的源码路径与仓库中的 Python 文件。架构文件变化但本文未同步时，文档契约测试会失败。

## 总体分层

```text
外部文件、计算程序和数据服务
          │
          ▼
ChemBlender/core/ readers 与 adapters       worker/ 可选独立进程
          │                                      │
          └──────────── ImportBatch ─────────────┘
                             │
                             ▼
                    QCProject 语义模型
                             │
                    .cbq / .npy / OpenVDB
                             │
                             ▼
ChemBlender/ Blender adapters、Geometry Nodes、材质、动画和 UI
```

核心调用链：

1. `ReaderRegistry` 通过扩展名和内容 sniffing 选择 reader。
2. reader 返回只含标准语义对象的 `ImportBatch`。
3. `QCProject.commit()` 校验引用后原子接纳 source/revision、结构、计算、数据集和 provenance。
4. `sidecar.py` 将项目元数据写入 v0.2 manifest，将大型数组写入 `.npy`；v0.1 只在内存中迁移后读取。
5. Blender adapter 根据实体 UUID/revision 创建临时 Mesh、Curve、Volume、Material 或 Geometry Nodes。
6. 重计算任务通过 `worker_client.py` 启动独立 Python；worker 只在成功并复验结果后更新 sidecar。

## Extension 入口与基础数据

| 文件 | 主要入口 | 职责 |
| --- | --- | --- |
| `ChemBlender/__init__.py` | `register()`、`unregister()` | Extension 最小入口；延迟导入 `auto_load`，启动或卸载全部 Blender 注册项。 |
| `ChemBlender/auto_load.py` | `init()`、`register()`、`unregister()`、`toposort()` | 扫描扩展子模块，分析 Blender class 依赖并按拓扑顺序注册；卸载时反向清理类、模块副作用和 import cache。 |
| `ChemBlender/Chem_data.py` | `ELEMENTS_DEFAULT` | 保存元素序数、名称、颜色及共价/原子/范德华/离子半径等静态数据。该文件没有行为函数。 |
| `ChemBlender/_math.py` | `rotate_vec()`、`symop_xyz_to_matrix()`、`fract_symop_expand()`、`make_cell_matrix()`、`fract_to_cartn()`、`compute_thermal_ellipsoid()` | 旧结构建模层共享的向量、晶胞、分数坐标、对称操作和热振动椭球数学函数。 |
| `ChemBlender/ex_package.py` | `safe_check_rdkit()` | 检查 RDKit 是否存在并满足最低版本；不负责在线安装。 |
| `ChemBlender/extension.py` | `cat_generator()`、`NODE_MT_chem_GN_menu`、`NODE_OT_group_add`、`register()`、`unregister()` | 从节点库生成 Geometry Nodes 菜单，将节点组插入当前树，并管理菜单回调。 |

## 传统分子与晶体建模层

这组模块直接操作 `bpy`、BMesh、RDKit 和既有 Geometry Nodes，是原 ChemBlender 结构编辑功能的主体。

| 文件 | 主要入口 | 职责 |
| --- | --- | --- |
| `ChemBlender/read.py` | `read_MOL()`、`read_Cryst()`、`read_cif()`、`read_poscar()`、`init_cif_data()`、`update_cif_from_mesh()` | 兼容既有 UI 的分子/晶体读取路径；识别 SMILES、XYZ、MOL/SDF、PDB、JSON、CIF、POSCAR，建立键和 CIF PropertyGroup。新量子 reader 应进入 `core/`，不继续扩大此分支。 |
| `ChemBlender/scaffold.py` | `MESH_OT_SCAFFOLD_BUILD.execute()`、`show_error_dialog()` | 验证用户输入，调用读取函数，创建分子或晶体 scaffold，并统一显示输入错误。 |
| `ChemBlender/mesh.py` | `create_object()`、`add_scaffold_attr()`、`scaffold_to_mol()`、`set_sel_atoms_attr()`、`set_sel_bonds_attr()`、`mol_optimize()`、`unit_cell_edges()` | Mesh/BMesh 主工具箱：创建和合并对象、写原子/键属性、选择和编辑结构、RDKit 转换与优化、生成晶胞边。 |
| `ChemBlender/node.py` | `add_geometry_nodetree()`、`append()`、`Ball_Stick_nodetree()`、`Supercell()`、`CoordPolyhedra()`、`crys_filter()` | 创建或加载 Geometry Node Group，连接球棍、超胞、晶胞边、配位多面体和晶体过滤节点。 |
| `ChemBlender/chem_utils.py` | `SelectButton`、`EnhancedSelectButton`、`SetAtomsButton`、`SetBondsButton`、`ConnectByDistance`、`AddHydrogens`、`AddBranches`、`GeometryOptimizeButton` | 分子编辑 operators：选择、测距/测角、设置原子和键属性、补键/氢/支链、几何更新与优化、scaffold 转换。 |
| `ChemBlender/crys_utils.py` | `SupercellButton`、`AddCellButton`、`AddCrysScaffoldButton`、`AddCoordPolyhedraButton`、`SymmetrySelect`、`SymmetryDuplicate` | 晶体 operators：生成超胞和晶胞、添加/删除位点、配位多面体、等价位置选择及对称复制。 |
| `ChemBlender/output.py` | `xyz_block()`、`mol_block_v2000()`、`mol_block_v3000()`、`cif_block()`、`vasp_block()`、`SaveMolButton` | 从当前 Blender scaffold 生成 XYZ、MOL/SDF、CIF、POSCAR 文本并保存；还包含相机与快速渲染 operators。 |
| `ChemBlender/panel.py` | `CHEM_texts`、`CHEM_PT_Build`、`CHEM_PT_TOOLS`、`CRYSTAL_PT_TOOLS`、`CHEM_PT_OUTPUT` | 定义 Scene 属性和侧栏面板，组织结构构建、编辑、晶体工具及导出入口。 |
| `ChemBlender/periodictable.py` | `CHEMBLENDER_OT_OpenPeriodicTable`、`CHEMBLENDER_OT_SelectElement`、`CHEMBLENDER_PT_PeriodicPanel` | 周期表弹窗、元素选择与文本复制 UI。 |

## Blender 量子数据映射层

这些模块把 `core` 语义对象映射为 Blender 视图。它们可以写数据集 UUID、revision 和显示参数，但不成为权威数据存储。

| 文件 | 主要入口 | 职责 |
| --- | --- | --- |
| `ChemBlender/dataset_view.py` | `create_structure_view()`、`apply_atomic_scalar()`、`apply_atomic_vector()`、`apply_atom_selection()`、`link_stick_spectrum_selection()` | 建立标准结构 Mesh；把原子标量、矢量和选择写成 named attributes；记录光谱样点到源数据集的联动身份。 |
| `ChemBlender/grid_volume.py` | `volume_cache_path()`、`create_grid_volume()` | 将单个 `Grid3D` dataset 写成确定性 OpenVDB cache，并创建带 UUID/revision/affine metadata 的 Blender Volume。 |
| `ChemBlender/surface_view.py` | `create_signed_isosurfaces()`、`create_property_surface()`、`remove_surface_object()` | 用 Volume→Mesh Geometry Nodes 创建独立正/负相位面，或在密度面采样另一标量场并写入 `cbq_surface_property`。 |
| `ChemBlender/vibration_view.py` | `create_vibration_view()`、`apply_vibration_phase()` | 将一个振动模态写入位移属性和实例化箭头节点，并按相位更新原子位置。 |
| `ChemBlender/trajectory_view.py` | `configure_trajectory_view()`、`clear_trajectory_view()`、`register()`、`unregister()` | 绑定 `TrajectoryFrameManager` 与 Blender frame handler，只更新当前帧 Mesh 坐标并管理生命周期。 |
| `ChemBlender/spectrum_plot.py` | `create_spectrum_plot()` | 把 `Spectrum` 的横纵数据建立为 Blender Curve，并保存单位、类型和来源身份。 |
| `ChemBlender/electronic_plot.py` | `create_band_structure_plot()`、`create_dos_plot()`、`select_band_sample()`、`select_dos_sample()` | 创建 band/DOS Curve，处理费米能参考和 β-spin 镜像，并记录被选 k-point/band/energy 样点。 |
| `ChemBlender/fermi_surface_view.py` | `create_fermi_surface_view()`、`select_fermi_face()` | 将中立 `FermiSurfaceMesh` 转为三角 Mesh，把 band、投影、速度或自旋写入顶点/面属性并支持面到 band 的选择。 |
| `ChemBlender/topology_view.py` | `create_topology_view()` | 将 `TopologyGraph` 临界点映射为点 Mesh，将有采样坐标的路径映射为 Curve。 |
| `ChemBlender/scene_preset_view.py` | `apply_scene_preset()` | 复验 `ScenePresetPlan` 后分派结构、振动、光谱、band/DOS 和表面 adapter；任一 adapter 失败时删除本次创建的全部对象。 |
| `ChemBlender/project_link.py` | `MANIFEST_HASH_KEY`、`write_project_link()`、`resolve_project_link()` | 以不依赖 `bpy` 的内部 helper 计算 Scene locator；只从同一次 sidecar 验证取得 manifest hash，并以 UUID、schema 与 hash 解析、校验和恢复 `.cbq` 项目。 |
| `ChemBlender/worker_client.py` | `start_worker()`、`WorkerHandle.poll()`、`wait()`、`request_cancel()`、`terminate()` | 使用显式外部 Python 启动一次一任务的隐藏 worker 进程，管理 request/result/cancel 文件和 stdout/stderr 日志。 |

## 纯 Python 语义核心

### 模型、registry 与公共入口

| 文件 | 主要入口 | 职责 |
| --- | --- | --- |
| `ChemBlender/core/__init__.py` | 模块级 re-export | `core` 的普通 CPython、无 `bpy` 公共门面：稳定导出模型及其构造器/sidecar tag，并提供存储 API；Reader 与 Recipe 为 alpha 0.x 契约，具体 reader/adapter、派生、scene/reporting 与 connector 仅保持内部兼容导入，不是冻结插件 API。 |
| `ChemBlender/core/model/__init__.py` | 模块级显式 re-export | 模型 package 的兼容门面；从基础模块和各领域模块显式重导出公共名称，不保留领域模型定义。 |
| `ChemBlender/core/model/common.py` | `_require_uuid()`、`_require_token()`、`CalculationStatus`、`DatasetStatus`、`IssueKind` 等 12 个 enum | 提供模型共享的 token/UUID/text 校验器、正则模式和稳定枚举定义，不依赖 Blender 或可选科学栈。 |
| `ChemBlender/core/model/quality.py` | `QualityStatus`、`DiagnosticSeverity` | 定义导入质量和诊断严重度的稳定小写序列化值，并以显式映射固定摘要顺序。 |
| `ChemBlender/core/model/sources.py` | `SourceRecord`、`SourceRevision`、`source_parse_identity()` | 定义用户逻辑来源及其不可变内容/解析 revision；以内容 hash、reader plugin/id/version 和规范参数对计算与 locator 无关的解析身份。 |
| `ChemBlender/core/model/arrays.py` | `ArrayData` | 定义带命名维度、单位、shape 和 dtype 校验的中立数组包装，并由模型 package 原样 re-export。 |
| `ChemBlender/core/model/diagnostics.py` | `DiagnosticValue`、`ImportDiagnostic`、`diagnostic_from_parser_issue()`、`ParserIssue`、`ParserReport` | 以逐节点 type tag 定义不可变、JSON-safe 且可区分 sequence/mapping 的详细导入诊断，并提供 legacy reader issue 转换，同时保持既有 parser issue/report 契约。 |
| `ChemBlender/core/model/structure.py` | `PeriodicSiteData`、`MolecularTopology`、`Structure`、`SymmetryResult` | 定义分子/周期结构、拓扑关联和对称性结果；只依赖数组与共享校验基础层。 |
| `ChemBlender/core/model/properties.py` | `PropertyDataset`、`AtomicProperty`、`FrameSet` | 定义通用属性数据集及原子属性、坐标帧特化，是网格、光谱、周期和拓扑数据集的直接基类。 |
| `ChemBlender/core/model/grids.py` | `Grid3D` | 定义仿射三维网格、坐标单位、步进向量和可选结构引用校验。 |
| `ChemBlender/core/model/spectroscopy.py` | `VibrationalModeSet`、`ExcitedStateSet`、`Spectrum` | 定义振动模式、激发态贡献/引用和振动/电子光谱数据集。 |
| `ChemBlender/core/model/wavefunction.py` | `BasisSet`、`OrbitalSet`、`DensityMatrix` | 定义基组壳层/约定、轨道通道和 AO 密度矩阵及其内部一致性校验。 |
| `ChemBlender/core/model/periodic.py` | `BandStructure`、`DensityOfStates`、`PhononModeSet`、`FermiSurfaceMesh` | 定义能带、DOS、声子模式和费米面网格等周期体系数据集。 |
| `ChemBlender/core/model/topology.py` | `TopologyGraph`、`TopologyConnection`、`TopologyPath` | 定义临界点、连接和路径组成的中立拓扑图，并校验结构/网格引用所需的局部语义。 |
| `ChemBlender/core/model/project.py` | `CalculationRecord`、`ProvenanceRecord`、`ImportBatch`、`QCProject` | 定义交换 envelope、计算/溯源记录和项目聚合根；原子提交 source/revision、diagnostic 与科学实体，并校验全局 registry UUID 和双向 revision-diagnostic 关系。 |
| `ChemBlender/core/session.py` | `ProjectSession`、`create_session()`、`close_session()` | 在冻结科学模型之外管理可变会话状态；创建带 UUID ownership marker 的临时根，并在关闭 lazy resources 后仅删除标记匹配的受控目录。 |
| `ChemBlender/core/project_service.py` | `save_project_session()`、`relink_project_session()`、`verify_project_session()`、`clear_derived_cache()` | 编排原子 sidecar publication 与经 hash 验证的 Scene link；以显式状态恢复 session，并仅清理 `.cbq/cache/derivation/` 与 `.cbq/cache/render/` 非权威缓存。 |
| `ChemBlender/core/import_pipeline/__init__.py` | 模块级显式 re-export | 导入流水线的纯 Python package 门面；公开 request、preview、staging、preflight、conflict 与 grouping 契约，不加载 Blender 或可选科学栈。 |
| `ChemBlender/core/import_pipeline/conflicts.py` | `ImportConflictCandidate`、`ImportConflict`、`DuplicateAction`、`ConflictDecision`、`detect_import_conflicts()`、`apply_conflict_decisions()` | 只读比较 parse identity、内容 hash 与纯词法 locator，以不可拆分候选快照保留最高优先级的全部匹配；提交决定前根据 live project 和 staging session 重检完整冲突，target action 必须显式选择 revision，并返回新的 preview，不修改 session 或项目。 |
| `ChemBlender/core/import_pipeline/grouping.py` | `GroupingEvidence`、`SourceGroupSuggestion`、`CalculationGroup`、`suggest_source_groups()` | 从严格关联的暂存 batch 生成确定性、不可变的跨来源证据与分组建议；依次评估显式 UUID 引用、结构映射、Kabsch RMSD（`<= 0.15 Å`）、metadata 和文件名/目录，周期原胞/惯用胞候选只标记 review conflict，只有用户显式确认才创建独立 `CalculationGroup`，不修改 preview、session 或项目。 |
| `ChemBlender/core/import_pipeline/parse.py` | `staged_reader_batch()` | 将现有 reader 的 `ImportBatch` 适配为带 `SourceRecord`、`SourceRevision` 和双向诊断引用的暂存结果；规范参数绑定 reader execution mode，但不提交项目。 |
| `ChemBlender/core/import_pipeline/preflight.py` | `preflight_import()`、`ImportCancelled` | 对显式文件执行 bounded hash、reader 选择与 availability 检查、可取消解析和稳定失败诊断；只登记到 owned staging session，不写 `QCProject`。 |
| `ChemBlender/core/import_pipeline/request.py` | `ValidationMode`、`ImportSource`、`ReaderOverride`、`ImportRequest` | 定义不可变导入意图；规范化并去重显式文件路径，拒绝目录扫描，并将 reader override 限定到请求内来源。 |
| `ChemBlender/core/import_pipeline/preview.py` | `SourcePreview`、`ImportPreview` | 以不可变路径、标量和 UUID 引用描述 source row、暂存 batch、冲突、归组建议、诊断及默认 view plan，不持有项目或 Blender 对象。 |
| `ChemBlender/core/import_pipeline/staging.py` | `StagedImportSession.create()`、`register_result()`、`discard()` | 创建带 UUID ownership marker 的独占暂存根、artifact 目录和受控 `ImportBatch` registry；仅在路径、文件身份及 marker 均匹配时删除。 |
| `ChemBlender/core/readers.py` | `ReaderDescriptor`、`ReaderRuntimeDescriptor`、`ReaderAvailability`、`ReaderRegistry.register()`、`select()`、`parse()` | 定义 reader capability、扩展名、bounded sniffing 和确定性分派；以兼容 wrapper 分离 reader 选择与运行时 availability，拒绝未知或歧义 reader。 |
| `ChemBlender/core/reader_catalog.py` | `builtin_reader_descriptors()`、`builtin_reader_registry()`、`reader_capability_document()` | 汇总内置 reader，并生成机器可读的格式能力矩阵。 |
| `ChemBlender/core/cache_identity.py` | `source_hash_bytes()`、`parser_cache_key()`、`derivation_cache_key()`、`render_cache_key()` | 用规范 JSON 和 SHA-256 分别标识源文件、解析、派生和渲染缓存。 |

### 文件 reader 与第三方 adapter

| 文件 | 主要入口 | 职责 |
| --- | --- | --- |
| `ChemBlender/core/xyz.py` | `sniff_xyz()`、`parse_xyz()` | 读取单帧/多帧 XYZ 和受支持的 extXYZ lattice/PBC/property 子集，输出 `Structure`、`FrameSet` 和报告。 |
| `ChemBlender/core/mol_v2000.py` | `sniff_mol_v2000()`、`parse_mol_v2000()` | 使用标准库解析 MOL V2000 原子和结构；未建模的拓扑信息通过 `ParserReport` 明示。 |
| `ChemBlender/core/cube.py` | `sniff_cube()`、`parse_cube()` | 读取 Cube 原点、完整非正交 step vectors、多 dataset/MO index 和 voxel 数据，输出 `Grid3D`。 |
| `ChemBlender/core/cclib_adapter.py` | `sniff_cclib_output()`、`adapt_ccdata()`、`parse_cclib_output()` | 延迟加载 cclib，将 Gaussian/ORCA 等输出归一化为结构轨迹、能量、原子属性、振动、激发态及 parser issues。 |
| `ChemBlender/core/iodata_adapter.py` | `sniff_iodata_wavefunction()`、`adapt_iodata()`、`parse_iodata_wavefunction()` | 延迟加载 IOData，将 FCHK/Molden 的结构、basis、restricted/unrestricted/generalized MO 和 RDM 转为内部模型。 |
| `ChemBlender/core/ase_adapter.py` | `sniff_ase_structure()`、`adapt_ase_atoms()`、`parse_ase_structure()` | 延迟加载 ASE，归一化分子/周期结构、约束、per-atom arrays 和轨迹。 |
| `ChemBlender/core/gemmi_adapter.py` | `sniff_cif()`、`parse_cif()` | 用 Gemmi 解析 CIF block/loop、周期位点、occupancy、Uij 和原始 envelope，避免手写 CIF 词法。 |
| `ChemBlender/core/spglib_adapter.py` | `derive_symmetry()` | 用 spglib 从周期结构派生空间群、Hall number、操作、Wyckoff/equivalent atoms 和标准化变换。 |
| `ChemBlender/core/pymatgen_adapter.py` | `sniff_vasp_volumetric()`、`adapt_pymatgen_structure()`、`adapt_vasp_volumetric()`、`parse_vasp_volumetric()` | 读取 CHGCAR/PARCHG/ELFCAR/LOCPOT 类周期体数据并保留晶格与 dataset 语义。 |
| `ChemBlender/core/pymatgen_electronic.py` | `sniff_vasprun()`、`adapt_pymatgen_electronic()`、`parse_vasprun_electronic()` | 从 pymatgen electronic objects/vasprun 归一化 band、DOS/PDOS、spin、投影和能量参考。 |
| `ChemBlender/core/phonopy_adapter.py` | `adapt_phonopy_qpoints()` | 将 phonopy q-point、频率、复数 eigenvector、权重和晶胞关系转为 `PhononModeSet`。 |
| `ChemBlender/core/pyprocar_adapter.py` | `adapt_pyprocar_fermi_surface()` | 将已生成的 PyVista-compatible PyProcar surface 转为不依赖 PyVista 的顶点、三角面、band 和属性数组。 |
| `ChemBlender/core/critic2_adapter.py` | `parse_critic2_cpreport()` | 解析 critic2 `cpreport` JSON 的临界点、cell copies、connectivity、属性和 provenance，输出 `TopologyGraph`。 |
| `ChemBlender/core/qcschema_adapter.py` | `parse_qcschema_atomic_result()`、`parse_qcschema_molecule()`、`parse_qcschema()`、`export_qcschema()` | 兼容 QCSchema v1/v2 结果和 Molecule envelope，在内部模型与版本化交换文档之间转换。 |
| `ChemBlender/core/cjson_adapter.py` | `parse_cjson()`、`export_cjson()`、`sniff_cjson()` | 导入/导出 Avogadro CJSON 的结构、拓扑、轨迹和轻量原子数据，并保留原始 envelope。 |

### 派生计算、工作流与存储

| 文件 | 主要入口 | 职责 |
| --- | --- | --- |
| `ChemBlender/core/wavefunction_grid.py` | `evaluate_molecular_orbital_grid()`、`evaluate_electron_density_grid()` | 验证内部 basis/MO convention，延迟调用 `qc-gbasis==0.1.0`，在任意 affine 规则网格求 MO 或按 occupation 合成电子密度。 |
| `ChemBlender/core/wavefunction_observables.py` | `evaluate_density_matrix_grid()`、`evaluate_electrostatic_potential_grid()` | 从 `DensityMatrix` 求 electron/spin density，并结合有效核电荷调用 GBasis 求 ESP；拒绝核奇点和无效矩阵。 |
| `ChemBlender/core/vibration_spectrum.py` | `derive_vibrational_spectrum()`、`derive_electronic_spectrum()` | 从振动强度或激发态强度生成 stick/高斯展宽 IR、Raman、UV-Vis、ECD `Spectrum`，记录派生身份。 |
| `ChemBlender/core/phonon_frames.py` | `derive_phonon_frames()` | 根据复数 q-point eigenvector 和 `Re[e exp(i(q·R-ωt+φ))]` 生成周期超胞声子动画帧。 |
| `ChemBlender/core/trajectory_frames.py` | `TrajectoryFrameManager.frame()`、`prefetch_around()`、`interpolate()`、`mean()` | 对 sidecar 轨迹执行逐帧 lazy 读取、有界 LRU 缓存、预取、插值和区间平均。 |
| `ChemBlender/core/grid_lod.py` | `derive_grid_lod()`、`volume_render_cache_key()`、`surface_render_cache_key()` | 通过确定性 stride 生成 `Grid3D` LOD，并计算 Volume/Surface 渲染缓存身份。 |
| `ChemBlender/core/model_registry.py` | `MODEL_TYPES`、`MODEL_ENUMS`、`model_type_tag()`、`model_type_from_tag()` | 明确登记 sidecar 可序列化的 dataclass 和 enum；以不可变映射固定 type tag 与具体模型类的对应关系。 |
| `ChemBlender/core/sidecar.py` | `LazyNpyArray`、`save_project()`、`open_project()`、`close_project()` | `.cbq` v0.2 存储实现：写 generation metadata 与 canonical manifest hash，原子发布 manifest/数组；读取当前 manifest 时先验证原始 hash/header，以迁移副本严格 decode，并向内部 publication 返回未经改写的已验证 metadata。 |
| `ChemBlender/core/sidecar_migrations.py` | `migrate_manifest()` | 在严格模型 decode 前把已校验的 v0.1 文档复制并迁移为 schema `0.2`，并为早期 v0.2 项目补空 diagnostic registry；不改写 fixture 或已发布 sidecar。 |
| `ChemBlender/core/storage/publication.py` | `solidify_session()`、`inspect_publication_orphans()`、`PublishedProject`、`PublicationRecoveryReport`、`PublicationRecoveryError` | 在目标同目录写入并复验完整 `.cbq` generation，经 backup rename 发布或非破坏回滚；恢复不完整时同时保留原发布错误、回滚错误和不可变路径报告，不删除无法证明归属的目录。 |
| `ChemBlender/core/recipe.py` | `RecipeDefinition`、`plan_recipe()`、`recipe_document()`、`recipe_from_document()`、`builtin_recipes()` | 定义版本化分析 recipe 的输入语义、参数、输出、view、验证和引用；plan 阶段只绑定实体，不执行计算。 |
| `ChemBlender/core/scene_preset.py` | `builtin_scene_presets()`、`plan_scene_preset()`、`validate_scene_plan()`、`scene_preset_for_recipe_view()` | 定义 publication scene preset，验证数据绑定和设置，并生成可重放的 render identity。 |
| `ChemBlender/core/analysis_report.py` | `build_analysis_report()`、`validate_analysis_report()`、`render_analysis_report_markdown()`、`write_analysis_report_bundle()` | 汇总 calculation、dataset、recipe、provenance、artifact 和引用，生成确定性 JSON/Markdown 报告包。 |
| `ChemBlender/core/external_connector.py` | `builtin_external_connectors()`、`ExternalRecordRequest`、`external_record_request_document()`、`external_record_source_uri()` | 定义 QCArchive/AiiDA/NOMAD 的 provider-neutral 请求、locator、凭据环境变量引用和脱敏 provenance URI。 |
| `ChemBlender/core/worker_protocol.py` | `WorkerRequest`、`WorkerResult`、`write_request()`、`read_request()`、`write_result()`、`read_result()` | Blender 与外部 worker 共用的严格 JSON 协议；校验版本、operation、实体 revision、artifact 相对路径、错误和取消状态。 |

## Extension 维护脚本

这些脚本随源码保存，但由开发者或 CI 调用，不在 Extension 运行时执行。

| 文件 | 主要入口 | 职责 |
| --- | --- | --- |
| `ChemBlender/scripts/validate_extension.py` | `main()` | 检查 manifest、wheel 路径、依赖策略、绝对 import 和源码布局，再调用 Blender 原生 Extension validate。 |
| `ChemBlender/scripts/build_extension.py` | `main()` | 解析 Blender/Python/MCP 路径与系统兼容性，先验证再调用 Blender 原生 Extension build。 |
| `ChemBlender/scripts/verify_release_artifact.py` | `verify_artifact()`、`main()` | 校验 Release ZIP 的 SHA-256、版本、路径安全、必需/禁止内容和 manifest contract。 |
| `ChemBlender/scripts/extract_release_notes.py` | `extract_release_notes()`、`main()` | 从 `CHANGELOG.md` 精确提取一个版本的非空 Release body。 |
| `ChemBlender/scripts/benchmark_sidecar.py` | `run_benchmark()`、`main()` | 对代表性结构、轨迹、轨道和网格 `.npy` 写入/打开/切片性能进行基准测量。 |

## 外部 worker

worker 使用调用者明确提供的 Python 环境。默认 registry 只接受固定 operation，request 不能指定任意 module、callable、shell 或 argv。

| 文件 | 主要入口 | 职责 |
| --- | --- | --- |
| `worker/__init__.py` | 包标记 | 声明独立 worker package；没有运行逻辑。 |
| `worker/protocol.py` | re-export | 从 `ChemBlender.core.worker_protocol` 重导出协议，使 runner 与 Blender client 使用同一数据契约。 |
| `worker/operation.py` | `OperationContext`、`OperationOutput`、`OperationError` | 定义 operation 接收的项目上下文、待提交 batch/artifact/metadata，以及稳定错误码。 |
| `worker/runner.py` | `OperationRegistry`、`run_request()`、`default_registry()`、`main()` | 打开 sidecar、校验输入 revision、检查取消、执行固定 operation、原子提交并重开复验输出，最后写 result。 |
| `worker/wavefunction_operations.py` | `register_wavefunction_operations()` | 注册 `wavefunction.mo_grid@1` 与 `wavefunction.electron_density_grid@1`，把 structure/basis/orbital 引用交给 GBasis 派生函数。 |
| `worker/qcengine_operation.py` | `execute_qcschema()`、`qcschema_compute_operation()`、`register_qcschema_compute_operation()` | 注册 `qcschema.compute@1`；受控调用 QCEngine 或最小 PySCF HF/RHF/UHF adapter，将成功结果统一转回 AtomicResult。 |
| `worker/connector_operation.py` | `external_record_operation()`、`register_external_record_operation()` | 注册 `external_record.fetch@1`；当前完成离线 QCSchema/CJSON replay、凭据检查、内容寻址 artifact 和脱敏 provenance。 |
| `worker/external_program.py` | `ExternalAdapterDescriptor`、`ExternalInvocation`、`run_external_program()`、`critic2_invocation()`、`multiwfn_invocation()` | 为 critic2/Multiwfn 构造固定、安全、`shell=False` 的进程调用；处理 timeout/cancel、日志 hash、缺失/陈旧输出和版本探测。 |

## 阅读建议

- 想理解数据边界：先从 `model/__init__.py` 找到对应领域模块，再读 `readers.py`、一个具体 reader 和 `sidecar.py`。
- 想增加文件格式：复用 `ReaderDescriptor`，返回 `ImportBatch`，不要从 parser 直接创建 `bpy` 对象。
- 想增加物理量：先扩展 `PropertyDataset` 语义和 provenance，再添加派生函数与 Blender adapter。
- 想增加 Blender 显示：从 `dataset_view.py`、`grid_volume.py`、`surface_view.py` 或 `scene_preset_view.py` 选择最近的现有 contract。
- 想增加重型计算：在 `worker/` 注册固定 operation；不要让 Extension import、安装或同步运行重型后端。
- 想修改发布流程：阅读 `docs/development/testing-and-ci.md` 和 `.agents/reference/dependencies-and-release.md`，不要只验证 ZIP 是否生成。

## 附录 A：量子化学术语与缩写

| 缩写/术语 | 英文全称 | 本项目中的含义 |
| --- | --- | --- |
| AO | Atomic Orbital | 原子轨道/基函数。GBasis 在空间采样点计算 AO 值，MO 和密度由 AO 组合得到。 |
| MO | Molecular Orbital | 分子轨道，通常写成 AO 的线性组合；ChemBlender 将其求值为带正负相位的 `Grid3D`。 |
| HOMO | Highest Occupied Molecular Orbital | 最高占据分子轨道。开放壳层体系必须同时区分 α/β 通道。 |
| LUMO | Lowest Unoccupied Molecular Orbital | 最低未占据分子轨道；常与 HOMO 一起用于前线轨道显示。 |
| SOMO | Singly Occupied Molecular Orbital | 单占据分子轨道，常见于自由基和其他开放壳层体系。 |
| NTO | Natural Transition Orbital | 自然跃迁轨道；把复杂激发态跃迁压缩为主要 hole/particle 轨道对。当前模型保存引用，尚未自行求解 NTO。 |
| RDM / 1-RDM | Reduced Density Matrix / One-particle Reduced Density Matrix | 约化密度矩阵/一阶约化密度矩阵；与 AO 基函数收缩后得到电子或自旋密度。 |
| SCF | Self-Consistent Field | 自洽场迭代，是 HF/DFT 等方法获得轨道和密度的基本过程。 |
| HF | Hartree–Fock | Hartree–Fock 电子结构方法；当前 PySCF worker 的最小计算范围。 |
| RHF | Restricted Hartree–Fock | 限制性 HF，α/β 电子共享同一套空间轨道，通常用于闭壳层。 |
| UHF | Unrestricted Hartree–Fock | 非限制性 HF，α/β 使用不同轨道，适用于开放壳层但可能有自旋污染。 |
| DFT | Density Functional Theory | 密度泛函理论；以电子密度为基本变量的电子结构方法。当前核心可显示其结果，但最小 PySCF worker 未承诺完整 DFT 执行。 |
| TDDFT | Time-Dependent Density Functional Theory | 含时密度泛函理论；常用于激发能、振子强度和 UV-Vis/ECD 光谱。 |
| ESP / MEP | Electrostatic Potential / Molecular Electrostatic Potential | 静电势/分子静电势。通常采样到电子密度表面，用发散色标显示，而不是替代密度表面。 |
| IR | Infrared Spectroscopy | 红外光谱；由振动频率与 IR 强度生成 stick 或展宽曲线。 |
| Raman | Raman Spectroscopy | 拉曼光谱；以 Raman activity 与振动频率生成。名称来自 Raman 效应，不是首字母缩写。 |
| UV-Vis | Ultraviolet–Visible Spectroscopy | 紫外-可见吸收光谱；由激发能和 oscillator strength 派生。 |
| ECD | Electronic Circular Dichroism | 电子圆二色谱；通常由激发能和旋光强度派生。 |
| DOS | Density of States | 态密度，描述给定能量附近可用电子态数量。 |
| PDOS | Projected Density of States | 投影态密度，将 DOS 分解到元素、原子或轨道。 |
| PBC | Periodic Boundary Conditions | 周期性边界条件；周期结构、轨迹和体网格必须显式保存。 |
| BZ | Brillouin Zone | 布里渊区，即倒空间中的原胞；band path 和 Fermi surface 位于该空间。 |
| QTAIM | Quantum Theory of Atoms in Molecules | 分子中原子的量子理论；通过电子密度临界点、键径和 basin 分析化学键拓扑。 |
| CP | Critical Point | 标量场临界点；QTAIM 中常区分 nuclear、bond、ring 和 cage critical point。 |
| NCI | Non-Covalent Interaction | 非共价相互作用分析；常用 RDG 等值面并以 `sign(λ₂)ρ` 着色。 |
| RDG | Reduced Density Gradient | 约化密度梯度，用于突出弱相互作用区域。 |
| ELF | Electron Localization Function | 电子局域函数，用于观察电子对、孤对电子和成键局域性。 |
| LOL | Localized Orbital Locator | 局域轨道定位函数，是另一类电子局域性指标。 |
| FCHK | Formatted Checkpoint | Gaussian 格式化 checkpoint 文件，包含结构、基组、MO、RDM、梯度或 Hessian 等机器可读数据。 |
| WFN / WFX | Wavefunction File / Extended Wavefunction File | 波函数交换格式，保存基组、轨道与密度相关数据；WFX 是扩展格式。 |
| CIF | Crystallographic Information File | 晶体学信息文件；本项目用 Gemmi 解析语法，用 spglib 派生/核验对称性。 |
| CJSON | Chemical JSON | Avogadro 使用的化学 JSON 交换格式，适合结构和轻量结果，不承载大型权威数组。 |
| QCSchema | Quantum Chemistry Schema | MolSSI 的量子化学计算输入/结果数据规范；本项目通过版本化 adapter 与内部模型交换。 |
| VASP | Vienna Ab initio Simulation Package | 周期第一性原理程序；本项目读取其结构、体数据、band 和 DOS 输出，不把 VASP 嵌入 Blender。 |

## 附录 B：Blender 与科学可视化术语和缩写

| 缩写/术语 | 英文全称 | 本项目中的含义 |
| --- | --- | --- |
| `bpy` | Blender Python API | Blender 官方 Python 模块；只允许出现在 Blender 映射/UI 层，不允许进入纯 Python core。 |
| BMesh | Blender Mesh Editing API | 面向拓扑编辑的 Mesh API；传统结构编辑代码用它读写顶点、边、面和自定义 layer。 |
| GN | Geometry Nodes | 几何节点系统；用 named attributes 驱动球棍、箭头、超胞、表面和实例化几何。 |
| Node Group | Geometry Node Group | 可复用节点网络；`node.py` 从库加载或构建节点组，并连接到 modifier。 |
| Modifier | Blender Modifier | 非破坏式对象处理器；ChemBlender 使用 Geometry Nodes 和 Volume-to-Mesh 类 modifier 生成最终视图。 |
| Datablock | Blender Data-block | Blender ID 数据单元，例如 Mesh、Curve、Volume、Material、Object 和 Collection；本项目把它视为视图或缓存。 |
| Mesh | Polygon Mesh | 顶点、边、面的几何数据；用于结构、费米面、临界点和等值面输出。 |
| Curve | Curve Data-block | 曲线几何；用于 band、DOS、光谱和采样后的拓扑路径。 |
| Volume | Volume Data-block | 体数据对象；加载 OpenVDB 网格，再由 Blender 显示或转换为等值面。 |
| VDB / OpenVDB | Open Volume Database | 稀疏体数据格式与库；ChemBlender 用它缓存大型 `Grid3D` 并交给 Blender Volume。 |
| Named Attribute | Geometry Nodes Named Attribute | Mesh/Curve 上按名称访问的属性；保存原子标量、矢量、selection、band index 和 surface property。 |
| Object Custom Property | Blender ID Property | 写在 Object/Scene 上的轻量 metadata；保存 UUID、revision、显示设置和 sidecar locator，不保存大型权威数组。 |
| Operator | Blender Operator | 可撤销的用户动作类，通常实现 `execute()`/`invoke()`；按钮和菜单通过 `bl_idname` 调用。 |
| Panel | Blender UI Panel | 侧栏或属性编辑器中的 UI 面板；负责排列操作入口，不承担量子数据解析。 |
| PropertyGroup | Blender Property Group | Blender 可注册的结构化属性集合；旧 CIF/UI 状态仍使用它，但它不是量子项目权威模型。 |
| Scene | Blender Scene | 场景及其全局设置；只保存 project link 和 UI 状态。 |
| Collection | Blender Collection | Object 的逻辑容器；adapter 可把同一 preset 生成的对象放入指定 collection。 |
| Handler | Blender Application Handler | Blender 事件回调；轨迹模块使用 frame-change handler 更新当前帧坐标。 |
| Extension | Blender Extension | Blender 4.2+ 的安装/打包形式；本仓库 2.2.x 的发布根目录是 `ChemBlender/`。 |
| Add-on | Blender Add-on | 传统插件形式；2.1.1 是本项目最后一个 legacy add-on 版本，2.2.x 不再复制到旧 add-ons 目录。 |
| LOD | Level of Detail | 多分辨率表示；`Grid3D` 通过确定性 stride 生成预览或终稿级网格。 |
| UI | User Interface | 用户界面；包括 Panel、Operator、菜单、属性和 linked selection。 |
| UUID | Universally Unique Identifier | 跨 sidecar、数据集和 Blender 视图稳定关联实体的唯一标识。 |
| ABI | Application Binary Interface | Python/NumPy 与 `.pyd`/DLL 等编译扩展的二进制兼容边界，是重依赖留在 worker 的主要原因之一。 |
| IPC | Inter-Process Communication | 进程间通信；当前 worker v1 使用 request/result/cancel JSON 文件和子进程状态，而不是常驻网络服务。 |
