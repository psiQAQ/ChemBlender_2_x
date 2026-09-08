# OUTSIDE — 材质、场景呈现与插件边界

## R25 最终复核

执行者：**Agent 模拟用户**。2026-09-08，Blender **5.1.1** / Python **3.13.9**。源码 `039bde7e1bf028b4b691d888d51460ae331ff678`；ZIP SHA-256 `661c58f82ae0a5564d37e713eca281e992ad24fd5b5b81fe2b2aee321862368b`。

UI 与 MCP 各使用独立的干净测试副本。按用户授权，重复动作从 [UI → MCP 命令目录](../../../../../tests/blender_review_commands.py) 读取公开命令；原生首测证据保留在下方阶段记录，重放不记为新的原生 UI 首测。

本次范围：普通材质/World/Area/Camera 及 Collection 随文件恢复；最终包下两张 Eevee 渲染已实际查看且像素相同，科学数组不变。

| 路径 | 最终结果 | 状态与耗时证据 | 配对文件 |
| --- | --- | --- | --- |
| UI | Passed（上述复核范围） | [操作结果](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-OUTSIDE-UI-actions-summary.json)；[加载状态](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-OUTSIDE-UI-loaded.json) | [最终副本](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25/OUTSIDE/UI/OUTSIDE-UI.blend) |
| MCP | Passed（上述复核范围） | [操作结果](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-OUTSIDE-MCP-actions-summary.json)；[加载状态](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-OUTSIDE-MCP-loaded.json) | [最终副本](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25/OUTSIDE/MCP/OUTSIDE-MCP.blend) |

所有最终副本的安装 Python 字节与 R25 ZIP 匹配，Reader API、Scene RNA、公开 poll 通过；原始配对文件及其权威数组未被本轮复核改写。[完整性核查](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25-integrity.json)与[逐项范围索引](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25-review.json)记录 UUID、manifest hash 和数组检查。每条命令的 JSON 留有实际 `seconds`，不将观察间隔计入产品等待。

最终 [14 集合展示文件](../../../../../.blend-analysis/2026-09-07-review/outputs/final-gallery/ChemBlender-R25-14-cases.blend)含本项同名 Collection 和 UI/MCP 子集合；[总览渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/FINAL-R25-gallery.png)与[真实窗口](../../../../../.blend-analysis/2026-09-07-review/screenshots/FINAL-R25-gallery-window-14-collections.png)已查看。展示模型按单体缩放，不用于科学距离比较；科学操作使用上表配对文件。

[UI 最终 Eevee](../../../../../.blend-analysis/2026-09-07-review/screenshots/FINAL-R25-OUTSIDE-UI-render.png)与[MCP 最终 Eevee](../../../../../.blend-analysis/2026-09-07-review/screenshots/FINAL-R25-OUTSIDE-MCP-render.png)均已实际查看。原生 UI 渲染取消已测试；同步 MCP 渲染调用中途取消仍为 **Not Run**，不以调用完成代替取消体验。

## 阶段验收记录（保留当时状态）

以下版本、失败和“待最终复核”描述对应当时检查点；当前结果以上方 R25 复核为准。

执行者：**Agent 模拟用户**。UI **Passed**；MCP **Passed**。Blender 5.1.1，source `76d1d9e`，R21 ZIP SHA-256 `61b64592fbab352aaaa70ea319963ab6c6436a4f2d2d0728c68fabb7daa73635`。本项操作属于通用 Blender；最终全项同包复核仍待完成。

独立空项目、独立 profile/端口；UI 完成后 MCP 从空文件开始。输入是本轮不可变 `inputs/OUTSIDE/water.mol`，来自仓库 `mol/water-v2000.mol`，三原子、两个来源键。Quick Import 默认 atoms-only View，没有本项未明确接受的显示键。科学 Structure、revision 和坐标保持源值。

| 项目 | UI 原生步骤和实际结果 | MCP 公开操作和实际结果 |
| --- | --- | --- |
| 导入 | Select Files → 原生选择器 → Complete Preview → Confirm；三个原子可见 | quick_import → 读取 preview_json → confirm_import；各约0.38秒，committed |
| 材质 | Material Properties → New；Presentation Blue，Base Color `2B78CFFF`、Roughness0.32、Metallic0.15 | 读取明确唯一 View、材质槽与节点 RNA；槽原为空，创建展示材质并设置相同参数 |
| 世界 / 灯光 / 相机 | Add Camera；位置(0,-4,4)、X旋转45°、50mm；Add Area Light，(0,-3,4)、X旋转35°、1000W、size3；World New、默认灰0.05、strength0.3 | 先确认没有 World/Light/Camera，检查3个可渲染实例和 Operator poll；通过普通 bpy 与公开 object.camera_add/light_add 建立相同配置 |
| 集合 | Shift+M → Link to New Collection → OUTSIDE；隐藏/恢复；Outliner New Collection → UI，额外链接全部展示对象 | 创建 OUTSIDE/MCP，额外 link 并保留 Scene Collection；隐藏/恢复 LayerCollection，返回 membership/visible 状态 |
| 渲染 | Output Properties设1280×800；F12，Image → Save As保存PNG；F12后Esc取消，再F12恢复，最终图像实际打开检查 | 先读RenderSettings engine枚举，BLENDER_EEVEE、64 samples；public render.render(write_still=True)，实际打开PNG检查 |
| 保存与重开 | Ctrl+S → 新文件；Ctrl+O同进程重开；配对、材质、灯光、相机、集合和坐标一致 | public save_as_mainfile与open_mainfile；公开状态快照完全一致，sidecar数组hash通过 |

入口与文案：材质/World/输出属性图标需要辨认，F3能找到相机和灯光。原生新集合应使用 Outliner 工具栏；一次快捷键误操作将自建 OUTSIDE 改名为UI，已立即恢复，没有改动插件 owned object。相机初始旋转与快速连续键输入导致首次构图空白，截图保留；Clear Rotation菜单加分开的R、X输入修正。两者是测试操作问题，未修改产品代码。

等待、取消与恢复：UI首张Eevee渲染显示6.27秒，恢复后最终渲染完成；原生渲染窗口可见，Esc可退出。UI原生输入累计116.1秒，不含阅读/诊断间隔。MCP完整流程12.19秒，其中同步render调用9.34秒；调用结束返回FINISHED。MCP同步调用没有本次验证过的中途取消通道，**该子步骤Not Run**；不把UI取消结果当作MCP取消通过。

最终两张渲染均完整显示红氧和白氢，没有黑屏或严重裁切。蓝色对象材质槽未覆盖Geometry Nodes实例里的CH_Molecule材质，这是普通Blender材质作用范围；文档已补充必须检查evaluated实例材质，不能仅凭槽值宣称画面变色。OUTSIDE集合隐藏时，保留的原Scene Collection链接使对象仍可见，符合预期。本项不把渲染当作科学导出，也不把集合当作科学分组。

科学检查：两路线均为O/H/H，坐标`[[0,0,0],[0.7586,0,0.5043],[-0.7586,0,0.5043]] Å`；View顶点、边、已有科学custom properties与transform未被展示操作改写。保存后逐一核对sidecar坐标文件hash；重开后的展示快照与保存前完全相同。本次为**同进程重开**，不宣称冷启动。

- [UI材质](../../../../../.blend-analysis/2026-09-07-review/screenshots/OUTSIDE-R21-06-color-picker.png) / [相机构图](../../../../../.blend-analysis/2026-09-07-review/screenshots/OUTSIDE-R21-10-add-light.png)
- [原生渲染及耗时](../../../../../.blend-analysis/2026-09-07-review/screenshots/OUTSIDE-R21-13-render-wait.png) / [Image保存菜单](../../../../../.blend-analysis/2026-09-07-review/screenshots/OUTSIDE-R21-15-image-save.png)
- [集合隐藏状态](../../../../../.blend-analysis/2026-09-07-review/outputs/OUTSIDE-R21-UI-collection-hidden.json) / [取消与集合](../../../../../.blend-analysis/2026-09-07-review/screenshots/OUTSIDE-R21-26-render-cancel.png)
- [UI最终渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/OUTSIDE-R21-UI-render-final.png) / [MCP最终渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/OUTSIDE-R21-MCP-render-final.png)
- [UI配对](../../../../../.blend-analysis/2026-09-07-review/outputs/OUTSIDE-R21-UI/OUTSIDE-UI.blend) / [MCP配对](../../../../../.blend-analysis/2026-09-07-review/outputs/OUTSIDE-R21-MCP/OUTSIDE-MCP.blend)
- [UI重开状态](../../../../../.blend-analysis/2026-09-07-review/outputs/OUTSIDE-R21-UI-reopen.json) / [MCP重开状态](../../../../../.blend-analysis/2026-09-07-review/outputs/OUTSIDE-R21-MCP-reopen.json) / [MCP流程耗时](../../../../../.blend-analysis/2026-09-07-review/outputs/OUTSIDE-R21-MCP-workflow.json)
- [配对文件hash及科学检查](../../../../../.blend-analysis/2026-09-07-review/outputs/OUTSIDE-R21-science-check.json)
