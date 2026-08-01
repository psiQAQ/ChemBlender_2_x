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
4. `sidecar.py` 将项目元数据写入 v1 manifest，将大型数组写入 `.npy`；v0.1/v0.2 只在内存中迁移后读取。
5. Blender adapter 根据实体 UUID/revision 创建临时 Mesh、Curve、Volume、Material 或 Geometry Nodes。
6. 重计算任务通过 `worker_client.py` 启动独立 Python；worker 只在成功并复验结果后更新 sidecar。

## Extension 入口与基础数据

| 文件 | 主要入口 | 职责 |
| --- | --- | --- |
| `ChemBlender/__init__.py` | `register()`、`unregister()` | Extension 最小入口；只延迟委托给 `runtime.registration`，不保存 Blender class、callback 或 Reader API handle 状态。 |
| `ChemBlender/auto_load.py` | `get_ordered_classes_to_register()`、`toposort()`、`_safe_register_class()`、`_safe_unregister_class()` | 只分析显式模块中的 Blender class 依赖、执行拓扑排序并提供安全 class 注册/注销；不扫描 package、不清 import cache，也不是第二条生产注册路径。 |
| `ChemBlender/runtime/__init__.py` | package marker | 隔离依赖 Blender host 状态的 runtime bridge；导入该 package 本身不加载注册实现或触发注册副作用。 |
| `ChemBlender/runtime/registration.py` | `REGISTER_MODULE_NAMES`、`register_extension()`、`unregister_extension()` | Blender 注册唯一 owner：按实际 package root 导入显式传统 UI/operator/handler 根（包括 diagnostics、topology、biological、scientific-edit、export 与 grid），去重并拓扑注册 class，再执行 module callback、最后发布 Reader API handle；注册一条自有 persistent `load_post` 以在 Blender 清空 driver namespace 后重新发布同一 handle并刷新既有 Reader discovery snapshot，不扫描 module 或重注册 Blender class；卸载与失败回滚只反向清理自有状态并把 cleanup failure 作为原异常 note 保留。未来 Blender UI 模块必须显式加入清单和 lifecycle 测试，pure core、Reader API 与 optional stack 不参与注册扫描。 |
| `ChemBlender/runtime/reader_api_bridge.py` | `ReaderAPIHandle`、`register_reader_api_handle()`、`remove_reader_api_handle()`、`get_reader_plugin_registry()`、`refresh_reader_plugin_discovery()` | 以实际安装 package root 构造 Reader API 模块名，在 `bpy.app.driver_namespace` 发布由模块私有 identity 和不透明 token 共同约束的版本化 handle；稳定 wrapper callback 把外部插件显式注册/注销统一委托给单一 discovery owner，由 registry 保持内置 reader 不可替换，reserved-ID collision 则形成可见且可清理的 unavailable state；普通 enable/disable 只更换自有 handle，持续复用 registry、内置 reader 对象、discovery 状态和公开模型 class identity；内部 accessor 让主进程导入管线复用同一 registry，但不把 registry 交给插件；模块导入保持 `bpy`-free，仅调用 bridge 时访问 Blender。 |
| `ChemBlender/ui/__init__.py` | package marker | 声明 Blender UI package；不导入 Blender、注册 root 或科学模型。 |
| `ChemBlender/ui/tasks.py` | `Task`、`TaskProgressAdapter`、`TaskWorker` | 不导入 `bpy` 的线程安全任务状态边界：严格表示 pending/running/cancelling/cancelled/failed/succeeded、单调阶段进度与失败；把嵌套的 reader/worker event 映射为单调 UI 进度，并只把纯 callback 放入 daemon worker。Blender timer/操作符在主线程读取不可变 snapshot、请求取消并决定何时写 RNA 或 datablock。 |
| `ChemBlender/ui/session.py` | `get_scene_session()`、`new_scene_session()`、`close_scene_session()`、`register_session_cleanup()`、`register_session_mutation()`、`register()`、`unregister()` | 用一个显式 owned entry 管理当前已加载 `.blend` 的共享 `ProjectSession`，所有 Scene 经兼容入口 `get_scene_session(scene)` 取得同一科学项目与临时根；Scene 只保留状态/显示投影，不拥有独立项目。load/unregister 只 drain 一次共享 entry，失败保留 recovery entry 供重试；会话替换或关闭前调用全部已注册 UI cleanup，并在失败时保留可重试所有权。`load_post` 对无 link、相同 link、一个有效 link 加空 Scene 和冲突有效 link 分别执行空会话、一次采纳、统一投影和 fail-closed；`save_pre` 对 scientific/unknown dirty reason、无 sidecar 或 Save As 执行完整 publication，对 clean connected、新空 Scene、`project_link` 或 `view_cache` retry 先只读复验现有 sidecar 再同步 Scene link，成功连接后才调用 derived View cache repair，绝不为纯 cache retry 重新 publication。跨目录或重命名 Save As 在 publication 前仅捕获 connected 的 previous sidecar，并作为一次性 fallback context 传入 cache repair。新建/替换以及成功采用 sidecar 后通知小型 UI projection invalidator，失败或无效恢复不通知；脏会话关闭时只写一个非权威 recovery marker 并保留临时根，干净会话关闭时释放 lazy resource 与受控临时根。 |
| `ChemBlender/ui/view_cache.py` | `repair_project_view_caches()` | 仅扫描带完整 scene preset binding/settings/render identity 的 ChemBlender-owned Volume，从 verified `session.sidecar_path` 推导 `<sidecar>/cache/render/` 目标并 fail-closed 校验 UUID/revision/cache identity；在任何 writer/read 前拒绝最终 VDB link/junction，缺失或损坏 VDB 调用既有 adapter 重建，成功后写相对 `.blend` RNA 路径。失败事务始终保留 `view_cache` retry；只在旧路径位于 owned session `view-cache/` 或 verified sidecar `cache/render/` 且 VDB identity 匹配时重新加载，绝不访问任意 `cb_cache_path`、UNC 或外部旧路径。Save As 新 cache promotion 失败时，以一次性 previous sidecar context 和当前 verified render identity 推导、只读验证旧 durable VDB，再相对新 `.blend` 重投影其 filepath；不解释旧 `//...`，也不向旧 sidecar 写入或重建 cache。 |
| `ChemBlender/ui/properties.py` | `CHEMBLENDER_PG_quick_import`、`CHEMBLENDER_OT_derive_crystal_symmetry`、`CHEMBLENDER_OT_view_standardized_structure`、`crystal_symmetry_property_sections()`、`QuickImportUIState`、`get_quick_import_state()`、`advance_browser_revision()`、`store_quick_import_preview()` | 只把 validation mode 与最近摘要等小型显示状态放入 Scene RNA，并以 RNA property `as_pointer()`（测试环境回退到对象 identity）精确记录 `Scene.chemblender_quick_import` 所有权：拒绝覆盖预先存在的 foreign property，卸载也不删除后来替换的 foreign property。周期 Structure 的 declared/derived/comparison symmetry 分区只投影小型文本；spglib 缺失时禁用显式 derive action并显示原因，派生成功只提交独立 `SymmetryResult`/standard Structure、不改源 Structure；用户可为 standard Structure 创建独立 View，源 View 不删除。`ImportPreview`、`StagedImportSession`、live conflicts/source grouping/conformer grouping suggestions、canonical diagnostics document、显式 revision prompt、browser revision 与 active import job 保持在按 `ProjectSession.id` 归属的内存状态中；staging 清理后保留最近一次 canonical diagnostics 和未决 revision prompt，绝不把完整报告写入 RNA。成功 import/view 与 session project adoption 共用单一 revision helper 使 Project Browser cache 失效。staging 创建后立即取得所有权；替换、会话关闭、文件加载与卸载时先取消并等待正在发布的 commit owner 安全退出，再显式 discard staging root，清理失败则保留状态供重试。 |
| `ChemBlender/ui/quick_import.py` | `CHEMBLENDER_OT_quick_import`、`CHEMBLENDER_OT_import_smiles_text`、`CHEMBLENDER_PT_quick_import` | 多文件选择器、FileHandler 注入的 transient 路径或显式 SMILES 文本经相同安全校验确定性构造共享 `ImportRequest`；有效 drop 路径与 SMILES 直接进入既有 staging，手动文件调用仍打开 File Browser，且本次 drop 后清空路径避免复用。Quick Import 只在 host-owned 闭包中调用 `attach_verified_pubchem_provenance()`；同步与 modal worker 复用该闭包，使每次 preview/materialization 对当前 `ProjectSession` 的受控 PubChem source 复验 URL、metadata 与实际 SHA-256，再把确定性 provenance 附加到 batch，绝不接收 operator RNA provenance claim 或把 legacy 语义写入 canonical parameters。仅通过 Reader API registry accessor 调用 `preflight_reader_plugins()` 并暂存 preview。交互模式把可能超过 1 秒的 preflight、SDF indexing/parse 与 conformer suggestion 预计算放入同一可取消 worker，经 `Task` 映射为单调小型进度，再由 modal timer 在主线程更新 Blender progress；完成后以 session-owned 缓存打开 Import Preview，background 模式保持同步。N 面板只显示 task snapshot 的阶段/进度/取消入口，不写入 batch/array RNA；同模块还显示 session/link/dirty、文件/SMILES import、review、保存与 workspace fallback。 |
| `ChemBlender/ui/default_views.py` | `DefaultViewPlan`、`plan_default_view()`、`describe_default_view()` | 纯 UI planner；只按一个 SourceRevision 已创建的 entity UUID、Grid3D 状态与 semantic role 选择 `structure_publication`、`grid_volume` 或 `signed_isosurface`，不导入 `bpy`，也不把 view plan 写入科学模型或 sidecar schema。 |
| `ChemBlender/ui/diagnostics.py` | `QualityPresentation`、`RevisionViewPrompt`、`quality_presentation()`、`diagnostic_detail_rows()`、`canonical_report_text()`、`project_recovery_actions()`、`detach_project_links_for_scenes()` | `bpy`-free 的共享 UX 契约：五态质量恒有文字与不同 icon，颜色只作补充；diagnostic detail 和 Copy/Export 直接复用 import report schema/Markdown validator，不定义第二套报告；revision prompt 仅持有 current/new revision UUID 并默认 Keep Current，执行操作时从 live preset bindings 唯一且 fail-closed 推导 replacement；link recovery action 由 live status 限定，多 Scene Detach 仅原子删除四个 link 字段并在失败时全量回滚，绝不删除 Blender object。 |
| `ChemBlender/ui/import_preview.py` | `CHEMBLENDER_PG_import_preview_row`、`CHEMBLENDER_PG_import_conflict_candidate`、`CHEMBLENDER_PG_import_grouping_suggestion`、`CHEMBLENDER_PG_import_conformer_suggestion`、`CHEMBLENDER_OT_confirm_import`、`CHEMBLENDER_OT_apply_poscar_species`、`CHEMBLENDER_OT_cancel_import`、`project_import_preview()`、`unavailable_reader_plugin_status()`、`restage_poscar_species_assignment()`、`project_grouping_suggestions()`、`project_conformer_suggestions()`、`commit_project_import()` | 将 staged preview、reader availability、共享五态 quality、format-aware default view、extXYZ frame/property/cell/PBC/assumed-unit 摘要、molecular record/version/recovery/topology/property 摘要、MOL2 molecule/atom/bond/type/charge/unsupported-section 摘要、Cube Grid 摘要、CIF block/site/cell/occupancy/ADP/disorder/declared-symmetry 摘要，以及 POSCAR comment/scale/cell/species/count/mode/Selective Dynamics/velocity 摘要投影为小型 RNA 行；另把 discovery 中失败的外部 Reader plugin 投影为只读 unavailable 文本，不让它进入 reader selection 或提交行。VASP 4 缺失 species 时 fail-closed，通过既有 Reader API canonical parameters 在新 staging generation 中原子重解析 ordered assignment，成功后才替换旧 preview。科学数组、完整 records 与未截断 evidence 留在 session-owned Python state。Source 与 conformer grouping 均默认 Keep Independent；确认前重检 live snapshot，并经单一 `ImportCommitDecisions` 进入 `commit_import_preview()`。提交科学数据后在 Blender 主线程把 committed revision 的纯 `DefaultViewPlan` 转为真实 `ScenePresetPlan`；`NEW_REVISION` 只生成显式 revision prompt，绝不自动创建或切换 View；任一 view 失败只删除本次 attempt 创建对象并明确报告，不伪称科学事务已回滚。 |
| `ChemBlender/ui/extxyz_preview.py` | `ExtXYZPreviewSummary`、`extxyz_preview_summary()` | 不依赖 Blender 的 extXYZ Import Preview 摘要边界；只读取 entity 类型、shape、semantic role、cell/PBC 和 diagnostics，不读取科学 array values，由真实 UI 与 benchmark 共享。 |
| `ChemBlender/ui/project_browser/__init__.py` | `BrowserMode`、`BrowserRow`、`ViewRecord`、`build_browser_rows()`、`clear_browser_session_cache()`、`clear_browser_caches()` | 公开纯 Python Project Browser 投影与 cache 生命周期入口；不导入 `bpy`，不触碰 scientific array payload。 |
| `ChemBlender/ui/project_browser/model.py` | `BrowserMode`、`BrowserRow`、`ViewRecord`、`build_browser_rows()`、`clear_browser_session_cache()`、`clear_browser_caches()` | 从 `QCProject` registry 与独立 presentation `ViewRecord` 生成 By Source/By Data 确定性 flat tree；By Data 将 frame/atom/cell properties 归入其 `FrameSet`，将匹配 record inventory 的 typed columns 归入 `ConformerSet`，独立显示 raw `MolecularRecord`，并以唯一 Biological Hierarchies group 展开 chain/residue/atom count 小型摘要；chain/residue detail row 携带所属 BiologicalHierarchy UUID，可继续作为真实科学选择。周期 Structure 增加只读 site count、occupancy/disorder 与 Uiso/Uij availability 子行，但不读取 scientific array payload。TopologyRecord 行显示 source、quality、bond count、inference parameters 与 view count。ViewRecord 显式携带 derived view quality 与 report eligibility，ambiguous Surface 不进入报告。By Source 的 row ID 包含完整 parent path并在同一 parent 内确定性去重，空项目也返回显式 empty row；view 只有在 entity UUID 与 revision 同时匹配时关联，投影后的 BrowserRow 以兼容默认字段保留 `view_kind`，让小项目搜索保留与 large generator 相同的 view-kind 语义。小项目保留完整 tuple API；当总可索引条目超过 page size 或估算 row 开销超过 1000 时，使用 `page`/`page_size` 有界投影；无 molecular records 的大项目也生成 generic result page，未被 entity/diagnostic 覆盖的 standalone source 与 empty revision branch 作为轻量 sentinel 进入同一 By Source 索引和 pager，mixed project 的默认页以精确 summary 暴露并可搜索到它们。搜索与 filter 单遍扫描预排序的 By Source/By Data 轻量索引，只保留当前页；ViewRecord label/kind/quality 在本次 generator 消费时动态匹配，view-only 命中只显示匹配 view，entity 命中才显示全部 sibling views。row cache 由 browser revision 失效；最多两个索引由 project/session、运行时 project identity 与 registry/source/revision/diagnostic 数量的结构签名失效，纯 browser revision 变化复用索引。两类持久 cache 都只在 non-empty session ID 与精确非负 browser revision 同时可靠时启用，可按 session 或整体释放，且不持有 project、scientific entity 或 lazy array。 |
| `ChemBlender/ui/project_browser/panel.py` | `CHEMBLENDER_UL_project_rows`、`CHEMBLENDER_PT_project_browser`、`CHEMBLENDER_OT_project_browser_page`、`CHEMBLENDER_OT_diagnostic_page`、`CHEMBLENDER_OT_copy_diagnostics`、`CHEMBLENDER_OT_export_diagnostics`、`CHEMBLENDER_OT_revision_view_action`、`CHEMBLENDER_OT_project_link_recovery`、`presentation_view_records()`、`refresh_project_browser()` | 在 Blender 主线程严格解析 object 的 scene-preset binding 与 selected topology UUID/revision metadata，投影为 presentation-only `ViewRecord`，并只接受 model 返回的最多 1000 行有界页复制到小字符串、整数与枚举 RNA；record/result page 共用 total/page/page-count metadata、Prev/Next/Jump 与通用 entry label，不静默截断 model rows。面板复用共享五态 badge，分页显示有界 draw-time diagnostic preview；Copy/Export 以同目录短 temp 原子导出或复制完整 canonical Markdown/JSON。revision flow 明示 current/new UUID；Keep Current 不改 View，Comparison 新建并保留旧 View，Update Selected Views 仅在新 View 成功后隐藏旧 View，任一失败回滚新对象和 visibility。link recovery 在 execute 时复验 live status；Relink/Verify 委托现有多 Scene service，Inspect Existing 仅进入“不采用/不写候选”的 inspection 状态且不声称全局写保护，Detach 只清 link metadata 并保留对象。注册时将 per-session cache clear 接入既有 session cleanup；卸载可先清空 Browser cache，但只在所有 owned RNA property 成功 teardown 后解除 callback，partial teardown 失败保留 callback，register retry 会重建缺失 property 并确认 callback。UIList 只允许当前 project scientific registry 中的 UUID 更新 `ProjectSession.active_entity_id`，过滤隐藏的有效选择继续保留，stale/malformed/group/view/empty 选择清空。面板为选中的周期 Structure 分区显示 source-declared 与独立 spglib-derived symmetry，以当前 frame 的 force vector 调用既有 dataset vector-view writer；MOL2 substructure action 直接复用 `CategoricalData` code、既有 atom scalar coloring 与 `cbq_selected` attribute，不把分类数组复制进 RNA；biological controls 复用独立 UI root，以小型 RNA 输入驱动 hierarchy selection、altloc filter、property threshold 与 MODEL playback。Structure、FrameSet、ConformerSet 与 MolecularRecord 选择调用显式 export root；以私有 module alias 复用 diagnostics、topology、biological、scientific-edit 与 grid controls，且精确拥有 `Scene.chemblender_project_browser` 与 `Scene.chemblender_topology`，不覆盖或删除 foreign property。 |
| `ChemBlender/ui/grid.py` | `grid_preview_summary()`、`resolve_grid_selection()`、`grid_action_availability()`、`plan_grid_view()`、`CHEMBLENDER_OT_resolve_grid_semantics`、`CHEMBLENDER_OT_create_grid_view` | Cube/Grid 的显式 Blender registration root；Preview 只读取每个 dataset 的有界样本并投影小型摘要。Resolve 委托 pure core 生成确定性派生 Grid3D 后提交项目，保留 raw ambiguous grid；Volume、signed surface 与 property-on-surface 操作只生成并应用既有 ScenePresetPlan，完整/affine 不匹配时禁用。交互 Volume cache 以共享 `TaskWorker` 调用既有 pure `prepare_volume_cache()`，可在 atomic publish 前取消并清理 temp；worker 只返回 ready cache result，Blender datablock 只在主线程 completion 执行；Scene RNA 仅保存 dataset index、preset、unit 与 isovalue。 |
| `ChemBlender/ui/export.py` | `resolve_export_selection()`、`preview_export_selection()`、`ExportJob`、`CHEMBLENDER_OT_export_project_entity` | XYZ/extXYZ/MOL/SDF/SMILES/CIF/POSCAR 导出的显式 Blender registration root；只把路径、格式、确认和有界 export-plan 摘要放入 RNA。主线程只从 Project Browser 的科学 entity UUID 解析 Structure、FrameSet、MolecularRecord 或 ConformerSet，不读取 evaluated/supercell Blender geometry；周期 Structure 的预览明确列出 source/derived identity、输出路径和 preserved/changed/omitted 字段，CIF 提供 Preserve/Normalized，POSCAR 提供 comment、坐标、scale/target-volume、Selective Dynamics 与 velocity 设置。Partial/Ambiguous 或有损计划必须显式确认。周期 Structure 精确绑定 CIF envelope，或按同一 source/provenance 绑定 POSCAR Selective Dynamics 与 ion/lattice velocities。ConformerSet preview 只读取 metadata，派生与序列化统一留在 worker。modal timer 在主线程更新 progress/cancel，取消或失败由 exporter 清理 sibling temp。 |
| `ChemBlender/ui/topology.py` | `TopologyChoice`、`TopologyInferenceJob`、`compute_topology_proposal()`、`record_topology_decision()`、`CHEMBLENDER_OT_compute_topology`、`CHEMBLENDER_OT_accept_topology`、`CHEMBLENDER_OT_reject_topology`、`CHEMBLENDER_OT_switch_topology` | 将 nonperiodic/periodic distance inference 作为确定性 proposal 提交到既有 `QCProject`；交互式推断在 background job 中只准备候选，取消不改项目，main thread 才 commit。Accept/Reject 以 canonical Scene JSON 保存 presentation decision，proposal 历史仍在项目中。Switch 只更新当前 Structure view edge/display identity；不修改源 Structure 或旧 TopologyRecord。 |
| `ChemBlender/ui/biological.py` | `biological_selection_indices()`、`resolve_biological_context()`、`require_live_biological_view()`、`plan_biological_view()`、`altloc_filter_mask()`、`CHEMBLENDER_OT_create_biological_view`、`CHEMBLENDER_OT_select_biological_atoms`、`CHEMBLENDER_OT_play_biological_models` | 从 Project Browser 真实选中 entity 解析同 revision Structure、BiologicalHierarchy、AtomicProperty、FrameSet 与可选 TopologyRecord；每次操作前以共享 snapshot guard 校验 view identity、hierarchy revision、category hash、dataset binding 及实际 POINT attribute 的 type/count/value，foreign/stale/remapped view fail-closed。Chain/residue/atom/altloc/property threshold 仅写 view-owned `cbq_selected`/`cbq_visible`；altloc 同时更新 visibility、filter 与 selection，任一步失败即回滚原快照；default altloc 选择 blank 或最大有效 occupancy，MODEL 复用既有 trajectory manager。默认显示按 topology 与 atom count 选择 atom points 或 ball-and-stick，不实现 ribbon/cartoon、secondary structure 或 biological assembly。 |
| `ChemBlender/ui/scientific_edit.py` | `preview_structure_object_edits()`、`CHEMBLENDER_OT_apply_scientific_edits` | 从 canonical Structure view 的 object-local Mesh 与 named attributes 投影科学 edit 输入，因此 Object transform 保持 presentation-only；对话框显示 atom/coordinate/element/bond/cell diff、最大位移和不继承的关联 dataset 数，确认后创建新的 Structure view，可选导出 derived XYZ，取消不修改项目。 |
| `ChemBlender/ui/file_handlers.py` | `CHEMBLENDER_FH_view_3d_window`、`CHEMBLENDER_FH_project_browser` | 为 3D View WINDOW 与 Project Browser UI region 提供 Blender FileHandler，并统一委托 `chemblender.quick_import`；只广告当前可用 built-in Reader descriptor 的确定性扩展名集合，`poll_drop()` 仅检查 area/region，不读取路径、解析文件或访问项目数据。缺少 Blender FileHandler API 时不访问 reader registry 并 fail closed；模块精确管理手动注册的 handler 所有权。 |
| `ChemBlender/ui/workspace.py` | `CHEMBLENDER_OT_open_workspace`、`workspace_is_compatible()` | 从 Extension 包内安全追加或复用唯一 `ChemBlender` WorkSpace；切换前验证 3D View、浏览侧栏、Properties 和底部编辑区布局，失败时只回滚本次追加的 datablock，不影响 Quick Import、Project Browser 或科学项目状态。 |
| `ChemBlender/ui/migration.py` | `legacy_migration_detection()`、`preview_legacy_migration()`、`migrate_legacy_scene()`、`CHEMBLENDER_OT_migrate_legacy_scene` | 旧 `.blend` 的显式注册 UI root：`load_post` 只缓存冻结检测结果，不写 Scene link 或改旧对象；确认迁移复用 legacy plan/commit、现有 Structure/periodic view builder 和多 Scene relink service，先创建并验证全部稳定命名的 View，随后将旧对象移入隐藏且带窄 owner contract 的 Backup collection。任一异常只回滚本事务创建的 View、sidecar、Backup 和 Scene link/session projection，恢复旧 collection/hide state；fatal exception 继续抛出，foreign 同名 View、Backup 或无 session-owned proof 的既有 `.cbq` 均 fail closed。 |
| `ChemBlender/Chem_data.py` | `ELEMENTS_DEFAULT` | 保存元素序数、名称、颜色及共价/原子/范德华/离子半径等静态数据。该文件没有行为函数。 |
| `ChemBlender/_math.py` | `rotate_vec()`、`symop_xyz_to_matrix()`、`fract_symop_expand()`、`make_cell_matrix()`、`fract_to_cartn()` | 旧 direct crystal writer 共享的向量、晶胞、分数坐标和对称操作数学函数；不再承担文件解析或热振动椭球计算。 |
| `ChemBlender/ex_package.py` | `safe_check_rdkit()` | 检查 RDKit 是否存在并满足最低版本；不负责在线安装。 |
| `ChemBlender/extension.py` | `cat_generator()`、`NODE_MT_chem_GN_menu`、`NODE_OT_group_add`、`register()`、`unregister()` | 从节点库生成 Geometry Nodes 菜单，将节点组插入当前树，并管理菜单回调。 |
| `ChemBlender/legacy/__init__.py` | `detect_legacy_scene()`、`extract_legacy_objects()`、`plan_legacy_migration()`、`commit_legacy_migration()`、`LegacyMigrationPlan` | 旧场景迁移 bridge 的公开、Blender-neutral 门面；不注册 UI，导入时不加载 `bpy`。 |
| `ChemBlender/legacy/detection.py` | `detect_legacy_scene()`、`LegacySceneDetection` | 延迟访问 `bpy`，仅从旧 scaffold/cell 标识生成冻结检测结果；不创建、删除或重命名 datablock。 |
| `ChemBlender/legacy/extraction.py` | `extract_legacy_objects()`、`LegacyExtractionReport` | 将旧 Mesh、covalent/van der Waals radii、属性、CIF PropertyGroup、collection、材质显示参数和可安全规范化的 Geometry Nodes modifier 输入复制为冻结 primitive 快照；仅已保存的常规非链接 `.blend` 以 `source_verified` 和 extraction-time SHA-256 标记为可哈希来源。科学坐标始终由原始 base mesh 顶点经 `matrix_world` 转为世界坐标，绝不取 modifier evaluated geometry；modifier、实际 world matrix 的非均匀/剪切变换、未知属性、unsupported node input 和缺失 `.blend` 来源均成为诊断。 |
| `ChemBlender/legacy/migration.py` | `plan_legacy_migration()`、`commit_legacy_migration()`、`LegacyMigrationPlan`、`ViewSettings`、`ViewPlan` | 将冻结 legacy snapshot 暂存为既有 `QCProject` 的 Structure/TopologyRecord/PeriodicSiteData/ProvenanceRecord，并以拥有 staged project、views、report 与 base/candidate inventory 的冻结 plan 传递；边界验证展示字段、结果 atom 数与规范拓扑顺序。commit 先验证 exact base project identity 与含 registry object identity、persisted content fingerprint 的 inventory，publication 成功后才采用经验证 reopened project，不访问 `bpy` 或旧 Blender 对象。 |
| `ChemBlender/legacy/reader_bridge.py` | `file_import_request()`、`smiles_import_request()`、`stage_pubchem_import()`、`verified_pubchem_parameters()`、`attach_verified_pubchem_provenance()` | legacy File/SMILES/PubChem 控件的 Blender-neutral import bridge。File/SMILES 只构造共享 `ImportRequest`；PubChem 把 SDF 写入对应 `ProjectSession` 的临时根和同 token metadata。host 每次附加 provenance 前复验当前 session ownership marker、非链接 `legacy-pubchem` root、严格 CID URL、metadata owner/hash 与实际文件 SHA-256；随后以 URL、实际 SHA-256、reader/source identity 生成确定性既有 `ProvenanceRecord`，并同步完整 `SourceRevision.created_entity_ids` 与 parser report。篡改或越界以 `legacy.pubchem_untrusted` fail closed。网络或协议失败转换为受控 import diagnostic，不在 UI 中解析 SDF。 |
| `ChemBlender/legacy/scaffold_bridge.py` | `route_legacy_export()`、`route_legacy_scientific_edit()`、`is_unified_structure_view()`、`legacy_scaffold_write_blocked()` | legacy scaffold 控件到统一 Project Browser export、Scientific Edit 与 Structure View contract 的窄映射；保留旧 operator ID/标签，不创建或解释科学数据。统一 Structure View 上该 guard 拒绝 legacy scaffold 直写并要求 Apply Scientific Edits。 |

## 传统分子与晶体建模层

这组模块直接操作 `bpy`、BMesh、RDKit 和既有 Geometry Nodes，是原 ChemBlender 结构编辑功能的主体。

| 文件 | 主要入口 | 职责 |
| --- | --- | --- |
| `ChemBlender/read.py` | `add_BONDS()`、`CIF_Atom`、`CIF_Structure`、`init_cif_data()`、`copy_cif_data()` | 旧 direct crystal scaffold 的最小数据 helper；所有分子和晶体文件格式均由 Reader API 负责，direct crystal writer helpers 在其入口完成统一 Structure View 迁移后于 2.4 清理。 |
| `ChemBlender/scaffold.py` | `MESH_OT_SCAFFOLD_BUILD.execute()`、`show_error_dialog()` | 保留旧控件 ID、标签和输入校验；File（含 CIF/POSCAR）、SMILES/preset 与 PubChem 分别经 `ImportRequest` 或 session-owned PubChem staging 进入统一 Quick Import/Reader API。PubChem 只携带 URL/SHA-256 provenance 参数，失败显示 diagnostic；不再解析或直接构建 legacy scaffold。 |
| `ChemBlender/mesh.py` | `create_object()`、`add_scaffold_attr()`、`scaffold_to_mol()`、`set_sel_atoms_attr()`、`set_sel_bonds_attr()`、`mol_optimize()`、`unit_cell_edges()` | Mesh/BMesh 主工具箱：创建和合并对象、写原子/键属性、选择和编辑结构、RDKit 转换与优化、生成晶胞边。 |
| `ChemBlender/node.py` | `add_geometry_nodetree()`、`append()`、`Ball_Stick_nodetree()`、`ensure_structure_ball_stick_modifier()`、`ensure_periodic_cell_modifier()`、`ensure_periodic_adp_modifier()`、`Supercell()`、`CoordPolyhedra()`、`crys_filter()` | 创建或加载 Geometry Node Group，连接球棍、超胞、晶胞边、配位多面体和晶体过滤节点；统一 Structure view 通过 data API 建立带显式 contract/version 的球棍、完整晶格矩阵 cell-edge 与热椭球 modifier，拒绝同名不兼容节点，避免依赖活动对象 operator context；legacy 超胞桥保持原节点输入并写入独立 contract。 |
| `ChemBlender/chem_utils.py` | `SelectButton`、`EnhancedSelectButton`、`SetAtomsButton`、`SetBondsButton`、`ConnectByDistance`、`AddHydrogens`、`AddBranches`、`GeometryOptimizeButton` | 分子编辑 operators：选择、测距/测角、设置原子和键属性、补键/氢/支链、几何更新与优化、scaffold 转换。 |
| `ChemBlender/crys_utils.py` | `SupercellButton`、`AddCellButton`、`AddCrysScaffoldButton`、`AddCoordPolyhedraButton`、`SymmetrySelect`、`SymmetryDuplicate` | 晶体 operators：生成超胞和晶胞、添加/删除位点、配位多面体、等价位置选择及对称复制。会修改 legacy scaffold 的入口在统一 Structure View 上 fail closed，科学修改必须经 Apply Scientific Edits。 |
| `ChemBlender/output.py` | `xyz_block()`、`SaveMolButton`、`UpdateCIFFromMesh` | `xyz_block()` 仅供 Scientific Edit 的 derived XYZ 输出；旧 `chem.molecule_output` 转发统一 `chemblender.export_project_entity`，旧 `chem.update_cif_from_mesh` 转发 `chemblender.apply_scientific_edits`。保留旧 ID/标签但不暴露已失效的 legacy export properties；还包含相机与快速渲染 operators。 |
| `ChemBlender/panel.py` | `CHEM_texts`、`CHEM_PT_Build`、`CHEM_PT_TOOLS`、`CRYSTAL_PT_TOOLS`、`CHEM_PT_OUTPUT` | 定义 Scene 属性和原有侧栏面板，组织结构构建、编辑、晶体工具及导出入口；检测到统一 Structure View contract 时，分子与晶体编辑区只显示 Apply Scientific Edits，隐藏 legacy scaffold 和 legacy view-direction controls。 |
| `ChemBlender/periodictable.py` | `CHEMBLENDER_OT_OpenPeriodicTable`、`CHEMBLENDER_OT_SelectElement`、`CHEMBLENDER_PT_PeriodicPanel` | 周期表弹窗、元素选择与文本复制 UI。 |

## Blender 量子数据映射层

这些模块把 `core` 语义对象映射为 Blender 视图。它们可以写数据集 UUID、revision 和显示参数，但不成为权威数据存储。

| 文件 | 主要入口 | 职责 |
| --- | --- | --- |
| `ChemBlender/dataset_view.py` | `create_structure_view()` compatibility wrapper、`apply_atomic_scalar()`、`apply_atomic_vector()`、`apply_atom_selection()`、`link_stick_spectrum_selection()` | 保留旧结构入口的开发期 DeprecationWarning；把原子标量、矢量和选择写成 named attributes，确保 vector modifier 位于默认球棍 modifier 前，并记录光谱样点到源数据集的联动身份。categorical presentation-only 模式只复用标量颜色计算与 `colour` 写入，并清除旧 scalar identity/attributes，不把 categorical dataset 伪装成 numeric scientific binding。 |
| `ChemBlender/views/__init__.py` | `StructureViewSettings`、`PeriodicViewSettings`、`create_structure_view()`、`create_periodic_structure_view()`、`update_structure_view_topology()`、`remove_structure_view()` | 作为统一 Blender view package 门面，公开 Structure/periodic Structure view 构建、只切换 topology 的原位更新与成组清理。 |
| `ChemBlender/views/periodic.py` | `PeriodicViewSettings`、`create_periodic_structure_view()` | 在统一 Structure view 上投影 occupancy、site/disorder、Uiso/Uij、Selective Dynamics 和显示设置；以完整 row-vector cell matrix 建立 cell/supercell derived display，以 occupancy/ADP validity、quality badge、概率缩放与主轴驱动版本化 Geometry Nodes；字符串位点字段写稳定 categorical codes/mapping，源 Mesh 不复制科学 atom。 |
| `ChemBlender/views/structure.py` | `BIOLOGICAL_NUMERIC_ROLE_SPECS`、`StructureViewSettings`、`biological_point_data()`、`default_altloc_mask()`、`create_structure_view()`、`update_structure_view_topology()`、`remove_structure_view()` | 从 Structure、显式 selected TopologyRecord、可选 Selective Dynamics AtomicProperty 与匹配 BiologicalHierarchy 建立单一 canonical-atom Mesh，写入新旧 atom/bond attributes、`cbq_selective_x/y/z`、biological categorical codes/validity/numeric properties/category hashes/dataset bindings、科学 identity 和默认球棍节点；单一只读 numeric role spec 约束 role、Mesh attribute、unit 与 missing policy，投影只接受 atom-aligned real numeric ArrayData，NaN 只允许 Partial 并以有限 placeholder 加 validity mask 表示。默认 altloc 只形成 view-owned selection/visibility mask。受约束 atom 另建可切换的 derived marker Mesh/Geometry Nodes。切换 topology 时保留 canonical vertices/point attributes，只替换 edges、periodic display 与 topology render identity；所有 derived display 均不写回科学实体。 |
| `ChemBlender/grid_volume.py` | `volume_cache_path()`、`ensure_grid_volume_cache()`、`create_grid_volume()` | OpenVDB/Blender adapter：向 pure cache transaction 提供 FloatGrid writer/validator；cache-only helper 为创建与 reopen repair 共用，创建函数仅在 cache preparation 成功后于主线程生成带 UUID/revision/affine/render identity metadata 的 Blender Volume。 |
| `ChemBlender/surface_view.py` | `surface_cache_path()`、`ensure_signed_surface_cache()`、`ensure_property_surface_cache()`、`create_signed_isosurfaces()`、`create_property_surface()`、`remove_surface_object()` | 共用 cache-only helper 在任何 VDB read/write 前拒绝最终文件 link/junction，写入并验证 signed/property VDB，再用 Volume→Mesh Geometry Nodes 创建独立正/负相位面，或在密度面采样另一标量场并写入 `cbq_surface_property`；property surface 复用 core affine guard，object 保存 surface/property 两侧 UUID、revision、dataset index、role、unit、isovalue、colormap/range 与 render identity。 |
| `ChemBlender/vibration_view.py` | `create_vibration_view()`、`apply_vibration_phase()` | 将一个振动模态写入位移属性和实例化箭头节点，并按相位更新原子位置。 |
| `ChemBlender/trajectory_view.py` | `configure_trajectory_view()`、`clear_trajectory_view()`、`register()`、`unregister()` | 绑定 `TrajectoryFrameManager` 与 Blender frame handler，只更新当前帧 Mesh 坐标并管理生命周期。 |
| `ChemBlender/spectrum_plot.py` | `create_spectrum_plot()` | 把 `Spectrum` 的横纵数据建立为 Blender Curve，并保存单位、类型和来源身份。 |
| `ChemBlender/electronic_plot.py` | `create_band_structure_plot()`、`create_dos_plot()`、`select_band_sample()`、`select_dos_sample()` | 创建 band/DOS Curve，处理费米能参考和 β-spin 镜像，并记录被选 k-point/band/energy 样点。 |
| `ChemBlender/fermi_surface_view.py` | `create_fermi_surface_view()`、`select_fermi_face()` | 将中立 `FermiSurfaceMesh` 转为三角 Mesh，把 band、投影、速度或自旋写入顶点/面属性并支持面到 band 的选择。 |
| `ChemBlender/topology_view.py` | `create_topology_view()` | 将 `TopologyGraph` 临界点映射为点 Mesh，将有采样坐标的路径映射为 Curve。 |
| `ChemBlender/scene_preset_view.py` | `apply_scene_preset()` | 复验 `ScenePresetPlan` 后分派统一结构、Grid3D Volume、振动、光谱、band/DOS 和表面 adapter；Structure publication 自动绑定同一 Structure 的 Selective Dynamics dataset；若该 Structure 唯一匹配 BiologicalHierarchy，则同时绑定 numeric AtomicProperty、显式 accepted 或唯一未拒绝 TopologyRecord，并复用 biological size planner 创建默认 biological view；无 hierarchy 时保持原路径，current Structure 的 stale topology decision fail-closed。任一 adapter 失败时连同 Structure view 的 derived display object/node group 删除本次创建的全部对象。 |
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
| `ChemBlender/core/model/categorical.py` | `CategoricalData` | 以整数 code、唯一字符串 category 和显式 missing code 保存分类属性，避免 object dtype 进入 sidecar。 |
| `ChemBlender/core/model/chemical_identity.py` | `AtomicIdentityData` | 定义可选逐 atom identity 值对象；以 dimensionless integer isotope/formal-charge/atom-map 和 `CategoricalData` 名称/stereo 标签保持同一 atom 轴，不保存 RDKit 对象。 |
| `ChemBlender/core/model/diagnostics.py` | `DiagnosticValue`、`ImportDiagnostic`、`diagnostic_from_parser_issue()`、`ParserIssue`、`ParserReport` | 以逐节点 type tag 定义不可变、JSON-safe 且可区分 sequence/mapping 的详细导入诊断，并提供 legacy reader issue 转换，同时保持既有 parser issue/report 契约。 |
| `ChemBlender/core/model/exchange.py` | `ChemicalAnnotation`、`ExternalReference`、`BiologicalModel`、`BiologicalChain`、`BiologicalResidue`、`BiologicalAtomSiteData`、`BiologicalHierarchy` | 定义不污染 `Structure`/`AtomicIdentityData` 的交换格式标量注释、外部标识和紧凑生物层级；逐 atom 数组仍复用 `ArrayData`/`CategoricalData`，不保存格式 parser 或第三方对象。 |
| `ChemBlender/core/model/structure.py` | `DeclaredSymmetry`、`PeriodicSiteData`、`MolecularTopology`、`Structure`、`SymmetryResult`、`unit_cell_parameters()`、`fractional_to_cartesian()`、`cartesian_to_fractional()`、`validate_periodic_coordinate_consistency()` | 定义统一分子/周期 Structure 和结构化对称性结果；CIF 周期位点以 envelope UUID 加稳定 block name/key/index 绑定源 block，独立保存 source-declared symmetry name/IT number/Hall/operations，并显式保存缺失 occupancy、disorder assembly/group 与可缺失的 Uiso/Uij；`Structure.cell` 是唯一持久化晶格权威，纯 helper 按 row-vector 约定派生晶胞参数、转换两套坐标并为 reader/adaptor 显式复验一致性；保留 `MolecularTopology` 读取兼容，让 Structure 记录零或多个独立 topology UUID，并拒绝非长度单位、非有限坐标及非有限或奇异 cell。 |
| `ChemBlender/core/model/molecular_topology.py` | `TopologySource`、`TopologyRecord` | 定义按来源和质量版本化的分子连接实体，校验 bond arrays、可选 integer lattice shifts、芳香/立体标签、规范推断参数及 provenance；文件显式、RDKit 解释、距离推断和用户编辑互不覆盖。 |
| `ChemBlender/core/model/records.py` | `RawRecordProperty`、`MolecularRecord`、`RecordPropertyColumn`、`ConformerSet` | 定义原始分子 record 的精确 bytes/有序属性、可选 typed record-column 与已归一化 conformer 坐标；由 project graph 校验 source revision、Structure/Topology、record UUID、atom 数和单位，不解析 RDKit 或实现 grouping。 |
| `ChemBlender/core/model/properties.py` | `PropertyDataset`、`AtomicProperty`、`FrameSet`、`FrameProperty`、`AtomFrameProperty`、`CellFrameProperty` | 定义通用属性数据集、原子/坐标帧特化，以及绑定 FrameSet 并带严格 validity mask 的帧属性。 |
| `ChemBlender/core/model/grids.py` | `Grid3D` | 定义仿射三维网格、坐标单位、步进向量和可选结构引用校验。 |
| `ChemBlender/core/model/spectroscopy.py` | `VibrationalModeSet`、`ExcitedStateSet`、`Spectrum` | 定义振动模式、激发态贡献/引用和振动/电子光谱数据集。 |
| `ChemBlender/core/model/wavefunction.py` | `BasisSet`、`OrbitalSet`、`DensityMatrix` | 定义基组壳层/约定、轨道通道和 AO 密度矩阵及其内部一致性校验。 |
| `ChemBlender/core/model/periodic.py` | `BandStructure`、`DensityOfStates`、`PhononModeSet`、`FermiSurfaceMesh` | 定义能带、DOS、声子模式和费米面网格等周期体系数据集。 |
| `ChemBlender/core/model/topology.py` | `TopologyGraph`、`TopologyConnection`、`TopologyPath` | 定义临界点、连接和路径组成的中立拓扑图，并校验结构/网格引用所需的局部语义。 |
| `ChemBlender/core/model/project.py` | `CIFEnvelope`、`CalculationRecord`、`ProvenanceRecord`、`ImportBatch`、`QCProject`、`validate_project_graph()` | 定义保留原始 bytes、完整 tag 与稳定 block identity 的交换 envelope、计算/溯源记录和项目聚合根；原子提交 source/revision、topology、biological hierarchy、annotation、external reference、diagnostic 与科学实体，并校验目标/溯源、唯一语义键、atom 维度、全局 registry UUID 和双向 revision-diagnostic 关系；`validate_project_graph()` 以一次临时 `QCProject.commit()` 和 calculation-group 提交复验完整已存在图。 |
| `ChemBlender/core/topology/radii.py` | `covalent_radius_angstrom()`、`is_metal()` | 把既有 `Chem_data.ELEMENTS_DEFAULT` 和 metals 表投影为纯 Python 拓扑推断查询，不导入 RDKit 或 Blender。 |
| `ChemBlender/core/topology/infer.py` | `TopologyInferenceSettings`、`infer_distance_topology()` | 对 angstrom/bohr 非周期 Structure 使用 27 邻格空间 cell list 生成确定性距离拓扑；记录全部设置、源 Structure revision 和 provenance，重复近点以 INVALID parser issue 阻断，金属配位保持 ambiguous/零键级。 |
| `ChemBlender/core/topology/periodic.py` | `infer_periodic_topology()` | 通过 cell inverse 映射 fractional displacement，只沿启用的 PBC 轴建立有界周期 image 邻格；连接保留规范 integer lattice shift，周期/材料连接使用 ambiguous 与零键级且支持单原子 self-image。 |
| `ChemBlender/core/edits/structure.py` | `StructureEditPreview`、`preview_structure_edits()`、`commit_structure_edits()` | 纯 Python 比较 Structure/Topology 与显式编辑状态，规范化 angstrom 后报告 atom、coordinate、element、bond、cell 与关联 dataset diff；确认路径以确定性 UUID/revision 创建 derived Structure、可选 USER_EDITED TopologyRecord 和 parent provenance，并在 report 中提示 source-linked results 不继承，不修改源实体。 |
| `ChemBlender/core/session.py` | `ProjectSession`、`create_session()`、`close_session()` | 在冻结科学模型之外管理可变会话状态；`mark_clean()` 仅显式清空已记录 dirty reasons；创建带 UUID ownership marker 的临时根，并在关闭 lazy resources 后仅删除标记匹配的受控目录。 |
| `ChemBlender/core/project_service.py` | `save_project_session()`、`save_project_session_for_scenes()`、`sync_project_session_links_for_scenes()`、`verify_project_session()`、`verify_project_session_for_scenes()`、`relink_project_session()`、`relink_project_session_for_scenes()`、`clear_derived_cache()` | 编排原子 sidecar publication 与经 hash 验证的 Scene link；link-only 同步只打开验证现有 sidecar 一次，精确 no-op 或只补空 Scene/移动后的 locator，不改 manifest、generation 或 authoritative arrays，partial/conflicting link 必须显式 relink。多 Scene relink 只打开候选一次，先快照全部四字段再写同一 UUID、schema、locator 与 manifest hash，任一写入或采用失败时恢复全部 Scene；rollback 不完整时保留原错误、逐 Scene/key failure 和 residual keys，全部写成功后才采用候选并关闭旧 project。单 Scene relink 保持兼容 wrapper。恢复时忽略空 Scene、只采纳一次相同有效 link，并对冲突有效 link fail-closed；另以显式状态恢复 session，并仅清理 `.cbq/cache/derivation/` 与 `.cbq/cache/render/` 非权威缓存。 |
| `ChemBlender/core/import_pipeline/__init__.py` | 模块级显式 re-export | 导入流水线的纯 Python package 门面；公开 request、preview、staging、preflight、conflict 与 grouping 契约，不加载 Blender 或可选科学栈。 |
| `ChemBlender/core/import_pipeline/conflicts.py` | `ImportConflictCandidate`、`ImportConflict`、`DuplicateAction`、`ConflictDecision`、`detect_import_conflicts()`、`apply_conflict_decisions()` | 只读比较 parse identity、内容 hash 与纯词法 locator；文件来源要求 absolute path 与 canonical locator 精确一致，SMILES text 只接受 `inline:smiles` 及 session-owned staged artifact，其他 locator fail-closed。不可拆分候选快照保留最高优先级的全部匹配；提交决定前根据 live project 和 staging session 重检完整冲突，target action 必须显式选择 revision，并返回新的 preview，不修改 session 或项目。 |
| `ChemBlender/core/import_pipeline/grouping.py` | `GroupingEvidence`、`SourceGroupSuggestion`、`suggest_source_groups()` | 从严格关联的暂存 batch 生成确定性、不可变的跨来源证据与分组建议；依次评估显式 UUID 引用、结构映射、Kabsch RMSD（`<= 0.15 Å`）、metadata 和文件名/目录，周期原胞/惯用胞候选只标记 review conflict，只有用户显式确认才创建 model 层 `CalculationGroup`，不修改 preview、session 或项目。 |
| `ChemBlender/core/import_pipeline/conformer_grouping.py` | `ConformerGroupSuggestion`、`suggest_conformer_groups()`、`suggest_staged_conformer_groups()`、`accept_conformer_group()` | 以完整 `ImportBatch` 的 `Structure`、`TopologyRecord`、`AtomicIdentityData` 和 `RecordPropertyColumn` 为权威，在同一 `SourceRevision` 的 SDF records 中生成不可变 conformer 建议；staged helper 跨 Preview source 收集建议并支持 cooperative cancellation，使 Quick Import 可在 worker 中预计算而 UI 主线程只投影缓存。RDKit 仅提供 atom-map/canonical-rank/isomorphism 候选，最终逐项复验元素、charge、isotope、stereo、bond order 与 aromaticity。显式确认后才返回含 reference-to-source mapping、重排序坐标/record columns 与 provenance 的 derived fragment；快照过期、对称映射截断或不完整证据均 fail-closed，不修改输入 batch、项目或 Blender。 |
| `ChemBlender/core/import_pipeline/transaction.py` | `GroupingDecision`、`ConformerGroupingDecision`、`ImportCommitDecisions`、`ImportCommitResult`、`commit_import_preview()` | 根据 live project 与 staging session 重检完整 conflict/source-group/conformer-group 快照；conformer acceptance 在 resolved live staged batch 中重算，skip/reuse 缺少成员即 fail-closed，reidentify 后按 remapped record IDs 重新匹配。所有 derived fragments 只写入 disposable candidate 并在一次 sidecar 原子发布和 verified project 移交后替换 live session；不创建 Blender datablock。 |
| `ChemBlender/core/import_pipeline/parse.py` | `staged_reader_batch()`、`stage_import_batch()` | reader-neutral 地构造或复验带 `SourceRecord`、`SourceRevision` 和双向诊断引用的暂存结果；可复用 host 预分配的最终 revision UUID，并为公开 Reader API 精确复验插件提供的完整来源身份。canonical parameters 只参与 reader parse identity，不解释任何 legacy source 或 provenance 语义；不提交项目。 |
| `ChemBlender/core/import_pipeline/preflight.py` | `preflight_import()`、`ImportCancelled` | 对显式文件执行 bounded hash、reader 选择与 availability 检查、可取消解析和稳定失败诊断；只登记到 owned staging session，不写 `QCProject`。 |
| `ChemBlender/core/import_pipeline/request.py` | `ValidationMode`、`ImportSource`、`ReaderOverride`、`ImportRequest` | 定义不可变导入意图；规范化并去重显式文件路径，拒绝目录扫描，并将 reader override 限定到请求内来源。 |
| `ChemBlender/core/import_pipeline/preview.py` | `SourcePreview`、`ImportPreview` | 以不可变路径、标量和 UUID 引用描述 source row、暂存 batch、冲突、归组建议、诊断及默认 view plan，不持有项目或 Blender 对象。 |
| `ChemBlender/core/import_pipeline/report.py` | `import_summary()`、`diagnostics_document()`、`render_diagnostics_markdown()` | 只读验证 preview 与 live staging batch 的身份及关联，按稳定键生成 schema v1 JSON-compatible diagnostic document、质量状态计数和 Markdown；不读取项目、不加载 Blender 或可选科学栈。 |
| `ChemBlender/core/import_pipeline/staging.py` | `StagedImportSession.create()`、`register_result()`、`materialize_result()`、`discard()` | 创建带 UUID ownership marker 的独占暂存根、artifact 目录和受控 `ImportBatch` registry；可登记一次性延迟 materializer，在确认时先完整生成 replacement 再原子替换 preview batch，失败保留可重试 preview；discard 会先关闭已注册 batch 的 staged memmap，再仅在路径、文件身份及 marker 均匹配时删除。 |
| `ChemBlender/core/readers.py` | `ReaderDescriptor`、`ReaderRuntimeDescriptor`、`ReaderAvailability`、`ReaderRegistry.register()`、`select()`、`parse()` | 定义 reader capability、扩展名、bounded sniffing 和确定性分派；可成对声明 content-verified preview/materialize request 以延迟大型数值数组，拒绝只配置一侧；以兼容 wrapper 分离 reader 选择与运行时 availability，拒绝未知或歧义 reader。 |
| `ChemBlender/core/reader_catalog.py` | `builtin_reader_descriptors()`、`builtin_reader_registry()`、`reader_capability_document()` | 汇总内置 reader，并以 Reader API version、运行时依赖契约、扩展名/basename、import capability、export maturity/loss policy 和 fixture family 生成确定性的机器可读格式能力矩阵；不把当前机器 availability 固化为成功。 |
| `ChemBlender/core/cache_identity.py` | `source_hash_bytes()`、`parser_cache_key()`、`derivation_cache_key()`、`render_cache_key()` | 用规范 JSON 和 SHA-256 分别标识源文件、解析、派生和渲染缓存。 |

### Reader API v1 RC 门面

`reader_api` 是冻结为 `1.0-rc1` 的公共、纯 Python（`bpy`-free）门面。manifest 是可安装插件的静态声明，runtime descriptor 是已解析 reader 的只读元数据；两者都不持有 parse callable，插件也不能取得或修改 `QCProject`。模块只通过相对导入解析已安装命名空间，不绑定源码包名或 extension repository namespace。可选依赖 availability 探测只使用 `find_spec()`，不导入该依赖。

| 文件 | 主要入口 | 职责 |
| --- | --- | --- |
| `ChemBlender/reader_api/__init__.py` | 模块级 re-export | Reader API `1.0-rc1` 的严格公共门面；导出版本、manifest/runtime descriptor、exact `SniffMatch`/`SniffResult`、受控科学实体（含 exchange annotation/reference/hierarchy）和 `PublicImportBatch`，不导出 `QCProject` 或内部 `ImportBatch`。 |
| `ChemBlender/reader_api/version.py` | `READER_API_VERSION` | 声明冻结的 Reader API `1.0-rc1` token，供 manifest v1 兼容范围校验。 |
| `ChemBlender/reader_api/manifest.py` | `ExecutionMode`、`ReaderManifestEntry`、`ReaderPluginManifest.from_toml()` | 用标准库 `tomllib` 读取受控 UTF-8 TOML，拒绝未知字段和不兼容 API 范围，并确定性规范化静态 reader 声明；manifest capability list 恒表示 `SUPPORTED`。 |
| `ChemBlender/reader_api/descriptors.py` | `PublicReaderDescriptor`、`_probe_availability()` | 定义不含 callable、模块路径或项目上下文的不可变 runtime 元数据；以相对导入取得现有 `CapabilitySupport`/`ReaderAvailability`，并保留 `SUPPORTED`、`PARTIAL`、`UNSUPPORTED` 三态 capability。 |
| `ChemBlender/reader_api/discovery.py` | `ReaderPluginDiscovery`、`ReaderDiscoverySnapshot`、`DiscoveredReaderPlugin` | 以单一纯 Python owner 包装既有 registry：只接受 handle 的显式注册/注销，不扫描 `sys.path`；成功时保留 reader descriptor identity，重复 ID、reserved built-in ID、malformed plugin 或普通 callback failure 转为稳定 unavailable state；注销按 registry 的完整 manifest value equality 在一次事务中 reconcile 同一 Extension 的成功 ownership 与失败记录，不影响其他 manifest；`refresh()` 缓存同一 generation 的只读 snapshot，不重建 registry 或 Blender class，fatal exception 原样传播。 |
| `ChemBlender/reader_api/public_model.py` | `PublicImportBatch` | 以精确受信科学实体类型构成不可变、无复制的导入批次，包括 biological hierarchy、chemical annotation 和 external reference 三组兼容扩展；拒绝子类和未批准数据集，并为 bridge 提供递归嵌套值校验，插件不能经此获得项目。 |
| `ChemBlender/reader_api/builtin_bridge.py` | `public_batch_from_internal()`、`internal_batch_from_public()` | 内置 `ImportBatch` 与公开批次间的薄、无复制转换边界；公共转换保持完整 `QCProject.commit()` 图校验，私有 structural conversion 只供 exact 内置插件在 host 绑定最终 `SourceRevision` 前使用，均递归拒绝 callable、mutable container 与未登记嵌套对象。 |
| `ChemBlender/reader_api/canonical_document.py` | `public_batch_document()`、`public_batch_from_document()`、`write_public_batch_bundle()`、`read_public_batch_bundle()` | 将严格 `PublicImportBatch` 确定性编码为 Reader Import Document v0.1；以 content-addressed、禁 pickle 的 NPY artifacts 承载数组，并在读取边界复验 exact schema/type、相对路径、shape、dtype 与双 hash；对 CIF block identity 和兼容新增的空 exchange groups 提供明确旧文档缺省；写后 hash/临时文件清理失败统一为稳定 integrity error；只构造公开 batch，项目图校验留给 built-in bridge。 |
| `ChemBlender/reader_api/import_pipeline_bridge.py` | `preflight_reader_plugins()` | 把主进程持有的 `ReaderPluginRegistry` 接入既有 `ImportRequest`、`StagedImportSession` 与 `ImportPreview`：每次 parse 预分配一个最终 revision UUID，exact 内置结果先绑定同一 `SourceRevision` 再做完整项目图校验，外部 reader 仍须返回 UUID 与请求一致的完整来源身份。仅供 host 内部使用的 keyword-only batch attachment 只在每个最终 staged preview/deferred candidate 的 reader fallback、图校验与 base identity comparison 完成后运行一次，保持 public reader/core 模型 reader-neutral；它只能追加 provenance 及其 created-ID bookkeeping，任意替换来源、reader science、诊断或 report 均以结构化 host contract error fail closed，host 异常会先释放未登记 batch 的 lazy array/memmap 和受控 artifacts 再原样透传。可信内置 reader 可先登记 content-verified preview，再在确认时以相同 entity inventory、语义诊断及原 diagnostic IDs 原子物化；不一致时清理新 artifacts、保留 snapshot 并要求刷新 Preview。确认前不修改 `QCProject`、Scene 或 Blender datablock。 |
| `ChemBlender/reader_api/conformance.py` | `ReaderConformanceCase`、`ReaderConformanceCheck`、`ReaderConformanceResult`、`run_reader_conformance()`、`run_reader_conformance_v1()` | 保持 Reader API 0.1 公共类型与 12 项检查兼容，并生成 v1 suite document；复用 registry、graph bridge 与 canonical bundle 验证 bounded/deterministic sniff、来源身份、引用、单位/质量/诊断、progress、capability、artifact 安全、取消和异常隔离，不创建项目或 Blender 状态。 |
| `ChemBlender/reader_api/conformance_cli.py` | `main()` | 从显式目录在子进程中加载插件 `reader.py`，只运行 reader 声明 extension 的安全 fixture，输出 compact/sorted UTF-8 v1 conformance JSON；required failure 返回 1，CLI/路径/加载失败返回 2，不扫描任意 `sys.path`、不安装依赖。 |
| `ChemBlender/reader_api/protocol.py` | `SniffRequest`、`ParseRequest`、`ProgressEvent`、`ReaderPlugin` | 定义无项目、无 Blender 上下文的 Reader 插件请求与进度协议；每个插件必须持有与 runtime descriptor 一致的 exact manifest，解析请求携带已验证来源、host 最终 `source_revision_id`、规范参数、安全 staging root 及进度/取消回调。 |
| `ChemBlender/reader_api/registry.py` | `ReaderPluginRegistry`、`builtin_reader_plugin_registry()` | 确定性选择公开 Reader 插件，在注册时交叉验证 manifest/runtime metadata，并要求同一 `plugin_id` 使用一份完整 manifest；仅以 exact complete manifest 原子注销同一插件全部 reader；在解析前后分块复验来源 hash，只有 exact 内置 wrapper 可走绑定前 structural validation，外部 reader 的完整 revision UUID 必须匹配请求；隔离 sniff/parse 异常并保留最近一次 parse 的私有异常类型证据。 |
| `ChemBlender/reader_api/worker_bridge.py` | `parse_with_worker()`、`WorkerReaderError` | 主进程对固定 `reader.parse@0.1` 的已完成 `WorkerResult` 做 request ID、状态、exact metadata、NTFS-safe 相对路径、无 link/junction 的 exact bundle inventory、来源与全部输出 hash 复验；重开 canonical bundle 并经 `internal_batch_from_public()` 图校验后才返回内部 `ImportBatch`。 |

### 文件 reader 与第三方 adapter

| 文件 | 主要入口 | 职责 |
| --- | --- | --- |
| `ChemBlender/core/exporters/__init__.py` | 模块级 re-export | 暴露原生 XYZ/extXYZ、MOL/SDF/SMILES 与 controlled CIF 的纯 Python 导出入口、MOL2 P1 readiness、无写入 loss/patch preview、取消异常和语义比较器，不加载 Blender 或 RDKit。 |
| `ChemBlender/core/exporters/cif.py` | `CIFExportPlan`、`plan_cif_export()`、`export_cif()` | 复用 Gemmi 只在 CIF 导出调用时读取 source envelope；Preserve mode 以稳定 block identity patch cell、atom-site、occupancy、Uiso/Uij、ADP type、disorder group/assembly 与明确声明的 symmetry，并保留未知 block/tag/loop；Normalized mode 从无 envelope 的周期 Structure 写最小 CIF，不虚构 uncertainty、disorder 或 symmetry。两种模式共用短临时文件、fsync、原子替换与取消清理。 |
| `ChemBlender/core/exporters/poscar.py` | `PoscarExportSettings`、`export_poscar()`、`semantic_poscar_differences()` | 原生 POSCAR/CONTCAR exporter：确定性输出 species groups、Direct/Cartesian、unit/preserved/target-volume scale、Selective Dynamics 及选中的 ion/lattice velocities；ion velocity 在模型中使用 Cartesian canonical basis，导出 Direct 时按当前科学 cell 变换，语义比较也使用 canonical basis；复用 atomic writer。 |
| `ChemBlender/core/exporters/xyz.py` | `atomic_write_chunks()`、`export_xyz()`、`export_extxyz()`、`preview_extxyz_export()`、`semantic_extxyz_differences()` | 提供同目录短临时文件、fsync、replace、取消清理的共享 UTF-8 原子写入；其上确定性导出 XYZ/extXYZ，保留 typed frame/atom/cell property、integral-valued real metadata 与 validity，显式报告 partial/ambiguous loss，并按科学数据而非 UUID/空白比较 round-trip。 |
| `ChemBlender/core/exporters/rdkit_molecular.py` | `SDFExportEntry`、`sdf_entries_from_conformer_set()`、`preview_molecular_export()`、`export_mol()`、`export_sdf()`、`export_smiles()`、`semantic_molecular_differences()` | 仅在写入时加载 RDKit，从 `Structure`、`AtomicIdentityData` 和选定 `TopologyRecord` 重建临时分子；纯 metadata preview 复用同一 loss contract 而不构造或序列化 RDKit Mol；严格审计 V2000 表示能力并自动选择 V3000，MOL/SDF 的 atom name 或 multiplicity loss 先要求确认，SDF 以 caller-selected `SDFExportEntry` 顺序保留 raw SD 属性的重复项；ConformerSet helper 按 reference atom order 生成派生记录而不二次应用 mapping；SMILES 在确认前只报告 loss，所有目标文件复用 shared atomic writer。 |
| `ChemBlender/core/exporters/mol2_readiness.py` | `Mol2ExportStatus`、`Mol2ExportReadiness`、`mol2_export_readiness()` | 纯 Python MOL2 P1 可表示性检查；从既有 Structure/TopologyRecord/MolecularRecord/AtomicProperty/ChemicalAnnotation 收集确定性缺失字段并返回 Complete/Partial/Unsupported，不写入文件、不接 UI、不新增科学模型。 |
| `ChemBlender/core/exporters/pdb_readiness.py` | `PDBPQRExportStatus`、`PDBPQRExportReadiness`、`pdb_export_readiness()`、`pqr_export_readiness()` | 纯 Python PDB/PQR P1 可表示性检查；只按显式 Structure UUID 关联 BiologicalHierarchy、AtomicProperty 与 FrameSet，确定性报告缺失、歧义、无效值、字段溢出及 serial 重编号边界，不格式化或写文件、不接 UI、不新增科学模型。 |
| `ChemBlender/core/formats/__init__.py` | 模块级 re-export | 暴露原生文本格式 reader 的低层入口，不注册 reader 或接触项目状态。 |
| `ChemBlender/core/formats/cif.py` | `CIF_READER`、`sniff_cif()`、`parse_cif()` | 内置 CIF reader；仅在解析时加载 Gemmi，把多 block/loop、fractional/Cartesian 坐标、位点 identity、缺失或部分 occupancy、disorder assembly/group、U/B displacement 和原始 envelope 映射到统一模型；坐标派生及 B→U 转换写入 diagnostics 与 provenance。 |
| `ChemBlender/core/formats/extxyz.py` | `parse_extxyz()`、`sniff_extxyz()`、`iter_extxyz_frames()` | 原生选择并逐帧解析 extXYZ，将兼容帧映射为确定性 `Structure`、`FrameSet` 与 typed frame/atom/cell property；大型 Quick Import 先对同一 hash-verified snapshot 扫描 frame/schema/comment 并用零复制 broadcast array 建立小型 preview，确认时再可取消地物化完整 staging NPY memmap；不一致 fail-closed，不依赖 ASE。 |
| `ChemBlender/core/formats/mol.py` | `MOL_READER`、`sniff_mol()`、`parse_mol()`、`parse_mol_request()` | 对单记录 MOL V2000/V3000 做完整 CTAB/atom/bond 结构 sniff，并仅在调用时加载 RDKit；保留原始 bytes，借助共享 adapter 输出结构、原子身份、显式拓扑、MolecularRecord、provenance 与诊断；产品请求直接沿用 host 的 source revision、hash、validation 和 cancellation。 |
| `ChemBlender/core/formats/mol2.py` | `MOL2_READER`、`sniff_mol2()`、`iter_mol2_records()`、`parse_mol2_record()`、`parse_mol2()`、`parse_mol2_request()` | 以标准库按 `MOLECULE` 边界和 case-insensitive exact section marker 保留 MOL2 原始记录；解析任意 atom/bond ID、Tripos atom/bond/substructure/charge 语义，并映射为统一 Structure、explicit-file TopologyRecord、MolecularRecord、ChemicalAnnotation 与 atomic properties。Balanced 模式逐 record 恢复，坏 bond 只阻断 topology，缺失类别/charge 明示 Partial；descriptor 为 dependency-free built-in reader。 |
| `ChemBlender/core/formats/pdb.py` | `PDB_READER`、`sniff_pdb()`、`parse_pdb_records()`、`parse_pdb()`、`parse_pdb_request()` | 纯标准库 fixed-column PDB reader；保留语法层的原始 bytes/line ending，以内部 MODEL occurrence 区分重复 serial 的 source block，并在冻结模型前校验 atom serial/occupancy；把七字段 atom identity、MODEL/altloc/hierarchy、occupancy/B-factor、occurrence-scoped CONECT 与 CRYST1 映射到统一 Structure、FrameSet、BiologicalHierarchy、AtomicIdentityData、AtomicProperty、explicit-file TopologyRecord 和 periodic cell；不实现 PQR、altloc view filter、UI 或 export。 |
| `ChemBlender/core/formats/pqr.py` | `PQR_READER`、`sniff_pqr()`、`parse_pqr_records()`、`parse_pqr()`、`parse_pqr_request()` | 纯标准库 validated-whitespace PQR reader；严格区分 with-chain/no-chain field count，校验 serial、residue/insertion、xyz、charge 与 radius，按 PDB atom-name 规则诊断式推断 element，并映射统一 Structure、BiologicalHierarchy、AtomicIdentityData 与 charge/radius AtomicProperty；坏行按 validation mode 隔离或拒绝，不产生或推断 topology。 |
| `ChemBlender/core/formats/sdf.py` | `SDF_READER`、`iter_sdf_records()`、`parse_sdf()`、`parse_sdf_request()` | 用 standalone `$$$$` 的原始字节行边界逐条索引 SDF；先保留 MOL slice 与重复/空 SD 字段，再独立调用 RDKit adapter；Balanced 模式保留坏记录周围的有效索引并诊断，只有无歧义的 bool/int/float 字段生成带 mask 的 record property column，不做 conformer grouping。 |
| `ChemBlender/core/formats/smiles.py` | `SMILES_READER`、`parse_smiles()`、`parse_smiles_text()`、`parse_smiles_request()` | 以单条 UTF-8 SMILES 原始 bytes 为权威来源；文件 reader 仅在调用时加载 RDKit，direct text 使用稳定 `inline:smiles`/`inline_text` source 语义而不持久化随机临时路径。解析固定生成显式 planar 2D 坐标，保留 canonical/isomeric SMILES、atomic identity、charge 与 explicit topology；无效、radical、dummy 或 unspecified bond 只返回 blocking diagnostic，不生成 Structure。 |
| `ChemBlender/core/formats/poscar.py` | `POSCAR_READER`、`PoscarDocument`、`sniff_poscar()`、`parse_poscar_document()`、`parse_poscar()` | 纯标准库 POSCAR/CONTCAR 语法与 built-in Reader API：校验 lattice、VASP 4/5 species/count、Direct/Cartesian/K、Selective Dynamics 与 velocity blocks；有效 `.vasp/.poscar/.contcar` 和 canonical basename 均为 native exact match，避免降级到 optional ASE；映射统一 periodic `Structure`、typed properties 和 source-convention provenance，并将 Direct ion velocity 按科学 cell 转为 Cartesian canonical basis。VASP 4 缺失元素时只产生 Ambiguous preview，显式 ordered species 参数恢复完整结构。 |
| `ChemBlender/core/formats/rdkit_common.py` | `adapt_rdkit_molecule()` | 在函数内加载 RDKit，将临时分子映射为现有的不可变结构、原子身份、显式/必要时 sanitized 拓扑、原始 record、provenance 与诊断；不保存 RDKit Mol，缺失 conformer 不虚构坐标。 |
| `ChemBlender/core/derivations/__init__.py` | `derive_smiles_3d()` | 派生模块的纯 Python 门面，不加载 RDKit。 |
| `ChemBlender/core/derivations/smiles_3d.py` | `derive_smiles_3d()` | 从关联的 `Structure`、`TopologyRecord`、`MolecularRecord` 与真实 `SourceRevision` 重建临时 RDKit Mol，以固定 ETKDGv3 seed、单线程及显式 AddHs/UFF/MMFF 参数生成新 3D Structure/Topology；通过 `CalculationRecord` 表示 success、failed 或 incomplete，保留来源实体且不持久化 RDKit Mol。 |
| `ChemBlender/core/xyz.py` | `sniff_xyz()`、`parse_xyz()` | 读取单帧/多帧 XYZ 和受支持的 extXYZ lattice/PBC/property 子集，输出 `Structure`、`FrameSet` 和报告。 |
| `ChemBlender/core/mol_v2000.py` | `MOL_V2000_READER`、`parse_mol_v2000()` | 已弃用的 V2000-only 显式兼容 alias；委托 `formats.mol` 的同一实现，自动选择始终由 replacement `mol` 处理并在 alias report 中说明迁移目标。 |
| `ChemBlender/core/cube.py` | `sniff_cube()`、`parse_cube()` | 读取 Cube 原点、完整非正交 step vectors、多 dataset/MO index、voxel 数据与逐原子 nuclear charge，输出共享 `Structure` 的 `Grid3D` 和 `AtomicProperty`，并在 provenance 保留 comments、dataset IDs 与有符号轴约定。 |
| `ChemBlender/core/cclib_adapter.py` | `sniff_cclib_output()`、`adapt_ccdata()`、`parse_cclib_output()` | 延迟加载 cclib，将 Gaussian/ORCA 等输出归一化为结构轨迹、能量、原子属性、振动、激发态及 parser issues。 |
| `ChemBlender/core/iodata_adapter.py` | `sniff_iodata_wavefunction()`、`adapt_iodata()`、`parse_iodata_wavefunction()` | 延迟加载 IOData，将 FCHK/Molden 的结构、basis、restricted/unrestricted/generalized MO 和 RDM 转为内部模型。 |
| `ChemBlender/core/ase_adapter.py` | `sniff_ase_structure()`、`adapt_ase_atoms()`、`parse_ase_structure()` | 延迟加载 ASE，归一化分子/周期结构、约束、per-atom arrays 和轨迹。 |
| `ChemBlender/core/gemmi_adapter.py` | 兼容 re-export | 保留旧导入路径，并委托 `core.formats.cif`；不包含第二套实现。 |
| `ChemBlender/core/spglib_adapter.py` | `spglib_availability()`、`derive_symmetry()` | 只在显式 availability/derive 调用时实际导入 spglib，用显式 symprec/angle tolerance 从周期结构派生独立 `SymmetryResult` 与标准 Structure；native import 失败会禁用 capability，不改源 Structure、CIF envelope 或 source-declared symmetry。 |
| `ChemBlender/core/symmetry_service.py` | `symmetry_availability()`、`derive_structure_symmetry()`、`symmetry_comparison_rows()` | 提供不依赖 Blender 的可选 spglib capability、派生入口和 declared/derived 对比投影；复用 adapter 与 comparison，不在 core import 时加载 spglib。 |
| `ChemBlender/core/symmetry_comparison.py` | `SymmetryComparison`、`compare_symmetry()` | 比较 source-declared 与 spglib-derived group identity，区分 match、different、insufficient data；只有调用方提供并通过校验的显式 setting transformation 才可标记 setting equivalent。 |
| `ChemBlender/core/pymatgen_adapter.py` | `sniff_vasp_volumetric()`、`adapt_pymatgen_structure()`、`adapt_vasp_volumetric()`、`parse_vasp_volumetric()` | 读取 CHGCAR/PARCHG/ELFCAR/LOCPOT 类周期体数据并保留晶格与 dataset 语义。 |
| `ChemBlender/core/pymatgen_electronic.py` | `sniff_vasprun()`、`adapt_pymatgen_electronic()`、`parse_vasprun_electronic()` | 从 pymatgen electronic objects/vasprun 归一化 band、DOS/PDOS、spin、投影和能量参考。 |
| `ChemBlender/core/phonopy_adapter.py` | `adapt_phonopy_qpoints()` | 将 phonopy q-point、频率、复数 eigenvector、权重和晶胞关系转为 `PhononModeSet`。 |
| `ChemBlender/core/pyprocar_adapter.py` | `adapt_pyprocar_fermi_surface()` | 将已生成的 PyVista-compatible PyProcar surface 转为不依赖 PyVista 的顶点、三角面、band 和属性数组。 |
| `ChemBlender/core/critic2_adapter.py` | `parse_critic2_cpreport()` | 解析 critic2 `cpreport` JSON 的临界点、cell copies、connectivity、属性和 provenance，输出 `TopologyGraph`。 |
| `ChemBlender/core/qcschema_adapter.py` | `parse_qcschema_atomic_result()`、`parse_qcschema_molecule()`、`parse_qcschema()`、`export_qcschema()` | 兼容 QCSchema v1/v2 结果和 Molecule envelope，在内部模型与版本化交换文档之间转换。 |
| `ChemBlender/core/cjson_adapter.py` | `parse_cjson()`、`preview_cjson_export()`、`export_cjson()`、`sniff_cjson()` | 把 Avogadro CJSON whitelist 映射到统一结构、拓扑、categorical identity、annotation 和轻量数据；保留原始 envelope，并以 `ExportReport` 控制大型数组省略。 |

### 派生计算、工作流与存储

| 文件 | 主要入口 | 职责 |
| --- | --- | --- |
| `ChemBlender/core/wavefunction_grid.py` | `evaluate_molecular_orbital_grid()`、`evaluate_electron_density_grid()` | 验证内部 basis/MO convention，延迟调用 `qc-gbasis==0.1.0`，在任意 affine 规则网格求 MO 或按 occupation 合成电子密度。 |
| `ChemBlender/core/wavefunction_observables.py` | `evaluate_density_matrix_grid()`、`evaluate_electrostatic_potential_grid()` | 从 `DensityMatrix` 求 electron/spin density，并结合有效核电荷调用 GBasis 求 ESP；拒绝核奇点和无效矩阵。 |
| `ChemBlender/core/vibration_spectrum.py` | `derive_vibrational_spectrum()`、`derive_electronic_spectrum()` | 从振动强度或激发态强度生成 stick/高斯展宽 IR、Raman、UV-Vis、ECD `Spectrum`，记录派生身份。 |
| `ChemBlender/core/phonon_frames.py` | `derive_phonon_frames()` | 根据复数 q-point eigenvector 和 `Re[e exp(i(q·R-ωt+φ))]` 生成周期超胞声子动画帧。 |
| `ChemBlender/core/trajectory_frames.py` | `TrajectoryFrameManager.frame()`、`prefetch_around()`、`interpolate()`、`mean()` | 对 sidecar 轨迹执行逐帧 lazy 读取、有界 LRU 缓存、预取、插值和区间平均。 |
| `ChemBlender/core/grid_lod.py` | `derive_grid_lod()`、`volume_render_cache_key()`、`surface_render_cache_key()` | 通过确定性 stride 生成 `Grid3D` LOD，并计算 Volume/Surface 渲染缓存身份。 |
| `ChemBlender/core/grid_semantics.py` | `GridSemanticPreset`、`builtin_grid_semantic_presets()`、`resolve_grid_semantics()`、`default_grid_isovalue()` | 定义 Cube/Grid 显式语义与 unit 组合、默认 surface/isovalue policy；从 raw ambiguous 多 dataset grid 选择一个 dataset，生成不改 voxel 值的确定性 complete `Grid3D` revision 和 provenance。 |
| `ChemBlender/core/grid_cache_service.py` | `VolumeCacheRequest`、`CacheResult`、`prepare_volume_cache()`、`volume_cache_path()` | 不导入 Blender/OpenVDB 的 derived Volume cache transaction：计算 dataset/render identity 与 affine metadata，在 array load、slice、VDB population、publish 前后提供 progress/cancel checkpoint，以同目录短临时名验证后原子替换；cache hit 不重写，取消/失败保留既有目标并清理 staging。 |
| `ChemBlender/core/model_registry.py` | `MODEL_TYPES`、`MODEL_ENUMS`、`model_type_tag()`、`model_type_from_tag()` | 明确登记 sidecar 可序列化的 dataclass 和 enum；以不可变映射固定 type tag 与具体模型类的对应关系。 |
| `ChemBlender/core/sidecar.py` | `LazyNpyArray`、`save_project()`、`open_project()`、`close_project()` | `.cbq` v1 存储实现：写 generation metadata 与 canonical manifest hash，原子发布 manifest/数组；读取 v0.2/v1 hashed manifest 时先验证原始 hash/header，再以迁移副本严格 decode 并复验完整项目图，最后向内部 publication 返回未经改写的已验证 metadata。 |
| `ChemBlender/core/sidecar_migrations.py` | `migrate_manifest()` | 在严格模型 decode 前复制已校验文档：把 v0.1/v0.2 升到 schema `1.0`，补实验期及 Wave 3 兼容新增 registry、atomic identity 与 lattice-shift 缺省，并把 Structure 内嵌 `MolecularTopology` 确定性提升为独立 `TopologyRecord`；不改写旧 fixture 或已发布 sidecar。 |
| `ChemBlender/core/storage/atomic_paths.py` | `short_sibling_temporary_path()` | 为 NPY、JSON 和 VDB writer 生成同目录、完整随机 UUID 且不重复 content hash 的短原子临时路径，避免 Windows 临时路径预算被 basename 放大。 |
| `ChemBlender/core/storage/hashing.py` | `sha256_bytes()`、`sha256_file_snapshot()`、`sha256_file()` | 为 preflight、Reader API source recheck 和延迟 snapshot 提供共享、可取消 SHA-256；Windows ≤256 MiB 输入使用系统 CNG one-shot 并保持 64 KiB 取消检查语义，其他平台或更大文件退回 stdlib streaming，不导入 Blender。 |
| `ChemBlender/core/storage/publication.py` | `solidify_session()`、`inspect_publication_orphans()`、`PublishedProject`、`PublicationCancelled`、`PublicationRecoveryReport`、`PublicationRecoveryError` | 在目标同目录写入并复验完整 `.cbq` generation，经 backup rename 发布或非破坏回滚；可选 `progress`/`is_cancelled` 只在 atomic replacement 前允许取消并删除 owned staging，进入 replace/verify/rollback 后不再取消。默认关闭验证时打开的 project，仅在显式 opt-in 时把 final generation 的 exact verified project ownership 移交给事务；恢复不完整时同时保留原发布错误、回滚错误和不可变路径报告，不删除无法证明归属的目录。 |
| `ChemBlender/core/recipe.py` | `RecipeDefinition`、`plan_recipe()`、`recipe_document()`、`recipe_from_document()`、`builtin_recipes()` | 定义版本化分析 recipe 的输入语义、参数、输出、view、验证和引用；plan 阶段只绑定实体，不执行计算。 |
| `ChemBlender/core/scene_preset.py` | `builtin_scene_presets()`、`grids_share_affine()`、`plan_scene_preset()`、`validate_scene_plan()`、`scene_preset_for_recipe_view()` | 定义 publication scene preset，验证数据绑定和设置，并生成可重放的 render identity；`grid_volume` 允许显示 ambiguous/partial Grid3D，`signed_isosurface` 允许 Complete 或 Ambiguous preview，后者由 presentation 层标记为不可报告。Property surface 两侧必须 shape/unit/Structure 完全一致，origin/step vectors 使用 `1e-9` source-coordinate-unit absolute tolerance，绝不隐式重采样。 |
| `ChemBlender/core/analysis_report.py` | `build_analysis_report()`、`validate_analysis_report()`、`render_analysis_report_markdown()`、`write_analysis_report_bundle()` | 汇总 calculation、dataset、recipe、provenance、artifact 和引用，生成确定性 JSON/Markdown 报告包。 |
| `ChemBlender/core/external_connector.py` | `builtin_external_connectors()`、`ExternalRecordRequest`、`external_record_request_document()`、`external_record_source_uri()` | 定义 QCArchive/AiiDA/NOMAD 的 provider-neutral 请求、locator、凭据环境变量引用和脱敏 provenance URI。 |
| `ChemBlender/core/worker_protocol.py` | `WorkerRequest`、`WorkerResult`、`write_request()`、`read_request()`、`write_result()`、`read_result()` | Blender 与外部 worker 共用的严格 JSON 协议；校验版本、operation、实体 revision、artifact 相对路径、错误和取消状态。 |

## 独立 Reader Extension 示例

`examples/reader-extension/` 是单独构建、安装和卸载的 Blender Extension
源码，不进入 ChemBlender 基础 ZIP。`__init__.py` 只从
`bpy.app.driver_namespace["chemblender.reader_api.v1"]` 解析宿主发布的 API
module 并注册/注销插件；`reader.py` 只接收该公开 module，使用公开
manifest、descriptor、request 和科学模型读取 `CBSIMPLE 1`，不导入 `bpy`
或 `ChemBlender.core/ui/views`。

## Extension 维护脚本

这些脚本随源码保存，但由开发者或 CI 调用，不在 Extension 运行时执行。

| 文件 | 主要入口 | 职责 |
| --- | --- | --- |
| `ChemBlender/benchmarks/__init__.py` | package marker | 声明 2.3.0 基准数据集 package；不导入 `bpy` 或在 import 时生成/测量数据。 |
| `ChemBlender/benchmarks/datasets.py` | `BENCHMARK_SCALES`、`generate_structure_xyz()`、`generate_trajectory_npy()`、`generate_grid_npy()`、`generate_sdf_fixture()` | 固定 seed 的 50k/250k structure、1k/100k lazy NPY trajectory、128³/256³ grid 和 10k/100k SDF 流式 fixture；生成时逐行或 memmap 写入，不构造大型 Python tuple，并返回 SHA-256。 |
| `ChemBlender/scripts/benchmark_230.py` | `CASE_REGISTRY`、`PreparedFixtures`、`run_benchmark()`、`canonical_json()`、`write_canonical_json()`、`main()` | 统一 2.3.0 benchmark 输出：每个 run 在计时外一次性准备 deterministic source/hash、lazy trajectory 和必要 batch；per-sample project/sidecar/browser setup 与 cleanup 均在计时外，首次 fixture access 是 cold、warmup 后至少两个 hot samples 记录完整 CPython environment、median/p95/min/max 和 failure count。只延迟调用已存在的 pure-core stage，Blender enable/VDB/default-view 显式为外部运行时边界，canonical JSON 原子写入且不导入 `bpy`。 |
| `ChemBlender/scripts/benchmark_230_product.py` | `PRODUCT_CASES`、`run_product_qualification()`、`worker_main()`、`main()` | 仅供开发与发布资格审查的 exact-ZIP 产品性能 harness；orchestrator 为六个固定 interactive gate 启动独立 Blender 进程和隔离 profile，保存逐命令 stdout/stderr/timing，并用 `benchmark_230.py` 的 fail-closed schema/budget comparator 生成 canonical JSON/Markdown。Blender worker 只从 `bl_ext.user_default.chemblender` 导入已安装产品，校验 ZIP SHA 和 module origin，覆盖真实 Import Preview、Structure preset、OpenVDB、`TrajectoryFrameManager` mesh update 与 10k SDF Browser 路径；该脚本由 manifest 排除，不进入扩展包。 |
| `ChemBlender/scripts/benchmark_cube_flow.py` | `generate_cube()`、`run_benchmark()`、`main()` | 生成不入库的 128³ Cube，以真实 Blender/OpenVDB 路径分别测量 parse、NPY staging、sidecar save、cold/hot VDB 和 hot Volume view 的 samples/median/p95，并记录 peak Python allocation、硬件、cache 状态与 10 s 产品流门限。 |
| `ChemBlender/scripts/benchmark_crystal.py` | `benchmark_crystal()`、`main()` | 以固定 CIF/POSCAR 和合成 1000-site CIF 记录 Reader API preview、对称展开、10×10×10 supercell、POSCAR import 与真实 Blender periodic view 的 samples/median/p95、tracemalloc peak 和硬件环境；非 Blender 运行必须把 view 明确记为 `Not Run`。 |
| `ChemBlender/scripts/benchmark_exchange.py` | `benchmark_exchange()`、`main()` | 逐行生成 50k-atom MOL2/PDB/PQR/CJSON，记录 native parse 与 Reader API preflight/staged summary 的 cold/median/p95、`tracemalloc` peak、source bytes、硬件和 draw-path 边界；无 `bpy` 的 CLI 必须将 Blender RNA projection 记为 `Not Run`。 |
| `ChemBlender/scripts/validate_extension.py` | `main()` | 检查 manifest、共享 release version grammar、wheel 路径、依赖策略、绝对 import 和源码布局；非法 release version 是本地 preflight error，再调用 Blender 原生 Extension validate。 |
| `ChemBlender/scripts/release_metadata.py` | `ParsedReleaseVersion`、`parse_release_version()`、`ReleaseMetadata`、`read_release_metadata()`、`release_metadata_document()`、`workflow_run_records_from_pages()`、`select_exact_package_run()`、`select_exact_package_artifact()`、`main()` | 以单一 strict parser 定义 Blender 已验证的 stable/alpha/beta/rc version grammar；从 production manifest 严格读取 extension id、version 和单一 Windows platform，并确定性派生 package、checksum 与 artifact 名称；同时以标准库 JSON 展平全部 REST workflow-runs 分页响应，严格读取 `id`、`head_sha`、`head_branch` 并选择唯一 exact-SHA successful tag package run，CLI 输出其 `run_id`；artifact 选择保持唯一未过期 metadata-named REST artifact；不导入 Blender 或执行构建。 |
| `ChemBlender/scripts/probe_prerelease_version.py` | `probe_prerelease_version()`、`main()` | 把 Extension 复制到自动清理的临时目录，排除本地构建产物、缓存、Git metadata 和 wheel 目录，仅替换副本中的单一 manifest version，再调用 Blender 原生 validate 记录预发布版本兼容性；不修改 production manifest。 |
| `ChemBlender/scripts/build_extension.py` | `main()` | 解析 Blender/Python/MCP 路径与系统兼容性，读取一次 `ReleaseMetadata`，先验证再调用 Blender 原生 Extension build，并要求 metadata 指定的 exact package 文件存在。 |
| `ChemBlender/scripts/dependency_inventory.py` | `inventory()`、`main()` | 读取固定 `dependencies.toml` 与已下载 wheel，严格比对 manifest、SHA-256、ZIP 路径安全、许可证来源和压缩/解压预算，确定性生成 wheel inventory 与 license copy list；不下载、安装、解压或删除依赖。 |
| `ChemBlender/scripts/generate_format_docs.py` | `render_documents()`、`main()` | 复用 live reader capability document 与 `dependencies.toml` schema validator，在内存中确定性生成 canonical format/dependency JSON 和 `formats.md` marked table；`--check` 只比较 tracked bytes，不探测、下载或安装依赖。 |
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
- 想增加文件格式：阅读 `docs/development/import-pipeline.md`，复用 `ReaderDescriptor`，返回 `ImportBatch`，不要从 parser 直接创建 `bpy` 对象。
- 想增加物理量：先扩展 `PropertyDataset` 语义和 provenance，再添加派生函数与 Blender adapter。
- 想增加 Blender 显示：从 `dataset_view.py`、`grid_volume.py`、`surface_view.py` 或 `scene_preset_view.py` 选择最近的现有 contract。
- 想增加重型计算：在 `worker/` 注册固定 operation；不要让 Extension import、安装或同步运行重型后端。
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
