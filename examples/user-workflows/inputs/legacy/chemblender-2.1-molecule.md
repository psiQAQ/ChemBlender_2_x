# ChemBlender 2.1 旧场景迁移样例

## 用途与选择理由

这个文件不是分子交换格式，而是 ChemBlender 2.1 创建的 `.blend` 场景。它只用于验证旧集合、对象和属性能否先预览、再由用户确认迁移；不能拿它判断新版导入器的分子数据精度。

## 来源与许可

- 取得日期：`2026-08-07`。

- 来源标识：`tests/fixtures/legacy-blend/chemblender-2.1-molecule.blend@3e1d02e046851c6c89a81ac8dce42b435bb25509`。
- 来源路径：仓库测试夹具 `tests/fixtures/legacy-blend/chemblender-2.1-molecule.blend`。
- 许可：`GPL-3.0`，随 ChemBlender 仓库分发。

## 规模与分辨率

文件大小 `153914` bytes，来源版本为 2.1。`.blend` 大小反映场景序列化结果，不是分子坐标或渲染分辨率；迁移后应检查实体、拓扑、View 和备份集合，而不是仅看文件能否打开。

## 字段说明

| 内容 | 含义 |
| --- | --- |
| Blender datablocks | 场景、集合、对象、网格和材质等 Blender 数据块 |
| ChemBlender 2.1 属性 | 旧版插件写入的分子与显示状态 |
| 旧集合层级 | 迁移器识别来源对象并建立备份的依据 |
| 文件版本信息 | Blender 用来决定兼容读取路径的头部信息 |

## ChemBlender 支持边界

ChemBlender 2.4.0 只通过显式迁移处理 2.1 场景：`preview_legacy_migration` 生成报告，`migrate_legacy_scene` 在确认后建立项目实体和备份。直接打开 `.blend` 不等于完成迁移；Agent 不得修改旧自定义属性、私有缓存或绕过确认。

## 操作流程

1. 在 Blender 5.1 打开 [`chemblender-2.1-molecule.blend`](chemblender-2.1-molecule.blend)。
2. 在 ChemBlender 迁移入口运行 Preview，核对将创建和保留的对象。
3. 确认后执行迁移，检查项目树、View 与 legacy backup collection。
4. 另存为新的 `.blend`，并让生成的 `.cbq` 与其相邻；不要覆盖原文件。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，先读取 Operator RNA，再打开 examples/user-workflows/inputs/legacy/chemblender-2.1-molecule.blend。只使用公开的 bpy.ops.chemblender.*：先调用 bpy.ops.chemblender.preview_legacy_migration，报告来源对象、将创建的项目实体、诊断和备份计划，等我确认后再调用 bpy.ops.chemblender.migrate_legacy_scene。不得改私有属性或覆盖原文件；将迁移结果另存为 .blend，并把 .cbq 放在旁边，随后报告缺失外部文件数。
```

## 完整性与验证

- SHA-256：`36b05c3cacbcc067714615a49df35cf20973bc8122329194ddaecd249df6c3d4`
- 精确大小：`153914` bytes
- 自动检查：文件可由 Blender 5.1 读取，并通过公开 Operator 完成预览、确认、保存和冷重开检查。

## 参考资料

- [Blender Manual：Opening and Saving](https://docs.blender.org/manual/en/latest/files/blend/open_save.html)
- [ChemBlender GPL-3.0 许可](https://github.com/psiQAQ/ChemBlender_2_x/blob/main/LICENSE)
