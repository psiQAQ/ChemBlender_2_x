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
| `ChemBlender/__init__.py` | `register()`、`unregister()` | Extension 最小入口；只延迟委托给 `runtime.registration`，不保存 Blender class、callback 或 Reader API handle 状态。 |
| `ChemBlender/auto_load.py` | `get_ordered_classes_to_register()`、`toposort()`、`_safe_register_class()`、`_safe_unregister_class()` | 只分析显式模块中的 Blender class 依赖、执行拓扑排序并提供安全 class 注册/注销；不扫描 package、不清 import cache，也不是第二条生产注册路径。 |
| `ChemBlender/runtime/__init__.py` | package marker | 隔离依赖 Blender host 状态的 runtime bridge；导入该 package 本身不加载注册实现或触发注册副作用。 |
| `ChemBlender/runtime/registration.py` | `REGISTER_MODULE_NAMES`、`register_extension()`、`unregister_extension()` | Blender 注册唯一 owner：按实际 package root 导入显式传统 UI/operator/handler 根，去重并拓扑注册 class，再执行 module callback、最后发布 Reader API handle；注册一条自有 persistent `load_post` 以在 Blender 清空 driver namespace 后重新发布同一 handle/registry，卸载与失败回滚只反向清理自有状态并把 cleanup failure 作为原异常 note 保留。未来 Blender UI 模块必须显式加入清单和 lifecycle 测试，pure core、Reader API 与 optional stack 不参与注册扫描。 |
| `ChemBlender/runtime/reader_api_bridge.py` | `ReaderAPIHandle`、`register_reader_api_handle()`、`remove_reader_api_handle()`、`get_reader_plugin_registry()` | 以实际安装 package root 构造 Reader API 模块名，在 `bpy.app.driver_namespace` 发布由模块私有 identity 和不透明 token 共同约束的版本化 handle；稳定 wrapper callback 保护内置 reader，只允许外部插件精确注册/注销自身 manifest；普通 enable/disable 只更换自有 handle，持续复用 registry、内置 reader 对象和公开模型 class identity；内部 accessor 让主进程导入管线复用同一 registry，但不把 registry 交给插件；模块导入保持 `bpy`-free，仅调用 bridge 时访问 Blender。 |
| `ChemBlender/ui/__init__.py` | package marker | 声明 Blender UI package；不导入 Blender、注册 root 或科学模型。 |
| `ChemBlender/ui/session.py` | `get_scene_session()`、`new_scene_session()`、`close_scene_session()`、`register_session_cleanup()`、`register_session_mutation()`、`register()`、`unregister()` | 用一个显式 owned entry 管理当前已加载 `.blend` 的共享 `ProjectSession`，所有 Scene 经兼容入口 `get_scene_session(scene)` 取得同一科学项目与临时根；Scene 只保留状态/显示投影，不拥有独立项目。load/unregister 只 drain 一次共享 entry，失败保留 recovery entry 供重试；会话替换或关闭前调用全部已注册 UI cleanup，并在失败时保留可重试所有权。`load_post` 对无 link、相同 link、一个有效 link 加空 Scene 和冲突有效 link 分别执行空会话、一次采纳、统一投影和 fail-closed；`save_pre` 不依赖 active Scene，只发布一次并把相同已验证 link 原子投影到全部 Scene。新建/替换以及成功采用 sidecar 后通知小型 UI projection invalidator，失败或无效恢复不通知；脏会话关闭时只写一个非权威 recovery marker 并保留临时根，干净会话关闭时释放 lazy resource 与受控临时根。 |
| `ChemBlender/ui/properties.py` | `CHEMBLENDER_PG_quick_import`、`QuickImportUIState`、`get_quick_import_state()`、`advance_browser_revision()`、`store_quick_import_preview()` | 只把 validation mode 与最近摘要等小型显示状态放入 Scene RNA，并以 RNA property `as_pointer()`（测试环境回退到对象 identity）精确记录 `Scene.chemblender_quick_import` 所有权：拒绝覆盖预先存在的 foreign property，卸载也不删除后来替换的 foreign property。`ImportPreview`、`StagedImportSession`、live conflicts/grouping suggestions、browser revision 与 active import job 保持在按 `ProjectSession.id` 归属的内存状态中；成功 import/view 与 session project adoption 共用单一 revision helper 使 Project Browser cache 失效。staging 创建后立即取得所有权；替换、会话关闭、文件加载与卸载时先取消并等待正在发布的 commit owner 安全退出，再显式 discard staging root，清理失败则保留状态供重试。 |
| `ChemBlender/ui/quick_import.py` | `CHEMBLENDER_OT_quick_import`、`CHEMBLENDER_PT_quick_import` | 多文件选择器或 FileHandler 注入的 transient 路径经相同安全校验确定性构造共享 `ImportRequest`；有效 drop 路径直接进入既有 staging，手动调用仍打开 File Browser，且本次 drop 后清空路径避免复用。仅通过 Reader API registry accessor 调用 `preflight_reader_plugins()` 并暂存 preview；交互模式把可能超过 1 秒的 preflight 放入可取消 worker，通过 modal timer 在主线程更新 Blender progress/RNA，并在完成后打开 Import Preview，background 模式保持同步；同模块 N 面板显示 session/link/dirty 状态与 preflight、review/cancel、保存、workspace fallback 入口；不解析格式、不提交项目、不把 batch/array 写入 Blender RNA。 |
| `ChemBlender/ui/default_views.py` | `DefaultViewPlan`、`plan_default_view()`、`describe_default_view()` | 纯 UI planner；只按一个 SourceRevision 已创建的 entity UUID、Grid3D 状态与 semantic role 选择 `structure_publication`、`grid_volume` 或 `signed_isosurface`，不导入 `bpy`，也不把 view plan 写入科学模型或 sidecar schema。 |
| `ChemBlender/ui/import_preview.py` | `CHEMBLENDER_PG_import_preview_row`、`CHEMBLENDER_PG_import_conflict_candidate`、`CHEMBLENDER_PG_import_grouping_suggestion`、`CHEMBLENDER_OT_confirm_import`、`CHEMBLENDER_OT_cancel_import`、`project_import_preview()`、`project_grouping_suggestions()`、`commit_project_import()` | 将 staged preview、reader availability、quality、format-aware default view、live conflict candidates 与 grouping evidence 投影为只含 UUID 字符串、标签、计数、枚举和布尔值的小型 RNA 行；动态只显示允许的 conflict action，多候选 target 必须显式单选。Grouping 默认 Keep Independent，Accept Group 只把用户选择且能连通全部来源的 evidence 组装为既有 `GroupingDecision`，review suggestion 另需确认，Split/Edit 明确显示为 alpha.1 不可用；确认前重检 live conflict/grouping snapshot，并经单一 `ImportCommitDecisions` 进入 `commit_import_preview()`。提交科学数据后在 Blender 主线程把 committed revision 的纯 `DefaultViewPlan` 转为真实 `ScenePresetPlan`；Grid3D cache 受控于 session temporary root。交互 commit 在具有 teardown ownership barrier 的 modal worker 中发布纯项目数据，任一 view 失败只删除本次 attempt 创建对象并明确报告 `data committed; view failed`，不伪称科学事务已回滚。 |
| `ChemBlender/ui/project_browser/__init__.py` | `BrowserMode`、`BrowserRow`、`ViewRecord`、`build_browser_rows()` | 公开纯 Python Project Browser 投影入口；不导入 `bpy`，不触碰 scientific array payload。 |
| `ChemBlender/ui/project_browser/model.py` | `BrowserMode`、`BrowserRow`、`ViewRecord`、`build_browser_rows()` | 从 `QCProject` registry 与独立 presentation `ViewRecord` 生成 By Source/By Data 确定性 flat tree；By Source 的 row ID 包含完整 parent path 并在同一 parent 内确定性去重，空项目也返回显式 empty row；view 只有在 entity UUID 与 revision 同时匹配时关联。搜索保留命中项祖先，显式 filter 不保留无关 group；缓存身份包含 project/session、单调 browser revision、规范化搜索/filter 与含 revision 的稳定 view fingerprint，全程不读取 `ArrayData.values`。 |
| `ChemBlender/ui/project_browser/panel.py` | `CHEMBLENDER_UL_project_rows`、`CHEMBLENDER_PT_project_browser`、`presentation_view_records()`、`refresh_project_browser()` | 在 Blender 主线程严格解析 object 的 scene-preset binding entity UUID/revision metadata，投影为 presentation-only `ViewRecord`，并把 flat tree 复制到只含小字符串、整数与枚举的 RNA 行；UIList 只允许当前 project scientific registry 中的 UUID 更新 `ProjectSession.active_entity_id`，过滤隐藏的有效选择继续保留，stale/malformed/group/view/empty 选择清空。精确拥有 `Scene.chemblender_project_browser`，注册失败保留主错误与可重试 residual ownership，不覆盖或删除 foreign property。 |
| `ChemBlender/ui/file_handlers.py` | `CHEMBLENDER_FH_view_3d_window`、`CHEMBLENDER_FH_project_browser` | 为 3D View WINDOW 与 Project Browser UI region 提供 Blender FileHandler，并统一委托 `chemblender.quick_import`；只广告当前可用 built-in Reader descriptor 的确定性扩展名集合，`poll_drop()` 仅检查 area/region，不读取路径、解析文件或访问项目数据。缺少 Blender FileHandler API 时不访问 reader registry 并 fail closed；模块精确管理手动注册的 handler 所有权。 |
| `ChemBlender/ui/workspace.py` | `CHEMBLENDER_OT_open_workspace`、`workspace_is_compatible()` | 从 Extension 包内安全追加或复用唯一 `ChemBlender` WorkSpace；切换前验证 3D View、浏览侧栏、Properties 和底部编辑区布局，失败时只回滚本次追加的 datablock，不影响 Quick Import、Project Browser 或科学项目状态。 |
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
| `ChemBlender/panel.py` | `CHEM_texts`、`CHEM_PT_Build`、`CHEM_PT_TOOLS`、`CRYSTAL_PT_TOOLS`、`CHEM_PT_OUTPUT` | 定义 Scene 属性和原有侧栏面板，组织结构构建、编辑、晶体工具及导出入口。 |
| `ChemBlender/periodictable.py` | `CHEMBLENDER_OT_OpenPeriodicTable`、`CHEMBLENDER_OT_SelectElement`、`CHEMBLENDER_PT_PeriodicPanel` | 周期表弹窗、元素选择与文本复制 UI。 |

## Blender 量子数据映射层

这些模块把 `core` 语义对象映射为 Blender 视图。它们可以写数据集 UUID、revision 和显示参数，但不成为权威数据存储。

| 文件 | 主要入口 | 职责 |
| --- | --- | --- |
| `ChemBlender/dataset_view.py` | `create_structure_view()`、`apply_atomic_scalar()`、`apply_atomic_vector()`、`apply_atom_selection()`、`link_stick_spectrum_selection()` | 建立标准结构 Mesh；把原子标量、矢量和选择写成 named attributes；记录光谱样点到源数据集的联动身份。 |
| `ChemBlender/grid_volume.py` | `volume_cache_path()`、`create_grid_volume()` | 将单个 `Grid3D` dataset 写成确定性 OpenVDB cache，并创建带 UUID/revision/affine/render identity metadata 的 Blender Volume。 |
| `ChemBlender/surface_view.py` | `create_signed_isosurfaces()`、`create_property_surface()`、`remove_surface_object()` | 用 Volume→Mesh Geometry Nodes 创建独立正/负相位面，或在密度面采样另一标量场并写入 `cbq_surface_property`。 |
| `ChemBlender/vibration_view.py` | `create_vibration_view()`、`apply_vibration_phase()` | 将一个振动模态写入位移属性和实例化箭头节点，并按相位更新原子位置。 |
| `ChemBlender/trajectory_view.py` | `configure_trajectory_view()`、`clear_trajectory_view()`、`register()`、`unregister()` | 绑定 `TrajectoryFrameManager` 与 Blender frame handler，只更新当前帧 Mesh 坐标并管理生命周期。 |
| `ChemBlender/spectrum_plot.py` | `create_spectrum_plot()` | 把 `Spectrum` 的横纵数据建立为 Blender Curve，并保存单位、类型和来源身份。 |
| `ChemBlender/electronic_plot.py` | `create_band_structure_plot()`、`create_dos_plot()`、`select_band_sample()`、`select_dos_sample()` | 创建 band/DOS Curve，处理费米能参考和 β-spin 镜像，并记录被选 k-point/band/energy 样点。 |
| `ChemBlender/fermi_surface_view.py` | `create_fermi_surface_view()`、`select_fermi_face()` | 将中立 `FermiSurfaceMesh` 转为三角 Mesh，把 band、投影、速度或自旋写入顶点/面属性并支持面到 band 的选择。 |
| `ChemBlender/topology_view.py` | `create_topology_view()` | 将 `TopologyGraph` 临界点映射为点 Mesh，将有采样坐标的路径映射为 Curve。 |
| `ChemBlender/scene_preset_view.py` | `apply_scene_preset()` | 复验 `ScenePresetPlan` 后分派结构、Grid3D Volume、振动、光谱、band/DOS 和表面 adapter；任一 adapter 失败时删除本次创建的全部对象。 |
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
| `ChemBlender/core/model/grouping.py` | `CalculationGroup` | 定义用户确认的跨来源计算分组实体；以完整 suggestion、source revision 与 evidence 身份生成稳定 UUID，并作为 `QCProject` 与 `.cbq` 的权威科学关系保存。 |
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
| `ChemBlender/core/model/project.py` | `CalculationRecord`、`ProvenanceRecord`、`ImportBatch`、`QCProject`、`validate_project_graph()` | 定义交换 envelope、计算/溯源记录和项目聚合根；原子提交 source/revision、diagnostic 与科学实体，并校验全局 registry UUID 和双向 revision-diagnostic 关系；`validate_project_graph()` 以一次临时 `QCProject.commit()` 和 calculation-group 提交复验完整已存在图。 |
| `ChemBlender/core/session.py` | `ProjectSession`、`create_session()`、`close_session()` | 在冻结科学模型之外管理可变会话状态；`mark_clean()` 仅显式清空已记录 dirty reasons；创建带 UUID ownership marker 的临时根，并在关闭 lazy resources 后仅删除标记匹配的受控目录。 |
| `ChemBlender/core/project_service.py` | `save_project_session()`、`save_project_session_for_scenes()`、`verify_project_session()`、`verify_project_session_for_scenes()`、`relink_project_session()`、`clear_derived_cache()` | 编排原子 sidecar publication 与经 hash 验证的 Scene link；多 Scene API 只验证/发布一个项目并先快照全部 link，再写入同一 UUID、schema、locator 与 manifest hash，任一 Scene 写失败时恢复所有原 link、保持 dirty 且不报告 connected；单 Scene API 保持兼容 wrapper。恢复时忽略空 Scene、只采纳一次相同有效 link，并对冲突有效 link fail-closed；只有 publication 与全部 Scene link 成功、或成功采纳并投影经验证磁盘项目后才标记 session clean。另以显式状态恢复 session，并仅清理 `.cbq/cache/derivation/` 与 `.cbq/cache/render/` 非权威缓存。 |
| `ChemBlender/core/import_pipeline/__init__.py` | 模块级显式 re-export | 导入流水线的纯 Python package 门面；公开 request、preview、staging、preflight、conflict 与 grouping 契约，不加载 Blender 或可选科学栈。 |
| `ChemBlender/core/import_pipeline/conflicts.py` | `ImportConflictCandidate`、`ImportConflict`、`DuplicateAction`、`ConflictDecision`、`detect_import_conflicts()`、`apply_conflict_decisions()` | 只读比较 parse identity、内容 hash 与纯词法 locator，以不可拆分候选快照保留最高优先级的全部匹配；提交决定前根据 live project 和 staging session 重检完整冲突，target action 必须显式选择 revision，并返回新的 preview，不修改 session 或项目。 |
| `ChemBlender/core/import_pipeline/grouping.py` | `GroupingEvidence`、`SourceGroupSuggestion`、`suggest_source_groups()` | 从严格关联的暂存 batch 生成确定性、不可变的跨来源证据与分组建议；依次评估显式 UUID 引用、结构映射、Kabsch RMSD（`<= 0.15 Å`）、metadata 和文件名/目录，周期原胞/惯用胞候选只标记 review conflict，只有用户显式确认才创建 model 层 `CalculationGroup`，不修改 preview、session 或项目。 |
| `ChemBlender/core/import_pipeline/transaction.py` | `GroupingDecision`、`ImportCommitDecisions`、`ImportCommitResult`、`commit_import_preview()` | 根据 live project 与 staging session 重检完整 conflict/grouping 快照，重建发生身份映射的 grouping evidence，将所有保留 batch 合并后在候选 `QCProject` 中一次校验；仅在 sidecar 原子发布和 verified project 移交后替换 live session，纯 Python 层原样返回但不应用或认证默认 view plan UUID（由 Blender caller 校验），并把旧 project 清理失败作为 committed result warning 报告，不创建 Blender datablock。 |
| `ChemBlender/core/import_pipeline/parse.py` | `staged_reader_batch()`、`stage_import_batch()` | 共享构造或复验带 `SourceRecord`、`SourceRevision` 和双向诊断引用的暂存结果；保留旧 reader wrapper，并为公开 Reader API 精确复验插件提供的来源身份；规范参数只包含影响科学解析的输入，不提交项目。 |
| `ChemBlender/core/import_pipeline/preflight.py` | `preflight_import()`、`ImportCancelled` | 对显式文件执行 bounded hash、reader 选择与 availability 检查、可取消解析和稳定失败诊断；只登记到 owned staging session，不写 `QCProject`。 |
| `ChemBlender/core/import_pipeline/request.py` | `ValidationMode`、`ImportSource`、`ReaderOverride`、`ImportRequest` | 定义不可变导入意图；规范化并去重显式文件路径，拒绝目录扫描，并将 reader override 限定到请求内来源。 |
| `ChemBlender/core/import_pipeline/preview.py` | `SourcePreview`、`ImportPreview` | 以不可变路径、标量和 UUID 引用描述 source row、暂存 batch、冲突、归组建议、诊断及默认 view plan，不持有项目或 Blender 对象。 |
| `ChemBlender/core/import_pipeline/report.py` | `import_summary()`、`diagnostics_document()`、`render_diagnostics_markdown()` | 只读验证 preview 与 live staging batch 的身份及关联，按稳定键生成 schema v1 JSON-compatible diagnostic document、质量状态计数和 Markdown；不读取项目、不加载 Blender 或可选科学栈。 |
| `ChemBlender/core/import_pipeline/staging.py` | `StagedImportSession.create()`、`register_result()`、`discard()` | 创建带 UUID ownership marker 的独占暂存根、artifact 目录和受控 `ImportBatch` registry；仅在路径、文件身份及 marker 均匹配时删除。 |
| `ChemBlender/core/readers.py` | `ReaderDescriptor`、`ReaderRuntimeDescriptor`、`ReaderAvailability`、`ReaderRegistry.register()`、`select()`、`parse()` | 定义 reader capability、扩展名、bounded sniffing 和确定性分派；以兼容 wrapper 分离 reader 选择与运行时 availability，拒绝未知或歧义 reader。 |
| `ChemBlender/core/reader_catalog.py` | `builtin_reader_descriptors()`、`builtin_reader_registry()`、`reader_capability_document()` | 汇总内置 reader，并生成机器可读的格式能力矩阵。 |
| `ChemBlender/core/cache_identity.py` | `source_hash_bytes()`、`parser_cache_key()`、`derivation_cache_key()`、`render_cache_key()` | 用规范 JSON 和 SHA-256 分别标识源文件、解析、派生和渲染缓存。 |

### Reader API alpha 门面

`reader_api` 是面向实验性 0.x reader plugin 的公共、纯 Python（`bpy`-free）门面。manifest 是可安装插件的静态声明，runtime descriptor 是已解析 reader 的只读元数据；两者都不持有 parse callable，插件也不能取得或修改 `QCProject`。模块只通过相对导入解析已安装命名空间，不绑定源码包名或 extension repository namespace。可选依赖 availability 探测只使用 `find_spec()`，不导入该依赖。

| 文件 | 主要入口 | 职责 |
| --- | --- | --- |
| `ChemBlender/reader_api/__init__.py` | 模块级 re-export | Reader API 0.x 的严格公共门面；导出版本、manifest/runtime descriptor、exact `SniffMatch`/`SniffResult`、受控科学实体和 `PublicImportBatch`，不导出 `QCProject` 或内部 `ImportBatch`。 |
| `ChemBlender/reader_api/version.py` | `READER_API_VERSION` | 声明当前实验性 Reader API 版本 `0.1`，供 manifest 兼容范围校验。 |
| `ChemBlender/reader_api/manifest.py` | `ExecutionMode`、`ReaderManifestEntry`、`ReaderPluginManifest.from_toml()` | 用标准库 `tomllib` 读取受控 UTF-8 TOML，拒绝未知字段和不兼容 API 范围，并确定性规范化静态 reader 声明；manifest capability list 恒表示 `SUPPORTED`。 |
| `ChemBlender/reader_api/descriptors.py` | `PublicReaderDescriptor`、`_probe_availability()` | 定义不含 callable、模块路径或项目上下文的不可变 runtime 元数据；以相对导入取得现有 `CapabilitySupport`/`ReaderAvailability`，并保留 `SUPPORTED`、`PARTIAL`、`UNSUPPORTED` 三态 capability。 |
| `ChemBlender/reader_api/public_model.py` | `PublicImportBatch` | 以精确受信科学实体类型构成不可变、无复制的导入批次；拒绝子类和未批准数据集，并为 bridge 提供递归嵌套值校验，插件不能经此获得项目。 |
| `ChemBlender/reader_api/builtin_bridge.py` | `public_batch_from_internal()`、`internal_batch_from_public()` | 内置 `ImportBatch` 与公开批次间的薄、无复制转换边界；递归拒绝 callable、mutable container 与未登记嵌套对象，后者再复用临时 `QCProject.commit()` 图校验，并转换为公开验证错误。 |
| `ChemBlender/reader_api/canonical_document.py` | `public_batch_document()`、`public_batch_from_document()`、`write_public_batch_bundle()`、`read_public_batch_bundle()` | 将严格 `PublicImportBatch` 确定性编码为 Reader Import Document v0.1；以 content-addressed、禁 pickle 的 NPY artifacts 承载数组，并在读取边界复验 exact schema/type、相对路径、shape、dtype 与双 hash；写后 hash/临时文件清理失败统一为稳定 integrity error；只构造公开 batch，项目图校验留给 built-in bridge。 |
| `ChemBlender/reader_api/import_pipeline_bridge.py` | `preflight_reader_plugins()` | 把主进程持有的 `ReaderPluginRegistry` 接入既有 `ImportRequest`、`StagedImportSession` 与 `ImportPreview`：复用 bounded hash、sniff prefix、取消和暂存 helper，复验外部 reader 的完整来源身份；确认前不修改 `QCProject`、Scene 或 Blender datablock。 |
| `ChemBlender/reader_api/conformance.py` | `ReaderConformanceCase`、`ReaderConformanceCheck`、`ReaderConformanceResult`、`run_reader_conformance()` | Reader API 0.x alpha 的纯 Python conformance runner；复用 registry、公开 batch graph bridge 与 canonical bundle，对 manifest、双重 sniff/registry 选择、完整 `SourceRevision` 或严格受限内建 provenance identity、单位、diagnostics、round-trip、取消和 reader 异常输出确定性机器可读证据，不创建 registry、项目或 Blender 状态。 |
| `ChemBlender/reader_api/protocol.py` | `SniffRequest`、`ParseRequest`、`ProgressEvent`、`ReaderPlugin` | 定义无项目、无 Blender 上下文的 Reader 插件请求与进度协议；每个插件必须持有与 runtime descriptor 一致的 exact manifest，解析请求只携带已验证来源、规范参数、安全 staging root 及进度/取消回调。 |
| `ChemBlender/reader_api/registry.py` | `ReaderPluginRegistry`、`builtin_reader_plugin_registry()` | 确定性选择公开 Reader 插件，在注册时交叉验证 manifest/runtime metadata，并要求同一 `plugin_id` 使用一份完整 manifest；仅以 exact complete manifest 原子注销同一插件全部 reader；在解析前后分块复验来源 hash，隔离 sniff/parse 异常并保留最近一次 parse 的私有异常类型证据；现有 11 个 descriptor 薄包装为共享受控 manifest 的 `chemblender.builtin` 插件，可选依赖只做 presence probe。 |
| `ChemBlender/reader_api/worker_bridge.py` | `parse_with_worker()`、`WorkerReaderError` | 主进程对固定 `reader.parse@0.1` 的已完成 `WorkerResult` 做 request ID、状态、exact metadata、NTFS-safe 相对路径、无 link/junction 的 exact bundle inventory、来源与全部输出 hash 复验；重开 canonical bundle 并经 `internal_batch_from_public()` 图校验后才返回内部 `ImportBatch`。 |

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
| `ChemBlender/core/sidecar.py` | `LazyNpyArray`、`save_project()`、`open_project()`、`close_project()` | `.cbq` v0.2 存储实现：写 generation metadata 与 canonical manifest hash，原子发布 manifest/数组；读取当前 manifest 时先验证原始 hash/header，以迁移副本严格 decode 并在写入和读取边界复验完整项目图，再向内部 publication 返回未经改写的已验证 metadata。 |
| `ChemBlender/core/sidecar_migrations.py` | `migrate_manifest()` | 在严格模型 decode 前把已校验的 v0.1 文档复制并迁移为 schema `0.2`，并为早期 v0.2 项目补空 diagnostic registry；不改写 fixture 或已发布 sidecar。 |
| `ChemBlender/core/storage/publication.py` | `solidify_session()`、`inspect_publication_orphans()`、`PublishedProject`、`PublicationRecoveryReport`、`PublicationRecoveryError` | 在目标同目录写入并复验完整 `.cbq` generation，经 backup rename 发布或非破坏回滚；默认关闭验证时打开的 project，仅在显式 opt-in 时把 final generation 的 exact verified project ownership 移交给事务；恢复不完整时同时保留原发布错误、回滚错误和不可变路径报告，不删除无法证明归属的目录。 |
| `ChemBlender/core/recipe.py` | `RecipeDefinition`、`plan_recipe()`、`recipe_document()`、`recipe_from_document()`、`builtin_recipes()` | 定义版本化分析 recipe 的输入语义、参数、输出、view、验证和引用；plan 阶段只绑定实体，不执行计算。 |
| `ChemBlender/core/scene_preset.py` | `builtin_scene_presets()`、`plan_scene_preset()`、`validate_scene_plan()`、`scene_preset_for_recipe_view()` | 定义 publication scene preset，验证数据绑定和设置，并生成可重放的 render identity；`grid_volume` 允许显示质量仍为 ambiguous/partial 的 Grid3D，但其它 publication preset 继续要求 Complete dataset。 |
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
| `worker/operation.py` | `OperationContext`、`OperationOutput`、`OperationError` | 定义 operation 的项目/任务目录上下文、待提交 batch/artifact/metadata，以及稳定错误码；无项目的 reader operation 只使用任务目录。 |
| `worker/reader_operation.py` | `register_reader_operation()` | 注册固定 `reader.parse@0.1`：只接受 exact 参数白名单和任务目录内来源 artifact，从内置 Reader registry 解析，写入并重开自有 `reader-bundle` canonical document，再经内部 batch 图校验后发布 hashes；取消或失败时安全清理本次新建 bundle，不写权威项目 sidecar。 |
| `worker/runner.py` | `OperationRegistry`、`run_request()`、`default_registry()`、`main()` | 默认 operation 打开 sidecar、校验输入 revision、原子提交并重开复验；固定 `reader.parse@0.1` 改走不打开 sidecar 的任务目录 artifact 分支，并在 result publication 失败时只清理本次 operation 创建的 bundle；两者均检查取消并在输出验证后写 result。 |
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
