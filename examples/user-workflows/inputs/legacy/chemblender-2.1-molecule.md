# ChemBlender 2.1 旧场景迁移样例

## 用途与选择理由

这个文件不是分子交换格式，而是 ChemBlender 2.1 创建的 `.blend` 场景。它只用于验证旧集合、对象和属性能否先预览、再由用户确认迁移；不能拿它判断新版导入器的分子数据精度。

## 来源与许可

- 取得日期：`2026-08-07`。

- 来源标识：`tests/fixtures/legacy-blend/chemblender-2.1-molecule.blend@3e1d02e046851c6c89a81ac8dce42b435bb25509`。
- 来源路径：仓库测试夹具 `tests/fixtures/legacy-blend/chemblender-2.1-molecule.blend`。
- 许可：`GPL-3.0`，随 ChemBlender 仓库分发。

## 规模与分辨率

文件大小 `153914` bytes，来源版本为 2.1。`.blend` 大小反映场景序列化结果，不是分子坐标或渲染分辨率；迁移后应检查实体、拓扑、恢复的 View 和保留的原文件，而不是仅看文件能否打开。

## 字段说明

| 内容 | 含义 |
| --- | --- |
| Blender datablocks | 场景、集合、对象、网格和材质等 Blender 数据块 |
| ChemBlender 2.1 属性 | 旧版插件写入的分子与显示状态 |
| 旧集合层级 | 外部导出器识别来源对象的依据；原文件单独保留 |
| 文件版本信息 | Blender 用来决定兼容读取路径的头部信息 |

## ChemBlender 支持边界

ChemBlender 2.5 使用外部迁移导出：独立 Blender 进程运行 prepare 的 `legacy/__main__.py`，产生 `project.cbq` 和 `migration.json`。Viewer 通过 **Preview CBQ**、**Import CBQ** 和 **Restore Legacy Views** 恢复结果。旧版直接修改场景的迁移 Operator 不适用于这条路径。

导出器不改写原 `.blend`，也不执行报告中记录的旧节点设置。报告保留显示参数，恢复时按当前 View 规则应用；这不保证任意旧材质或节点网络逐项还原。该样本的 4 个原子、3 条键和坐标已核对；它不是独立实验数据的精度基准。

## 操作流程

1. 复制 [`chemblender-2.1-molecule.blend`](chemblender-2.1-molecule.blend)，保留原件和哈希。
2. 在独立 Blender 进程中使用 `--background --factory-startup --disable-autoexec --python-exit-code 1` 打开副本，通过 `--python` 指定 prepare 的 `legacy/__main__.py`。脚本参数放在 `--` 后，先使用 `--output <新的结果目录> --preview`。预览不应生成结果目录。
3. 阅读预览的诊断和显示恢复范围后，去掉 `--preview` 再运行，得到 `project.cbq` 与 `migration.json`。原进程退出后才启动 Viewer。运行包可从已核验 wheel 提取 `chemblender_prepare` 和 `cbq_core` 两个目录；不要把外部 Python 环境的 NumPy 或其他二进制依赖复制进 Blender。
4. 在 Viewer 的 **CBQ Scientific Project** 面板选择 `project.cbq`，依次执行 **Preview CBQ**、**Import CBQ**。把 **Legacy Migration Report** 指向 `migration.json`，执行 **Restore Legacy Views**。
5. 检查 `legacy_formaldehyde (Migrated)`，另存为新的 `.blend`，并保留同名相邻 `.cbq`。独立进程重开后核对科学数据和显示参数，检查外部资源引用再交付。

以上是当前入口说明；实际 GUI 留证与独立人工复做尚待完成，不能将 Operator 验证当成人工验收。

在已确认可用的 Viewer 操作重放中，可通过 Blender MCP 调用 `bpy.ops.chemblender.preview_cbq()`、`bpy.ops.chemblender.import_cbq()` 和 `bpy.ops.chemblender.restore_legacy_views()`；先将 `scene.chemblender_cbq.input_path` 与 `legacy_report_path` 分别设置为导出 CBQ 和迁移报告路径。重放仅替代已验证的操作，不替代首次 GUI 路径或截图留证。外部 legacy 导出仍须使用前述独立进程。

## Agent 提示词

```text
使用 ChemBlender 2.5 外部 legacy 导出路径处理这个样本副本。先预览并报告诊断，再按当前任务授权执行导出；不要覆盖原件。独立导出进程退出后，在 Viewer 中 Preview/Import CBQ，再用 migration.json 执行 Restore Legacy Views。核对4个原子、3条键、显示参数及同名配对工程冷重开；单独报告 GUI、外部引用和人工验收状态。不得在 Blender 中安装科学依赖。
```

## 完整性与验证

- SHA-256：`36b05c3cacbcc067714615a49df35cf20973bc8122329194ddaecd249df6c3d4`
- 精确大小：`153914` bytes
- 已验证：外部预览无写入、导出不改原件、科学字段比对、Viewer Operator 恢复和独立冷重开。
- 证据：[导出检查](../../../tutorials/2.5.0/T18-run007-legacy-export-check.json)、[恢复检查](../../../tutorials/2.5.0/T18-run007-legacy-restore-check.json)。
- 待验证：GUI 路径、完整外部依赖审计和人工复做。

## 参考资料

- [Blender Manual：Opening and Saving](https://docs.blender.org/manual/en/latest/files/blend/open_save.html)
- [ChemBlender GPL-3.0 许可](https://github.com/psiQAQ/ChemBlender_2_x/blob/main/LICENSE)
