# 保存、重开、恢复与迁移

一个已保存的 ChemBlender Project 是一对路径：`example.blend` 保存 Blender scene、View 和 project link；`example.cbq/` 保存 authoritative scientific project、manifest 和 arrays。备份、移动、恢复时必须把两者视为同一份项目。

## 要完成什么

- 用 `Save Project` 发布 `.blend`/`.cbq` 配对。
- 关闭 Blender 后冷重开，验证 Project link、科学实体与 View。
- 用 `Relink`、`Verify`、`Inspect Existing`、`Diagnostics` 或 `Detach` 处理 link 状态。
- 从完整 Grid3D 重建缺失的自有 derived cache。
- 显式预览并迁移 2.1/2.2 legacy scene。

## 示例

普通保存/重开可先从 [water.xyz](../../../examples/user-workflows/inputs/xyz/water.xyz)创建合同项目，再用带 topology 的 [AIN aspirin MOL](../../../examples/user-workflows/inputs/mol/ain-aspirin-v2000.mol)做代表性冷重开。旧版本迁移使用 hash-locked 的 [chemblender-2.1-molecule.blend](../../../examples/user-workflows/inputs/legacy/chemblender-2.1-molecule.blend)，只在副本上操作。

仓库还提供已经冷重开的 [workflow.blend](../../../examples/user-workflows/outputs/workflow-project/workflow.blend)（[sidecar manifest](../../../examples/user-workflows/outputs/workflow-project/workflow.cbq/manifest.json)）和 [migrated.blend](../../../examples/user-workflows/outputs/legacy-migration/migrated.blend)（[sidecar manifest](../../../examples/user-workflows/outputs/legacy-migration/migrated.cbq/manifest.json)）。五个按数据类型拆分的代表项目见[展示数据](03-visualize.md#示例)。它们各自依赖同目录的完整同名 `.cbq/`，用于直接查看和对照，不替代下面的手工保存、迁移与重开练习。

`.blend` 保存的 sidecar locator 以及 Volume/VDB 路径使用相对位置，因此配对可整体移动。`SourceRevision.locator` 可能保留首次导入时的绝对源路径；它只是重定位/重新解析提示，不参与科学身份或当前 sidecar 恢复。换机器后项目与已保存 View 仍可打开，但再次解析原始文件前可能需要重新选择来源。

## 操作前检查

1. 准备一个可写、路径稳定的测试目录。关闭其他正在使用同一项目的 Blender 进程。
2. 重要项目先复制 `.blend` 与完整 `.cbq/`；不要只复制 manifest 或单个 array。
3. legacy 迁移必须从外部副本开始，并保留原副本直到迁移结果冷重开通过。
4. 不要为消除 `Missing` 状态而新建空的同名 `.cbq`，也不要按文件名接受 `Mismatch`。

## UI 操作

### 保存与冷重开

1. 导入并确认数据后，在 `Quick Import` 选择 `Save Project`。未保存的 `.blend` 会进入 Save As。
2. 保存到 `example.blend`。ChemBlender 使用 Blender 保存回调传入的目标路径，在同目录发布并验证 `example.cbq/`，再把 link 写入 `.blend`。
3. 首次保存或另存到新目录、名称都只需一次 Save / Save As；旧配对保留，新的 locator 指向新配对。
4. 查看 Quick Import/Project Browser 状态应为 clean、Connected。
5. 关闭 Blender。重新启动 Blender 5.1，再打开 `example.blend`；这才是冷重开测试。
6. 在 Project Browser 核对 Project identity、sources、entities、quality、active View 和 sidecar locator。

### Link 恢复

| 状态 | 首选操作 |
| --- | --- |
| `Connected` | 继续工作；必要时选择 `Verify` 重新检查 locator、manifest 和 arrays |
| `Missing` | 找回原配对后选择 `Relink`，选择真实 `.cbq/manifest.json` |
| `Mismatch` | 停止，确认正确备份；不要仅按 basename 接受候选 |
| `Incompatible` | 保持文件不变，使用兼容版本打开 |
| `Invalid` | 保存证据，先开 `Diagnostics`，再决定恢复 |

Relink 的文件选择器选择 `.cbq/` 内的 `manifest.json`；MCP 的 `filepath` 也可直接传 `.cbq/` 目录。候选必须匹配 `.blend` 已保存的 UUID、schema 与 manifest hash，不能仅因 UUID 相同就采用另一代数据。成功 Relink/Verify 后 Browser 与 Quick Import 同步刷新。

`Inspect Existing` 只检查候选，不会采用它。`Detach` 会移除 link metadata，但保留 Blender objects；这些 detached objects 不能替代 scientific project。

### Revision 与缓存

导入新 source revision 时，现有 View 不会自动切换。选择 `Update Selected Views`、`Comparison View` 或 `Keep Current`，并核对旧结果仍绑定旧 Structure revision。

ChemBlender 自有的 `cache/render/` 与 `cache/derivation/` 可以重建。冷重开时，如果 View cache 缺失但 link 与 Grid3D 完整，让插件重建；不要删除 `.cbq` root、manifest 或 authoritative arrays。当前普通用户面板没有通用 cache-delete 按钮。

### Legacy 2.1/2.2 迁移

1. 复制 legacy `.blend` 到新目录并打开副本；先保存为普通文件。
2. 打开 `ChemBlender > Legacy Migration`，选择 `Preview Legacy Migration`。
3. 检查 destination、每个 legacy object、拟创建的 Structure/Topology/PeriodicSite、显示恢复和 unsupported diagnostics。长路径与科学警告会自动换行；MCP 执行公开预览 Operator 后读取 `Scene.chemblender_migration_preview_json`，其完整 JSON 不写入 `.blend`，重开或完成迁移后清空。`backup only` 项只保留原对象，不创建科学实体。
4. 预览可接受后，选择 `Migrate to Project`，并明确确认原对象将移入 backup collection。
5. 迁移后，新 View 应立即可渲染，状态为 Connected；没有原始 SourceRevision 的实体在默认 By Source 中列于 `Unattributed project data`。包内显示节点以新的 datablock 身份载入，原 legacy node groups 保留。保存迁移后的 `.blend`，关闭 Blender，冷重开；检查 link 为 Connected、migrated View 正常，并保留隐藏的 `ChemBlender Legacy Backup` collection。

迁移完成后没有受支持的自动 unmigrate。要回退，关闭 Blender 并一起恢复外部的 pre-migration `.blend`/`.cbq` 备份。

## 屏幕上应看到什么

- 保存后同目录有 `.blend` 文件和同 basename 的 `.cbq/` 目录。
- Project Browser 显示 Connected、project identity、sources、entities 和 View；clean save 不应改写未变化的 scientific arrays。
- Link 错误只显示当前状态允许的恢复操作，不会默默采用另一个 sidecar。
- 成功迁移后，legacy 原对象位于隐藏 backup collection，新 Project/View 与它们分开。

## 成功判据

1. 关闭所有 Blender 窗口后，用 Blender 5.1 冷重开 `.blend`，Project link 仍为 Connected。
2. 样例的 source、atom count、quality、关键 View binding 与保存前一致。
3. 移走并放回测试 sidecar 后，`Missing -> Relink/Verify -> Connected` 的恢复路径可完成，且 project UUID/manifest hash 一致。
4. 缺失的自有 Grid cache 可从 Grid3D 重建；foreign Volume 路径不被更改。
5. legacy migration 的 sidecar、migrated View、diagnostics 与 backup collection 在重开后仍可检查。

## Agent 提示词

### Save Project 与冷重开

```text
使用当前 Blender MCP 通过 `bpy.ops.chemblender.quick_import`/`confirm_import` 导入 `examples/user-workflows/inputs/mol/ain-aspirin-v2000.mol`。一次完成 Blender 5.1/Extension/RDKit/active-file/dirty-state 预检，并检查 ChemBlender Operator RNA、`bpy.ops.wm.save_as_mainfile`、`bpy.ops.wm.save_mainfile` 的 RNA 与 poll。对未保存文件用 UI 等价 Save As 选择全新测试路径，一次保存后检查配对；再另存到新目录，检查新的 locator 和旧配对仍完整；不得直接写 `.cbq`。验证 `.blend` 和同 basename `.cbq/`、clean/Connected、project identity。然后正常关闭并重启 exact Blender 5.1，重开 `.blend`，核对 source、21-atom Structure、21-bond Topology、View binding 和 diagnostics。不得 import private modules 或 bypass save/link confirmation。
```

### Verify / Relink

```text
使用当前 Blender MCP 在测试副本中检查 Project link。先返回 active file、dirty state、link state 和 `bpy.ops.chemblender.project_link_recovery` Operator RNA/poll。只调用 UI 当前显示允许的 Verify 或 Relink action；候选 `.cbq` 的 project UUID、schema、manifest hash 和 arrays 必须通过公开验证，任何 Mismatch/Invalid confirmation 都停止。不得 import private modules、直接改 scene link custom property、manifest 或 `.cbq`。完成后冷重开并验证 Connected，不得 bypass confirmation。
```

### Revision 与 View

```text
使用当前 Blender MCP 导入同一 source 的新 revision，先检查 `bpy.ops.chemblender.revision_view_action` Operator RNA 和 Project Browser 显示的 current/replacement revision。把 `Update Selected Views`、`Comparison View`、`Keep Current` 及其 confirmation 返回给我，不自动选择。调用批准的公开 Operator 后验证旧/新 View visibility、entity/revision binding 和旧结果仍绑定旧 Structure。不得 import private modules、写 `.cbq`、直接改 `cb_` state 或 bypass confirmation。
```

### Legacy migration

```text
使用当前 Blender MCP 打开 `examples/user-workflows/inputs/legacy/chemblender-2.1-molecule.blend` 的工作副本，要求 Blender >= 5.1 和 enabled key 正确。检查 `bpy.ops.chemblender.preview_legacy_migration`、`migrate_legacy_scene` 及保存 Operator RNA/poll。先执行非突变 preview，返回 destination、legacy objects、拟创建实体、backup-only items、diagnostics 和 migration confirmation；未经我确认不迁移。批准后调用公开 Operator，保存新的 `.blend`/`.cbq` 配对并冷重开，验证 Connected、migrated View 和 `ChemBlender Legacy Backup`。不得 import private modules、直接编辑 `.cbq`/custom properties 或 bypass confirmation。
```

## 常见问题

| 现象 | 处理 |
| --- | --- |
| 只有 `.blend`，没有 `.cbq/` | 检查保存报告、目标目录权限和 Project 状态；不要继续把对象当作 authoritative data |
| 移动后显示 `Missing` | 把配对一起移动，或用 `Relink` 指向原 sidecar；不要创建空目录 |
| 显示 `Mismatch` | 找到同一备份代的 `.blend`/`.cbq`。混用两次备份应被拒绝 |
| 重开后 View 缺失 | 先确认实体和 link，再检查是否为可重建 cache 或 revision prompt；不要从对象缺失推断 Project 丢失 |
| `ChemBlender Legacy Backup` 已存在 | 停止迁移。文件可能已迁移或含保留证据，先检查 project link 与 transaction markers |

详细恢复规则见[项目与 sidecar](../project-sidecar.md)和[legacy migration](../legacy-migration.md)。返回[工作流总览](README.md)。
