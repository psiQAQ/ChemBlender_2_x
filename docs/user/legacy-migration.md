# Legacy scene migration

当前 CBQ 架构先用外部 Blender 提取脚本迁移旧 `.blend`，再由 Viewer 从迁移报告显式重建 View。旧面板流程仅适用于本文后半部分所述的归档 2.3.0 版本。

## 目录

- [外部提取与导出](#外部提取与导出)
- [输出、验证及晶体升级](#输出验证及晶体升级)
- [显示恢复边界](#显示恢复边界)
- [历史 2.3.0 面板流程](#历史-230-面板流程)

## 外部提取与导出

使用 Blender 5.1 或更新版本，在本仓库根目录运行。将示例输入、输出路径改为自己的绝对路径。输出父目录必须已存在，结果目录必须不存在。

```powershell
$previousResources = $env:BLENDER_USER_RESOURCES
$env:BLENDER_USER_RESOURCES = Join-Path $env:TEMP ("cb-legacy-" + [guid]::NewGuid())
try {
    & "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --factory-startup --disable-autoexec --python-exit-code 1 "D:\data\old.blend" --python ".\chemblender_prepare\legacy\__main__.py" -- --output "D:\data\legacy-prepared" --preview
} finally {
    $env:BLENDER_USER_RESOURCES = $previousResources
}
```

检查打印的结构清单、显示参数和诊断后，用相同命令去掉末尾 `--preview` 执行导出。脚本只读取原场景；不保存或覆盖原 `.blend`，不加载旧插件，不自动执行文件内脚本。

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--output` | 必填 | 新目录，包含 `project.cbq/` 和 `migration.json` |
| `--preview` | 关闭 | 仅输出诊断报告，不写结果 |
| `--cancel-file` | 未设置 | 可选取消标记路径；检测到文件即停止发布 |

## 输出、验证及晶体升级

`project.cbq` 使用共享 CBQ 1.1 模型，保存结构、显式键、晶体位点、ADP 和来源哈希。报告记录每个新结构 UUID、原对象名称、显示参数、诊断，以及 CBQ manifest 文件 SHA-256。两个文件在同一目录准备并校验后一起发布；失败、取消或目标已存在时不覆盖结果。

```powershell
.\.venv\Scripts\chemblender-prepare.exe validate "D:\data\legacy-prepared\project.cbq" --json
```

若报告的 `requires_numeric_symmetry_upgrade` 非空，在已配置 Gemmi 的外部准备环境执行：

```powershell
.\.venv\Scripts\chemblender-prepare.exe upgrade "D:\data\legacy-prepared\project.cbq" --output "D:\data\legacy-upgraded.cbq" --json
```

升级保留原包、结构 UUID、晶胞和原数值，并为新增数值对称操作更新结构 revision 和来源记录。升级前只支持原位点展示，不支持完整对称展开；不在 Blender 安装 Gemmi。显示恢复必须先导入与 `migration.json` 同目录、哈希匹配的原始 `project.cbq`，再按下述流程恢复旧 View。升级后的 CBQ 是后续完整对称展开使用的独立科学数据包；当前恢复器不会把原报告自动套用到升级包。

## 显示恢复边界

报告中的原子半径、颜色、缩放、键显示、材质和节点输入是独立的显示恢复记录，不属于科学数组。`display_restore_status: recorded_only` 表示可移植报告本身只记录参数；它不会在导入 CBQ 时自动改变场景。

在 Viewer 的 **CBQ Scientific Project** 区域完成以下步骤：

1. 导入 `legacy-prepared/project.cbq`，确认预览无 UUID 内容冲突。
2. 在 **Legacy Migration Report** 选择同目录的 `migration.json`。
3. 点击 **Restore Legacy Views**。成功后会新增以 `(Migrated)` 结尾的 View，旧对象和已有 View 均保留。
4. 用新文件名保存 `.blend`，关闭并重开，确认 Project 状态为 Connected，并检查新 View。

恢复器重新校验报告格式、原始 manifest 文件哈希和完整 CBQ 内容；只在相邻 CBQ 已完整导入且无冲突时创建 View。节点名称和输入只写入 View 的审计属性，不执行旧节点、不修改同名旧节点组，也不根据报告中的来源路径加载文件。任一 View 创建失败会删除本次已创建的 View、材质和节点资产，并恢复原 active entity/View；科学项目、旧对象和已有 View 不变。目标名称已存在时拒绝重复恢复。

实际验证覆盖本文列出的三个历史 fixture：普通分子、编辑后 scaffold、含占据率和 Uij 的晶体。未知文件仍以具体诊断为准，不承诺恢复任意 `.blend`。

## 历史 2.3.0 面板流程

以下为归档版本的使用说明，当前 Viewer 不提供这些旧迁移按钮。


The **Legacy Migration** panel converts detected ChemBlender 2.1/2.2 mesh
objects into the 2.3 Project model. It is an explicit migration, not a file-open
side effect. Current `structure_view_v1` objects and already owned migration
backup objects are not treated as legacy input.

## Work on a copy

1. Close other Blender processes using the project.
2. Copy the source `.blend` and, if present, its complete `.cbq/` directory to
   a new working location. Keep the `.blend` and `.cbq` together.
3. Open and save the working-copy `.blend` as a regular file. The wizard needs
   a saved path and publishes a same-basename `.cbq` beside it.
4. Keep the external pre-migration pair until the migrated pair has saved and
   reopened successfully.

The migration refuses to replace an unrelated existing `.cbq`. Do not delete
or rename an unknown sidecar merely to make the wizard continue.

## Detect and preview

Loading a scene only records a non-mutating detection result. In the panel:

1. Choose **Preview Legacy Migration**.
2. Review the destination, every legacy object, the proposed Structure,
   Topology/PeriodicSite and Provenance entities, recovered display settings,
   and all unsupported diagnostics.
3. Treat an item marked **backup only** as an original object that will be
   preserved but will not create a Project entity or migrated View. Cell-only
   helper geometry is one such case.
4. Run **Migrate to Project** only after the preview is acceptable and provide
   the explicit confirmation that the original objects will move to backup.

Execution re-extracts and replans the scene; an earlier preview is not a permit
to commit changed objects.

## What a successful migration does

- Molecule scaffolds become `Structure` plus explicit `TopologyRecord` data.
- Crystal scaffolds use the retained CIF site/cell data to create `Structure`
  plus `PeriodicSiteData`. Evaluated modifier geometry is not promoted to
  scientific coordinates.
- Recovered display values are applied only when their shape and values pass
  validation. Unsupported values stay in diagnostics rather than becoming
  scientific facts.
- The candidate Project is published and verified before every Blender scene
  is relinked to the new sidecar.
- Original detected objects move to the hidden
  `ChemBlender Legacy Backup` collection. The collection and objects carry the
  same project and transaction markers; each original is linked only to that
  collection.

Save the `.blend`, reopen it, confirm the Project link is Connected, inspect
the migrated Views, and leave the backup collection intact while validating
the result.

## Provenance and diagnostics

Source provenance is trusted only when extraction sees a saved regular
non-linked `.blend`, records its source path and source hash, and planning
rechecks the same SHA-256. If that proof is absent, invalid or changes, the
provenance source fields remain empty and a diagnostic is retained; a filename
is never fabricated as proof.

Missing bond orders or display arrays, unknown custom properties, ignored
modifier output, non-uniform transforms and other unverified recovery facts
are reported with stable `legacy_unverified` diagnostics and Ambiguous quality.
Read the scientific consequence before using or exporting the migrated data.

The shipped acceptance evidence uses three hash-locked fixtures:

| Fixture | SHA-256 |
| --- | --- |
| `chemblender-2.1-molecule.blend` | `36b05c3cacbcc067714615a49df35cf20973bc8122329194ddaecd249df6c3d4` |
| `chemblender-2.2-crystal.blend` | `f2995e826762a85bfb6854e314483175c3d39c2cceef109db3f395ab2e83c06a` |
| `chemblender-2.2-edited-scaffold.blend` | `a6af8e232fe7b934bf850f8e6b24d396596b79cc1fd38e8ff6eb071c50bf8740` |

Their provenance and inventory are recorded in the
[fixture README](../../tests/fixtures/legacy-blend/README.md); the installed
Extension save/reopen run is recorded in the
[Wave 4 usability results](../quantum-visualization/2.3.0/usability-results-rc1.md).
These fixtures prove the named cases only. Preview diagnostics remain the
authority for a different scene.

## Failure rollback and completed-migration recovery

Before a migration reports success, its transaction rollback attempts to
remove candidate Views/materials, restore scene links and session state,
restore the prior sidecar, and put original objects back in their former
collections. Cleanup failures are attached to the original error. Preserve the
working files and diagnostic text if any rollback step reports a residual path.

After a successful migration there is no supported automatic undo or
"unmigrate" command. Blender Undo is not the recovery contract, and the hidden
backup collection alone cannot restore the former Project/sidecar state. To
return to the old state, close Blender and restore the external pre-migration
`.blend` and `.cbq` backup pair together.

If `ChemBlender Legacy Backup` already exists, stop: the file may already have
been migrated or contain retained evidence. Do not merge, rename or delete the
collection until the Project link, transaction markers and external backup are
understood.

For sidecar link recovery, continue with
[Project and sidecar](project-sidecar.md). For the 2.2-to-2.3 package and schema
upgrade, see [Upgrade to ChemBlender 2.3.0](../migration/2.3.0.md).
