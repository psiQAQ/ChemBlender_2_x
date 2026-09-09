# ChemBlender 代码架构导览

本文面向需要阅读、维护或扩展 ChemBlender 的开发者，说明当前代码分层、主要数据流，以及每个 Python 文件承担的职责和主要入口。下方清单按当前共享核心、外部准备工具与 Viewer 路径记录；路径覆盖不代表迁移后的功能和生命周期已全部验收。已批准的本地编辑／单一本地处理程序边界及移除依赖门槛见[实施方案](../../docs/quantum-visualization/architecture/local-processor.md)和[决策0044](../decisions/0044-cbq-viewer-local-processor-boundary.md)。

## 维护规则

- 新增、删除、移动源码文件，或者改变模块职责、跨层依赖、主要公开入口时，必须在同一提交中更新本文。
- 小型私有 helper、局部变量和不改变调用方式的内部重构无需逐项记录。
- `cbq_core/` 只依赖标准库和 NumPy；`chemblender_prepare/` 可加载外部科学依赖，两者均不依赖 `bpy`。
- Blender datablock 是视图和缓存；`QCProject` 与 `.cbq` sidecar 才是量子化学数据的权威来源。
- `chemblender_prepare/worker/` 在外部包、不进入 Extension ZIP；Extension 只保留共用协议 client，并通过单一可执行文件异步调用固定 operation。

`tests/test_quantum_visualization_docs.py` 会比较本文列出的源码路径与仓库中的 Python 文件。架构文件变化但本文未同步时，文档契约测试会失败。

## 总体分层

```text
原始文件 / 外部程序
  -> chemblender_prepare readers / adapters / worker
  -> cbq_core QCProject + 验证后的 CBQ 1.1 / NPY
  -> ChemBlender CBQ 事务导入
  -> Blender View / Geometry Nodes / 材质 / 动画
  -> 可重建显示缓存（OpenVDB 等）
```


核心调用链：

1. `ReaderRegistry` 通过扩展名和内容 sniffing 选择 reader。
2. reader 返回只含标准语义对象的 `ImportBatch`。
3. `QCProject.commit()` 校验引用后原子接纳 source/revision、结构、计算、数据集和 provenance。
4. `sidecar.py` 将项目元数据写入 CBQ 1.1 manifest，将大型数组写入 `.npy`；v0.1/v0.2 只在内存中迁移后读取。
5. Blender adapter 根据实体 UUID/revision 创建临时 Mesh、Curve、Volume、Material 或 Geometry Nodes。
6. 重计算任务通过 `worker_client.py` 启动独立 Python；worker 只在成功并复验结果后更新 sidecar。

## 共享核心、外部准备与构建入口（迁移中）

| 文件 | 主要入口 | 职责 |
| --- | --- | --- |
| `chemblender_prepare/pubchem_import.py` | stage_pubchem_import()、verified_pubchem_parameters()、attach_verified_pubchem_provenance() | 外部PubChem取数、owned session暂存与URL/hash/provenance复验，复用旧纯数据实现；默认urllib、30秒超时、64MiB响应上限。文件/SMILES请求供外部Python管线使用，不发布Viewer网络入口。is_cancelled在HTTP间和写入/返回前检查；失败仅清理本次创建文件并保留原始异常。实际网络、CLI/GUI和阻塞HTTP两秒取消仍待验证。 |
| `chemblender_prepare/cli.py` | `main()` | 独立 Python 的 capabilities/worker/doctor/formats/inspect/convert/derive/validate/upgrade/export统一入口。reader转换恢复ERROR/INVALID诊断门禁，仅严格孤立SDF坏记录且仍有有效记录可恢复；全失败/完整性错误不发布。复用 Worker 与共享模型，在私有目录完成结果验证后发布新CBQ；MOL/SDF inspect复用preflight与构象分组输出有界记录/属性/诊断/映射依据，标记歧义与截断并默认保持独立，不自动发布构象集；CBQ inspect复用相同有界依据，供derive显式接受稳定身份候选；取消或源hash变化清理暂存；MOL2 inspect 校验源hash并展示有界摘要/诊断；CIF inspect 展示有界多块/位点/晶胞/诊断预览并校验输入hash，转换保留全部有效结构及原block绑定；POSCAR inspect 展示有界源约定预览，convert 拒绝无有效结构或缺元素的POSCAR，多dataset物理量解释要求显式dataset index，单dataset可省略。inline SMILES使用外部preflight暂存/校验链保留文本身份和二维坐标诊断，拒绝文件混输，成功后发布CBQ。PubChem convert --pubchem 复用暂存下载、preflight和来源hash验证，发布前固化数组并将来源locator规范为URL，失败/取消清理下载。 |
| `chemblender_prepare/runtime.py` | `capability_document()`、`doctor_document()`、`run_worker()`、`critic2_command()` | 读取外部版本化绝对路径配置，按固定operation/reader白名单选择current/wavefunction/scientific/fermi环境；phonon固定进入scientific环境，QTAIM/NCI要求实时critic2能力。Windows配置WSL ELF时只构造固定`wsl.exe --cd ... --exec ...`参数，不使用shell。以隔离Python metadata探测生成真实版本能力；Standard 的 NumPy/RDKit/Gemmi 缺失为 doctor failure，未配置provider和专业route明确为 unavailable/warning。routed worker 必须在目标环境安装同版本包，并用目标Python的`-I -m chemblender_prepare.worker.runner`启动，禁止把主环境site-packages或源码根注入目标环境；配置失败发布结构化非成功结果。 |
| `chemblender_prepare/gui.py` | `PrepareWindow`、`CliProcess`、`command_arguments()` | Windows GUI entry point 的 Tkinter 面板生成CLI参数，公开7个数据操作及只读capabilities/doctor共9个入口；convert支持文件、inline SMILES或PubChem CID/名称输入选择，文本模式不传隐藏文件参数并明确二维坐标边界；convert提供与CLI一致的三种validation mode并逐文件传给worker，通过无shell隐藏子进程调用CLI，轮询进度、结果与取消文件；首次取消后两秒未退出仅终止其持有的CLI进程，等待退出再清理，有最终结果优先读取，否则报告强制终止且结果未知；不将该检查视为外部程序树取消验收。日志和临时目录构造使用ExitStack逆序清理；界面初始化成功后才启动进程。进度异常请求取消并保留任务所有权，终态结果收集后独立于界面更新清理；清理失败保留所有权供轮询重试；启动与结果清理中的MemoryError等Fatal异常不被普通错误掩盖，原Fatal异常优先保留；不包含格式算法，不承担Blender异步控制器。；CBQ inspect后专用构象复核窗口展示候选和映射依据，切换候选清除复核，拒绝截断映射，只填入derive参数并清空旧输出，不自动启动计算。；历史SMILES片段选择复用element_data.preset_smiles，仅填可编辑文本，不触发计算，继续走inline SMILES CLI。 |
| `ChemBlender/scripts/stage_viewer.py` | stage_viewer() | 审计 Viewer import，将同源 cbq_core 字节复制到 _cbq_core 并记录 SHA-256；重写 Viewer 的共享核心 import，拒绝共享核心内部的绝对 cbq_core import，排除外部处理源码，只复制 manifest 明确声明的过渡 wheels。 |
| `cbq_core/__init__.py` | package marker | 共享科学模型、存储与显示数学包边界；标准库与 NumPy，不恢复旧科学计算公共门面。 |
| `cbq_core/diagnostics_report.py` | render_diagnostics_markdown() | 校验已持久化的诊断文档并输出 Markdown；Viewer 无需导入 reader 或 parser。 |
| `cbq_core/package_import.py` | preview_package()、import_package()、commit_session_batch() | 整包预览、内容/UUID 冲突和重复来源检查，科学引用验证与数组自有存储；事务接纳 CBQ，拒绝半成品和未确认重复来源；本地编辑共用候选项目校验、发布后切换和旧实体保留事务；导入/Apply统一写会话temporary_root/project.cbq，不提前覆盖已保存sidecar，显式保存仍由session生命周期处理。 |
| `cbq_core/storage/text.py` | atomic_write_chunks()、ExportReport | 共享原子 UTF-8 文本写入、取消和导出报告类型；可供外部科学导出及本地切片/剖面数值输出复用。 |
| `chemblender_prepare/__init__.py` | package marker | 外部科学准备包入口，不导入 Blender。 |
| `chemblender_prepare/__main__.py` | main() | python -m chemblender_prepare 委托同一 CLI，并传播退出码。 |
| `chemblender_prepare/core/__init__.py` | package marker | 外部 parser、科学派生、编辑和导出模块边界；实体定义仍来自共享核心。 |
| `chemblender_prepare/core/grid_lod.py` | derive_grid_lod() | 产生带 derivation identity 的科学 LOD 网格；显示缓存数学继续由共享核心提供。 |
| `chemblender_prepare/core/grid_semantics.py` | resolve_grid_semantics() | 按显式 dataset、preset 和单位生成科学解释结果，保留源网格与 provenance；不由 Viewer 猜测场语义。 |
| `chemblender_prepare/core/orbital_browser.py` | suggest_grid()、estimate_grid_memory() | 外部计算前的科学网格建议与求值内存估算；轨道列表投影在共享核心。 |
| `chemblender_prepare/core/package_upgrade.py` | upgrade_project() | 外部生成 CBQ 1.1 所需数值对称操作，校验科学图并保持身份/来源约束；CLI 先验证旧包再发布新目录，不覆盖旧包。 |
| `chemblender_prepare/topology_service.py` | load_topology_batch()、commit_topology_batch() | 读取 critic2 CPREPORT/FLUXPRINT，绑定已有 Structure，复验输入/结构 hash 和取消状态后提交；不虚构缺失路径。 |
| `chemblender_prepare/worker/conformer_operation.py` | `accept_group()` | 将已有构象分组适配到 molecule.group_conformers@1；以持久化CBQ候选/快照及完整记录输入复核，复用科学算法，返回新增ConformerSet/属性列/provenance；不覆盖原实体。 |
| `chemblender_prepare/worker/grid_operations.py` | register_grid_operations() | 将已有网格差分及语义解释注册为固定 Worker operation，复用 ImportBatch 与当前协议。 |

## Extension 入口与基础数据

| 文件 | 主要入口 | 职责 |
| --- | --- | --- |
| `ChemBlender/__init__.py` | `register()`、`unregister()` | Extension 最小入口；只延迟委托给 `runtime.registration`，不保存 Blender class、callback 或 Reader API handle 状态。 |
| `ChemBlender/auto_load.py` | `get_ordered_classes_to_register()`、`toposort()`、`_safe_register_class()`、`_safe_unregister_class()` | 只分析显式模块中的 Blender class 依赖、执行拓扑排序并提供安全 class 注册/注销；不扫描 package、不清 import cache，也不是第二条生产注册路径。 |
| `ChemBlender/runtime/__init__.py` | package marker | 隔离依赖 Blender host 状态的 runtime bridge；导入该 package 本身不加载注册实现或触发注册副作用。 |
| `ChemBlender/runtime/registration.py` | `REGISTER_MODULE_NAMES`、`register_extension()`、`unregister_extension()` | Viewer 注册唯一 owner：显式加载显示/编辑/CBQ UI 模块，去重拓扑注册 class 后执行 callback；只反向清理本次拥有的状态，失败保留原异常和清理 notes，残留状态可重试卸载。不会发布 Reader API handle、读取原始格式或加载外部处理器。 |
| `ChemBlender/ui/cbq_import.py` | `import_reviewed_package()`、`export_package()`、`CHEMBLENDER_OT_restore_legacy_views`、`register()` | 整包预览、校验与事务追加，数组固化到当前项目，独立 CBQ 导出；提供显式 Legacy Migration Report 路径和当前 Viewer 恢复按钮。Scene 属性按 RNA 身份跟踪，拒绝占用、身份验证失败回滚，仅卸载自有属性。 |
| `ChemBlender/legacy_restore.py` | `legacy_restore_plan()`、`restore_legacy_views()` | 校验外部 legacy `migration.json` 与相邻 `project.cbq` 的格式、原始 manifest 哈希、project identity 和完整已导入内容；只对白名单 scaffold/crystal 显示字段重建当前 Structure View，旧节点输入仅保存审计。同步事务失败时清理本次 View、材质及 fresh packaged node assets并恢复 active state，不修改科学项目、旧对象或已有 View。 |
| `ChemBlender/ui/mesh_edit.py` | `structure_edit_arguments()`、`measure_points()`、`CHEMBLENDER_OT_mesh_edit`、`CHEMBLENDER_OT_apply_mesh_edits`、`CHEMBLENDER_PT_mesh_edit` | 恢复原scientific_edit中的本地Mesh输入提取，检查源revision、拓扑绑定、对象模式及显示单位，保留atom mapping与键级；纯 Mesh 元素选择、原子/键属性和二点距离/三点角度；测量使用对象局部科学显示坐标，忽略展示变换，不释放 Blender 持有的 BMesh。修改只标记草稿，权威 Structure/Topology 不变；显式 Apply 追加新 Structure/Topology 与可重建 View，保留旧实体/对象。对象模式下复用统一processor面板；未Apply草稿禁用分子重算，处理程序缺失不影响本地编辑。 |
| `ChemBlender/ui/processor.py` | `CHEMBLENDER_Preferences`、`CHEMBLENDER_OT_test_processor`、`ProcessorTask`、`start_capability_test()`、`start_worker()` | 全局仅保存一个绝对处理程序路径；用无 shell 子进程和 Worker Protocol v1 启动能力检查或任务，轮询有界进度，先写 cancel marker、两秒后只终止本任务进程树。严格校验任务目录、请求身份、结果状态和退出码，失败、取消及卸载不提交项目状态；能力缓存仅驻留当前模块。 |
| `ChemBlender/ui/processor_operations.py` | `start_reader_operation()`、`start_fermi_operation()`、`start_wavefunction_operation()`、`start_molecule_operation()`、`start_professional_operation()`、`publish_operation()`、`CHEMBLENDER_OT_processor_operation` | 将 reader、Fermi、wavefunction、molecule 及QTAIM/NCI/phonon请求统一冻结到私有任务目录并交给同一 Worker v1 控制器；主线程只做有界轮询。发布前复验源文件/hash、输入revision、输出inventory、语义、affine、数组和来源；专业结果只归一化当前请求的artifact provenance，避免改写历史结果。成功事务追加新UUID、自动选择并创建Topology/Grid/Phonon View；取消、过期、篡改和失败不改项目。 |
| `ChemBlender/ui/__init__.py` | package marker | 声明 Blender UI package；不导入 Blender、注册 root 或科学模型。 |
| `ChemBlender/ui/tasks.py` | `Task`、`TaskProgressAdapter`、`TaskWorker` | 不导入 `bpy` 的线程安全任务状态边界：严格表示 pending/running/cancelling/cancelled/failed/succeeded、单调阶段进度与失败；把嵌套的 reader/worker event 映射为单调 UI 进度，并只把纯 callback 放入 daemon worker。Blender timer/操作符在主线程读取不可变 snapshot、请求取消并决定何时写 RNA 或 datablock。 |
| `ChemBlender/ui/session.py` | `get_scene_session()`、`new_scene_session()`、`close_scene_session()`、`register_session_cleanup()`、`register_session_mutation()`、`register()`、`unregister()` | 注册时安排一次性 timer，在 Blender 解除注册阶段数据限制后恢复当前已保存文件的链接；重复注册保留已有 dirty session，unregister 取消待执行 timer。用一个显式 owned entry 管理当前已加载 `.blend` 的共享 `ProjectSession`，所有 Scene 经兼容入口 `get_scene_session(scene)` 取得同一科学项目与临时根；Scene 只保留状态/显示投影，不拥有独立项目。load/unregister 只 drain 一次共享 entry，失败保留 recovery entry 供重试；会话替换或关闭前调用全部已注册 UI cleanup，并在失败时保留可重试所有权。`load_post` 对无 link、相同 link、一个有效 link 加空 Scene 和冲突有效 link 分别执行空会话、一次采纳、统一投影和 fail-closed；`save_pre` 使用 Blender 回调传入的目标路径（而非 Save As 尚未更新的 `bpy.data.filepath`），首次保存和跨目录另存一次发布正确配对；直接 retry 调用的 None 才读取当前路径。`save_pre` 对 scientific/unknown dirty reason、无 sidecar 或 Save As 执行完整 publication，对 clean connected、新空 Scene、`project_link` 或 `view_cache` retry 先只读复验现有 sidecar 再同步 Scene link，成功连接后才调用 derived View cache repair，绝不为纯 cache retry 重新 publication。跨目录或重命名 Save As 在 publication 前仅捕获 connected 的 previous sidecar，并作为一次性 fallback context 传入 cache repair。新建/替换以及成功采用 sidecar 后通知小型 UI projection invalidator，失败或无效恢复不通知；脏会话关闭时只写一个非权威 recovery marker 并保留临时根，干净会话关闭时释放 lazy resource 与受控临时根。 |
| `ChemBlender/ui/view_cache.py` | `repair_project_view_caches()`、`scene_plan_from_view()`、`rebuild_scene_view()`、`plan_property_view_rebuild()` | 统一校验当前或显式重建的旧版 scene preset，创建新实例成功后替换旧对象，保留位姿、无关用户子对象；逐对象记录 stale/diagnostic/report eligibility 后继续其他缓存修复；旧 property v1 的 bindings/settings/render identity 验证通过后才显式规划当前版本。对 slice/profile/colorbar 仅校验 root 的科学绑定和保存参数，不依赖外部显示文件；扫描带完整 scene preset binding/settings/render identity 的 ChemBlender-owned Volume，从 verified `session.sidecar_path` 推导 `<sidecar>/cache/render/` 目标并 fail-closed 校验 UUID/revision/cache identity；在任何 writer/read 前拒绝最终 VDB link/junction，缺失或损坏 VDB 调用既有 adapter 重建，打开/普通修复成功后写相对 `.blend` RNA 路径；save_pre 使用 absolute RNA，避免原生 Save As 再次 relative_remap，重开后从 verified 相邻 sidecar 恢复相对路径。当前项目的失败事务保留 `view_cache` retry；具有明确其他项目 UUID 且绑定无交集的 View 保留诊断而不置当前项目 dirty，旧 View 仅在完整校验通过后补项目归属；只在旧路径位于 owned session `view-cache/` 或 verified sidecar `cache/render/` 且 VDB identity 匹配时重新加载，绝不访问任意 `cb_cache_path`、UNC 或外部旧路径。Save As 新 cache promotion 失败时，以一次性 previous sidecar context 和当前 verified render identity 推导、只读验证旧 durable VDB，再相对新 `.blend` 重投影其 filepath；不解释旧 `//...`，也不向旧 sidecar 写入或重建 cache。 |
| `ChemBlender/ui/properties.py` | ProjectUIState、get_project_ui_state()、advance_browser_revision() | Project Browser 的 session-owned 小型状态、晶体声明/比较摘要、约束显隐及标准结构 View 入口。管理 Scene 属性和 load handler 的精确所有权；不保存旧 raw import job，不执行 spglib 计算。 |
| `ChemBlender/ui/default_views.py` | `DefaultViewPlan`、`plan_default_view()`、`default_grid_preset()`、`describe_default_view()` | 纯 UI planner；default_grid_preset按共享grid_semantics默认表示及COMPLETE状态选择，供scientific_view的AUTO复用，普通scalar仍volume。只按一个 SourceRevision 已创建的 entity UUID、Grid3D 状态与 semantic role 选择 `structure_publication`、`grid_volume` 或 `signed_isosurface`，不导入 `bpy`，也不把 view plan 写入科学模型或 sidecar schema。 |
| `ChemBlender/ui/diagnostics.py` | `QualityPresentation`、`RevisionViewPrompt`、`quality_presentation()`、`diagnostic_detail_rows()`、`canonical_report_text()`、`project_recovery_actions()`、`detach_project_links_for_scenes()` | `bpy`-free 的共享 UX 契约：五态质量恒有文字与不同 icon，颜色只作补充；diagnostic detail 和 Copy/Export 直接复用 import report schema/Markdown validator，不定义第二套报告；revision prompt 仅持有 current/new revision UUID 并默认 Keep Current，执行操作时从 live preset bindings 唯一且 fail-closed 推导 replacement；link recovery action 由 live status 限定，多 Scene Detach 仅原子删除四个 link 字段并在失败时全量回滚，绝不删除 Blender object。 |
| `chemblender_prepare/extxyz_preview.py` | `ExtXYZPreviewSummary`、`extxyz_preview_summary()` | 不依赖 Blender 的 extXYZ Import Preview 摘要边界；只读取 entity 类型、shape、semantic role、cell/PBC 和 diagnostics，不读取科学 array values，由外部inspect与benchmark共享；CLI复用staging预览并在成功/失败后清理，不加载全科学数组。 |
| `ChemBlender/ui/project_browser/__init__.py` | `BrowserMode`、`BrowserRow`、`ViewRecord`、`build_browser_rows()`、`clear_browser_session_cache()`、`clear_browser_caches()` | 公开纯 Python Project Browser 投影与 cache 生命周期入口；不导入 `bpy`，不触碰 scientific array payload。 |
| `ChemBlender/ui/project_browser/model.py` | `BrowserMode`、`BrowserRow`、`ViewRecord`、`build_browser_rows()`、`clear_browser_session_cache()`、`clear_browser_caches()` | 从 `QCProject` registry 与独立 presentation `ViewRecord` 生成 By Source/By Data 确定性 flat tree；By Data 将 frame/atom/cell properties 归入其 `FrameSet`，将匹配 record inventory 的 typed columns 归入 `ConformerSet`，独立显示 raw `MolecularRecord`，并以唯一 Biological Hierarchies group 展开 chain/residue/atom count 小型摘要；chain/residue detail row 携带所属 BiologicalHierarchy UUID，可继续作为真实科学选择。周期 Structure 增加只读 site count、occupancy/disorder 与 Uiso/Uij availability 子行，但不读取 scientific array payload。TopologyRecord 行显示 source、quality、bond count、inference parameters 与 view count。ViewRecord 显式携带 derived view quality 与 report eligibility，ambiguous Surface 不进入报告。By Source 将没有 SourceRevision 的迁移/派生实体列于 `Unattributed project data`，已归属实体不重复；row ID 包含完整 parent path并在同一 parent 内确定性去重，空项目也返回显式 empty row；view 只有在 entity UUID 与 revision 同时匹配时关联，投影后的 BrowserRow 以兼容默认字段保留 `view_kind`，让小项目搜索保留与 large generator 相同的 view-kind 语义。小项目保留完整 tuple API；当总可索引条目超过 page size 或估算 row 开销超过 1000 时，使用 `page`/`page_size` 有界投影；无 molecular records 的大项目也生成 generic result page，未被 entity/diagnostic 覆盖的 standalone source 与 empty revision branch 作为轻量 sentinel 进入同一 By Source 索引和 pager，mixed project 的默认页以精确 summary 暴露并可搜索到它们。搜索与 filter 单遍扫描预排序的 By Source/By Data 轻量索引，只保留当前页；ViewRecord label/kind/quality 在本次 generator 消费时动态匹配，view-only 命中只显示匹配 view，entity 命中才显示全部 sibling views。row cache 由 browser revision 失效；最多两个索引由 project/session、运行时 project identity 与 registry/source/revision/diagnostic 数量的结构签名失效，纯 browser revision 变化复用索引。两类持久 cache 都只在 non-empty session ID 与精确非负 browser revision 同时可靠时启用，可按 session 或整体释放，且不持有 project、scientific entity 或 lazy array。 |
| `ChemBlender/ui/project_browser/panel.py` | `CHEMBLENDER_UL_project_rows`、`CHEMBLENDER_PT_project_browser`、`CHEMBLENDER_OT_project_browser_page`、`CHEMBLENDER_OT_diagnostic_page`、`CHEMBLENDER_OT_copy_diagnostics`、`CHEMBLENDER_OT_export_diagnostics`、`CHEMBLENDER_OT_revision_view_action`、`CHEMBLENDER_OT_project_link_recovery`、`presentation_view_records()`、`refresh_project_browser()` | 在 Blender 主线程严格解析 object 的 scene-preset binding 与 selected topology UUID/revision metadata，投影为 presentation-only `ViewRecord`；draw 只请求合并刷新，由主线程一次性 timer 在可写上下文将 model 返回的最多 1000 行有界页复制到小字符串、整数与枚举 RNA，输入未变化时不重复调度，文件切换或卸载取消待执行 timer；record/result page 共用 total/page/page-count metadata、Prev/Next/Jump 与通用 entry label，不静默截断 model rows。面板复用共享五态 badge，分页显示有界 draw-time diagnostic preview；Copy/Export 以同目录短 temp 原子导出或复制完整 canonical Markdown/JSON。revision flow 明示 current/new UUID；Keep Current 不改 View，Comparison 新建并保留旧 View，Update Selected Views 仅在新 View 成功后隐藏旧 View，任一失败回滚新对象和 visibility。link recovery 在 execute 时复验 live status；Relink 的文件选择器提示选择 .cbq/manifest.json，同时保留 filepath 直接传目录；Relink/Verify 成功后记录当前 service status 并推进 Browser projection。Relink/Verify 委托现有多 Scene service，Inspect Existing 仅进入“不采用/不写候选”的 inspection 状态且不声称全局写保护，Detach 只清 link metadata 并保留对象。注册时将 per-session cache clear 接入既有 session cleanup；卸载可先清空 Browser cache，但只在所有 owned RNA property 成功 teardown 后解除 callback，partial teardown 失败保留 callback，register retry 会重建缺失 property 并确认 callback。UIList 只允许当前 project scientific registry 中的 UUID 更新 `ProjectSession.active_entity_id`，过滤隐藏的有效选择继续保留，stale/malformed/group/view/empty 选择清空。面板为选中的周期 Structure 分区显示 source-declared 与独立 spglib-derived symmetry，以当前 frame 的 force vector 调用既有 dataset vector-view writer；MOL2 substructure action 直接复用 `CategoricalData` code、既有 atom scalar coloring 与 `cbq_selected` attribute，不把分类数组复制进 RNA；biological controls 复用独立 UI root，以小型 RNA 输入驱动 hierarchy selection、altloc filter、property threshold 与 MODEL playback。Structure、FrameSet、ConformerSet 与 MolecularRecord 选择调用显式 export root；以私有 module alias 复用 diagnostics、topology、biological、scientific-edit 与 grid controls，且精确拥有 `Scene.chemblender_project_browser` 与 `Scene.chemblender_topology`，不覆盖或删除 foreign property。 |
| `ChemBlender/ui/grid.py` | grid_preview_summary()、grid_action_availability()、plan_grid_view()、rebuild_property_view() | 已准备网格的有界摘要、dataset 选择、Volume/正负表面/属性着色与切片剖面。显示缓存使用可取消 TaskWorker，Blender datablock 仅在主线程创建；显式重建保留变换并失败回滚。科学语义解释已移外部，不再提供 resolve_grid_selection 或本地科学派生入口。 |
| `ChemBlender/ui/wavefunction.py` | `select_wavefunction_source()`、`prepare_wavefunction_request()` | 保留已准备 Orbital Set 的选择、spin/frontier 列表、缓存网格绑定及轨道图像导出；以显式 origin/step/count、spin/orbital、density level 和有效核电荷参数接入统一处理器，提供 MO、occupation density、RDM density、matrix ESP 与 orbital-derived ESP 五项按钮。显式源 UUID 失效时返回不可用并提供重新选择，不静默切换到第一套轨道；DensityMatrix 分支只显示适用计算。 |
| `ChemBlender/ui/orbital_export.py` | `iter_orbital_images()`、`export_orbital_images()`、`CHEMBLENDER_OT_export_orbitals` | 按显式轨道列表串行复用科学网格或 WavefunctionJob，通过共享 RenderScope 以统一相机及 signed-surface preset 输出 PNG；全部图片、显示参数与分析报告成功后才发布新目录，取消和失败清理自有资源并恢复场景状态；共用继承用户输出目录权限的暂存目录，避免 Windows Python 3.13 私有临时目录 ACL 随最终文件发布。 |
| `ChemBlender/ui/scientific_view.py` | `draw_scientific_controls()`、`CHEMBLENDER_OT_scientific_view`、`CHEMBLENDER_OT_derive_scientific_spectrum`、`CHEMBLENDER_OT_derive_density_difference` | 从 Browser 实体选择物理量表示、数据绑定、材质模板和参数；Grid AUTO复用default_views语义默认值，显式选择保留，RDG仍用NCI；Create/Load/Update/Rebuild 统一使用版本化 preset 与事务。光谱和密度差委托 pure core，成功后一次提交 ImportBatch。相位和源帧变更通过 Blender timer 合并为 100 ms 尾随本地预览，不启动外部任务；时间轴按保存的 View 相位与周期驱动分子/声子显示，不修改科学数组。 |
| `ChemBlender/ui/scientific_export.py` | `iter_scientific_images()`、`export_scientific_images()`、`CHEMBLENDER_OT_export_scientific` | 将选定 View 用 Research/Teaching 模板经 Cycles 输出 PNG 或相位序列，使用 Blender 原生 FFmpeg 编码 MP4；复用导出任务与分析报告边界，全部输出成功且恢复场景后原子发布。 |
| `chemblender_prepare/export_service.py` | `ExportSelection`、`resolve_export_selection()`、`preview_export_selection()`、`export_selection()` | 外部科学格式导出的实体选择、精确属性/拓扑/生物层级投影与损失预览。直接使用科学Structure/FrameSet/MolecularRecord/ConformerSet，不读取Blender evaluated geometry；保留周期导出设置和原子writer取消。Conformer预览只读metadata；原Blender ExportJob/modal/RNA不属于此模块，异步执行由CLI/GUI负责。底层report.written=False表示未写入，CLI将未确认损失作为失败返回，预览仍可成功。 |
| `ChemBlender/ui/topology.py` | topology_choices()、suggested_topology_id()、record_topology_decision() | 已有 TopologyRecord 的选择及 Accept/Reject 显示决策；切换 View 不改源结构。距离推断已在外部转换器执行，不再创建本地 TopologyInferenceJob。 |
| `ChemBlender/ui/biological.py` | `biological_selection_indices()`、`resolve_biological_context()`、`require_live_biological_view()`、`plan_biological_view()`、`altloc_filter_mask()`、`CHEMBLENDER_OT_create_biological_view`、`CHEMBLENDER_OT_select_biological_atoms`、`CHEMBLENDER_OT_play_biological_models` | 从 Project Browser 真实选中 entity 解析同 revision Structure、BiologicalHierarchy、AtomicProperty、FrameSet 与可选 TopologyRecord；每次操作前以共享 snapshot guard 校验 view identity、hierarchy revision、category hash、dataset binding 及实际 POINT attribute 的 type/count/value，foreign/stale/remapped view fail-closed。Chain/residue/atom/altloc/property threshold 仅写 view-owned `cbq_selected`/`cbq_visible`；altloc 同时更新 visibility、filter 与 selection，任一步失败即回滚原快照；default altloc 选择 blank 或最大有效 occupancy，MODEL 复用既有 trajectory manager。默认显示按 topology 与 atom count 选择 atom points 或 ball-and-stick，不实现 ribbon/cartoon、secondary structure 或 biological assembly。 |
| `ChemBlender/ui/file_handlers.py` | `CHEMBLENDER_FH_view_3d_window`、`CHEMBLENDER_FH_project_browser` | 3D View WINDOW与UI区域的CBQ拖放入口，仅声明.cbq并委托chemblender.import_cbq执行预览确认；poll_drop仅检查area/region。无Reader注册表或科学依赖导入；缺少FileHandler API时无注册，失败逆序清理且保留可重试残留所有权。 |
| `ChemBlender/ui/workspace.py` | `CHEMBLENDER_OT_open_workspace`、`workspace_is_compatible()` | 从 Extension 包内安全追加或复用唯一 `ChemBlender` WorkSpace；切换前验证 3D View、浏览侧栏、Properties 和底部编辑区布局，失败时只回滚本次追加的 datablock，不影响 Quick Import、Project Browser 或科学项目状态。 |
| `cbq_core/element_data.py` | `ELEMENTS_DEFAULT` | 保存元素序数、名称、颜色及共价/原子/范德华/离子半径等静态数据。该文件没有行为函数。 |
| `ChemBlender/extension.py` | `cat_generator()`、`NODE_MT_chem_GN_menu`、`NODE_OT_group_add`、`register()`、`unregister()` | 从节点库生成 Geometry Nodes 菜单，将节点组插入当前树，并管理菜单回调。 |
| `chemblender_prepare/legacy/__init__.py` | `detect_legacy_scene()`、`extract_legacy_objects()`、`plan_legacy_migration()`、`commit_legacy_migration()`、`LegacyMigrationPlan` | 旧场景迁移 bridge 的公开、Blender-neutral 门面；不注册 UI，导入时不加载 `bpy`。 |
| `chemblender_prepare/legacy/detection.py` | `detect_legacy_scene()`、`LegacySceneDetection` | 延迟访问 `bpy`，仅从旧 scaffold/cell 标识生成冻结检测结果；不创建、删除或重命名 datablock。 |
| `chemblender_prepare/legacy/extraction.py` | `extract_legacy_objects()`、`LegacyExtractionReport` | 将旧 Mesh、covalent/van der Waals radii、属性、CIF PropertyGroup、collection、材质显示参数和可安全规范化的 Geometry Nodes modifier 输入复制为冻结 primitive 快照；仅已保存的常规非链接 `.blend` 以 `source_verified` 和 extraction-time SHA-256 标记为可哈希来源。科学坐标始终由原始 base mesh 顶点经 `matrix_world` 转为世界坐标，绝不取 modifier evaluated geometry；modifier、实际 world matrix 的非均匀/剪切变换、未知属性、unsupported node input 和缺失 `.blend` 来源均成为诊断。 |
| `chemblender_prepare/legacy/migration.py` | `plan_legacy_migration()`、`commit_legacy_migration()`、`LegacyMigrationPlan`、`ViewSettings`、`ViewPlan` | 将冻结 legacy snapshot 暂存为既有 `QCProject` 的 Structure/TopologyRecord/PeriodicSiteData/ProvenanceRecord，并以拥有 staged project、views、report 与 base/candidate inventory 的冻结 plan 传递；边界验证展示字段、结果 atom 数与规范拓扑顺序。commit 先验证 exact base project identity 与含 registry object identity、persisted content fingerprint 的 inventory，publication 成功后才采用经验证 reopened project，不访问 `bpy` 或旧 Blender 对象。 |

`ChemBlender/ui/project_browser/panel.py` 还公开 `CHEMBLENDER_OT_configure_trajectory_playback`：仅当 Project Browser 选中 `FrameSet` 且 active object 是当前 revision 的匹配 Structure View 时，才复用 `trajectory_view` 绑定时间轴；它不修改 source revision 或科学数组。

## 本地分子与晶体显示基础

Geometry Nodes 留在 Blender。纯 Mesh 编辑和快照提取在 ui/mesh_edit；旧混合 parser/RDKit/界面的入口已拆除。分子优化、加氢和导出的异步替代闭环尚未完成，不能据此移除正式 RDKit wheel；Apply 面板也仍待接通。

| 文件 | 主要入口 | 职责 |
| --- | --- | --- |
| `ChemBlender/node.py` | `add_geometry_nodetree()`、`append()`、`Ball_Stick_nodetree()`、`ensure_structure_ball_stick_modifier()`、`ensure_periodic_cell_modifier()`、`ensure_periodic_adp_modifier()`、`Supercell()`、`CoordPolyhedra()`、`crys_filter()` | 创建或加载 Geometry Node Group，连接球棍、超胞、晶胞边、配位多面体和晶体过滤节点；统一 Structure view 通过 data API 建立带显式 contract/version 的球棍、完整晶格矩阵 cell-edge 与热椭球 modifier，拒绝同名不兼容节点，避免依赖活动对象 operator context；legacy 超胞桥保持原节点输入并写入独立 contract。；生物 Atoms/points fallback 使用 owned `biological_points_v1` 低细分原子标记，读取 vdw_radius 与 cbq_visible，不生成推断键。 |

## Blender 量子数据映射层

这些模块把 `cbq_core` 语义对象映射为 Blender 视图。它们可以写数据集 UUID、revision 和显示参数，但不成为权威数据存储。

| 文件 | 主要入口 | 职责 |
| --- | --- | --- |
| `ChemBlender/dataset_view.py` | `create_structure_view()` compatibility wrapper、`apply_atomic_scalar()`、`apply_atomic_vector()`、`apply_atom_selection()`、`link_stick_spectrum_selection()` | 保留旧结构入口的开发期 DeprecationWarning；把原子标量、矢量和选择写成 named attributes，确保 vector modifier 位于默认球棍 modifier 前，并记录光谱样点到源数据集的联动身份。标量与 categorical 更新同时同步已存在的 scientific shader 颜色属性；categorical presentation-only 模式清除旧 scalar identity/attributes，不把分类数据伪装成 numeric scientific binding。力箭头实例绕过旧球棍原子处理，保留可渲染几何，并在应用时修复已保存的受控节点组。 |
| `ChemBlender/views/__init__.py` | `StructureViewSettings`、`PeriodicViewSettings`、`create_structure_view()`、`create_periodic_structure_view()`、`update_structure_view_topology()`、`remove_structure_view()` | 作为统一 Blender view package 门面，公开 Structure/periodic Structure view 构建、只切换 topology 的原位更新与成组清理。 |
| `ChemBlender/views/periodic.py` | `PeriodicViewSettings`、`create_periodic_structure_view()` | 在统一 Structure view 上投影 occupancy、site/disorder、Uiso/Uij、Selective Dynamics 和显示设置；以完整 row-vector cell matrix 建立 cell/supercell derived display，以 occupancy/ADP validity、quality badge、概率缩放与主轴驱动版本化 Geometry Nodes；字符串位点字段写稳定 categorical codes/mapping，源 Mesh 不复制科学 atom。 |
| `ChemBlender/views/structure.py` | `BIOLOGICAL_NUMERIC_ROLE_SPECS`、`StructureViewSettings`、`biological_point_data()`、`default_altloc_mask()`、`create_structure_view()`、`update_structure_view_topology()`、`remove_structure_view()` | 从 Structure、显式 selected TopologyRecord、可选 Selective Dynamics AtomicProperty 与匹配 BiologicalHierarchy 建立单一 canonical-atom Mesh，写入新旧 atom/bond attributes、`cbq_selective_x/y/z`、biological categorical codes/validity/numeric properties/category hashes/dataset bindings、科学 identity 和默认球棍节点；单一只读 numeric role spec 约束 role、Mesh attribute、unit 与 missing policy，投影只接受 atom-aligned real numeric ArrayData，NaN 只允许 Partial 并以有限 placeholder 加 validity mask 表示。默认 altloc 只形成 view-owned selection/visibility mask。受约束 atom 另建可切换的 derived marker Mesh/Geometry Nodes。切换 topology 时保留 canonical vertices/point attributes，只替换 edges、periodic display 与 topology render identity；所有 derived display 均不写回科学实体。；无球棍的 biological View 挂载低细分点显示 modifier，删除 View 时同步清理 owned 节点组。 |
| `ChemBlender/grid_volume.py` | `volume_cache_path()`、`ensure_grid_volume_cache()`、`create_grid_volume()` | OpenVDB/Blender adapter：向 pure cache transaction 提供 FloatGrid writer/validator；cache-only helper 为创建与 reopen repair 共用，创建函数仅在 cache preparation 成功后于主线程生成带 UUID/revision/affine/render identity metadata 的 Blender Volume。 |
| `ChemBlender/surface_view.py` | `surface_cache_path()`、`ensure_signed_surface_cache()`、`ensure_property_surface_cache()`、`create_signed_isosurfaces()`、`create_property_surface()`、`remove_surface_object()` | 共用 cache-only helper 在任何 VDB read/write 前拒绝最终文件 link/junction，写入并验证 signed/property VDB，再用 Volume→Mesh Geometry Nodes 创建独立正/负相位面，或以 `density` Named Grid 经 Grid to Mesh 单独生成几何，再采样 `property` 写入 `cbq_surface_property`（`property_surface_v2`）；色图以实际零值定位中性色并与切片/色标共享；property surface 复用 core affine guard，object 保存 surface/property 两侧 UUID、revision、dataset index、role、unit、isovalue、colormap/range 与 render identity。 |
| `ChemBlender/grid_sample_view.py` | `create_grid_sample_view()`、`remove_grid_sample_view()` | 将科学平面采样显示为带值和有效性属性的 Mesh、剖面显示为断线 Curve；创建原生网格与文字色标，切片及色标共享无光照影响的 emission 色图。坐标转为显示用 angstrom，采样参数仍在原 Grid 坐标系；按 root/component 管理自有对象和材质。 |
| `ChemBlender/vibration_view.py` | `create_vibration_view()`、`apply_vibration_phase()` | 将一个振动模态写入位移属性和实例化箭头节点，并按相位更新原子位置。 |
| `ChemBlender/trajectory_view.py` | `configure_trajectory_view()`、`clear_trajectory_view()`、`register()`、`unregister()` | 绑定 `TrajectoryFrameManager` 与 Blender frame handler，更新当前帧 Mesh 坐标和已选 AtomFrameProperty 力矢量；缺失力帧隐藏箭头并记录公开状态，恢复有效帧后显示。管理 View 绑定生命周期；持久 load_pre 回调在文件切换前关闭旧帧管理器并清空绑定。 |
| `ChemBlender/spectrum_plot.py` | `create_spectrum_plot()` | 把 `Spectrum` 的横纵数据建立为 Blender Curve，并保存单位、类型和来源身份。 固定 8×5 显示图框、科学数值刻度与可逆轴范围元数据，避免光谱被量纲跨度压扁。 |
| `ChemBlender/electronic_plot.py` | `create_band_structure_plot()`、`create_dos_plot()`、`select_band_sample()`、`select_dos_sample()` | 创建 band/DOS Curve，处理费米能参考和 β-spin 镜像，并记录被选 k-point/band/energy 样点。 复用固定图框并保留 Band/DOS 的实际轴单位；可选能量范围用于 linked 共轴显示。 |
| `ChemBlender/fermi_surface_view.py` | `create_fermi_surface_view()`、`select_fermi_face()` | 将中立 `FermiSurfaceMesh` 转为三角 Mesh，把 band、投影、速度或自旋写入顶点/面属性并支持面到 band 的选择。 |
| `ChemBlender/topology_view.py` | `create_topology_view()` | 将 `TopologyGraph` 临界点映射为点 Mesh，将有采样坐标的路径映射为 Curve。 |
| `ChemBlender/scene_preset_view.py` | `apply_scene_preset()`、`scene_view_objects()`、`apply_scientific_phase()`、`apply_scientific_frame()` | 实例 UUID 区分相同科学绑定的独立 View，项目 UUID 记录其科学项目归属，统一拥有组件与材质；支持原子标量/矢量、声子、PDOS、Fermi、QTAIM 及原有场景 adapter；linked 图表按求值几何并排放置，Band/DOS 使用共同能量范围；复验 `ScenePresetPlan` 后分派统一结构、Grid3D Volume、振动、光谱、band/DOS、表面以及 grid_slice/grid_profile/grid_colorbar adapter；Structure publication 自动绑定同一 Structure 的 Selective Dynamics dataset；若该 Structure 唯一匹配 BiologicalHierarchy，则同时绑定 numeric AtomicProperty、显式 accepted 或唯一未拒绝 TopologyRecord，并复用 biological size planner 创建默认 biological view；无 hierarchy 时保持原路径，current Structure 的 stale topology decision fail-closed。任一 adapter 失败时连同 Structure view 的 derived display object/node group 删除本次创建的全部对象。 |
| `ChemBlender/scientific_materials.py` | `flat_material()`、`matte_material()`、`scalar_material()`、`volume_material()`、`apply_structure_materials()` | 构造原生定量 Emission、matte 表面和正负分离体积材质；每 View 的球棍或生物点显示材质和顶层 Geometry Nodes 使用独立副本，避免旧资产覆写颜色或模板互相影响。色图、透明度和光学密度只属于显示。 |
| `ChemBlender/render_scene.py` | `RenderScope` | 轨道批量和通用物理量导出共用的临时渲染场景范围；拥有相机、灯光、背景与输出设置，提供方向、边距和体积相机聚焦阈值；按求值后的几何拟合相机，模式/轨迹动画固定包络视野并保留真实帧/时间来源；输出区分空间 Å、倒空间 Å⁻¹ 与图表轴单位，并记录源 View 变换；体积聚焦分块扫描，退出时恢复用户显示状态。 |
| `ChemBlender/render_annotations.py` | `create_render_annotations()` | 在临时相机坐标系创建原生 Text/Mesh 标题、单位、轨道通道、真实零点色标及分类图例；复用科学色图的 Emission，避免照明改变图例，返回完整标注元数据并清理 owned 资源。 |
| `ChemBlender/phonon_view.py` | `create_phonon_view()`、`apply_phonon_phase()` | 从权威 primitive Structure 和 PhononModeSet 创建三轴超胞显示；保存 primitive 映射、晶格平移及参考位置，复用 pure 复相位和质量加权求值，支持保存重开与单位一致的相位更新。 |
| `cbq_core/project_link.py` | `MANIFEST_HASH_KEY`、`write_project_link()`、`resolve_project_link()` | 以不依赖 `bpy` 的内部 helper 计算 Scene locator；只从同一次 sidecar 验证取得 manifest hash，并以 UUID、schema 与 hash 解析、校验和恢复 `.cbq` 项目。 |
| `chemblender_prepare/worker_client.py` | `start_worker()`、`WorkerHandle.poll()`、`wait()`、`request_cancel()`、`terminate()` | 使用显式外部 Python 启动一次一任务的隐藏 worker 进程，管理 request/result/cancel 文件和日志；启动阶段以with管理父进程日志句柄，第二次open或Popen异常也关闭，成功后子进程使用独立句柄继续写入；可选 staged_inputs 在启动前复制并校验任务内输入路径，拒绝路径逃逸、链接和保留文件名。 |

## 纯 Python 语义核心

### 模型、registry 与公共入口

| 文件 | 主要入口 | 职责 |
| --- | --- | --- |
| `cbq_core/model/__init__.py` | 模块级显式 re-export | 模型 package 的兼容门面；从基础模块和各领域模块显式重导出公共名称，不保留领域模型定义。 |
| `cbq_core/model/common.py` | `_require_uuid()`、`_require_token()`、`CalculationStatus`、`DatasetStatus`、`IssueKind` 等 12 个 enum | 提供模型共享的 token/UUID/text 校验器、正则模式和稳定枚举定义，不依赖 Blender 或可选科学栈。 |
| `cbq_core/model/quality.py` | `QualityStatus`、`DiagnosticSeverity` | 定义导入质量和诊断严重度的稳定小写序列化值，并以显式映射固定摘要顺序。 |
| `cbq_core/model/grouping.py` | `CalculationGroup` | 定义用户确认的跨来源计算分组实体；以完整 suggestion、source revision 与 evidence 身份生成稳定 UUID，并作为 `QCProject` 与 `.cbq` 的权威科学关系保存。 |
| `cbq_core/model/sources.py` | `SourceRecord`、`SourceRevision`、`source_parse_identity()` | 定义用户逻辑来源及其不可变内容/解析 revision；以内容 hash、reader plugin/id/version 和规范参数对计算与 locator 无关的解析身份。 |
| `cbq_core/model/arrays.py` | `ArrayData` | 定义带命名维度、单位、shape 和 dtype 校验的中立数组包装，并由模型 package 原样 re-export。 |
| `cbq_core/model/categorical.py` | `CategoricalData` | 以整数 code、唯一字符串 category 和显式 missing code 保存分类属性，避免 object dtype 进入 sidecar。 |
| `cbq_core/model/chemical_identity.py` | `AtomicIdentityData` | 定义可选逐 atom identity 值对象；以 dimensionless integer isotope/formal-charge/atom-map 和 `CategoricalData` 名称/stereo 标签保持同一 atom 轴，不保存 RDKit 对象。 |
| `cbq_core/model/diagnostics.py` | `DiagnosticValue`、`ImportDiagnostic`、`diagnostic_from_parser_issue()`、`ParserIssue`、`ParserReport` | 以逐节点 type tag 定义不可变、JSON-safe 且可区分 sequence/mapping 的详细导入诊断，并提供 legacy reader issue 转换，同时保持既有 parser issue/report 契约。 |
| `cbq_core/model/exchange.py` | `ChemicalAnnotation`、`ExternalReference`、`BiologicalModel`、`BiologicalChain`、`BiologicalResidue`、`BiologicalAtomSiteData`、`BiologicalHierarchy` | 定义不污染 `Structure`/`AtomicIdentityData` 的交换格式标量注释、外部标识和紧凑生物层级；逐 atom 数组仍复用 `ArrayData`/`CategoricalData`，不保存格式 parser 或第三方对象。 |
| `cbq_core/model/structure.py` | `DeclaredSymmetry`、`PeriodicSiteData`、`MolecularTopology`、`Structure`、`SymmetryResult`、`unit_cell_parameters()`、`fractional_to_cartesian()`、`cartesian_to_fractional()`、`validate_periodic_coordinate_consistency()` | 定义统一分子/周期 Structure 和结构化对称性结果；CIF 周期位点以 envelope UUID 加稳定 block name/key/index 绑定源 block，独立保存 source-declared symmetry name/IT number/Hall/operations，并显式保存缺失 occupancy、disorder assembly/group 与可缺失的 Uiso/Uij；`Structure.cell` 是唯一持久化晶格权威，纯 helper 按 row-vector 约定派生晶胞参数、转换两套坐标并为 reader/adaptor 显式复验一致性；保留 `MolecularTopology` 读取兼容，让 Structure 记录零或多个独立 topology UUID，并拒绝非长度单位、非有限坐标及非有限或奇异 cell。 |
| `cbq_core/model/molecular_topology.py` | `TopologySource`、`TopologyRecord` | 定义按来源和质量版本化的分子连接实体，校验 bond arrays、可选 integer lattice shifts、芳香/立体标签、规范推断参数及 provenance；文件显式、RDKit 解释、距离推断和用户编辑互不覆盖。 |
| `cbq_core/model/records.py` | `RawRecordProperty`、`MolecularRecord`、`RecordPropertyColumn`、`ConformerSet` | 定义原始分子 record 的精确 bytes/有序属性、可选 typed record-column 与已归一化 conformer 坐标；由 project graph 校验 source revision、Structure/Topology、record UUID、atom 数和单位，不解析 RDKit 或实现 grouping。 |
| `cbq_core/model/properties.py` | `PropertyDataset`、`AtomicProperty`、`FrameSet`、`FrameProperty`、`AtomFrameProperty`、`CellFrameProperty` | 定义通用属性数据集、原子/坐标帧特化，以及绑定 FrameSet 并带严格 validity mask 的帧属性。 |
| `cbq_core/model/grids.py` | `Grid3D` | 定义仿射三维网格、坐标单位、步进向量和可选结构引用校验。 |
| `cbq_core/model/spectroscopy.py` | `VibrationalModeSet`、`ExcitedStateSet`、`Spectrum` | 定义振动模式、激发态贡献/引用和振动/电子光谱数据集。 |
| `cbq_core/model/wavefunction.py` | `BasisSet`、`OrbitalSet`、`DensityMatrix` | 定义基组壳层/约定、轨道通道和 AO 密度矩阵及其内部一致性校验。 |
| `cbq_core/model/periodic.py` | `BandStructure`、`DensityOfStates`、`PhononModeSet`、`FermiSurfaceMesh` | 定义能带、DOS、声子模式和费米面网格等周期体系数据集。 |
| `cbq_core/model/topology.py` | `TopologyGraph`、`TopologyConnection`、`TopologyPath` | 定义临界点、连接和路径组成的中立拓扑图，并校验结构/网格引用所需的局部语义。 |
| `cbq_core/model/project.py` | `CIFEnvelope`、`CalculationRecord`、`ProvenanceRecord`、`ImportBatch`、`QCProject`、`validate_project_graph()` | 定义保留原始 bytes、完整 tag 与稳定 block identity 的交换 envelope、计算/溯源记录和项目聚合根；原子提交 source/revision、topology、biological hierarchy、annotation、external reference、diagnostic 与科学实体，并校验目标/溯源、唯一语义键、atom 维度、全局 registry UUID 和双向 revision-diagnostic 关系；`validate_project_graph()` 以一次临时 `QCProject.commit()` 和 calculation-group 提交复验完整已存在图。 |
| `chemblender_prepare/core/topology/radii.py` | `covalent_radius_angstrom()`、`is_metal()` | 把既有 `Chem_data.ELEMENTS_DEFAULT` 和 metals 表投影为纯 Python 拓扑推断查询，不导入 RDKit 或 Blender。 |
| `chemblender_prepare/core/topology/infer.py` | `TopologyInferenceSettings`、`infer_distance_topology()` | 对 angstrom/bohr 非周期 Structure 使用 27 邻格空间 cell list 生成确定性距离拓扑；记录全部设置、源 Structure revision 和 provenance，重复近点以 INVALID parser issue 阻断，金属配位保持 ambiguous/零键级。 |
| `chemblender_prepare/core/topology/periodic.py` | `infer_periodic_topology()` | 通过 cell inverse 映射 fractional displacement，只沿启用的 PBC 轴建立有界周期 image 邻格；连接保留规范 integer lattice shift，周期/材料连接使用 ambiguous 与零键级且支持单原子 self-image。 |
| `cbq_core/structure_edit.py` | `StructureEditPreview`、`preview_structure_edits()`、`commit_structure_edits()` | 纯 Python 比较 Structure/Topology 与显式编辑状态，规范化 angstrom 后报告 atom、coordinate、element、bond、cell 与关联 dataset diff；确认路径以确定性 UUID/revision 创建 derived Structure、可选 USER_EDITED TopologyRecord 和 parent provenance。原子序号与一一映射不变的纯坐标/键编辑保留 `atomic_identity`，增删原子或改元素时清除，避免错误继承旧映射；不修改源实体。 |
| `cbq_core/session.py` | `ProjectSession`、`create_session()`、`close_session()` | 在冻结科学模型之外管理可变会话状态；`mark_clean()` 仅显式清空已记录 dirty reasons；创建带 UUID ownership marker 的临时根，并在关闭 lazy resources 后仅删除标记匹配的受控目录。 |
| `cbq_core/project_service.py` | `save_project_session()`、`save_project_session_for_scenes()`、`sync_project_session_links_for_scenes()`、`verify_project_session()`、`verify_project_session_for_scenes()`、`relink_project_session()`、`relink_project_session_for_scenes()`、`clear_derived_cache()` | 编排原子 sidecar publication 与经 hash 验证的 Scene link；link-only 同步只打开验证现有 sidecar 一次，精确 no-op 或只补空 Scene/移动后的 locator，不改 manifest、generation 或 authoritative arrays，partial/conflicting link 必须显式 relink。多 Scene relink 先校验已保存的四字段一致且完整，使用 Scene 保存的 UUID、schema 与 manifest hash 匹配候选，而非 Missing load 的空会话 UUID；无任何 Scene link 的既有 service 调用仍以当前 session identity 为准。只打开候选一次，先快照全部四字段再写同一 UUID、schema、locator 与 manifest hash，任一写入或采用失败时恢复全部 Scene；rollback 不完整时保留原错误、逐 Scene/key failure 和 residual keys，全部写成功后才采用候选并关闭旧 project。单 Scene relink 保持兼容 wrapper。恢复时忽略空 Scene、只采纳一次相同有效 link，并对冲突有效 link fail-closed；另以显式状态恢复 session，并仅清理 `.cbq/cache/derivation/` 与 `.cbq/cache/render/` 非权威缓存。 |
| `chemblender_prepare/core/import_pipeline/__init__.py` | 模块级显式 re-export | 导入流水线的纯 Python package 门面；公开 request、preview、staging、preflight、conflict 与 grouping 契约，不加载 Blender 或可选科学栈。 |
| `chemblender_prepare/core/import_pipeline/conflicts.py` | `ImportConflictCandidate`、`ImportConflict`、`DuplicateAction`、`ConflictDecision`、`detect_import_conflicts()`、`apply_conflict_decisions()` | 只读比较 parse identity、内容 hash 与纯词法 locator；同 locator 的 reader/参数升级也进入显式新 revision 决策；文件来源要求 absolute path 与 canonical locator 精确一致，SMILES text 只接受 `inline:smiles` 及 session-owned staged artifact，其他 locator fail-closed。不可拆分候选快照保留最高优先级的全部匹配；提交决定前根据 live project 和 staging session 重检完整冲突，target action 必须显式选择 revision，并返回新的 preview，不修改 session 或项目。 |
| `chemblender_prepare/core/import_pipeline/grouping.py` | `GroupingEvidence`、`SourceGroupSuggestion`、`suggest_source_groups()` | 从严格关联的暂存 batch 生成确定性、不可变的跨来源证据与分组建议；依次评估显式 UUID 引用、结构映射、Kabsch RMSD（`<= 0.15 Å`）、metadata 和文件名/目录，周期原胞/惯用胞候选只标记 review conflict，只有用户显式确认才创建 model 层 `CalculationGroup`，不修改 preview、session 或项目。 |
| `chemblender_prepare/core/import_pipeline/conformer_grouping.py` | `ConformerGroupSuggestion`、`suggest_conformer_groups()`、`suggest_staged_conformer_groups()`、`accept_conformer_group()` | 以完整 `ImportBatch` 的 `Structure`、`TopologyRecord`、`AtomicIdentityData` 和 `RecordPropertyColumn` 为权威，在同一 `SourceRevision` 的 SDF records 中生成不可变 conformer 建议；project_conformer_batch从已保存项目构建保持实体身份的输入，供CBQ检查/接受复用；staged helper 跨 Preview source 收集建议并支持 cooperative cancellation，使 Quick Import 可在 worker 中预计算而 UI 主线程只投影缓存。RDKit 仅提供 atom-map/canonical-rank/isomorphism 候选，最终逐项复验元素、charge、isotope、stereo、bond order 与 aromaticity。显式确认后才返回含 reference-to-source mapping、重排序坐标/record columns 与 provenance 的 derived fragment；快照过期、对称映射截断或不完整证据均 fail-closed，不修改输入 batch、项目或 Blender。 |
| `chemblender_prepare/core/import_pipeline/transaction.py` | `GroupingDecision`、`ConformerGroupingDecision`、`ImportCommitDecisions`、`ImportCommitResult`、`commit_import_preview()` | 根据 live project 与 staging session 重检完整 conflict/source-group/conformer-group 快照；conformer acceptance 在 resolved live staged batch 中重算，skip/reuse 缺少成员即 fail-closed，reidentify 后按 remapped record IDs 重新匹配。所有 derived fragments 只写入 disposable candidate 并在一次 sidecar 原子发布和 verified project 移交后替换 live session；不创建 Blender datablock。 |
| `chemblender_prepare/core/import_pipeline/parse.py` | `staged_reader_batch()`、`stage_import_batch()` | reader-neutral 地构造或复验带 `SourceRecord`、`SourceRevision` 和双向诊断引用的暂存结果；可复用 host 预分配的最终 revision UUID，并为公开 Reader API 精确复验插件提供的完整来源身份。canonical parameters 只参与 reader parse identity，不解释任何 legacy source 或 provenance 语义；不提交项目。 |
| `chemblender_prepare/core/import_pipeline/preflight.py` | `preflight_import()`、`ImportCancelled` | 对显式文件执行 bounded hash、reader 选择与 availability 检查、可取消解析和稳定失败诊断；只登记到 owned staging session，不写 `QCProject`。 |
| `chemblender_prepare/core/import_pipeline/request.py` | `ValidationMode`、`ImportSource`、`ReaderOverride`、`ImportRequest` | 定义不可变导入意图；规范化并去重显式文件路径，拒绝目录扫描，并将 reader override 限定到请求内来源。 |
| `chemblender_prepare/core/import_pipeline/preview.py` | `SourcePreview`、`ImportPreview` | 以不可变路径、标量和 UUID 引用描述 source row、暂存 batch、冲突、归组建议、诊断及默认 view plan，不持有项目或 Blender 对象。 |
| `chemblender_prepare/core/import_pipeline/report.py` | `import_summary()`、`diagnostics_document()`、`render_diagnostics_markdown()` | 只读验证 preview 与 live staging batch 的身份及关联，按稳定键生成 schema v1 JSON-compatible diagnostic document、质量状态计数和 Markdown；不读取项目、不加载 Blender 或可选科学栈。 |
| `chemblender_prepare/core/import_pipeline/staging.py` | `StagedImportSession.create()`、`register_result()`、`materialize_result()`、`discard()` | 创建带 UUID ownership marker 的独占暂存根、artifact 目录和受控 `ImportBatch` registry；可登记一次性延迟 materializer，在确认时先完整生成 replacement 再原子替换 preview batch，失败保留可重试 preview；discard 会先关闭已注册 batch 的 staged memmap，再仅在路径、文件身份及 marker 均匹配时删除。 |
| `chemblender_prepare/core/readers.py` | `ReaderDescriptor`、`ReaderRuntimeDescriptor`、`ReaderAvailability`、`ReaderRegistry.register()`、`select()`、`parse()` | 定义 reader capability、扩展名、bounded sniffing 和确定性分派；可成对声明 content-verified preview/materialize request 以延迟大型数值数组，拒绝只配置一侧；以兼容 wrapper 分离 reader 选择与运行时 availability，拒绝未知或歧义 reader。 |
| `chemblender_prepare/core/reader_catalog.py` | `builtin_reader_descriptors()`、`builtin_reader_registry()`、`reader_capability_document()` | 外部22 reader 的能力和版本清单；导出 execution_mode=prepare，记录外部后端依赖、字段、损失政策和fixture family，不将当前机器可用性或完整Viewer验收状态写成保证。 |
| `cbq_core/cache_identity.py` | `source_hash_bytes()`、`parser_cache_key()`、`derivation_cache_key()`、`render_cache_key()` | 用规范 JSON 和 SHA-256 分别标识源文件、解析、派生和渲染缓存。 |

### Reader API v1 RC 门面

`reader_api` 是冻结为 `1.0-rc1` 的公共、纯 Python（`bpy`-free）门面。manifest 是可安装插件的静态声明，runtime descriptor 是已解析 reader 的只读元数据；两者都不持有 parse callable，插件也不能取得或修改 `QCProject`。模块只通过相对导入解析已安装命名空间，不绑定源码包名或 extension repository namespace。可选依赖 availability 探测只使用 `find_spec()`，不导入该依赖。

| 文件 | 主要入口 | 职责 |
| --- | --- | --- |
| `chemblender_prepare/reader_api/__init__.py` | 模块级 re-export | Reader API `1.0-rc1` 的严格公共门面；导出版本、manifest/runtime descriptor、exact `SniffMatch`/`SniffResult`、受控科学实体（含 exchange annotation/reference/hierarchy）和 `PublicImportBatch`，不导出 `QCProject` 或内部 `ImportBatch`。 |
| `chemblender_prepare/reader_api/version.py` | `READER_API_VERSION` | 声明冻结的 Reader API `1.0-rc1` token，供 manifest v1 兼容范围校验。 |
| `chemblender_prepare/reader_api/manifest.py` | `ExecutionMode`、`ReaderManifestEntry`、`ReaderPluginManifest.from_toml()` | 用标准库 `tomllib` 读取受控 UTF-8 TOML，拒绝未知字段和不兼容 API 范围，并确定性规范化静态 reader 声明；manifest capability list 恒表示 `SUPPORTED`。 |
| `chemblender_prepare/reader_api/descriptors.py` | `PublicReaderDescriptor`、`_probe_availability()` | 定义不含 callable、模块路径或项目上下文的不可变 runtime 元数据；以相对导入取得现有 `CapabilitySupport`/`ReaderAvailability`，并保留 `SUPPORTED`、`PARTIAL`、`UNSUPPORTED` 三态 capability。 |
| `chemblender_prepare/reader_api/discovery.py` | `ReaderPluginDiscovery`、`ReaderDiscoverySnapshot`、`DiscoveredReaderPlugin` | 以单一纯 Python owner 包装既有 registry：只接受 handle 的显式注册/注销，不扫描 `sys.path`；成功时保留 reader descriptor identity，重复 ID、reserved built-in ID、malformed plugin 或普通 callback failure 转为稳定 unavailable state；注销按 registry 的完整 manifest value equality 在一次事务中 reconcile 同一 Extension 的成功 ownership 与失败记录，不影响其他 manifest；`refresh()` 缓存同一 generation 的只读 snapshot，不重建 registry 或 Blender class，fatal exception 原样传播。 |
| `chemblender_prepare/reader_api/public_model.py` | `PublicImportBatch` | 以精确受信科学实体类型构成不可变、无复制的导入批次，包括 biological hierarchy、chemical annotation 和 external reference 三组兼容扩展；拒绝子类和未批准数据集，并为 bridge 提供递归嵌套值校验，插件不能经此获得项目。 |
| `chemblender_prepare/reader_api/builtin_bridge.py` | `public_batch_from_internal()`、`internal_batch_from_public()` | 内置 `ImportBatch` 与公开批次间的薄、无复制转换边界；公共转换保持完整 `QCProject.commit()` 图校验，私有 structural conversion 只供 exact 内置插件在 host 绑定最终 `SourceRevision` 前使用，均递归拒绝 callable、mutable container 与未登记嵌套对象。 |
| `chemblender_prepare/reader_api/canonical_document.py` | `public_batch_document()`、`public_batch_from_document()`、`write_public_batch_bundle()`、`read_public_batch_bundle()` | 将严格 `PublicImportBatch` 确定性编码为 Reader Import Document v0.1；以 content-addressed、禁 pickle 的 NPY artifacts 承载数组，并在读取边界复验 exact schema/type、相对路径、shape、dtype 与双 hash；对 CIF block identity 和兼容新增的空 exchange groups 提供明确旧文档缺省；写后 hash/临时文件清理失败统一为稳定 integrity error；只构造公开 batch，项目图校验留给 built-in bridge。 |
| `chemblender_prepare/reader_api/import_pipeline_bridge.py` | `preflight_reader_plugins()` | 把主进程持有的 `ReaderPluginRegistry` 接入既有 `ImportRequest`、`StagedImportSession` 与 `ImportPreview`：每次 parse 预分配一个最终 revision UUID，exact 内置结果先绑定同一 `SourceRevision` 再做完整项目图校验，外部 reader 仍须返回 UUID 与请求一致的完整来源身份。仅供 host 内部使用的 keyword-only batch attachment 只在每个最终 staged preview/deferred candidate 的 reader fallback、图校验与 base identity comparison 完成后运行一次，保持 public reader/core 模型 reader-neutral；它只能追加 provenance 及其 created-ID bookkeeping，任意替换来源、reader science、诊断或 report 均以结构化 host contract error fail closed，host 异常会先释放未登记 batch 的 lazy array/memmap 和受控 artifacts 再原样透传。可信内置 reader 可先登记 content-verified preview，再在确认时以相同 entity inventory、语义诊断及原 diagnostic IDs 原子物化；不一致时清理新 artifacts、保留 snapshot 并要求刷新 Preview。确认前不修改 `QCProject`、Scene 或 Blender datablock。 |
| `chemblender_prepare/reader_api/conformance.py` | `ReaderConformanceCase`、`ReaderConformanceCheck`、`ReaderConformanceResult`、`run_reader_conformance()`、`run_reader_conformance_v1()` | 保持 Reader API 0.1 公共类型与 12 项检查兼容，并生成 v1 suite document；复用 registry、graph bridge 与 canonical bundle 验证 bounded/deterministic sniff、来源身份、引用、单位/质量/诊断、progress、capability、artifact 安全、取消和异常隔离，不创建项目或 Blender 状态。 |
| `chemblender_prepare/reader_api/conformance_cli.py` | `main()` | 从显式目录在子进程中加载插件 `reader.py`，只运行 reader 声明 extension 的安全 fixture，输出 compact/sorted UTF-8 v1 conformance JSON；required failure 返回 1，CLI/路径/加载失败返回 2，不扫描任意 `sys.path`、不安装依赖。 |
| `chemblender_prepare/reader_api/protocol.py` | `SniffRequest`、`ParseRequest`、`ProgressEvent`、`ReaderPlugin` | 定义无项目、无 Blender 上下文的 Reader 插件请求与进度协议；每个插件必须持有与 runtime descriptor 一致的 exact manifest，解析请求携带已验证来源、host 最终 `source_revision_id`、规范参数、安全 staging root 及进度/取消回调。 |
| `chemblender_prepare/reader_api/registry.py` | `ReaderPluginRegistry`、`builtin_reader_plugin_registry()` | 确定性选择公开 Reader 插件，在注册时交叉验证 manifest/runtime metadata，并要求同一 `plugin_id` 使用一份完整 manifest；仅以 exact complete manifest 原子注销同一插件全部 reader；在解析前后分块复验来源 hash，只有 exact 内置 wrapper 可走绑定前 structural validation，外部 reader 的完整 revision UUID 必须匹配请求；隔离 sniff/parse 异常并保留最近一次 parse 的私有异常类型证据；内置 Gaussian/ORCA 的输入验证 ValueError 转为有长度限制的公开原因，外部 Reader 仍使用通用异常边界。 |
| `chemblender_prepare/reader_api/worker_bridge.py` | `parse_with_worker()`、`WorkerReaderError` | 主进程对固定 `reader.parse@0.1` 的已完成 `WorkerResult` 做 request ID、状态、exact metadata、NTFS-safe 相对路径、无 link/junction 的 exact bundle inventory、来源与全部输出 hash 复验；重开 canonical bundle 并经 `internal_batch_from_public()` 图校验，且 result outputs 非空时须与解码 batch 的完整顺序 inventory 一致，才返回内部 `ImportBatch`。 |

### 文件 reader 与第三方 adapter

| 文件 | 主要入口 | 职责 |
| --- | --- | --- |
| `chemblender_prepare/core/exporters/__init__.py` | 模块级 re-export | 暴露原生 XYZ/extXYZ、MOL/SDF/SMILES、PDB/PQR 与 controlled CIF 的纯 Python 导出入口、MOL2/PDB/PQR readiness、无写入 loss/patch preview、取消异常和语义比较器，不加载 Blender 或 RDKit。 |
| `chemblender_prepare/core/exporters/cif.py` | `CIFExportPlan`、`plan_cif_export()`、`export_cif()` | 复用 Gemmi 只在 CIF 导出调用时读取 source envelope；Preserve mode 以稳定 block identity patch cell、atom-site、occupancy、Uiso/Uij、ADP type、disorder group/assembly 与明确声明的 symmetry，并保留未知 block/tag/loop；Normalized mode 从无 envelope 的周期 Structure 写最小 CIF，不虚构 uncertainty、disorder 或 symmetry。两种模式共用短临时文件、fsync、原子替换与取消清理。 |
| `chemblender_prepare/core/exporters/cube_readiness.py` | `CubeExportStatus`、`CubeExportReadiness`、`cube_export_readiness()` | 纯 Python Cube core export 可表示性检查；要求唯一 Grid3D、其显式 Structure、完整 nuclear-charge AtomicProperty、有限实数数组、bohr/angstrom 坐标单位和显式多 dataset 选择，返回稳定状态/token，不序列化、不读取 VDB 或 Blender cache。 |
| `chemblender_prepare/core/exporters/cube.py` | `CubeExport`、`preview_cube_export()`、`export_cube()` | 从 readiness 已验证的 Structure、nuclear-charge AtomicProperty 与选定 Grid3D 确定性写出 bohr Cube；保留完整仿射 step vectors 和可信 DSET_ID，缺失 multi ID 使用显式确认的确定性 fallback，目标文件复用 shared atomic writer。 |
| `chemblender_prepare/core/exporters/poscar.py` | `PoscarExportSettings`、`export_poscar()`、`semantic_poscar_differences()` | 原生 POSCAR/CONTCAR exporter：确定性输出 species groups、Direct/Cartesian、unit/preserved/target-volume scale、Selective Dynamics 及选中的 ion/lattice velocities；ion velocity 在模型中使用 Cartesian canonical basis，导出 Direct 时按当前科学 cell 变换，语义比较也使用 canonical basis；复用 atomic writer。 |
| `chemblender_prepare/core/exporters/xyz.py` | `atomic_write_chunks()`、`export_xyz()`、`export_extxyz()`、`preview_extxyz_export()`、`semantic_extxyz_differences()` | 提供同目录短临时文件、fsync、replace、取消清理的共享 UTF-8 原子写入；其上确定性导出 XYZ/extXYZ，保留 typed frame/atom/cell property、integral-valued real metadata 与 validity，显式报告 partial/ambiguous loss，并按科学数据而非 UUID/空白比较 round-trip。 |
| `chemblender_prepare/core/exporters/rdkit_molecular.py` | `SDFExportEntry`、`sdf_entries_from_conformer_set()`、`preview_molecular_export()`、`export_mol()`、`export_sdf()`、`export_smiles()`、`semantic_molecular_differences()` | 仅在写入时加载 RDKit，从 `Structure`、`AtomicIdentityData` 和选定 `TopologyRecord` 重建临时分子；纯 metadata preview 复用同一 loss contract 而不构造或序列化 RDKit Mol；严格审计 V2000 表示能力并自动选择 V3000，MOL/SDF 的 atom name 或 multiplicity loss 先要求确认，SDF 以 caller-selected `SDFExportEntry` 顺序保留 raw SD 属性的重复项；ConformerSet helper 按 reference atom order 生成派生记录而不二次应用 mapping；SMILES 在确认前只报告 loss，所有目标文件复用 shared atomic writer。 |
| `chemblender_prepare/core/exporters/mol2.py` | `preview_mol2_export()`、`export_mol2()` | 从现有 Structure、TopologyRecord、MolecularRecord、AtomicProperty 与 Tripos annotation 确定性写出规范化 MOL2；原始 ID、状态、注释、扩展 substructure 字段和未知 section 的省略先进入 loss preview 并要求确认，目标文件复用 shared atomic writer；模块不加载 Blender 或可选依赖。 |
| `chemblender_prepare/core/exporters/pdb.py` | `preview_pdb_export()`、`export_pdb()` | 从现有 Structure、BiologicalHierarchy、FrameSet 与可选 occupancy/B-factor 确定性写出 fixed-column PDB；拓扑、cell、formal charge 与 source-only record 的省略先进入 loss preview 并要求确认，目标文件复用 shared atomic writer；模块不加载 Blender 或可选依赖。 |
| `chemblender_prepare/core/exporters/pqr.py` | `preview_pqr_export()`、`export_pqr()` | 从一个现有 Structure、matching BiologicalHierarchy 与完整 charge/radius AtomicProperty 确定性写出 10/11-field whitespace PQR；复用 native PQR element inference 在 readiness 和写入信任边界阻断 identity mismatch，真实 topology/cell/identity/molecular loss 先要求确认，目标文件复用 shared atomic writer；模块不加载 Blender 或可选依赖。 |
| `chemblender_prepare/core/exporters/mol2_readiness.py` | `Mol2ExportStatus`、`Mol2ExportReadiness`、`mol2_export_readiness()` | 纯 Python MOL2 P1 可表示性检查；从既有 Structure/TopologyRecord/MolecularRecord/AtomicProperty/ChemicalAnnotation 收集确定性缺失字段并返回 Complete/Partial/Unsupported，不写入文件、不接 UI、不新增科学模型。 |
| `chemblender_prepare/core/exporters/pdb_readiness.py` | `PDBPQRExportStatus`、`PDBPQRExportReadiness`、`pdb_export_readiness()`、`pqr_export_readiness()` | 纯 Python PDB/PQR P1 可表示性检查；只按显式 Structure UUID 关联 BiologicalHierarchy、AtomicProperty 与 FrameSet，确定性报告缺失、歧义、无效值、字段溢出及 serial 重编号边界，不格式化或写文件、不接 UI、不新增科学模型。 |
| `chemblender_prepare/core/formats/__init__.py` | 模块级 re-export | 暴露原生文本格式 reader 的低层入口，不注册 reader 或接触项目状态。 |
| `chemblender_prepare/core/formats/cif.py` | `CIF_READER`、`sniff_cif()`、`parse_cif()` | 内置 CIF reader；仅在解析时加载 Gemmi，把多 block/loop、fractional/Cartesian 坐标、位点 identity、缺失或部分 occupancy、disorder assembly/group、U/B displacement 和原始 envelope 映射到统一模型；坐标派生及 B→U 转换写入 diagnostics 与 provenance。 |
| `chemblender_prepare/core/formats/extxyz.py` | `parse_extxyz()`、`sniff_extxyz()`、`iter_extxyz_frames()` | 原生选择并逐帧解析 extXYZ，将兼容帧映射为确定性 `Structure`、`FrameSet` 与 typed frame/atom/cell property；大型 Quick Import 先对同一 hash-verified snapshot 扫描 frame/schema/comment 并用零复制 broadcast array 建立小型 preview，确认时再可取消地物化完整 staging NPY memmap；不一致 fail-closed，不依赖 ASE。 |
| `chemblender_prepare/core/formats/gaussian_input.py` | `GAUSSIAN_INPUT_READER`、`sniff_gaussian_input()`、`parse_gaussian_input()` | 零第三方依赖的 Gaussian `.gjf/.com` 结构 reader；严格读取 Link0/route/title 后的 charge、multiplicity 与四列内嵌 Cartesian 坐标，映射非周期 Structure 和 provenance；拒绝 Z-matrix、freeze/ONIOM/fragment 修饰及 Link1 多任务，解析 route 中的坐标单位并归一化到 Å、保留转换 provenance；不执行 Gaussian 或解释其他计算关键词。 |
| `chemblender_prepare/core/formats/mol.py` | `MOL_READER`、`sniff_mol()`、`parse_mol()`、`parse_mol_request()` | 对单记录 MOL V2000/V3000 做完整 CTAB/atom/bond 结构 sniff，并仅在调用时加载 RDKit；保留原始 bytes，借助共享 adapter 输出结构、原子身份、显式拓扑、MolecularRecord、provenance 与诊断；产品请求直接沿用 host 的 source revision、hash、validation 和 cancellation。 |
| `chemblender_prepare/core/formats/mol2.py` | `MOL2_READER`、`sniff_mol2()`、`iter_mol2_records()`、`parse_mol2_record()`、`parse_mol2()`、`parse_mol2_request()`、`mol2_preview_summary()` | 以标准库按 `MOLECULE` 边界和 case-insensitive exact section marker 保留 MOL2 原始记录；解析任意 atom/bond ID、Tripos atom/bond/substructure/charge 语义，并映射为统一 Structure、explicit-file TopologyRecord、MolecularRecord、ChemicalAnnotation 与 atomic properties。Balanced 模式逐 record 恢复，坏 bond 只阻断 topology，缺失类别/charge 明示 Partial；descriptor 为 dependency-free built-in reader；外部inspect复用旧纯摘要显示已解释键数、部分电荷覆盖率与不支持section，摘要不序列化科学数组。 |
| `chemblender_prepare/core/formats/orca_input.py` | `ORCA_INPUT_READER`、`sniff_orca_input()`、`parse_orca_input()` | 零第三方依赖的 ORCA `.inp` 结构 reader；严格读取唯一且闭合的 `* xyz charge multiplicity ... *` 四列 Cartesian 坐标块，映射非周期 Structure 和 provenance；识别但拒绝 `xyzfile`、内部/多坐标块和原子修饰，解析 `! Angs/Bohrs` 和 `%coords Units` 的坐标单位并归一化到 Å、保留转换 provenance；不执行 ORCA 或解释其他计算关键词。 |
| `chemblender_prepare/core/formats/pdb.py` | `PDB_READER`、`sniff_pdb()`、`parse_pdb_records()`、`parse_pdb()`、`parse_pdb_request()` | 纯标准库 fixed-column PDB reader；保留语法层的原始 bytes/line ending，以内部 MODEL occurrence 区分重复 serial 的 source block，并在冻结模型前校验 atom serial/occupancy；把七字段 atom identity、MODEL/altloc/hierarchy、occupancy/B-factor、occurrence-scoped CONECT 与 CRYST1 映射到统一 Structure、FrameSet、BiologicalHierarchy、AtomicIdentityData、AtomicProperty、explicit-file TopologyRecord 和 periodic cell；不实现 PQR、altloc view filter、UI 或 export。 |
| `chemblender_prepare/core/formats/pqr.py` | `PQR_READER`、`sniff_pqr()`、`parse_pqr_records()`、`parse_pqr()`、`parse_pqr_request()` | 纯标准库 validated-whitespace PQR reader；严格区分 with-chain/no-chain field count，校验 serial、residue/insertion、xyz、charge 与 radius，按 PDB atom-name 规则诊断式推断 element，并映射统一 Structure、BiologicalHierarchy、AtomicIdentityData 与 charge/radius AtomicProperty；坏行按 validation mode 隔离或拒绝，不产生或推断 topology。 |
| `chemblender_prepare/core/formats/sdf.py` | `SDF_READER`、`iter_sdf_records()`、`parse_sdf()`、`parse_sdf_request()` | 用 standalone `$$$$` 的原始字节行边界逐条索引 SDF；先保留 MOL slice 与重复/空 SD 字段，再独立调用 RDKit adapter；Balanced 模式保留坏记录周围的有效索引并诊断，只有无歧义的 bool/int/float 字段生成带 mask 的 record property column，不做 conformer grouping。 |
| `chemblender_prepare/core/formats/smiles.py` | `SMILES_READER`、`parse_smiles()`、`parse_smiles_text()`、`parse_smiles_request()` | 以单条 UTF-8 SMILES 原始 bytes 为权威来源；文件 reader 仅在调用时加载 RDKit，direct text 使用稳定 `inline:smiles`/`inline_text` source 语义而不持久化随机临时路径。解析固定生成显式 planar 2D 坐标，保留 canonical/isomeric SMILES、atomic identity、charge 与 explicit topology；无效、radical、dummy 或 unspecified bond 只返回 blocking diagnostic，不生成 Structure。 |
| `chemblender_prepare/core/formats/poscar.py` | `POSCAR_READER`、`PoscarDocument`、`sniff_poscar()`、`parse_poscar_document()`、`parse_poscar()` | 纯标准库 POSCAR/CONTCAR 语法与 built-in Reader API：校验 lattice、VASP 4/5 species/count、Direct/Cartesian/K、Selective Dynamics 与 velocity blocks；有效 `.vasp/.poscar/.contcar` 和 canonical basename 均为 native exact match，避免降级到 optional ASE；映射统一 periodic `Structure`、typed properties 和 source-convention provenance，并将 Direct ion velocity 按科学 cell 转为 Cartesian canonical basis。VASP 4 缺失元素时只产生 Ambiguous preview，显式 ordered species 参数恢复完整结构。 |
| `chemblender_prepare/core/formats/rdkit_common.py` | `adapt_rdkit_molecule()` | 在函数内加载 RDKit，将临时分子映射为现有的不可变结构、原子身份、显式/必要时 sanitized 拓扑、原始 record、provenance 与诊断；不保存 RDKit Mol，缺失 conformer 不虚构坐标。 |
| `chemblender_prepare/core/derivations/__init__.py` | `derive_smiles_3d()` | 派生模块的纯 Python 门面，不加载 RDKit。 |
| `chemblender_prepare/core/derivations/smiles_3d.py` | `derive_smiles_3d()` | 从关联的 `Structure`、`TopologyRecord`、`MolecularRecord` 与真实 `SourceRevision` 重建临时 RDKit Mol，以固定 ETKDGv3 seed、单线程及显式 AddHs/UFF/MMFF 参数生成新 3D Structure/Topology；通过 `CalculationRecord` 表示 success、failed 或 incomplete，保留来源实体且不持久化 RDKit Mol。 |
| `chemblender_prepare/core/xyz.py` | `sniff_xyz()`、`parse_xyz()` | 读取单帧/多帧 XYZ 和受支持的 extXYZ lattice/PBC/property 子集，输出 `Structure`、`FrameSet` 和报告。 |
| `chemblender_prepare/core/mol_v2000.py` | `MOL_V2000_READER`、`parse_mol_v2000()` | 已弃用的 V2000-only 显式兼容 alias；委托 `formats.mol` 的同一实现，自动选择始终由 replacement `mol` 处理并在 alias report 中说明迁移目标。 |
| `chemblender_prepare/core/cube.py` | `sniff_cube()`、`parse_cube()` | 读取 Cube 原点、完整非正交 step vectors、多 dataset/MO index、voxel 数据与逐原子 nuclear charge，输出共享 `Structure` 的 `Grid3D` 和 `AtomicProperty`，并在 provenance 保留 comments、dataset IDs 与有符号轴约定。 |
| `chemblender_prepare/core/cclib_adapter.py` | `sniff_cclib_output()`、`adapt_ccdata()`、`parse_cclib_output()` | 仅核对 Gaussian 原文单位和列的旋光强度作为定量 ECD，其余保持 ambiguous；延迟加载 cclib，将 Gaussian/ORCA 等输出归一化为结构轨迹、能量、原子属性、振动、激发态及 parser issues。 |
| `chemblender_prepare/core/iodata_adapter.py` | `sniff_iodata_wavefunction()`、`adapt_iodata()`、`parse_iodata_wavefunction()` | 延迟加载 IOData，将 FCHK/Molden 的结构、basis、restricted/unrestricted/generalized MO 和 RDM 转为内部模型。 |
| `chemblender_prepare/core/ase_adapter.py` | `sniff_ase_structure()`、`adapt_ase_atoms()`、`parse_ase_structure()` | 延迟加载 ASE，归一化分子/周期结构、约束、per-atom arrays 和轨迹。 |
| `chemblender_prepare/core/gemmi_adapter.py` | 兼容 re-export | 保留旧导入路径，并委托 `core.formats.cif`；不包含第二套实现。 |
| `chemblender_prepare/core/spglib_adapter.py` | `spglib_availability()`、`derive_symmetry()` | 只在显式 availability/derive 调用时实际导入 spglib，用显式 symprec/angle tolerance 从周期结构派生独立 `SymmetryResult` 与标准 Structure；native import 失败会禁用 capability，不改源 Structure、CIF envelope 或 source-declared symmetry。 |
| `chemblender_prepare/core/symmetry_service.py` | `symmetry_availability()`、`derive_structure_symmetry()`、`symmetry_comparison_rows()` | 提供不依赖 Blender 的可选 spglib capability、派生入口和 declared/derived 对比投影；复用 adapter 与 comparison，不在 core import 时加载 spglib。 |
| `cbq_core/symmetry_comparison.py` | `SymmetryComparison`、`compare_symmetry()` | 比较 source-declared 与 spglib-derived group identity，区分 match、different、insufficient data；只有调用方提供并通过校验的显式 setting transformation 才可标记 setting equivalent。 |
| `chemblender_prepare/core/pymatgen_adapter.py` | `sniff_vasp_volumetric()`、`adapt_pymatgen_structure()`、`adapt_vasp_volumetric()`、`parse_vasp_volumetric()` | 读取 CHGCAR/PARCHG/ELFCAR/LOCPOT 类周期体数据并保留晶格与 dataset 语义。 |
| `chemblender_prepare/core/pymatgen_electronic.py` | `sniff_vasprun()`、`adapt_pymatgen_electronic()`、`parse_vasprun_electronic()` | 从 pymatgen electronic objects/vasprun 归一化 band、DOS/PDOS、spin、投影和能量参考。 |
| `chemblender_prepare/core/phonopy_adapter.py` | `adapt_phonopy_qpoints()`、`parse_phonopy_file()`、`PHONOPY_FILE_READER` | 将 phonopy q-point、频率、复数 eigenvector、权重和晶胞关系转为 PhononModeSet；真实 YAML/type-1 FORCE_SETS 文件入口显式处理可选 BORN/NAC，验证配套文件和来源哈希，避免 cwd 隐式读取。 |
| `chemblender_prepare/core/pyprocar_file.py` | `parse_vasp_fermi()` | 从白名单 VASP 文本和完整均匀三维 k 网格生成 Structure、BandStructure 与 FermiSurfaceMesh；核验对称展开、绝对能量、2π 坐标约定与逐文件来源，不读取 POTCAR 或 pickle，不将高对称路径作为费米面输入。 |
| `chemblender_prepare/core/critic2_paths.py` | `parse_critic2_paths()` | 将 critic2 真实有序 FLUXPRINT TEXT 采样与 CPREPORT 的临界点身份核对，生成带双亲来源、单位和周期端点平移的派生 TopologyGraph；不从 connections 伪造路径。 |
| `cbq_core/color_mapping.py` | `color_stops()` | 纯数据科学色图：跨零发散色图按实际零值定位中性色，顺序色图保持统一端点；Blender 表面、原子和色标共用。 |
| `chemblender_prepare/core/grid_difference.py` | `derive_grid_difference()` | 对明确绑定同一结构、仿射和单位的两个 electron_density dataset 分块求差；记录两父身份及 dataset index，拒绝隐式重采样，取消或失败不返回部分有效结果。 |
| `chemblender_prepare/core/pyprocar_adapter.py` | `adapt_pyprocar_fermi_surface()` | 将已生成的 PyVista-compatible PyProcar surface 转为不依赖 PyVista 的顶点、三角面、band 和属性数组。 |
| `chemblender_prepare/core/critic2_adapter.py` | `parse_critic2_cpreport()` | 解析 critic2 `cpreport` JSON 的临界点、cell copies、connectivity、属性和 provenance，输出 `TopologyGraph`。 |
| `chemblender_prepare/core/qcschema_adapter.py` | `parse_qcschema_atomic_result()`、`parse_qcschema_molecule()`、`parse_qcschema()`、`export_qcschema()` | 原子梯度保留原符号与单位并绑定 Structure，View 可显式将负梯度展示为力；兼容 QCSchema v1/v2 结果和 Molecule envelope，在内部模型与版本化交换文档之间转换。 |
| `chemblender_prepare/core/cjson_adapter.py` | `parse_cjson()`、`preview_cjson_export()`、`export_cjson()`、`sniff_cjson()` | 把 Avogadro CJSON whitelist 映射到统一结构、拓扑、categorical identity、annotation 和轻量数据；保留原始 envelope，并以 `ExportReport` 控制大型数组省略。 |

### 派生计算、工作流与存储

| 文件 | 主要入口 | 职责 |
| --- | --- | --- |
| `chemblender_prepare/core/wavefunction_grid.py` | `evaluate_molecular_orbital_grid()`、`evaluate_electron_density_grid()`、`grid_evaluation_memory()` | 验证 basis/MO convention、实系数和占据数，延迟调用固定 GBasis；共享有界点块循环及内存估计，块间检查取消、成功后才返回完整 Grid3D；派生版本 2 保留父 Structure ID。 |
| `cbq_core/orbital_browser.py` | orbital_rows() | 轨道编号、能量、占据、spin、来源及已准备网格的只读投影。仅在数据充分时给出前线轨道标记，报告复数/spinor 不可求值；网格建议和计算内存估算位于外部模块。 |
| `chemblender_prepare/core/wavefunction_observables.py` | `derive_density_matrix_from_orbitals()`、`evaluate_density_matrix_grid()`、`evaluate_electrostatic_potential_grid()` | 从 one-RDM 分块求 electron/spin density，并用 total RDM 和显式有效核电荷求 ESP；拒绝核奇点、跨结构输入和无效矩阵。缺少 RDM 时，可根据显式 SCF/post-SCF level 从轨道占据数派生 total RDM 并记录来源，拒绝 NTO 权重误用；派生版本 2 保留 Structure ID。 |
| `chemblender_prepare/core/vibration_spectrum.py` | `derive_vibrational_spectrum()`、`derive_electronic_spectrum()` | 从振动强度或激发态强度生成 stick/高斯展宽 IR、Raman、UV-Vis、ECD `Spectrum`，记录派生身份。 |
| `cbq_core/phonon_frames.py` | `derive_phonon_frames()` | 根据复数 q-point eigenvector 和 `Re[e exp(i(q·R-ωt+φ))]` 生成周期超胞声子动画帧。 |
| `cbq_core/trajectory_frames.py` | `TrajectoryFrameManager.frame()`、`prefetch_around()`、`interpolate()`、`mean()` | 对 sidecar 轨迹执行逐帧 lazy 读取、有界 LRU 缓存、预取、插值和区间平均。 |
| `cbq_core/grid_lod.py` | volume_render_cache_key()、surface_render_cache_key() | Volume/Surface 显示缓存身份与 dataset 校验；科学 LOD 派生位于外部模块。 |
| `cbq_core/grid_sampling.py` | `sample_grid_points()`、`validate_plane()`、`validate_profile()`、`plane_slice()`、`line_profile()`、`export_grid_sample()` | NumPy 分块三线性采样完整仿射 Grid3D，显式 dataset/单位选择，越界为 NaN 与有效性 mask。平面/剖面共用科学采样，原子 CSV 导出记录原始坐标、数值、单位、来源和全部采样参数，不读取 Blender 变换。 |
| `cbq_core/grid_semantics.py` | builtin_grid_semantic_presets()、default_grid_isovalue()、validate_nci_pair() | 共享场语义定义、默认等值面阈值与 NCI 配对校验；科学网格解释、revision 和 provenance 派生在外部模块执行。 |
| `cbq_core/grid_cache_service.py` | `VolumeCacheRequest`、`CacheResult`、`prepare_volume_cache()`、`volume_cache_path()` | 不导入 Blender/OpenVDB 的 derived Volume cache transaction：计算 dataset/render identity 与 affine metadata，在 array load、slice、VDB population、publish 前后提供 progress/cancel checkpoint，以同目录短临时名验证后原子替换；cache hit 不重写，取消/失败保留既有目标并清理 staging。 |
| `cbq_core/model_registry.py` | `MODEL_TYPES`、`MODEL_ENUMS`、`model_type_tag()`、`model_type_from_tag()` | 明确登记 sidecar 可序列化的 dataclass 和 enum；以不可变映射固定 type tag 与具体模型类的对应关系。 |
| `cbq_core/sidecar.py` | `LazyNpyArray`、`save_project()`、`open_project()`、`close_project()` | `.cbq` v1 存储实现：写 generation metadata 与 canonical manifest hash，原子发布 manifest/数组；读取 v0.2/v1 hashed manifest 时先验证原始 hash/header，再以迁移副本严格 decode 并复验完整项目图，最后向内部 publication 返回未经改写的已验证 metadata。 |
| `cbq_core/sidecar_migrations.py` | `migrate_manifest()` | 在严格模型 decode 前复制已校验文档：把 v0.1/v0.2 升到 schema `1.0`，补实验期及 Wave 3 兼容新增 registry、atomic identity 与 lattice-shift 缺省，并把 Structure 内嵌 `MolecularTopology` 确定性提升为独立 `TopologyRecord`；不改写旧 fixture 或已发布 sidecar。 |
| `cbq_core/storage/atomic_paths.py` | `short_sibling_temporary_path()` | 为 NPY、JSON 和 VDB writer 生成同目录、完整随机 UUID 且不重复 content hash 的短原子临时路径，避免 Windows 临时路径预算被 basename 放大。 |
| `cbq_core/storage/hashing.py` | `sha256_bytes()`、`sha256_file_snapshot()`、`sha256_file()` | 为 preflight、Reader API source recheck 和延迟 snapshot 提供共享、可取消 SHA-256；Windows ≤256 MiB 输入使用系统 CNG one-shot 并保持 64 KiB 取消检查语义，其他平台或更大文件退回 stdlib streaming，不导入 Blender。 |
| `cbq_core/storage/publication.py` | `solidify_session()`、`inspect_publication_orphans()`、`PublishedProject`、`PublicationCancelled`、`PublicationRecoveryReport`、`PublicationRecoveryError` | 在目标同目录写入并复验完整 `.cbq` generation，经 backup rename 发布或非破坏回滚；可选 `progress`/`is_cancelled` 只在 atomic replacement 前允许取消并删除 owned staging，进入 replace/verify/rollback 后不再取消。默认关闭验证时打开的 project，仅在显式 opt-in 时把 final generation 的 exact verified project ownership 移交给事务；恢复不完整时同时保留原发布错误、回滚错误和不可变路径报告，不删除无法证明归属的目录。 在 staging 完成并校验后、原子替换之前关闭共享 lazy array mappings，避免 Windows 文件锁阻断目录重命名；失败恢复后仍可按旧路径延迟重开。 |
| `cbq_core/recipe.py` | `RecipeDefinition`、`plan_recipe()`、`recipe_document()`、`recipe_from_document()`、`builtin_recipes()` | 定义版本化分析 recipe 的输入语义、参数、输出、view、验证和引用；plan 阶段只绑定实体，不执行计算。 |
| `cbq_core/scene_preset.py` | `builtin_scene_presets()`、`grids_share_affine()`、`plan_scene_preset()`、`validate_scene_plan()`、`scene_preset_for_recipe_view()` | 定义 publication scene preset，包括科学平面、线剖面和独立色标；验证数据绑定和设置，并生成可重放的 render identity；property_on_surface v2 使用单 density 网格几何，旧版本 View 须显式重建；`grid_volume` 允许显示 ambiguous/partial Grid3D，`signed_isosurface` 允许 Complete 或 Ambiguous preview，后者由 presentation 层标记为不可报告。Property surface 两侧必须 shape/unit/Structure 完全一致，origin/step vectors 使用 `1e-9` source-coordinate-unit absolute tolerance，绝不隐式重采样。 |
| `cbq_core/analysis_report.py` | `build_analysis_report()`、`validate_analysis_report()`、`render_analysis_report_markdown()`、`write_analysis_report_bundle()` | 汇总 calculation、dataset、recipe、provenance、artifact 和引用，生成确定性 JSON/Markdown 报告包；沿科学实体及 source calculation 追踪真实 provenance，保留父身份且不读取数组或扩展 SourceRevision 的反向实体集合。 |
| `chemblender_prepare/core/external_connector.py` | `builtin_external_connectors()`、`ExternalRecordRequest`、`external_record_request_document()`、`external_record_source_uri()` | 定义 QCArchive/AiiDA/NOMAD 的 provider-neutral 请求、locator、凭据环境变量引用和脱敏 provenance URI。 |
| `cbq_core/worker_protocol.py` | `WorkerRequest`、`WorkerResult`、`write_request()`、`read_request()`、`write_result()`、`read_result()` | Blender 与外部 worker 共用的严格 JSON 协议；校验版本、operation、实体 revision、artifact 相对路径、错误和取消状态。 |

## 独立 Reader 示例

`examples/reader-extension/` 保留历史2.3的 Blender bootstrap 作迁移对照；当前
Viewer 不发布 Reader API handle。纯 reader.py 可在外部 Python 中使用显式
ReaderPluginDiscovery 注册；当前 CLI 默认只注册内置 reader，不自动发现第三方插件。
详见 [Reader API](../../docs/reader-api-v1/README.md#external-python-integration)。

## Extension 维护脚本

这些脚本随源码保存，但由开发者或 CI 调用，不在 Extension 运行时执行。

| 文件 | 主要入口 | 职责 |
| --- | --- | --- |
| `ChemBlender/benchmarks/__init__.py` | package marker | 声明 2.3.0 基准数据集 package；不导入 `bpy` 或在 import 时生成/测量数据。 |
| `ChemBlender/benchmarks/datasets.py` | `BENCHMARK_SCALES`、`generate_structure_xyz()`、`generate_trajectory_npy()`、`generate_grid_npy()`、`generate_sdf_fixture()` | 固定 seed 的 50k/250k structure、1k/100k lazy NPY trajectory、128³/256³ grid 和 10k/100k SDF 流式 fixture；生成时逐行或 memmap 写入，不构造大型 Python tuple，并返回 SHA-256。 |
| `ChemBlender/scripts/benchmark_230.py` | `CASE_REGISTRY`、`PreparedFixtures`、`run_benchmark()`、`canonical_json()`、`write_canonical_json()`、`main()` | 统一 2.3.0 benchmark 输出：每个 run 在计时外一次性准备 deterministic source/hash、lazy trajectory 和必要 batch；per-sample project/sidecar/browser setup 与 cleanup 均在计时外，首次 fixture access 是 cold、warmup 后至少两个 hot samples 记录完整 CPython environment、median/p95/min/max 和 failure count。只延迟调用已存在的 pure-core stage，Blender enable/VDB/default-view 显式为外部运行时边界，canonical JSON 原子写入且不导入 `bpy`。 运行时探针分别读取 Blender/RDKit/Gemmi，科学包导入失败记为 null，不丢掉可用的 Blender 版本；未配置可执行文件时全部未知。诊断报告允许未知，正式性能验收仍要求三项版本完整，不能用此探针修复替代真实性能测试。 |
| `ChemBlender/scripts/benchmark_230_product.py` | `PRODUCT_CASES`、`run_product_qualification()`、`worker_main()`、`main()` | 仅供开发与发布资格审查的 exact-ZIP 产品性能 harness；orchestrator 为六个固定 interactive gate 启动独立 Blender 进程和隔离 profile，保存逐命令 stdout/stderr/timing，并用 `benchmark_230.py` 的 fail-closed schema/budget comparator 生成 canonical JSON/Markdown。Blender worker 只从 `bl_ext.user_default.chemblender` 导入已安装产品，校验 ZIP SHA 和 module origin，覆盖真实 Import Preview、Structure preset、OpenVDB、`TrajectoryFrameManager` mesh update 与 10k SDF Browser 路径；该脚本由 manifest 排除，不进入扩展包。 |
| `ChemBlender/scripts/benchmark_cube_flow.py` | `generate_cube()`、`run_benchmark()`、`main()` | 生成不入库的 128³ Cube，以真实 Blender/OpenVDB 路径分别测量 parse、NPY staging、sidecar save、cold/hot VDB 和 hot Volume view 的 samples/median/p95，并记录 peak Python allocation、硬件、cache 状态与 10 s 产品流门限。 |
| `ChemBlender/scripts/benchmark_crystal.py` | `benchmark_crystal()`、`main()` | 以固定 CIF/POSCAR 和合成 1000-site CIF 记录 Reader API preview、对称展开、10×10×10 supercell、POSCAR import 与真实 Blender periodic view 的 samples/median/p95、tracemalloc peak 和硬件环境；非 Blender 运行必须把 view 明确记为 `Not Run`。 |
| `ChemBlender/scripts/benchmark_exchange.py` | `benchmark_exchange()`、`main()` | 逐行生成 50k-atom MOL2/PDB/PQR/CJSON，记录 native parse 与 Reader API preflight/staged summary 的 cold/median/p95、`tracemalloc` peak、source bytes、硬件和 draw-path 边界；无 `bpy` 的 CLI 必须将 Blender RNA projection 记为 `Not Run`。 |
| `ChemBlender/scripts/validate_extension.py` | `main()` | 检查 manifest、共享 release version grammar、无科学 wheel 的依赖策略、绝对 import 和源码布局；非法 release version 是本地 preflight error，再调用 Blender 原生 Extension validate。 |
| `ChemBlender/scripts/release_metadata.py` | `ParsedReleaseVersion`、`parse_release_version()`、`ReleaseMetadata`、`read_release_metadata()`、`release_metadata_document()`、`workflow_run_records_from_pages()`、`select_exact_package_run()`、`select_exact_package_artifact()`、`main()` | 以单一 strict parser 定义 Blender 已验证的 stable/alpha/beta/rc version grammar；从 production manifest 严格读取 extension id、version 和单一 Windows platform，并确定性派生 package、checksum 与 artifact 名称；同时以标准库 JSON 展平全部 REST workflow-runs 分页响应，严格读取 `id`、`head_sha`、`head_branch` 并选择唯一 exact-SHA successful tag package run，CLI 输出其 `run_id`；artifact 选择保持唯一未过期 metadata-named REST artifact；不导入 Blender 或执行构建。 |
| `ChemBlender/scripts/probe_prerelease_version.py` | `probe_prerelease_version()`、`main()` | 把 Extension 复制到自动清理的临时目录，排除本地构建产物、缓存、Git metadata 和 wheel 目录，仅替换副本中的单一 manifest version，再调用 Blender 原生 validate 记录预发布版本兼容性；不修改 production manifest。 |
| `ChemBlender/scripts/build_extension.py` | `main()` | 解析 Blender/Python/MCP 路径与系统兼容性，读取一次 `ReleaseMetadata`，先验证再调用 Blender 原生 Extension build，并要求 metadata 指定的 exact package 文件存在。 |
| `ChemBlender/scripts/dependency_inventory.py` | `inventory()`、`main()` | 读取固定 `dependencies.toml`；正式 Viewer 的空依赖数组必须与无 `wheels` manifest 一致，并确定性生成空 wheel inventory 与 license copy list。通用校验仍对未来显式依赖严格检查 SHA-256、ZIP 路径安全、许可证来源和压缩/解压预算；不下载、安装、解压或删除依赖。 |
| `ChemBlender/scripts/generate_format_docs.py` | `render_documents()`、`_prepare_export_ids()`、`main()` | 开发时生成确定性格式/依赖JSON及Markdown表；AST读取外部CLI的真实--format choices并校验能力矩阵导出ID一致，当前生成空 Viewer 依赖库存且不执行解析或依赖安装。--check比较生成字节。 |
| `ChemBlender/scripts/artifact_size_report.py` | `build_report()`、`canonical_json()`、`main()` | 复用依赖清单的 ZIP 安全成员校验，在不解压到磁盘的前提下记录 package SHA-256/bytes、互斥的 code/resources/wheels/other 外层成员、嵌套 wheel hash/大小/许可证证据及基线差异；严格执行版本化 package/new-wheel budget，并原子写出 canonical JSON。 |
| `ChemBlender/scripts/run_required_integration.py` | `run_required_modules()`、`main()` | 可选量子后端 CI 的标准库 unittest runner：只加载显式模块名，先校验版本锁（可由 `--require-version-file` 读取并逐项经 `importlib.metadata` 验证）与受工作目录约束的 fixture SHA-256，再记录 required/actual runtime version、稳定 test ID/count 和 fixture hash 的 canonical JSON；仅 ordinary pass 可成功，任一 skip、expected failure、unexpected success、subtest failure/error、load error、零发现、fixture/version preflight、failure 或 error 均以非零退出。 |
| `ChemBlender/scripts/verify_release_artifact.py` | `verify_artifact()`、`main()` | 使用同一 `ReleaseMetadata` 和 shared release version parser 校验 stable/prerelease tag、Release ZIP/checksum 名称、SHA-256、共享 ZIP 路径安全、必需/禁止内容和 manifest contract；两个 metadata mode 均先以 tagged-source outer ZIP budget 限制中央目录元数据，再进行 CRC 或成员读取；`package-ci` 还重算并绑定 canonical artifact-size、wheel inventory 与 license copy list，`release-assets` 只允许 ZIP/checksum。 |
| `ChemBlender/scripts/extract_release_notes.py` | `extract_release_notes()`、`main()` | 先经 shared release version parser 校验 stable/prerelease version，再从 `CHANGELOG.md` 精确提取一个 dated、非空 Release body。 |
| `ChemBlender/scripts/benchmark_extxyz.py` | `generate_extxyz()`、`run_benchmark()`、`main()` | 以确定性多帧 extXYZ 与 metadata-only 轨迹分别记录 first-frame decode、真实 reader/staged-batch/summary `preview_ready`、parse、sidecar write、single-frame access、export 的 sample/median/p95、tracemalloc peak、硬件与 cache 状态；只有 `preview_ready` 评估 Quick Import budget，同时验证 staging cancellation cleanup、publication rollback 和不构造嵌套 frame tuple。 |
| `ChemBlender/scripts/benchmark_sidecar.py` | `run_benchmark()`、`main()` | 对代表性结构、轨迹、轨道和网格 `.npy` 写入/打开/切片性能进行基准测量。 |
| `ChemBlender/scripts/benchmark_topology.py` | `run_benchmark()`、`main()` | 以 25k/50k 稀疏原子生成器记录非周期空间 cell-list 推断的 median、p95 和倍增比例，并执行 50k/3s 与低于三倍的倍增门。 |

## 外部 worker

worker 使用调用者明确提供的 Python 环境。默认 registry 只接受固定 operation，request 不能指定任意 module、callable、shell 或 argv。

| 文件 | 主要入口 | 职责 |
| --- | --- | --- |
| `chemblender_prepare/worker/__init__.py` | 包标记 | 声明独立 worker package；没有运行逻辑。 |
| `chemblender_prepare/worker/protocol.py` | re-export | 从 `cbq_core.worker_protocol` 重导出协议，使 runner 与 Blender client 使用同一数据契约。 |
| `chemblender_prepare/worker/operation.py` | `OperationContext`、`OperationOutput`、`OperationError` | 定义 operation 的项目/任务目录上下文、待提交 batch/artifact/metadata，以及稳定错误码；无项目的 reader operation 只使用任务目录。 |
| `chemblender_prepare/worker/reader_operation.py` | `register_reader_operation()` | 注册固定 `reader.parse@0.1`：只接受 exact 参数白名单和任务目录内来源 artifact，从内置 Reader registry 解析，写入并重开自有 `reader-bundle` canonical document，再经内部 batch 图校验后发布 hashes 及完整 created-entity references；取消或失败时安全清理本次新建 bundle，不写冻结输入 sidecar。 |
| `chemblender_prepare/worker/fermi_operation.py` | `register_fermi_surface_operation()` | 注册 periodic.fermi_surface@1；验证任务内 VASP 白名单文本路径及哈希，再在私有目录调用 PyProcar 文件适配器，完整成功后才返回中立科学 ImportBatch。 |
| `chemblender_prepare/worker/molecule_operations.py` | `register_molecule_operations()` | 注册固定 `molecule.smiles_to_3d/kekulize/optimize/energy/export@1`；从 CBQ Structure/Topology/Record 临时重建 RDKit Mol，复用 ETKDG/MMFF/UFF 与既有导出器，返回新实体或受控 artifact。势能为带单位标量 PropertyDataset；导出要求显式损失确认；取消/失败不发布半成品，RDKit Mol 不持久化。 |
| `chemblender_prepare/worker/professional_operations.py` | `register_professional_operations()` | 注册固定`topology.qtaim/periodic.phonon/grid.nci_fields@1`。冻结并复验WFX或phonopy YAML/FORCE_SETS/BORN的路径与SHA-256；复用critic2、phonopy和Cube适配器发布TopologyGraph、PhononModeSet或关联RDG/signed-density Grid3D，并记录实际后端与来源。 |
| `chemblender_prepare/worker/runner.py` | `OperationRegistry`、`run_request()`、`default_registry()`、`main()` | 默认 operation 打开任务 sidecar、校验输入 revision、原子提交并重开复验；固定 `reader.parse@0.1` 从任务 artifact 解析后创建独立 `reader-result.cbq`，复验 batch 与 output inventory，绝不覆盖冻结请求项目。两者均检查取消，在结果写入失败时仅清理本任务新建的 bundle/result，并在输出验证后发布 result。 |
| `chemblender_prepare/worker/wavefunction_operations.py` | `register_wavefunction_operations()` | 注册 MO、occupation density、RDM density/spin、ESP 与 occupation-derived ESP 的薄适配操作；复用取消回调、任务目录进度和 ImportBatch；进度写入短暂 PermissionError 不影响数值结果，后续块继续尝试。派生 total RDM 与 ESP 一次返回，失败不发布中间矩阵。 |
| `chemblender_prepare/worker/qcengine_operation.py` | `execute_qcschema()`、`qcschema_compute_operation()`、`register_qcschema_compute_operation()` | 注册 `qcschema.compute@1`；受控调用 QCEngine 或最小 PySCF HF/RHF/UHF adapter，将成功结果统一转回 AtomicResult。 |
| `chemblender_prepare/worker/connector_operation.py` | `external_record_operation()`、`register_external_record_operation()` | 注册 `external_record.fetch@1`；当前完成离线 QCSchema/CJSON replay、凭据检查、内容寻址 artifact 和脱敏 provenance。 |
| `chemblender_prepare/worker/external_program.py` | `ExternalAdapterDescriptor`、`ExternalInvocation`、`run_external_program()`、`critic2_invocation()`、`multiwfn_invocation()` | 为 critic2/Multiwfn 构造固定、安全、`shell=False` 的进程调用；处理 timeout/cancel、日志 hash、缺失/陈旧输出和版本探测。 |

## 阅读建议

- 想理解数据边界：先从 `model/__init__.py` 找到对应领域模块，再读 `readers.py`、一个具体 reader 和 `sidecar.py`。
- 想增加文件格式：阅读 `docs/development/import-pipeline.md`，复用 `ReaderDescriptor`，返回 `ImportBatch`，不要从 parser 直接创建 `bpy` 对象。
- 想增加物理量：先扩展 `PropertyDataset` 语义和 provenance，再添加派生函数与 Blender adapter。
- 想增加 Blender 显示：从 `dataset_view.py`、`grid_volume.py`、`surface_view.py` 或 `scene_preset_view.py` 选择最近的现有 contract。
- 想增加重型计算：在 `chemblender_prepare/worker/` 注册固定 operation；不要让 Extension import、安装或同步运行重型后端。
- 想修改发布流程：阅读 `docs/development/release-2.3.md`、`docs/development/testing-and-ci.md` 和 `.agents/reference/dependencies-and-release.md`，不要只验证 ZIP 是否生成。

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

### 外部旧项目迁移模块

`chemblender_prepare/legacy/` 保留旧 `.blend` 的检测、快照和科学数据事务逻辑，不进入 Extension ZIP。仅检测/提取阶段依赖 Blender；普通 Python 可校验快照并规划和提交 CBQ。专用 Blender 脚本可导出 project.cbq 与独立显示恢复报告；View 参数自动恢复仍待接通。

| 文件 | 入口 | 职责 |
| --- | --- | --- |
| `chemblender_prepare/legacy/__init__.py` | public exports | 导出历史快照与迁移接口；普通导入不加载 bpy。 |
| `chemblender_prepare/legacy/detection.py` | `detect_legacy_scene()` | 在 Blender 中识别旧 scaffold/crystal，排除当前 View 和已归档备份。 |
| `chemblender_prepare/legacy/extraction.py` | `extract_legacy_objects()` | 提取坐标、键、显示属性及来源哈希；晶体读取期间借助临时历史 RNA schema，结束清理。 |
| `chemblender_prepare/legacy/migration.py` | `plan_legacy_migration()`、`commit_legacy_migration()` | 使用唯一 cbq_core 模型，复验来源、候选和基础项目内容，事务发布科学实体。 |
| `chemblender_prepare/legacy/cif_schema.py` | `legacy_cif_schema()` | 仅在私有 Blender 迁移进程临时注册原 CIF 字段及默认值；拒绝覆盖已有 Object 属性，不包含解析器。 |
| `chemblender_prepare/legacy/export.py` | `export_legacy_scene()` | 在临时目录写 CBQ、复验数组与来源哈希，和独立显示报告一起发布新目录；支持只读预览及取消，不加载科学后端。 |
| `chemblender_prepare/legacy/__main__.py` | `main()` | Blender --python 专用入口，解析输出/预览/取消参数，不注册 Viewer 或旧插件。 |
