# AGENT — 公开操作、失败停止与连接恢复

## R25 最终复核

执行者：**Agent 模拟用户**。2026-09-08，Blender **5.1.1** / Python **3.13.9**。源码 `039bde7e1bf028b4b691d888d51460ae331ff678`；ZIP SHA-256 `661c58f82ae0a5564d37e713eca281e992ad24fd5b5b81fe2b2aee321862368b`。

UI 与 MCP 各使用独立的干净测试副本。按用户授权，重复动作从 [UI → MCP 命令目录](../../../../../tests/blender_review_commands.py) 读取公开命令；原生首测证据保留在下方阶段记录，重放不记为新的原生 UI 首测。

本次范围：公开 RNA/poll、未知单位阻断反馈、失败确认停止及取消恢复；两测试连接持续可用。

| 路径 | 最终结果 | 状态与耗时证据 | 配对文件 |
| --- | --- | --- | --- |
| UI | Passed（上述复核范围） | [操作结果](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-AGENT-UI-actions-summary.json)；[加载状态](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-AGENT-UI-loaded.json) | [最终副本](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25/AGENT/UI/AGENT-UI.blend) |
| MCP | Passed（上述复核范围） | [操作结果](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-AGENT-MCP-actions-summary.json)；[加载状态](../../../../../.blend-analysis/2026-09-07-review/outputs/FINAL-R25-AGENT-MCP-loaded.json) | [最终副本](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25/AGENT/MCP/AGENT-MCP.blend) |

所有最终副本的安装 Python 字节与 R25 ZIP 匹配，Reader API、Scene RNA、公开 poll 通过；原始配对文件及其权威数组未被本轮复核改写。[完整性核查](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25-integrity.json)与[逐项范围索引](../../../../../.blend-analysis/2026-09-07-review/outputs/final-R25-review.json)记录 UUID、manifest hash 和数组检查。每条命令的 JSON 留有实际 `seconds`，不将观察间隔计入产品等待。

最终 [14 集合展示文件](../../../../../.blend-analysis/2026-09-07-review/outputs/final-gallery/ChemBlender-R25-14-cases.blend)含本项同名 Collection 和 UI/MCP 子集合；[总览渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/FINAL-R25-gallery.png)与[真实窗口](../../../../../.blend-analysis/2026-09-07-review/screenshots/FINAL-R25-gallery-window-14-collections.png)已查看。展示模型按单体缩放，不用于科学距离比较；科学操作使用上表配对文件。

## 阶段验收记录（保留当时状态）

以下版本、失败和“待最终复核”描述对应当时检查点；当前结果以上方 R25 复核为准。

执行者：**Agent 模拟用户**。UI **Passed（R21）**；MCP **Passed（R21，隔离依赖修复后重测）**。Blender 5.1.1，source `76d1d9e`，ZIP SHA-256 `61b64592fbab352aaaa70ea319963ab6c6436a4f2d2d0728c68fabb7daa73635`。最终全项同包复核仍待完成。

前置状态为各自空项目、独立 profile 和端口。输入是本轮不可变 `inputs/LIFE-revision/original.xyz` 三原子水及 `inputs/IMP-invalid/unknown-unit.gjf`（Units=Furlongs）。两条路线均不使用私有产品函数，确认已由用户授权。

| 检查 | UI 原生步骤与实际结果 | MCP 公开步骤与实际结果 |
| --- | --- | --- |
| RNA / poll | Shift+F4，键入公开 introspection；显示 files/directory/validation_mode、poll=True；Shift+F5 返回 | 一次读取版本、路径、系统、repos、enabled key、Scene；读取目标 Operator 属性、默认值、枚举和 poll |
| 预览和取消 | ChemBlender > Select Files > 原生文件选择器 > Preview > Cancel；零对象、Import cancelled、预览清空 | quick_import，按公开 preview_json 条件等待；cancel_import 后零对象 |
| 正常操作 | 重选水分子、确认默认 Structure View，立即显示三原子与 committed | 明确审阅 Complete/nonblocking 行，confirm_import；三原子、committed |
| 失败停止 | 未知单位显示具体 Furlongs 原因；取消后原水坐标不变 | Invalid/blocking 公开原因一致；直接确认明确拒绝，再取消，前后坐标完全一致 |
| 连接恢复 | Preferences > Add-ons > MCP，端口9877，Stop 后 ConnectionRefusedError；Start 后完整环境查询及对象保持 | public server_stop 后连接关闭；只关闭自建 PID12412，按相同 executable 重启，随后因依赖缺失停止；修复后 PID30276 从空项目重跑全流程 |
| 保存 / 图像 | 原生 Ctrl+S 保存 AGENT/UI 集合、相机和配对；PID22328 冷重开仍 clean、UUID/hash/坐标一致 | public save_as_mainfile 保存 AGENT/MCP 集合及配对；确认 installed Python bytes、RDKit/Gemmi 来源、渲染和 sidecar 数组 |

体验评价：插件入口在 N 侧栏可找到；MCP 启停入口位于 Preferences，F3 不提供该外部扩展操作，需展开设置并滚动。导入有 stage/百分比和 committed/cancelled 反馈；正常与失败预览均可取消。R20 错误只显示 ValueError 的问题已修复，当前原因全文可读。单次 MCP stage/confirm/cancel 约0.39秒，完整恢复后工作流5.66秒；UI 记录内的原生输入累计61.8秒，不含阅读截图、修复与构建等待。三原子按源坐标、单位 Å 保持，XYZ 没有显式键，本项没有自动声明化学键。

| 问题 | 影响 / 严重程度 | 失败—修复—重测 |
| --- | --- | --- |
| 单位错误原因被通用 ValueError 隐藏 | Medium 文案；无错误坐标提交 | outputs/failures/AGENT-unit-diagnostic；四个 Gaussian/ORCA 回归先失败；76d1d9e 保留受限长度的内置验证原因，R21 UI/MCP重测通过 |
| 本轮 MCP profile 冷启动缺失93个 RDKit DLL | High 安装恢复；基础 XYZ 流程可运行，但依赖环境不合格，首次 Passed 判断撤回 | outputs/failures/AGENT-cold-dependency 保留原配对/记录；新增 blender_cold_dependencies.py 新进程先失败。关闭自建进程，归档仅本轮 .local，factory-startup 原生 Extensions 重装同一ZIP；第二个新进程逐一比对 wheel 文件及实际导入通过；PID30276完整重测通过 |
| 原生安装器默认 Existing MCP | 测试操作问题，未影响原用户；字节断言及时阻止验收 | 本轮多余目录隔离于 AGENT-test-installer-wrong-repo；原生明确选择 User Default 后全部 Python 文件匹配 |
| 证据相机忽略未展开的 GN 实例 | 测试取景问题，首次图像裁切；科学数据不变 | 保留原 render.png；展示助手改读 depsgraph.object_instances bounds，最终 render-final.png 两图实际检查完整 |

新包自动验证：2310 tests / 26已说明原因的skips / 零失败，隔离 smoke104.35秒，compile/docs/native validate/build/audit/verifier通过。只改 registry.py，+505 unpacked / +187 packed bytes，包29,989,349 / 解压32,111,568 bytes；unexplained allowance=0。MCP与UI各自的冷依赖检查均通过；此结果不代表被自动审批阻断的实际用户安装已通过。

- [UI RNA](../../../../../.blend-analysis/2026-09-07-review/screenshots/AGENT-R21-08-rna.png) / [具体错误](../../../../../.blend-analysis/2026-09-07-review/screenshots/AGENT-R21-11-error-reason.png)
- [停止](../../../../../.blend-analysis/2026-09-07-review/screenshots/AGENT-R21-13-stopped.png) / [恢复](../../../../../.blend-analysis/2026-09-07-review/screenshots/AGENT-R21-14-recovered.png)
- [UI 配对](../../../../../.blend-analysis/2026-09-07-review/outputs/AGENT-R21-UI/AGENT-UI.blend) / [UI 渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/AGENT-R21-UI-render-final.png) / [UI 冷重开](../../../../../.blend-analysis/2026-09-07-review/outputs/AGENT-R21-UI-cold.json)
- [MCP 配对](../../../../../.blend-analysis/2026-09-07-review/outputs/AGENT-R21-MCP/AGENT-MCP.blend) / [MCP 渲染](../../../../../.blend-analysis/2026-09-07-review/screenshots/AGENT-R21-MCP-render-final.png) / [依赖恢复截图](../../../../../.blend-analysis/2026-09-07-review/screenshots/AGENT-R21-19-mcp-repaired.png)
- [MCP 公开状态与耗时](../../../../../.blend-analysis/2026-09-07-review/outputs/AGENT-R21-MCP-final.json) / [科学数组与 hashes](../../../../../.blend-analysis/2026-09-07-review/outputs/AGENT-R21-science-check.json)
- [冷依赖失败](../../../../../.blend-analysis/2026-09-07-review/outputs/AGENT-R21-cold-dependencies-before.json) / [修复后](../../../../../.blend-analysis/2026-09-07-review/outputs/AGENT-R21-cold-dependencies-after.json)
