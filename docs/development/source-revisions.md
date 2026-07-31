# Source revision、派生实体与 View 绑定

ChemBlender 将“用户认为是同一个来源”和“该来源某一次不可变解析”分开。文件路径
可以移动；科学身份不能随路径或 Blender Object 的变化被重写。

## 两级来源身份

[`SourceRecord`](../../ChemBlender/core/model/sources.py) 表示逻辑来源，保存
UUID、显示名、source kind 和创建时间。

[`SourceRevision`](../../ChemBlender/core/model/sources.py) 表示一次已验证解析：

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
[`commit_structure_edits()`](../../ChemBlender/core/edits/structure.py) 创建
derived Structure（以及需要时的 user-edited topology）：

- derived entity 使用 canonical scientific content 计算自己的 `revision`；
- `ProvenanceRecord.parent_ids` 指回 source Structure 和选定 topology；
- source Structure 及其原结果不变，linked result 不自动继承；
- derived Structure 不是伪造的新文件解析，因此不会改写原 SourceRevision。

同一逻辑 source 出现新 bytes 时，Import Preview 创建新 SourceRevision，并要求
用户对 duplicate/reuse/new revision 做显式决定。既有 View 不自动跳到新 revision。

## View 绑定

默认 View planner 从 `SourceRevision.created_entity_ids` 中选择可显示实体；实际
Scene preset 写入的 binding 是每个输入的 `entity_id` 和实体 `revision`，不是任意
Object 名称或 source path。`cb_scene_bindings_json` 仅是 Blender 视图 metadata；
权威实体仍在 `.cbq`。

重新导入产生新 revision 后，Project Browser 保留 current/new revision prompt。
Update、Comparison 或 Keep Current 都先复验 live preset、entity type、revision 和
render settings；缺失、陈旧或歧义 binding fail closed。View 更新不删除旧科学实体。

## 持久化与恢复

- `.cbq` manifest 保存 SourceRecord、SourceRevision、科学实体、diagnostics 和
  provenance；大型数组使用 content-addressed NPY。
- `.blend` 保存 project link 与轻量 View binding。移动项目时应一起移动 `.blend`
  和 `.cbq`，再使用受控 relink/inspection 流程。
- derived OpenVDB、mesh 和其他 render cache 不是 provenance；删除后可由绑定的
  Grid3D/entity revision 重建。
- 插件缺失不删除已提交 revision，只使对应 reader 的 reparse unavailable。

相关决策：
[来源与事务](../../.agents/decisions/0031-source-session-import-transaction-boundary.md)、
[不可变科学编辑](../../.agents/decisions/0034-immutable-edit-and-topology-provenance.md)、
[sidecar 边界](../../.agents/decisions/0006-blend-sidecar-boundary.md)。
