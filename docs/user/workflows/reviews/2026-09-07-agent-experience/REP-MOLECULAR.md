# REP-MOLECULAR — 八类代表分子输入

## R25 最终复核

执行者：**Agent 模拟用户**。2026-09-08，Blender **5.1.1** / Python **3.13.9**。源码 `039bde7e1bf028b4b691d888d51460ae331ff678`；ZIP SHA-256 `661c58f82ae0a5564d37e713eca281e992ad24fd5b5b81fe2b2aee321862368b`。

UI 与 MCP 各使用独立的干净测试副本。按用户授权，重复动作从 [UI → MCP 命令目录](../../../../../tests/blender_review_commands.py) 读取公开命令；原生首测证据保留在下方阶段记录，重放不记为新的原生 UI 首测。

本次范围：八个默认 View 在 R25 下恢复并求值；59 个唯一权威数组与原配对一致；两路径各八模型展示快照入总览。

| 路径 | 最终结果 | 状态与耗时证据 | 配对文件 |
| --- | --- | --- | --- |
| UI | Passed（上述复核范围） | [操作结果](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-REP-MOLECULAR-UI-actions-summary.json)；[加载状态](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-REP-MOLECULAR-UI-loaded.json) | [最终副本](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25/REP-MOLECULAR/UI/REP-MOLECULAR-UI.blend) |
| MCP | Passed（上述复核范围） | [操作结果](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-REP-MOLECULAR-MCP-actions-summary.json)；[加载状态](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-REP-MOLECULAR-MCP-loaded.json) | [最终副本](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25/REP-MOLECULAR/MCP/REP-MOLECULAR-MCP.blend) |

所有最终副本的安装 Python 字节与 R25 ZIP 匹配，Reader API、Scene RNA、公开 poll 通过；原始配对文件及其权威数组未被本轮复核改写。[完整性核查](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25-integrity.json)与[逐项范围索引](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25-review.json)记录 UUID、manifest hash 和数组检查。每条命令的 JSON 留有实际 `seconds`，不将观察间隔计入产品等待。

最终 [14 集合展示文件](../../../../../.blend-analysis/2026-09-07-review/outputs/final-gallery/ChemBlender-R25-14-cases.blend)含本项同名 Collection 和 UI/MCP 子集合；[总览渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/FINAL-R25-gallery.png)与[真实窗口](../../../../../.blend-analysis/2026-09-07-review/screenshots/FINAL-R25-gallery-window-14-collections.png)已查看。展示模型按单体缩放，不用于科学距离比较；科学操作使用上表配对文件。

## 阶段验收记录（保留当时状态）

以下版本、失败和“待最终复核”描述对应当时检查点；当前结果以上方 R25 复核为准。

执行者：**Agent 模拟用户**。R22 UI **Passed**，MCP **Passed**；这是本项完整重测，最终全轮同包复核仍待完成。实际环境Blender5.1.1/Python3.13.9，source commit `1c290eec5d98a6f0cbbb5d6749069c3cc1872dca`，ZIP SHA-256 `82529f5564f8b4f9b319785c35094700c431747ff2daa3b438312c6a2b3a8e56`。

前置状态：独立UI/MCP配置均从空文件开始，UI先完成全部操作，MCP再独立执行。两个新进程冷依赖检查通过；启用键为`bl_ext.user_default.chemblender`，已安装Python源码逐字节匹配R22。输入均为仓库八个既定代表文件的不可变副本，来源、大小与hash见[输入清单](../../../../../.blend-analysis/2026-09-07-review/outputs/REP-MOLECULAR-inputs.json)。

UI步骤：N侧栏 → ChemBlender → Quick Import / Select Files → 原生文件选择器逐个选择 → 阅读Preview → OK；完成后By Data查看记录/实体，选中MOL2记录检查格式标签。展示整理仅移动Blender对象并建立`REP-MOLECULAR/UI`集合，不修改科学数组。八个输入各有子集合及独立渲染，最后原生Ctrl+Shift+S保存配对。

MCP步骤：读取quick_import、confirm_import、cancel_import的RNA/poll → 对每文件调用quick_import → 等待公开preview_json → 核对reader/quality/阻断状态 → 通过JSON调用confirm_import → 等待committed并核对新View。By Data读取公开行，完成后独立整理`REP-MOLECULAR/MCP`集合、渲染，并用public save_as_mainfile保存；产品流程没有调用私有函数。

| 输入 | 两路径实际结果与科学边界 | UI / MCP渲染 |
| --- | --- | --- |
| CJSON | 57 sites、68来源键；含atomic number0占位中心。原文件字节保留 | [UI](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-MOLECULAR-R22-UI-CJSON-render.png) / [MCP](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-MOLECULAR-R22-MCP-CJSON-render.png) |
| V2000 MOL | 21原子；21条来源键和21条sanitized解释键分别保留 | [UI](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-MOLECULAR-R22-UI-V2000-render.png) / [MCP](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-MOLECULAR-R22-MCP-V2000-render.png) |
| V3000 MOL | 113原子；119条来源/解释键分别保留 | [UI](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-MOLECULAR-R22-UI-V3000-render.png) / [MCP](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-MOLECULAR-R22-MCP-V3000-render.png) |
| MOL2 | 6185原子；6248原始声明键中有un，解释拓扑0；Incomplete。完整分子记录块保留，块前168字节注释仍在输入副本 | [UI](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-MOLECULAR-R22-UI-MOL2-render.png) / [MCP](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-MOLECULAR-R22-MCP-MOL2-render.png) |
| QCSchema | O/H/H、HF/cc-pVDZ、gradient、13numeric datasets；scf_iterations单位映射不支持而Ambiguous。内部Bohr，View正确换为Å。JSON规范化后语义完全相等 | [UI](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-MOLECULAR-R22-UI-QCSchema-render.png) / [MCP](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-MOLECULAR-R22-MCP-QCSchema-render.png) |
| SDF | AIN/CFF/TA1三个Structure，21/24/113原子、21/25/119键；一个文件默认创建首记录View。非零z保留，源2D标记警告在RDKit日志 | [UI](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-MOLECULAR-R22-UI-SDF-render.png) / [MCP](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-MOLECULAR-R22-MCP-SDF-render.png) |
| SMILES | 62图原子、68显式图键；View为确定性平面2D，不能当CCD三维构象 | [UI](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-MOLECULAR-R22-UI-SMILES-render.png) / [MCP](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-MOLECULAR-R22-MCP-SMILES-render.png) |
| XYZ | 113原子、Å坐标，无来源Topology；坐标与同源V3000一致 | [UI](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-MOLECULAR-R22-UI-XYZ-render.png) / [MCP](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-MOLECULAR-R22-MCP-XYZ-render.png) |

两路线均得到10个Structure、12个topology record、7个molecular record、8个default View。59个数组文件hash完全相同；逐个核对View坐标与sidecar，并按源JSON、MOL/SDF、MOL2、XYZ数值比较。SMILES检查62×3与平面z=0，不虚构来源三维坐标。QCSchema全部JSON内容相等；来源字节和规范化envelope字节不相等，未声称逐字节归档。

体验评价：Select Files在ChemBlender侧栏可找到，但位于旧工具面板下方，需要辨认。Preview按格式显示不同摘要，并不列出上表全部字段；已修正八份样例操作说明和Agent提示词中超出真实界面的要求。所有Preview有OK/Cancel；本项R22完整复测未另做取消子用例，取消行为的全轮最终复核仍由IMP承担。导入显示进度和committed反馈；UI原生输入累计100.13秒，MCP八次stage/confirm累计8.93秒，不含阅读与证据分析间隔。没有解析阻断，Incomplete/Ambiguous均保持诊断。窗口最小化后恢复曾显示旧Cube画面，公开area.tag_redraw后恢复当前集合，旧截图保留而不作为最终证据。

全部16张独立Workbench渲染均实际打开检查，无空白或裁切；默认都是原子视图，未为展示擅自接受拓扑。汇总取景保持相同比例，蛋白显著大于小分子，小分子应看独立图片。渲染与集合排版由证据脚本完成，不冒充鼠标执行渲染设置；UI产品导入、确认、Browser与保存由原生输入完成。

失败—修复—重测：R21实际UI将MOL2显示为SMILES，且Bonds:0没有说明6248原始键中的un不能解释。类别为导入反馈/科学含义，严重度P2，未改写科学数值，但会误导拓扑判断。已保存[失败截图与预览](../../../../../.blend-analysis/2026-09-07-review/outputs/failures/REP-MOLECULAR-mol2-preview/)，新增三项回归先失败，再以`1c290ee`修复格式标签、Interpreted bonds和不支持原因。R22上述两路径重新从空文件完成全部八输入，MOL2格式和原因均正确；[修复后Preview](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-MOLECULAR-R22-06-mol2-fixed-preview.png)、[Browser标签](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-MOLECULAR-R22-13-mol2-browser.png)。旧MCP失败未执行，不伪造旧包MCP失败结论。

修复验证：161专项测试Passed；完整2313tests/26有理由skips/0failure或error；compile、生成文档、原生隔离validate/build、ZIP审计、artifact verifier以及完整isolated smoke104.33秒Passed。R22包29989650bytes/解压32112542bytes；只有import_preview.py+664/+145与Browser model+310/+156，所有unexplained allowance为0。

- [UI配对文件](../../../../../.blend-analysis/2026-09-07-review/outputs/REP-MOLECULAR-R22-UI/REP-MOLECULAR-UI.blend) / [MCP配对文件](../../../../../.blend-analysis/2026-09-07-review/outputs/REP-MOLECULAR-R22-MCP/REP-MOLECULAR-MCP.blend)
- [科学检查、诊断与全部配对文件hash](../../../../../.blend-analysis/2026-09-07-review/outputs/REP-MOLECULAR-R22-science-check.json)
- [UI保存状态](../../../../../.blend-analysis/2026-09-07-review/outputs/REP-MOLECULAR-R22-UI-saved.json) / [MCP保存状态](../../../../../.blend-analysis/2026-09-07-review/outputs/REP-MOLECULAR-R22-MCP-saved.json)
- [MCP最终窗口](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-MOLECULAR-R22-17-mcp-redraw.png) / [UI保存窗口](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-MOLECULAR-R22-15-saved.png)

本项保存后未额外冷重开，不把安装前的冷依赖检查算作项目冷重开；LIFE和REP-GRID承担对应场景。实际用户安装仍Blocked，历史人工记录保持原状态。
