# REP-GRID — 64³ H₂ 密度、真实渲染与冷恢复

## R25 最终复核

执行者：**Agent 模拟用户**。2026-09-08，Blender **5.1.1** / Python **3.13.9**。源码 `039bde7e1bf028b4b691d888d51460ae331ff678`；ZIP SHA-256 `661c58f82ae0a5564d37e713eca281e992ad24fd5b5b81fe2b2aee321862368b`。

UI 与 MCP 各使用独立的干净测试副本。按用户授权，重复动作从 [UI → MCP 命令目录](../../../../../tests/blender_review_commands.py) 读取公开命令；原生首测证据保留在下方阶段记录，重放不记为新的原生 UI 首测。

本次范围：本项完整干净体验已使用 R25：64³ 全体素、显式语义/单位 provenance、Cycles Volume/正负表面、四 VDB 真正新进程重建；再复核配对及展示。

| 路径 | 最终结果 | 状态与耗时证据 | 配对文件 |
| --- | --- | --- | --- |
| UI | Passed（上述复核范围） | [操作结果](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-REP-GRID-UI-actions-summary.json)；[加载状态](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-REP-GRID-UI-loaded.json) | [最终副本](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25/REP-GRID/UI/REP-GRID-UI.blend) |
| MCP | Passed（上述复核范围） | [操作结果](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-REP-GRID-MCP-actions-summary.json)；[加载状态](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-REP-GRID-MCP-loaded.json) | [最终副本](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25/REP-GRID/MCP/REP-GRID-MCP.blend) |

所有最终副本的安装 Python 字节与 R25 ZIP 匹配，Reader API、Scene RNA、公开 poll 通过；原始配对文件及其权威数组未被本轮复核改写。[完整性核查](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25-integrity.json)与[逐项范围索引](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25-review.json)记录 UUID、manifest hash 和数组检查。每条命令的 JSON 留有实际 `seconds`，不将观察间隔计入产品等待。

最终 [14 集合展示文件](../../../../../.blend-analysis/2026-09-07-review/outputs/final-gallery/ChemBlender-R25-14-cases.blend)含本项同名 Collection 和 UI/MCP 子集合；[总览渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/FINAL-R25-gallery.png)与[真实窗口](../../../../../.blend-analysis/2026-09-07-review/screenshots/FINAL-R25-gallery-window-14-collections.png)已查看。展示模型按单体缩放，不用于科学距离比较；科学操作使用上表配对文件。

## 阶段验收记录（保留当时状态）

以下版本、失败和“待最终复核”描述对应当时检查点；当前结果以上方 R25 复核为准。

执行者：**Agent 模拟用户**。UI 路径 **Passed（既有 UI 操作的公开命令重放，实际窗口验收）**；独立 MCP **Passed**。复用 VIEW 中已经原生操作的导入、Resolve、Volume、Signed Surface，以及 OUTSIDE/LIFE 的渲染和保存操作；按用户后续授权重放，不冒充新一次原生首测。实际窗口另行检查，发现的问题在本项修复。

最终 Blender **5.1.1** / Python **3.13.9**；source `039bde7e1bf028b4b691d888d51460ae331ff678`；R25 ZIP SHA-256 `661c58f82ae0a5564d37e713eca281e992ad24fd5b5b81fe2b2aee321862368b`。两条路径及冷重开的安装 Python 字节均与同一 ZIP 一致。整轮最终同包复核单独记录。

输入为仓库不可变样例的字节副本 [`h2-lcao-1s-density-64.cube`](../../../../../.blend-analysis/2026-09-07-review/inputs/REP-GRID/h2-lcao-1s-density-64.cube)：3,932,577 bytes，SHA-256 `51fcb06343132c4b75f340aa5824434c9c622b51df7ea1ad3742920c78af66b4`。这是解析 H₂ bonding 1s LCAO 教学密度，**不是 HF/DFT**。两核间距 1.4 bohr，64³=262144 点，origin=(-6,-6,-6) bohr。文本步长舍入后离散积分 **1.9996717595939095 electrons**，全量最小/最大 **7.75746861e-10 / 0.229296377**；Preview 的 Sample range 是有界采样，不当作全量极值。

两条路径分别从空场景开始，UI 路径完整结束后才开始 MCP。每次通过 [命令目录](../../../../../tests/blender_review_commands.py) 调用公开 Operator/RNA，确认弹窗按已授权用例处理。产物保留 REP-GRID/UI 或 REP-GRID/MCP Collection。

| 步骤 | UI 路径与可见结果 | 独立 MCP |
| --- | --- | --- |
| 导入 | 重放 Select Files → Preview → Confirm；64³、bohr、unknown/Ambiguous；默认创建原始 Grid Volume | quick_import、preview_json、confirm_import；读取 committed 后继续 |
| 科学确认 | 选择原始 Grid，明确 electron_density / electron_per_cubic_bohr；Resolve 后选中 Complete Derived | 公开 Browser selected_index、Grid RNA、resolve_grid_semantics；独立记录参数与反馈 |
| 创建 View | Volume 与 Signed Surface；原始 Volume 保留，另有确认后 Volume、正/负 Surface | create_grid_view(mode=volume/signed_surface)，均绑定确认后的 Grid |
| 渲染 | Cycles CPU、32 samples、1280×800；同一相机分别渲染体密度、正表面、空负表面 | 独立设置相同普通 Blender 相机/Area/World，公开 render.render |
| 保存 | 已验证 Save As 操作的命令重放；相邻 `.blend/.cbq` 与四份 VDB | 同样流程独立保存，核对 project UUID / manifest hash |
| 冷恢复 | 完整复制测试配对，只移走副本 `cache/render`；停止自建 PID30924，新可见 PID20696 打开副本 | 停止自建 PID37564，新可见 PID29112 独立打开缺缓存副本 |
| 冷后核查 | 四份 VDB 自动重建到该副本 sidecar；真实 Volume/Surface 再渲染 | 独立相同核查；两个进程均保留 Connected 状态与公开 View 绑定 |

入口需要选中 Grid；Resolve 有明确反馈，原始 Ambiguous 数据和诊断保留，Derived Complete 数据被选中。窗口现在分行显示形状、坐标单位、语义、值单位、质量和实际 Threshold。导入及创建 View 的原生进度/取消流程已有 VIEW 首测；本项按授权使用同步 EXEC 重放，没有把命令调用称为新的取消按钮测试。失败不会默认为科学确认。创建后所有 View 最初位于同一空间，展示时用普通 Blender 可见性逐个查看，不修改数据或 cb 绑定。

**科学与缓存验证 Passed**：两个 Grid 的全部 float64 数值与源文本相等，raw 保持 scalar_field/unknown/Ambiguous，Derived 为 electron_density/electron_per_cubic_bohr/Complete，独立 provenance 记录显式确认。两个 H 的 bohr 坐标与源记录相同。3 个唯一权威数组 hash 在两路径相同。VDB 按 float32 保存源值，负表面缓存按相位取负；全部体素逐点核对，origin/step/边角坐标的 affine 变换按 `0.529177210903` 转为 Å。值单位保持电子/bohr³，没有偷偷缩放密度值。

四份 VDB 在新进程中从缺失状态重建。冷前后权威 manifest 文件 hash 相同，所有 VDB 的值、变换和元数据相同；VDB 容器二进制 hash 变化，不把它误报为科学数据变化。UI/MCP 三种初次渲染，以及两路径各自冷前后的 Volume/positive 渲染，**像素数据均完全相同**。实际查看了对应图像，体密度可见、正等值面有几何，非负密度的负等值面为空符合预期。

| 问题 | 影响与失败证据 | 修复/重测 |
| --- | --- | --- |
| P2：0.001 显示为 0.00，摘要截断且缺少确认后的值单位 | 影响阈值和单位核对；权威数组与渲染阈值正确。[不可变失败配对、截图与 RED test](../../../../../.blend-analysis/2026-09-07-review/outputs/failures/REP-GRID-isovalue-label/) | `039bde7`：控件 precision=6，增加有效数字 Threshold，分行显示单位/语义；回归覆盖 0.001 和 1e-9。新包两条干净路径、原生窗口、渲染与冷恢复 Passed |
| 样例文档写 nuclear charge=1，但源 charge 列为 0 | reader 按源保存 `[0,0]`；误写说明可能导致错误解释，不是 parser 丢值 | 校正文档为生成器占位零值，不能用于真实核电荷/核势；独立核查直接比较文本 charge 列，不改样例字节 |

R25 修复仅 `ui/grid.py` 增加 **268 unpacked / 89 packed bytes**，包 29,989,841 bytes、总解压 32,113,134 bytes，unexplained allowance=0。8 项专项、**2314 项完整 unittest / 26 skips / 0 failures/errors**、compile、生成文档、原生 validate/build、ZIP audit、artifact verifier、完整 isolated smoke **106.88 秒**均 Passed。两个停止旧进程后的命令目录安装与新进程依赖验证 Passed，分别约 3.31/1.96 秒和 3.10/1.95 秒；不涉及被阻断的实际用户安装。

实际公开渲染请求耗时 UI：Volume **4.530 秒**、positive **3.178 秒**、negative **2.294 秒**；MCP：**4.505 / 3.177 / 2.323 秒**。其他操作逐条 seconds、输入及反馈保留在本轮 outputs 和 mcp-actions 日志，不能把 Agent 观察间隔当作产品等待。

- [完整科学、冷恢复、配对 hash 与像素核查](../../../../../.blend-analysis/2026-09-07-review/outputs/REP-GRID-R25-science-check.json)
- [修复后的实际窗口](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-GRID-R25-01-threshold-fixed.png)、[冷重开窗口](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-GRID-R25-02-cold-final.png)
- [Volume 渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-GRID-R25-UI-volume-detail.png)、[正表面](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-GRID-R25-UI-positive-detail.png)、[空负表面](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-GRID-R25-UI-negative-detail.png)；同目录有 MCP 及 cold 对照图。
- [UI 原配对 .blend](../../../../../.blend-analysis/2026-09-07-review/outputs/REP-GRID-R25-UI/REP-GRID-UI.blend)、[MCP 原配对 .blend](../../../../../.blend-analysis/2026-09-07-review/outputs/REP-GRID-R25-MCP/REP-GRID-MCP.blend)，均带相邻 `.cbq`。
- [UI 冷恢复副本](../../../../../.blend-analysis/2026-09-07-review/outputs/REP-GRID-R25-UI-cold/REP-GRID-UI.blend)、[MCP 冷恢复副本](../../../../../.blend-analysis/2026-09-07-review/outputs/REP-GRID-R25-MCP-cold/REP-GRID-MCP.blend)，原移走缓存保存在各自 `removed-render-cache/`。
