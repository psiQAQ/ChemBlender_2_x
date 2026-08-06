# Agent 与 Blender MCP

本页适用于 Codex、Claude Code 或其他能连接同一 Blender MCP 的 Agent。不同客户端暴露的 tool 名可能不同，所以提示词只描述能力：查询 Blender runtime、在 Blender 内执行代码、读取结果。先让 Agent 列出当前可用工具，不能凭另一台机器的名称猜 tool。

## 使用边界

插件能力内的 Agent 操作必须与人工 UI 走同一条公开路径：调用已经注册的 `bpy.ops.chemblender.*` Operator，读取公开 Operator RNA、Scene RNA、报告、对象和输出文件。Blender 自带的打开/保存/渲染操作可使用对应 `bpy.ops.wm.*` 或 `bpy.ops.render.*`，但仍要先查 live RNA。

以下行为不算完成插件工作流：导入 `private modules`，直接写 `.cbq`、cache 或自定义 `cb_` 状态，调用 core/service 私有函数，绕过 Import Preview、quality/conflict decision、loss preview、migration confirmation 或其他 confirmation。

## 连接与一次性环境查询

每次新会话先做一次查询，返回这些字段，不要拆成多个互相矛盾的快照：

- `bpy.app.version_string` 与 `bpy.app.binary_path`；
- Blender bundled Python 的 `sys.executable` 与 `platform.system()`；
- Extension repositories 的公开配置；
- `bpy.data.filepath` 与 `bpy.data.is_dirty`；
- enabled extension key 是否包含 `bl_ext.user_default.chemblender`；
- `bpy.ops.chemblender` 下目标 Operator 是否存在；
- 当前 scene、active object、selected objects 和 ChemBlender 面板公开 RNA 状态。

要求 Blender 5.1.0 或更高版本。executable、Python、OS、extension repository 或 enabled key 不符时先停止，不用 stale path 继续。

## 检查 Operator RNA

在调用前对目标 Operator 使用公开 RNA introspection，报告 property identifier、type、enum items、default、required/optional 和 poll 结果。常见公开 Operator 如下；它们只是查找入口，live runtime 仍是参数事实源。

| 流程 | Operator |
| --- | --- |
| 文件 / SMILES 导入 | `bpy.ops.chemblender.quick_import`、`bpy.ops.chemblender.import_smiles_text` |
| Preview 确认 / 取消 | `bpy.ops.chemblender.confirm_import`、`bpy.ops.chemblender.cancel_import` |
| 科学编辑 / topology | `bpy.ops.chemblender.apply_scientific_edits`、`compute_topology`、`accept_topology`、`reject_topology`、`switch_topology` |
| 晶体 / 生物 | `derive_crystal_symmetry`、`view_standardized_structure`、`toggle_selective_constraints`、`select_biological_atoms`、`play_biological_models`、`create_biological_view` |
| Grid3D | `bpy.ops.chemblender.resolve_grid_semantics`、`bpy.ops.chemblender.create_grid_view` |
| 导出 | `bpy.ops.chemblender.export_project_entity` |
| 恢复 / 迁移 | `project_link_recovery`、`revision_view_action`、`preview_legacy_migration`、`migrate_legacy_scene` |

Operator 的短名不等于参数名。Agent 必须先“检查 Operator RNA”，再按 live signature 构造调用；`FINISHED` 也只表示 Operator 返回，不代表科学状态已经验证。

## 调用与等待

1. 记录调用前可见状态和目标输入/输出路径。
2. 调用 public Operator。需要 3D View、window 或 file browser context 时，先检查 `poll()`，再用公开 context override；不能改成私有函数调用来逃避 context。
3. modal/background job 只做条件轮询：读取 UI 暴露的 task state、stage、progress、Preview/Report 或对象状态。不要用一个固定长 `sleep` 猜完成时间。
4. 有质量、冲突、归组、loss 或 migration confirmation 时停在 Preview，把选项和后果交给用户；没有用户授权就不自动确认。
5. 调用后读取与人工 UI 相同的状态。导入要检查 Project Browser entity/View，Grid 要检查 binding/dataset/isovalue，导出要回读语义，保存要冷重开。

## 取消和失败停止规则

- 取消只调用公开 cancel Operator，等待 active job 消失，再检查 staging/半成品没有成为成功结果。
- `poll()` 失败、RNA 不符、依赖 unavailable、Preview 决策不明确、sidecar mismatch 或目标已存在时停止并报告。
- 不在 unknown dirty state 接着跑下一案例。先保存证据，回到该案例的干净前置状态。
- 任何 `MemoryError`、Blender exception、MCP disconnect 或崩溃都不能降级成“可能成功”。

## Blender 崩溃或 MCP 断开

1. 按上一次已确认的 exact executable path 和 command line 检查 Blender 5.1 进程。
2. 没有匹配进程时启动同一 Blender 5.1。需要观察 UI 的走查保持窗口可见；纯恢复检查才可隐藏窗口。
3. 条件轮询 MCP listener，恢复后重新执行完整环境查询。
4. 检查 active file、dirty state、上一个输出和 Project link。未知中间状态不继续，重置到该案例的干净输入后重跑。

端口正在监听、manifest 能解析、Operator 返回 `FINISHED` 或文件存在都不是充分证据。

## 可复制的通用提示词

```text
使用当前会话实际提供的 Blender MCP，不猜 MCP tool 名。先在一次查询中返回 Blender version/executable、bundled Python、runtime system、Extension repositories、active file、dirty state、enabled key `bl_ext.user_default.chemblender`，要求 Blender >= 5.1.0。然后检查 Operator RNA 和 poll，只调用 live registered `bpy.ops.chemblender.*`；Blender 自带文件/渲染操作也要检查其 RNA。不得 import private modules、直接编辑 `.cbq`/cache/`cb_` 状态，或 bypass quality/loss/migration confirmation。执行后读取与人工 UI 相同的公开状态并给出证据。任何前置、依赖、poll、Preview 或 confirmation 不明确时停止。

目标：<写明一个操作、绝对输入路径和新的输出目录>。
成功证据：<写明 Project Browser entity/View、报告、输出语义或冷重开状态>。
```

## 运行时审计提示词

```text
通过 Blender MCP 审计当前 Blender，不修改任何状态。一次返回 Blender version/executable、bundled Python、OS、Extension repositories、active file、dirty state、enabled key 和 `bpy.ops.chemblender` 可见 Operator。逐个检查目标 Operator RNA 与 poll，但不调用。确认没有使用 private modules、没有读写 `.cbq` 内部文件、没有 bypass confirmation。输出可复核字段和失败原因；Blender 低于 5.1 或 extension key 不是 `bl_ext.user_default.chemblender` 时判定 blocked。
```

插件内的具体提示词位于[导入](01-import.md)、[处理](02-process.md)、[展示](03-visualize.md)、[导出](04-export.md)和[项目生命周期](05-project-lifecycle.md)。调整材质、灯光、相机和渲染等通用 Blender 工作见[插件能力外案例](07-agent-beyond-plugin.md)。
