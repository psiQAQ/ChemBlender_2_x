# ChemBlender 2.5 真实用户教程：本地 agent 执行任务书

在当前本地仓库执行本任务，不要只返回计划或教程草稿。目标是按真实科学输入、当前已安装发布制品和正常 GUI 路径，交付可照做的 2.5 教程与可复做工程。没有实际执行的步骤保持 Not Run/Blocked/Failed，不得写成功。

## 固定参考与动态事实

调研基线：`psiQAQ/ChemBlender_2_x`，`release/2.5.0`，`478bbd498277a0ce9a32fc9b262f36ec8410d2d9`。这是调研锚点，不是授权你强制切换、重置或覆盖本地分支。先记录当前 HEAD、分支、工作区修改、运行进程和已安装制品，再比较差异。

先阅读根 AGENTS、`.agents/README.md` 与当前 active 文档，再读本任务包的报告、catalog 和对应 case。根 AGENTS 中仍存在 RDKit manifest wheel/import 的历史口径，与 2.5 wheel-free Viewer 交付记录冲突；先核查当前有效决策并同步范围内文档，不得恢复旧科学 wheel 来满足过期条目。

当前参考组合是 Extension 2.5.0、prepare 0.1.0、Worker Protocol 1、Reader API 1.0-rc1；历史资格 Blender 为 5.1.1，但执行时必须记录实际版本。不得从旧会话猜测路径或版本。

## 约束

只做本地、范围内的教程/证据/必要修复工作；不 push、改远端、PR、tag、Release 或 PyPI。保护未提交修改、旧案例、用户偏好、原始科学数据和已安装环境。不得 reset --hard、删除输入或批量结束所有 Python/Blender 进程。

不在 Blender Python 安装科学包，不注入源码/site-packages/PYTHONPATH 来让候选包看起来可用。优先使用已授权的独立环境；缺少后端时列出所需依赖、版本、来源、许可和风险并阻塞相应案例，继续其他可执行案例。未经授权不新装后端、不购买服务、不使用账号凭据获取私有数据。

当前稳定契约只有公开 CLI、Worker Protocol、Reader API。普通用户重放不得依赖 `chemblender_prepare.core.*` 或隐藏 helper。为独立审计只读检查科学状态可使用有明确标识的审计脚本，但不能把审计路径代替正常用户操作。

Fermi 旧档许可未闭合且含 POTCAR/pickle：不进入公开案例包，不提取或执行 pickle，不泄露 POTCAR。第三方 Reader 默认不会被 CLI 自动发现；历史 Blender Reader Extension 不安装到当前 Viewer。`external_record.fetch` 当前固定 unavailable，不能用 mock/fake transport 写“真实在线取数成功”。

## 执行顺序

创建或接续唯一 active 任务文件，记录当前 case/step、运行目录、失败原因、下一动作、产物位置及未解决项。每个关键状态变化后写盘；会话恢复先读该文件，不从记忆猜进度。一次只允许一个 GUI 操作者；其他 agent 可审阅来源、分析测试或校对文案，不同时点击同一窗口。

先完成 M0 环境与制品冻结。依据实际已安装工具发现 Blender/MCP 能力；既有 `blender-mcp` 可用时先读取其 help，再查询实际 Blender executable/version/bundled Python/extension repositories。MCP 能执行 Python 并不说明它能完成真实鼠标键盘操作。实际 GUI 路径缺少工具时，应明确 `GUI_NOT_RUN`，不能降格用后台执行冒充。

在新、唯一、可清理的项目内运行目录下工作。新 profile 显式设置并核对 Blender user resources/config/scripts/data 路径；从发布 ZIP 原生安装，核对 `bl_ext.user_default.chemblender` 或本次真实仓库标识。记录 Extension ZIP 与 prepare wheel SHA-256、安装来源、prepare executable、Python 版本、Blender/GPU/render 设置、界面语言和窗口缩放。全量环境变量与无关宿主配置不采集。

先执行 T00/T01：用真实输入完成 prepare GUI inspect/convert、Blender CBQ Preview/Import、选择实体、创建 View、调整显示、实际 Cycles 渲染、Save、退出并新进程重开。这一课完成之前不要批量撰写所有课程。

按当前公开 RNA、CLI --help、菜单和面板实测填写每步准确标签、参数与期待状态。首课正常 GUI 步骤必须由 OS/human GUI 输入完成；Operator/RNA/CLI 语义重放另做一条轨道。禁止先脚本搭完全部场景再拍图，随后写成“按菜单逐步完成”。

每步保存操作前/后原始 PNG、动作/事件记录和结果断言。截图与渲染分开：截图要看得到真实菜单/参数/实体/状态；渲染要检验物理量、单位、坐标、颜色、isovalue 和图注。标注图只能基于原图加箭头/编号/裁剪，不能改数值或隐藏关键报错。关键连续操作、动画或取消过程录制短视频。绑定本次制品哈希，禁止复用旧截图通过 2.5 门槛。

执行科学断言：来源哈希、单位、原子/帧/网格规模、实体关联与 revision、Apply 不覆盖原结构、浮点结果参考与容差。不能从分子名称猜原子数，不能把力场叫 DFT，不能把 rMD17 显示帧率叫物理时间，不能把独立 Band/DOS 计算拼成同一 provenance。

对最终 `.blend + .cbq` 做独立进程冷重开。整体复制到新目录再重开，比较科学数组/身份，不以 .blend 字节恒等作标准。缓存重建与 source/processor 不可用测试仅对测试副本和隔离 profile 做；原始科学数组不是可删缓存。取消、过期 revision、无效路径和损坏副本要不污染原工程。

再完成其余 P0：T02/T04/T06/T07/T17/T18；然后按真实可用能力推进 P1/P2。每个 optional 案例同时提供“合法预计算 CBQ 的 Viewer 路线”和“可选重算路线”，没有完整预计算实体则不承诺离线可用。无后端的分支保持 Blocked/Not Run，不计入正向通过。

## 文档与目录

优先整合现有 `docs/user/{zh-CN,en}`、离线生成器、公开能力清单和案例脚本。新案例可以落入 `examples/tutorials/2.5.0`；旧输入保持不变，来源/许可证/哈希不丢失。大二进制结果先作为本地产物和待发布资产，不直接堆进 Git；不进 Extension ZIP。

每课正文必须让不了解源码的读者照做：具体成果、前提、输入下载/本地路径、真实步骤、预期现象、逐步截图、最终结果、配对工程下载、科学边界、错误恢复、真实测试版本和测量耗时。命令可复制；没有 GUI 按钮的操作如实写 CLI/专家入口。

修复离线生成器实际存在的问题：正文链接不应只变成文字；图片应贴近步骤；表格应可读；缺失资源数来自检查而不是固定零。做真实离线浏览、链接/下载检查和中英一致性检查。不要仅用生成字节一致和全量单元测试替代这些检查。

安排第二个干净 profile，仅按草拟教程和发布数据重做，不读取作者的隐藏会话/内部脚本来补步骤。发现 UI 必须用脚本绕过的缺陷时，记 Failed，做范围内最小修复+回归，然后重跑受影响证据。

## 验收与结束输出

利用 catalog 将当前公开 operation/reader/export/CLI/GUI 映射到案例；如果源码公开面变化，重新生成映射。设计覆盖率、真实计算通过率、GUI 通过率、可分发完成率分别统计。`unavailable` 的预期负例不能抵消 mandatory 正例缺失。

可采用附带 `T01.case-spec.json`、`run-manifest.template.json` 和 `validate_evidence.py` 的约定，或映射到仓库已有等价工具；不要维护两套不一致的结果。检查器只能判一致性，无法证明截图真实，不能作为唯一验收。

每一阶段完成后做相关测试、文档检查和 git diff --check，保留逐案例 Passed/Failed/Blocked/Not Run 以及原因。必要源码修复只限当前已证实缺陷，同步架构文档（职责变化时）并回归；不顺手扩张功能。

最终提供：实际执行的基线与制品哈希、逐案例/逐轨道结果、真实截图与渲染索引、可重开工程、科学检查及生命周期报告、许可与可分发清单、测试命令和结果、未解决问题、待授权的发布步骤。只在对应证据全部存在时关闭 active 任务；无法执行的 GUI 或后端必须明确留作未完成，不给出“已全覆盖上线”的结论。
