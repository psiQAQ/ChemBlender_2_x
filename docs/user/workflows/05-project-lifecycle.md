# 保存、重开、恢复与迁移

一个已保存的 ChemBlender Project 是一对路径：`example.blend` 保存 Blender scene、View 和 project link；`example.cbq/` 保存 authoritative scientific project、manifest 和 arrays。备份、移动、恢复时必须把两者视为同一份项目。

## 要完成什么

- 用 `Save Project` 发布 `.blend`/`.cbq` 配对。
- 关闭 Blender 后冷重开，验证 Project link、科学实体与 View。
- 用 `Relink`、`Verify`、`Inspect Existing`、`Diagnostics` 或 `Detach` 处理 link 状态。
- 从完整 Grid3D 重建缺失的自有 derived cache。
- 显式预览并迁移 2.1/2.2 legacy scene。

## 示例

普通保存/重开可从 [water.xyz](../../../examples/user-workflows/inputs/xyz/water.xyz)创建项目。旧版本迁移使用 hash-locked 的 [chemblender-2.1-molecule.blend](../../../examples/user-workflows/inputs/legacy/chemblender-2.1-molecule.blend)，只在副本上操作。

## 操作前检查

1. 准备一个可写、路径稳定的测试目录。关闭其他正在使用同一项目的 Blender 进程。
2. 重要项目先复制 `.blend` 与完整 `.cbq/`；不要只复制 manifest 或单个 array。
3. legacy 迁移必须从外部副本开始，并保留原副本直到迁移结果冷重开通过。
4. 不要为消除 `Missing` 状态而新建空的同名 `.cbq`，也不要按文件名接受 `Mismatch`。

## UI 操作

### 保存与冷重开

1. 导入并确认数据后，在 `Quick Import` 选择 `Save Project`。未保存的 `.blend` 会进入 Save As。
2. 保存到 `example.blend`。ChemBlender 在同目录发布 `example.cbq/`，验证 sidecar 后再完成 Blender 保存。
3. 查看 Quick Import/Project Browser 状态应为 clean、Connected。
4. 关闭 Blender。重新启动 Blender 5.1，再打开 `example.blend`；这才是冷重开测试。
5. 在 Project Browser 核对 Project identity、sources、entities、quality、active View 和 sidecar locator。

### Link 恢复

| 状态 | 首选操作 |
| --- | --- |
| `Connected` | 继续工作；必要时选择 `Verify` 重新检查 locator、manifest 和 arrays |
| `Missing` | 找回原配对后选择 `Relink`，指定真实 `.cbq/` |
| `Mismatch` | 停止，确认正确备份；不要仅按 basename 接受候选 |
| `Incompatible` | 保持文件不变，使用兼容版本打开 |
| `Invalid` | 保存证据，先开 `Diagnostics`，再决定恢复 |

`Inspect Existing` 只检查候选，不会采用它。`Detach` 会移除 link metadata，但保留 Blender objects；这些 detached objects 不能替代 scientific project。

### Revision 与缓存

导入新 source revision 时，现有 View 不会自动切换。选择 `Update Selected Views`、`Comparison View` 或 `Keep Current`，并核对旧结果仍绑定旧 Structure revision。

ChemBlender 自有的 `cache/render/` 与 `cache/derivation/` 可以重建。冷重开时，如果 View cache 缺失但 link 与 Grid3D 完整，让插件重建；不要删除 `.cbq` root、manifest 或 authoritative arrays。当前普通用户面板没有通用 cache-delete 按钮。

### Legacy 2.1/2.2 迁移

1. 复制 legacy `.blend` 到新目录并打开副本；先保存为普通文件。
2. 打开 `ChemBlender > Legacy Migration`，选择 `Preview Legacy Migration`。
3. 检查 destination、每个 legacy object、拟创建的 Structure/Topology/PeriodicSite、显示恢复和 unsupported diagnostics。`backup only` 项只保留原对象，不创建科学实体。
4. 预览可接受后，选择 `Migrate to Project`，并明确确认原对象将移入 backup collection。
5. 保存迁移后的 `.blend`，关闭 Blender，冷重开；检查 link 为 Connected、migrated View 正常，并保留隐藏的 `ChemBlender Legacy Backup` collection。

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

> 在 Blender 5.1 中用 ChemBlender 公开 UI 保存当前 Project 到新的测试目录。验证 `.blend` 与同 basename `.cbq/` 都存在、Project 状态为 clean/Connected。然后正常关闭并重新启动同一 Blender 5.1，打开 `.blend`，只通过公开 UI/RNA 核对 project identity、source、Structure、View binding 和 diagnostics。不要直接改 `.cbq`、manifest 或 scene 的私有 link 属性；若 link 不一致，停在 Project Browser recovery UI。

## 常见问题

| 现象 | 处理 |
| --- | --- |
| 只有 `.blend`，没有 `.cbq/` | 检查保存报告、目标目录权限和 Project 状态；不要继续把对象当作 authoritative data |
| 移动后显示 `Missing` | 把配对一起移动，或用 `Relink` 指向原 sidecar；不要创建空目录 |
| 显示 `Mismatch` | 找到同一备份代的 `.blend`/`.cbq`。混用两次备份应被拒绝 |
| 重开后 View 缺失 | 先确认实体和 link，再检查是否为可重建 cache 或 revision prompt；不要从对象缺失推断 Project 丢失 |
| `ChemBlender Legacy Backup` 已存在 | 停止迁移。文件可能已迁移或含保留证据，先检查 project link 与 transaction markers |

详细恢复规则见[项目与 sidecar](../project-sidecar.md)和[legacy migration](../legacy-migration.md)。返回[工作流总览](README.md)。
