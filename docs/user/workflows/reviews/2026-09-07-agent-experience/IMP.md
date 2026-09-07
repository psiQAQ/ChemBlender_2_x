# IMP — 导入、预览、取消与单位

执行者：**Agent 模拟用户**。当前 UI **Passed（22b654d）**；MCP **Failed，现场修复后待重测**。尚不能作为最终包的完成验收。

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
