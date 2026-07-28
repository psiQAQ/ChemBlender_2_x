# ChemBlender.core 公共门面

`ChemBlender.core` 可在普通 CPython 中导入，且不依赖 `bpy`。精确的权威名称列表为 `ChemBlender.core.__all__`，由 [tests/test_core_public_api.py](../../../tests/test_core_public_api.py) 强制检查。

## 稳定模型门面

模型类和枚举是稳定门面；其构造器与 `.cbq` sidecar 类型标签保持兼容。请从 [ChemBlender.core](../../../ChemBlender/core/__init__.py) 导入这些语义模型。

`CalculationGroup` 是用户确认的跨来源计算关系；它属于权威项目模型，保存在 `QCProject.calculation_groups` 并随 `.cbq` 往返。

`TopologyRecord` 是独立的结构连接实体，使用 `TopologySource` 和
`QualityStatus` 区分文件显式连接、RDKit 解释、距离推断和用户编辑。
`ImportBatch.topologies` 与 `QCProject.topologies` 保存这些实体；
`Structure.topology_ids` 只保存关联 UUID，活动 topology 属于 View 状态。
旧 sidecar 中内嵌的 `MolecularTopology` 仅作为读取兼容输入。

周期晶体继续使用统一 `Structure`：`cell` 保存三个 row-vector 晶格向量，
`PeriodicSiteData` 保存 fractional coordinates 与 PBC。
`unit_cell_parameters()`、`fractional_to_cartesian()`、
`cartesian_to_fractional()` 和
`validate_periodic_coordinate_consistency()` 是纯 Python/NumPy 模型边界；
它们不引入第二套晶体实体，也不加载 Gemmi、spglib、ASE 或 pymatgen。

`AtomicIdentityData` 是可选逐 atom isotope、formal charge、atom-map、名称和
stereo 值对象。`MolecularRecord` 保留单一精确 raw block 与有序（允许重复）原始
属性。`RecordPropertyColumn` 与 `ConformerSet` 是可选 dataset 投影；它们不保存
RDKit 对象，也不实现 reader、grouping、export 或 UI 行为。RDKit is not a project model.

`GridSemanticPreset`、`builtin_grid_semantic_presets()`、
`resolve_grid_semantics()` 与 `default_grid_isovalue()` 构成 Cube/Grid
显式语义解析边界。解析保留 raw ambiguous grid；用户选择生成新的确定性
`Grid3D` revision 和 provenance。

## 存储 API

`open_project`、`save_project`、`close_project`、`LazyNpyArray` 及 `Sidecar*Error` 构成 sidecar 存储 API，用于 `.cbq` 项目和数组引用的读取、写入与错误处理。

## Session API

`ProjectSession` 在冻结的科学模型之外保存会话 UUID、临时根目录、dirty reasons、活动选择和 sidecar 链接状态。`create_session()` 创建带 UUID ownership marker 的临时根，`close_session()` 先关闭项目的 lazy resources，且只删除 marker 与会话 UUID 精确匹配的受控目录。

`sync_project_session_links_for_scenes()` 只把一个已验证 sidecar 的 UUID、schema、相对 locator 与 manifest hash 同步到当前 `.blend` 的全部 Scene，不重新发布科学数据；partial/conflicting link 必须通过 `relink_project_session_for_scenes()` 显式、原子地统一。`relink_project_session()` 保持单 Scene 兼容入口。

## Reader 契约

`ReaderDescriptor`、`ReaderRegistry`、`SniffMatch`、`SniffResult` 和 catalog API 是 alpha 0.x Reader 契约，尚非 v1。

内置 `mol` v2 reader 通过 RDKit 提供单记录 MOL V2000/V3000 的结构、原子身份、拓扑和 `MolecularRecord`；`mol-v2000` 仅保留为 V2000 的显式兼容 alias，并在报告中提示改用 `mol`。

内置 `sdf` reader 以原始字节逐条恢复多记录 SDF：每条 MOL block 和重复/空 SD 字段均保持独立 record 身份，Balanced 模式不会因单条坏记录而丢弃相邻有效记录；只为无歧义数值或布尔 SD 字段生成 typed record columns。

## Recipe 契约

`RecipeDefinition`、绑定、参数、计划、校验与文档函数构成 Recipe 契约；其版本化数据定义是该契约的边界。

## 内部 Adapter 兼容面

具体 reader 与 adapter、派生 helper、scene/reporting 和 connector 导出在本任务中保持 import 兼容，但属于内部兼容面，不是冻结的插件 API。
