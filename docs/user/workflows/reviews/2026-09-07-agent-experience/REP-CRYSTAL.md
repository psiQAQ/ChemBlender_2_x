# REP-CRYSTAL — CIF、POSCAR 与 CONTCAR

## R25 最终复核

执行者：**Agent 模拟用户**。2026-09-08，Blender **5.1.1** / Python **3.13.9**。源码 `039bde7e1bf028b4b691d888d51460ae331ff678`；ZIP SHA-256 `661c58f82ae0a5564d37e713eca281e992ad24fd5b5b81fe2b2aee321862368b`。

UI 与 MCP 各使用独立的干净测试副本。按用户授权，重复动作从 [UI → MCP 命令目录](../../../../../tests/blender_review_commands.py) 读取公开命令；原生首测证据保留在下方阶段记录，重放不记为新的原生 UI 首测。

本次范围：三个周期输入的 View/数据绑定、18 个唯一数组、单元格/占据/无序元数据完整性；缺 spglib 的公开失败停止。

| 路径 | 最终结果 | 状态与耗时证据 | 配对文件 |
| --- | --- | --- | --- |
| UI | Passed（上述复核范围） | [操作结果](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-REP-CRYSTAL-UI-actions-summary.json)；[加载状态](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-REP-CRYSTAL-UI-loaded.json) | [最终副本](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25/REP-CRYSTAL/UI/REP-CRYSTAL-UI.blend) |
| MCP | Passed（上述复核范围） | [操作结果](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-REP-CRYSTAL-MCP-actions-summary.json)；[加载状态](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-REP-CRYSTAL-MCP-loaded.json) | [最终副本](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25/REP-CRYSTAL/MCP/REP-CRYSTAL-MCP.blend) |

所有最终副本的安装 Python 字节与 R25 ZIP 匹配，Reader API、Scene RNA、公开 poll 通过；原始配对文件及其权威数组未被本轮复核改写。[完整性核查](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25-integrity.json)与[逐项范围索引](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25-review.json)记录 UUID、manifest hash 和数组检查。每条命令的 JSON 留有实际 `seconds`，不将观察间隔计入产品等待。

最终 [14 集合展示文件](../../../../../.blend-analysis/2026-09-07-review/outputs/final-gallery/ChemBlender-R25-14-cases.blend)含本项同名 Collection 和 UI/MCP 子集合；[总览渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/FINAL-R25-gallery.png)与[真实窗口](../../../../../.blend-analysis/2026-09-07-review/screenshots/FINAL-R25-gallery-window-14-collections.png)已查看。展示模型按单体缩放，不用于科学距离比较；科学操作使用上表配对文件。

## 阶段验收记录（保留当时状态）

以下版本、失败和“待最终复核”描述对应当时检查点；当前结果以上方 R25 复核为准。

执行者：**Agent 模拟用户**。UI 路径 **Passed（已验证 UI 操作的 MCP 重放，加实际窗口检查）**；独立 MCP **Passed**。根据用户后续授权，复用 IMP/DATA 中已经实际操作的导入、周期 View 和保存流程；没有把重放记成新一次原生鼠标键盘首测。Blender **5.1.1**，source `5066cab35b28e21c484eeb64db026273cdea4243`，R24 ZIP SHA-256 `66e0a701ddbac2bf4cf4c4104da9b32a4e14cb632cefaf46a471d2a966861e9b`。最终全案例统一复核另行记录。

两条路径各从空场景开始，先 UI profile，结束后再独立 MCP profile。每次执行从 [命令目录](../../../../../tests/blender_review_commands.py) 读取已验证公开操作，并核对安装 Python 文件与相同 ZIP 一致。[输入副本与 hash](../../../../../.blend-analysis/2026-09-07-review/outputs/REP-CRYSTAL-inputs.json) 保持仓库原始字节。

| 输入 | 预期与实际科学结果 |
| --- | --- |
| COD 4503272 CIF，14996 bytes | 64 个非对称位点，晶胞 6.6439×23.2514×33.5615 Å；23 个部分占位、9 个无序位点；声明 C m c a / IT 64 / 16 operations；CIFEnvelope 原始字节完整 |
| COD 9012293 POSCAR，180 bytes | 8 C，Direct，3.5669 Å 立方晶胞；未凭来源名称虚构空间群 |
| COD 9012293 2×2×2 CONTCAR，1494 bytes | 64 C，Direct，7.1338 Å 立方晶胞；64×3 atomic_velocity 全零，单位保留 unknown，不能赋予 MD 时间含义 |

| 步骤 | UI 路径 | 独立 MCP |
| --- | --- | --- |
| 导入/预览/确认 | 重放已验证 Select Files → Preview → Confirm 对应命令，依次导入三个文件 | quick_import → 读取 preview_json → confirm_import，等待 committed 后处理下一个文件 |
| 数据与默认 View | Browser By Data → Structure；原生 N 侧栏查看 CIF 声明/派生对照及禁用按钮 | 公开 Browser RNA/活动对象选择；读取 View 的周期属性、坐标、实例几何 |
| 缺失依赖 | 原生窗口显示 Derive Symmetry 禁用及 spglib 原因；已验证失败路径的 MCP 重放明确停止 | derive_crystal_symmetry 返回 spglib 缺失错误；保存项目内没有新增 SymmetryResult |
| 保存与展示 | 已验证 Save As/Render 的命令重放；REP-CRYSTAL/UI 集合 | 独立保存、渲染；REP-CRYSTAL/MCP 集合 |

入口在 ChemBlender 侧栏，需要选中对应 Structure 才显示对称性。声明与派生结果分开，未派生区域明确显示 Not derived。窄栏中依赖说明中间省略，但 spglib 和禁用按钮可见，公开失败反馈包含完整原因。导入有 staging/committed 反馈；本项未再次点击 Cancel，取消首测证据见 IMP。三个默认 View 均为导入位点的原子实例，不自动扩展 CIF 非对称单元，也不添加猜测键或晶胞边框。两个金刚石文件的位点范围正确。

科学核对独立读取源 CIF 列及 POSCAR 文本，验证全部分数/笛卡尔坐标、晶胞、占位、无序、原始 envelope、零速度和 View 浮点精度；**18 个唯一数组 hash 在两路径相同**。实际实例数分别 64/8/64，均有非零实例面数。父网格面数为零是实例表示，初版核查脚本的直接面数断言已纠正；这不是产品显示故障。三个同相机细节渲染的像素数据完全相同，UI 图像均已逐张查看。详见[科学核查、配对 hash 与图像对比](../../../../../.blend-analysis/2026-09-07-review/outputs/REP-CRYSTAL-R24-science-check.json)。

本项没有确认新的产品代码缺陷，修复 commit 不适用。调整了样例说明中过度具体的 Preview 预期：POSCAR 预览显示晶胞体积，CONTCAR 预览显示 Ion velocities，完整矩阵与单位在提交后核查。可选 spglib 推导 **Not Run（依赖未安装）**；其不可用提示与失败停止 **Passed**。本项保存后未冷重开，冷重开不借用历史结果。

证据保存在 `REP-CRYSTAL-R24-*`：每次公开命令的 arguments、反馈和 seconds 均记录于 [本轮 outputs](../../../../../.blend-analysis/2026-09-07-review/outputs/)。耗时按实际请求分别记录，包含渲染与只读检查，不当作连续人工操作时间。

- [声明/派生/缺失依赖窗口](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-CRYSTAL-R24-03-symmetry-unavailable.png)
- [CIF 渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-CRYSTAL-R24-UI-cif-detail.png)、[POSCAR 渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-CRYSTAL-R24-UI-poscar-detail.png)、[CONTCAR 渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/REP-CRYSTAL-R24-UI-contcar-detail.png)；对应 MCP 图同目录。
- [UI .blend](../../../../../.blend-analysis/2026-09-07-review/outputs/REP-CRYSTAL-R24-UI/REP-CRYSTAL-UI.blend) 与相邻 `.cbq`；[MCP .blend](../../../../../.blend-analysis/2026-09-07-review/outputs/REP-CRYSTAL-R24-MCP/REP-CRYSTAL-MCP.blend) 与相邻 `.cbq`。
