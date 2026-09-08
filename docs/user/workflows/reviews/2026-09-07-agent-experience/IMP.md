# IMP — 导入、预览、取消与单位

## R25 最终复核

执行者：**Agent 模拟用户**。2026-09-08，Blender **5.1.1** / Python **3.13.9**。源码 `039bde7e1bf028b4b691d888d51460ae331ff678`；ZIP SHA-256 `661c58f82ae0a5564d37e713eca281e992ad24fd5b5b81fe2b2aee321862368b`。

UI 与 MCP 各使用独立的干净测试副本。按用户授权，重复动作从 [UI → MCP 命令目录](../../../../../tests/blender_review_commands.py) 读取公开命令；原生首测证据保留在下方阶段记录，重放不记为新的原生 UI 首测。

本次范围：已保存导入数据和单位的数组完整性；CCO 预览取消；未知 Gaussian 单位诊断、拒绝确认、取消后几何不变。

| 路径 | 最终结果 | 状态与耗时证据 | 配对文件 |
| --- | --- | --- | --- |
| UI | Passed（上述复核范围） | [操作结果](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-IMP-UI-actions-summary.json)；[加载状态](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-IMP-UI-loaded.json) | [最终副本](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25/IMP/UI/IMP-R5-UI.blend) |
| MCP | Passed（上述复核范围） | [操作结果](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-IMP-MCP-actions-summary.json)；[加载状态](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-IMP-MCP-loaded.json) | [最终副本](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25/IMP/MCP/IMP-R5-MCP.blend) |

所有最终副本的安装 Python 字节与 R25 ZIP 匹配，Reader API、Scene RNA、公开 poll 通过；原始配对文件及其权威数组未被本轮复核改写。[完整性核查](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25-integrity.json)与[逐项范围索引](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25-review.json)记录 UUID、manifest hash 和数组检查。每条命令的 JSON 留有实际 `seconds`，不将观察间隔计入产品等待。

最终 [14 集合展示文件](../../../../../.blend-analysis/2026-09-07-review/outputs/final-gallery/ChemBlender-R25-14-cases.blend)含本项同名 Collection 和 UI/MCP 子集合；[总览渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/FINAL-R25-gallery.png)与[真实窗口](../../../../../.blend-analysis/2026-09-07-review/screenshots/FINAL-R25-gallery-window-14-collections.png)已查看。展示模型按单体缩放，不用于科学距离比较；科学操作使用上表配对文件。

## 阶段验收记录（保留当时状态）

以下版本、失败和“待最终复核”描述对应当时检查点；当前结果以上方 R25 复核为准。

执行者：**Agent 模拟用户**。当前 UI/MCP **Passed（f2cbd41 / 966dc8a7）**。后续 reload 修复产生新包，仍需最终复核。

## 前置与输入

UI 与 MCP 分别使用独立 factory-startup 文件和测试 profile，清空 ProjectSession；每个文件有 `IMP` 集合，其下分别为 `UI` 或 `MCP`。Blender 5.1.1，1920×1080、English。

输入为不可变 `water.xyz`、Gaussian/ORCA water 样例、SMILES `CCO`。四文件单位批次与未知单位负例是本轮派生副本，原文件 SHA 和改动写入 [derivations.json](../../../../../.blend-analysis/2026-09-07-review/inputs/derivations.json)，未改写历史样例。

## UI 路径

1. N → ChemBlender → Quick Import → Select Files，选 water；查看 xyz/Complete/Create Default View；Cancel。
2. 确認对象仍为 0，状态为 Import cancelled。重新选 water 并 OK，生成 3 原子 View。
3. 文件选择器进入 IMP-multi，用 A 全选四文件，确认四个 reader/Complete、Keep Independent 和默认 Structure View，OK。
4. 选择 unknown-unit.gjf，看到 Invalid。点击 OK 被拒绝；五个既有 Mesh 不变。取消 staging 后可继续导入。
5. Import SMILES 输入 CCO，确认 smiles/Complete/Structure，得到三重原子平面结构。
6. 将展示对象放入 IMP/UI；仅调整 Object transform 排列六个 View。Save Project → Save As，返回后再次 Save Project，生成同名 .cbq；读取坐标后生成展示渲染。

UI 复测约 20:28–20:35，动作时间逐条保存在 ui-actions.jsonl；含截图、数值核对和展示整理，不作为纯解析性能。小输入约 1 s 后可见 Preview ready/100%；有 Cancel，取消后可以重试。按钮入口位于旧 Build Molecules 下方，需要知道 N 侧栏；discoverability 中等。

实际五个水结构中，Bohr 的 x=±0.401434898、z=0.266855597 Å；默认单位 x=±0.758602023、z=0.504284024 Å。误差为 Blender Mesh float32 显示精度，符合因子 0.529177210903。CCO 生成确定性平面坐标，不冒称三维优化构象。未知单位没有产生实体。

## MCP 路径

1. 独立空文件调用公开 quick_import，返回 RUNNING_MODAL；读 recent_summary 等待暂存完成。
2. Export Diagnostics 保存报告，并窗口截图检查 Complete/默认 Structure。公开 cancel_import 返回 FINISHED，summary 为 Import cancelled，对象为 0。
3. 再次 quick_import，显式 confirm_import 返回 RUNNING_MODAL；最终 committed、一个 3 原子 Mesh。
4. 发现旧 Preview 在取消和确认后仍留在窗口，阻碍后续体验。该构建 MCP 判 Failed，停止将下游默认通过。

## 失败、修复与重测链

| 问题 | 严重程度 / 科学影响 | 修复与结果 |
| --- | --- | --- |
| Browser.draw 写入受限 RNA，导入后列表空白 | P1；数据在但用户无法正确浏览 | 7764e83，2290 tests 与隔离 smoke 通过，R2/R3 真实非空 Browser 正常 |
| Cancel 后仍显示 staged | P2；误导流程状态，未观察数据写入 | 22b654d；两入口回归先失败后通过；R3 UI 和 MCP 均显示 Import cancelled |
| default_view 内部字段名、旧 alpha.1 提示 | P3；无科学数据影响 | 22b654d；R3 截图为 Create Default View、Split / Edit is not available |
| MCP 直接执行后残留 Preview 弹窗 | P2；状态不可靠，后续操作受干扰 | 当前修复区分 invoke/execute，并以只读 preview_json 暴露同一预览；待最终包复测 |
| direct confirm 覆盖显式 default_view 决策 | P1；忽略用户选择，可能影响冲突/分组决定 | 回归证实 false 被默认 true 覆盖；当前修复保留显式 rows 并继续验证 live IDs，159 相关 tests 通过；待真实 MCP 重测 |

未知单位预览仅显示 reader parse failed: ValueError；明确拒绝但未给出具体单位字符串。记录为文案可诊断性限制，reader 层具体原因由回归覆盖；未扩大第三方 reader 错误披露规则。

## 文件与证据

本段 UI 绑定源码 `22b654d`，ZIP SHA-256 `c5e438aefeb200e32dfcb5a09b73825acdc5dc6971a3acd64d9f85349c7c4207`。

- [UI 配对文件](../../../../../.blend-analysis/2026-09-07-review/outputs/IMP-R3-UI.blend)、[sidecar manifest](../../../../../.blend-analysis/2026-09-07-review/outputs/IMP-R3-UI.cbq/manifest.json)
- [展示渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/IMP-R3-UI-render.png)、[排列截图](../../../../../.blend-analysis/2026-09-07-review/screenshots/IMP-R3-09-saved-gallery.png)
- [取消修复截图](../../../../../.blend-analysis/2026-09-07-review/screenshots/IMP-R3-03-cancelled.png)、[四文件预览](../../../../../.blend-analysis/2026-09-07-review/screenshots/IMP-R3-05-multi-preview.png)、[无效输入拒绝](../../../../../.blend-analysis/2026-09-07-review/screenshots/IMP-R3-07-invalid-refused.png)
- [UI 坐标](../../../../../.blend-analysis/2026-09-07-review/outputs/IMP-R3-final-UI.json)、[MCP 旧弹窗残留](../../../../../.blend-analysis/2026-09-07-review/screenshots/IMP-R3-MCP-03-confirmed.png)
- 旧 R2 的单次 Save As 文件没有配对 sidecar，属于中间证据；不能作为可冷重开的成功项目。R3 已按既定两步保存流程核对配对。


### 87580c4 窗口复测与 RNA 转换补充

`IMP-R4-*` 绑定 87580c4 / c206b53e ZIP。UI 再次通过水、四文件单位、Invalid 拒绝、Cancel 恢复、CCO 和配对保存；`IMP-R4-UI.blend/.cbq` 与 `IMP-R4-UI-final.json` 保留六结构及正确坐标。MCP 取消后不再残留弹窗，preview_json 在取消后为空，截图 `IMP-R4-MCP-01-cancelled.png`。

MCP 回传 JSON 确认触发 Blender collection converter 的 `keyword "name" missing`。归为 P2 接口可用性失败，无数据写入；本轮脚本最初未在失败后停止下一条命令，后续四文件暂存不作为成功确认，已据此修正编排纪律。Blender smoke 增加真实 JSON → Operator 调用并在旧 ZIP 复现同一失败（`logs/isolated-rna-conversion-before.log`）。补充修复使外层和嵌套 collection 记录包含继承的 PropertyGroup.name；保留显式 no-view 决定的 smoke 断言，修复包正在验证。

RNA conversion 修复后，2,294 tests 通过（26 个已有依赖/平台 skip），真实隔离 Blender smoke 通过（103.44 s），包含外层和 MOL2 嵌套 collection 的 JSON 确认及显式不创建 View。包 SHA-256 为 `966dc8a7def7343fa29b1823ea72e2ea43a04015655bf32da0bd2f6c2a824daf`；UI 已从原生安装器安装并核对模块 hash。完整 MCP 重测继续。

### R5 MCP 复测通过

`IMP-R5-MCP-*` 经公开 preview_json 审阅后确认 water、四文件和 CCO；未知单位确认被拒绝，对象保持五个，取消后恢复导入。最终六个三原子 Mesh，Bohr 坐标与 UI 相同；单次暂存约 0.34–0.39 s、确认约 0.46–2.71 s。两个 route 保存为 `outputs/IMP-R5-UI.blend/.cbq` 与 `outputs/IMP-R5-MCP.blend/.cbq`，集合 IMP/UI 和 IMP/MCP，渲染 `screenshots/IMP-R5-UI-render.png`、`IMP-R5-MCP-render.png`。UI 在新包冷打开原 UI 产物，验证公开链接 Connected 后生成配对副本；完整原生导入动作是 R4，R5 是最终包数据/显示复核。
