# Source revision、派生实体与 View 绑定

ChemBlender 将“用户认为是同一个来源”和“该来源某一次不可变解析”分开。文件路径
可以移动；科学身份不能随路径或 Blender Object 的变化被重写。

## 两级来源身份

[`SourceRecord`](../../cbq_core/model/sources.py) 表示逻辑来源，保存
UUID、显示名、source kind 和创建时间。

[`SourceRevision`](../../cbq_core/model/sources.py) 表示一次已验证解析：

| 字段 | 含义 |
| --- | --- |
| `content_hash` / `byte_size` | 本次读取的 exact source bytes |
| `reader_plugin_id` / `reader_id` / `reader_version` | 产生结果的 reader 身份 |
| `import_parameters_hash` | canonical parameters 的 SHA-256 |
| `parse_identity` | content hash、plugin、reader/version 和 canonical parameters 的确定性 hash |
| `created_entity_ids` | 本次解析实际创建的科学实体和 provenance |
| `diagnostic_ids` | 同一 batch 内与本 revision 对应的诊断 |
| `locator` / `locator_kind` | 可用于重定位的来源提示，不是科学身份 |

`SourceRevision.id` 是一次 staging/commit 使用的 UUID；重复和更新判断使用
`parse_identity`、content hash 与受控 locator 规则，不能仅比较路径或文件时间。
parse 前后 source bytes 都会复验，变化时当前 staging 结果失效。

## immutable source 与 derived Structure

已提交的 Structure、TopologyRecord、Dataset 和 SourceRevision 是 immutable。
Object transform、材质、可见性和缓存变化不创建科学 revision。坐标、元素、键、
晶胞、occupancy 等科学修改必须通过
[`commit_structure_edits()`](../../cbq_core/structure_edit.py) 创建
derived Structure（以及需要时的 user-edited topology）。此函数位于共享核心，
Blender 的显式 Apply 与整包导入共用持久化事务。派生约束：

- derived entity 使用 canonical scientific content 计算自己的 `revision`；
- `ProvenanceRecord.parent_ids` 指回 source Structure 和选定 topology；
- source Structure 及其原结果不变，linked result 不自动继承；
- derived Structure 不是伪造的新文件解析，因此不会改写原 SourceRevision。

外部 Python Import Preview 可创建新 SourceRevision，并通过显式决策处理来源
重复或新 revision。Blender 当前导入的是完整 CBQ：同 UUID、同内容复用；同 UUID、
不同内容拒绝；不同来源 UUID 的相同内容需要显式确认。规则由
[`package_import.py`](../../cbq_core/package_import.py) 统一校验。既有 View 不自动跳到新 revision。

## 在 Blender 应用分子编辑

1. 导入 CBQ 并显示分子 Structure，选中其 Mesh。
2. 在 **Molecular Mesh Editing → Edit Mesh** 中编辑原子、坐标和键；这是显示草稿，尚未更改 CBQ。
3. 离开 Edit Mode，点击 **Apply Mesh as New Structure**。程序验证源 revision、atom mapping、键级和单位，保存新 Structure/Topology，再创建和选中新 View。
4. 原 Structure、关联计算结果及旧 View 保留。新结构不自动继承旧波函数等计算结果。Object 平移、旋转和缩放仍属于显示，不写入科学坐标。
5. 写入失败时原项目不变；如果提示 **Structure saved; refresh or rebuild its View**，数据已经入库，应修复项目链接或重建 View，不要把它当作未提交后重新计算。

当前入口针对分子 Mesh；周期结构编辑和外部优化闭环仍需按实施方案分别验收。

## View 绑定

默认 View planner 从 `SourceRevision.created_entity_ids` 中选择可显示实体；实际
Scene preset 写入的 binding 是每个输入的 `entity_id` 和实体 `revision`，不是任意
Object 名称或 source path。`cb_scene_bindings_json` 仅是 Blender 视图 metadata；
权威实体仍在 `.cbq`。

View 重建须复验 live preset、entity type、revision 和 render settings；缺失、
陈旧或歧义 binding fail closed。View 更新不删除旧科学实体。旧版本的 raw-file
Import Preview revision prompt 不再是当前 Viewer 入口；统一异步处理返回结果后的
自动选择与显式重链接，仍须按本地处理模块方案完成控制器和生命周期验收。

## 持久化与恢复

- `.cbq` manifest 保存 SourceRecord、SourceRevision、科学实体、diagnostics 和
  provenance；大型数组使用 content-addressed NPY。
- `.blend` 保存 project link 与轻量 View binding。移动项目时应一起移动 `.blend`
  和 `.cbq`，再使用受控 relink/inspection 流程。
- derived OpenVDB、mesh 和其他 render cache 不是 provenance；删除后可由绑定的
  Grid3D/entity revision 重建。
- 外部处理程序或 reader 缺失不删除已提交 revision；Viewer 仍可读取和显示准备好的 CBQ，重新解析须在具备能力的外部环境进行。

相关决策：
[来源与事务](../../.agents/decisions/0031-source-session-import-transaction-boundary.md)、
[不可变科学编辑](../../.agents/decisions/0034-immutable-edit-and-topology-provenance.md)、
[sidecar 边界](../../.agents/decisions/0006-blend-sidecar-boundary.md)。

本地 Apply 的安装版回归见 `tests/blender_cbq_viewer_smoke.py`：在已保存场景中提交编辑，移走输入 CBQ，使用新 Blender 进程重开并显式重建派生结构 View，再 Save As/重开。测试数据为合成结构；这不替代真实 RDKit 外部优化和逐物理量验收。共享核心使用包内相对 import，使独立 Python 与扩展 vendoring 保持同一源码。
