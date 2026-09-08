# MIG — 旧项目迁移

## R25 最终复核

执行者：**Agent 模拟用户**。2026-09-08，Blender **5.1.1** / Python **3.13.9**。源码 `039bde7e1bf028b4b691d888d51460ae331ff678`；ZIP SHA-256 `661c58f82ae0a5564d37e713eca281e992ad24fd5b5b81fe2b2aee321862368b`。

UI 与 MCP 各使用独立的干净测试副本。按用户授权，重复动作从 [UI → MCP 命令目录](../../../../../tests/blender_review_commands.py) 读取公开命令；原生首测证据保留在下方阶段记录，重放不记为新的原生 UI 首测。

本次范围：新复制的旧场景分别预览、拒绝未确认执行、确认迁移、四原子/三键、备份和配对保存；原 MIG 文件另行完整性核对。

| 路径 | 最终结果 | 状态与耗时证据 | 配对文件 |
| --- | --- | --- | --- |
| UI | Passed（上述复核范围） | [操作结果](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-MIG-UI-actions-summary.json)；[加载状态](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-MIG-UI-loaded.json) | [最终副本](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25/MIG/UI/fresh/MIG-UI-final.blend) |
| MCP | Passed（上述复核范围） | [操作结果](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-MIG-MCP-actions-summary.json)；[加载状态](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-MIG-MCP-loaded.json) | [最终副本](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25/MIG/MCP/fresh/MIG-MCP-final.blend) |

所有最终副本的安装 Python 字节与 R25 ZIP 匹配，Reader API、Scene RNA、公开 poll 通过；原始配对文件及其权威数组未被本轮复核改写。[完整性核查](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25-integrity.json)与[逐项范围索引](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25-review.json)记录 UUID、manifest hash 和数组检查。每条命令的 JSON 留有实际 `seconds`，不将观察间隔计入产品等待。

最终 [14 集合展示文件](../../../../../.blend-analysis/2026-09-07-review/outputs/final-gallery/ChemBlender-R25-14-cases.blend)含本项同名 Collection 和 UI/MCP 子集合；[总览渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/FINAL-R25-gallery.png)与[真实窗口](../../../../../.blend-analysis/2026-09-07-review/screenshots/FINAL-R25-gallery-window-14-collections.png)已查看。展示模型按单体缩放，不用于科学距离比较；科学操作使用上表配对文件。

## 阶段验收记录（保留当时状态）

以下版本、失败和“待最终复核”描述对应当时检查点；当前结果以上方 R25 复核为准。

执行者：**Agent 模拟用户**。UI **Passed（R20）**；MCP **Passed（R20）**。最终同包全项复核仍待完成。

输入为不可变 `chemblender-2.1-molecule.blend`，SHA-256 `36b05c3cacbcc067714615a49df35cf20973bc8122329194ddaecd249df6c3d4`。UI/MCP 各从独立副本开始，原始文件保持不变。

| 问题 | 类别 / 影响 | 失败证据与修复 |
| --- | --- | --- |
| 长路径、坐标警告和 unsupported 说明截断 | Medium 可读性；确认前无法审阅科学限制 | R17 截图 MIG-R17-05-preview；冻结 outputs/failures/MIG-preview；2e374f6 改为完整换行 |
| EXEC 预览返回 FINISHED，却无公开结果 | High MCP 流程阻断；未确认迁移，科学数据未改变 | MIG-R17-MCP-preview.json；三个 native fixture 回归先失败；同一修复新增只读、非持久化 Scene.chemblender_migration_preview_json |
| 确认框文字截断 | Medium 可读性 | MIG-R18-06-confirmation；4b65a80 增大对话框；R19 完整文案截图通过，取消不变更对象 |
| 迁移结果仅点/边，无显示节点 | High 可见性；原坐标与键仍正确 | MIG-R19-04/05、MIG-R19-UI-empty-geometry.json；完整配对冻结 outputs/failures/MIG-empty-view |
| 默认 By Source 漏掉迁移实体，状态需保存才更新 | High 结果发现；无数据丢失 | 同上；新增 Browser 回归先失败，补齐未归属实体及迁移成功状态投影 |

R18 包 09815c028bb1f5104739a88bb7741e86fa85b7398fdf3da132d74cefb2a01c6c：2308 tests / 26 skips，隔离 smoke 105.79 s。R19 包 80b8804a1ec5f6b129df59206768c33fc759fba3f07b33d8ae27a9af446826e2：2308 tests / 26 skips，隔离 smoke 105.38 s。两个包的 compile/docs/native validate/build/audit/verifier 均通过。R18 的 migration.py 相对 R17 +1431 unpacked / +507 packed；R19 仅 +11/+3；allowance 均为零。

R19 UI 通过真实 Open、N 侧栏、ChemBlender > Legacy Migration、Preview、取消、再次确认勾选、Migrate、Ctrl+S。新旧对象均为 4 atoms / 3 bonds，坐标一致；原对象位于隐藏且不可渲染的 ChemBlender Legacy Backup。由于新 View 无面且 Browser 空，不能将迁移判为通过，尚未进入冷重开。

R20 修复使用包内显示节点的全新 datablock，避免改动原 legacy groups；回滚同时清理新增节点和材质。三个旧样例验证了 display attributes 保留、原子/键几何或晶体子视图可渲染、事务回滚、保存与重开。晶体 fixture 的主 View atom_scale_f 原值为零，其可见性由 cell/occupancy/thermal 子视图承担；回归按完整逻辑 View 检查，未篡改该旧显示设定。By Source 对没有 SourceRevision 的实体新增 Unattributed project data 分支，已有归属实体不重复。

- [原始失败预览](../../../../../.blend-analysis/2026-09-07-review/screenshots/MIG-R17-05-preview.png)
- [修复后的完整预览](../../../../../.blend-analysis/2026-09-07-review/screenshots/MIG-R19-02-preview.png)
- [完整确认文案](../../../../../.blend-analysis/2026-09-07-review/screenshots/MIG-R19-03-confirmation.png)
- [迁移后空几何](../../../../../.blend-analysis/2026-09-07-review/outputs/MIG-R19-UI-empty-geometry.json)
- [失败配对](../../../../../.blend-analysis/2026-09-07-review/outputs/failures/MIG-empty-view/UI/MIG-UI.blend)

完整 R20 UI/MCP 迁移、渲染、冷重开及包绑定正在执行；不把上面的自动测试代替实际体验结果。

R20 / 35c3bc9 两条路径完整重测通过，包 SHA-256 f7dfd72611e1cd61c7519b5110e8d8e83995419fa70e31e86de13d8347a666f8。2309 tests / 26 documented skips / 零失败，隔离 smoke 104.94 s，compile/docs/native build/audit/verifier 通过；仅 migration.py +2396 unpacked / +755 packed，Browser model +568/+95，包 29,989,162 / 32,111,063，allowance 为零。

UI：从全新副本 Open，N > ChemBlender > Legacy Migration，完整 Preview、取消确认、重开确认并勾选，再迁移。结果立即可见球棍模型，Browser 展开未归属 Structure/Topology/Provenance，Connected，无需额外保存才能更新。展示辅助仅添加 MIG/UI 集合和相机、渲染；原生 Ctrl+S 保存，再 Alt+F4 正常退出旧 PID2156。新 PID2220 冷重开仍为 clean、启用键正确、相同 UUID/hash/坐标/1536 polygons。

MCP：独立原始副本，公开 RNA/poll 预检；preview 0.0065 s，公开 JSON 显示 destination、一个 legacy scaffold、拟建三类实体、恢复字段及两个完整 warning。confirmed=False 明确拒绝且不生成 sidecar；停止检查后 confirmed=True 用时 0.0731 s，清空预览并创建相同科学结构和可渲染 View。公开保存后正常关闭自建 PID11352；新 PID12412 冷重开，启用、backup、UUID/hash、坐标和 1536 polygons 一致。关闭动作由原生进程测试管理完成，未绕过 MCP 的 quit 限制。

体验评价：入口在同一 ChemBlender 侧栏可找到；预览与确认全文可读，包含 base mesh 坐标和 dashed 不可恢复边界；取消无副作用；本样例迁移小于 0.1 秒，没有长等待。失败在确认前或事务中停止，旧数据保留。最终实际查看 UI/MCP 两张渲染，四个原子、两条 C=O 棍和两个 C-H 键均可见，未裁切。

- [UI 配对文件](../../../../../.blend-analysis/2026-09-07-review/outputs/MIG-R20-UI/MIG-UI.blend) / [渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/MIG-R20-UI-render.png) / [冷重开](../../../../../.blend-analysis/2026-09-07-review/outputs/MIG-R20-UI-cold.json)
- [MCP 配对文件](../../../../../.blend-analysis/2026-09-07-review/outputs/MIG-R20-MCP/MIG-MCP.blend) / [渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/MIG-R20-MCP-render.png) / [冷重开](../../../../../.blend-analysis/2026-09-07-review/outputs/MIG-R20-MCP-cold.json)
- [MCP 完整预览](../../../../../.blend-analysis/2026-09-07-review/outputs/MIG-R20-MCP-preview.json) / [未确认拒绝](../../../../../.blend-analysis/2026-09-07-review/outputs/MIG-R20-MCP-unconfirmed.json)
- [科学数组、拓扑和文件 hashes](../../../../../.blend-analysis/2026-09-07-review/outputs/MIG-R20-science-check.json)

每个文件的 MIG 集合下分别有 UI 或 MCP 子集合，隐藏备份完整保留在其中。历史人工记录没有改写。
