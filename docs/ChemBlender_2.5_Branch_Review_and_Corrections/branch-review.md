# ChemBlender 2.5 真实用户教程分支审查

## 结论与范围

产品方向基本对齐原任务：正在推进真实输入、GUI/公开 Operator、科学断言、渲染、配对工程与恢复，而不是只写文档或重构架构。已看到相关产品缺陷的修复和安装态验证记录。需要纠偏的重点是当前状态失真、验收检查器的提前返回、混合执行授权与规格尚未衔接、专业环境的跨环境依赖复用，以及多版本教程混排。建议保留成果，先校准证据与收口机制，不推倒重来。

审查固定到 `psiQAQ/ChemBlender_2_x` 的 `feat/2.5-real-user-tutorials`，提交 `c1fa7584f56d6df387617406958065573e9b56c1`，提交时间 `2026-09-10T14:49:53Z`。结束前再次查询仍为同一 HEAD。原研究基线是 `478bbd498277a0ce9a32fc9b262f36ec8410d2d9`。[R01]

这是对已提交源码、任务文件、案例文档和执行回执的只读审查，不是用户本机重跑。原始日志、截图和大体积项目多数位于本机 `.blend-analysis/2.5-real-user-tutorials/`，未在本次环境独立验真或重新计算哈希。下述“通过”指仓库记录，不等于本次独立执行成绩。没有修改远端、用户工作区或原研究包。[R02]

## 当前执行情况

所有 8 个 P0 案例已有不同程度的实操；其余 14 个 P1/P2 单元在当前状态表中尚未运行。完整人工接纳的案例为 0。8/22 只是已进入执行的案例数量，不是工作量完成率；状态表过期，不能直接拿它计算总体百分比。[R03–R05]

| 案例 | 已提交记录支持的进展 | 仍需关闭的关键门槛 |
|---|---|---|
| T00 安装与诊断 | 真实 GUI 安装/诊断、后续多次原生安装与制品文件比较记录 | 汇总到当前候选；旧入口、规格和验收状态校准 |
| T01 首课 | run-003 的 Prepare GUI、授权 MCP 重放、科学对照、Cycles、原位/移动冷重开及审阅包 | 当前候选适用性；GUI 复用规则；完整恢复/人工复做 |
| T02 乙醇 | 23e46b5 修复旧 View 坐标恢复、结果重绘、状态映射；run-003 GUI/科学/渲染/冷重开/包记录 | 当前候选复验或适用性；剩余缓存/GUI/人工门槛 |
| T04 晶体 | run-009 CIF/POSCAR/ASE GUI、坐标/晶胞核查、View/平滑渲染、移动/解包重开及重建 | 侧栏可读性、手动步骤/图片整合、专业部署资格和人工复做 |
| T06 轨迹 | run-009 32 帧 × 21 原子；全帧 View/力检查、真实 Play/Pause、32 张 PNG、MP4、可移动 VSE 和审阅包 | 完整手动渲染/节点步骤、部分 GUI/可读性及人工复做 |
| T07 网格 | run-009 Cube GUI→Viewer 重放、262144 数值、4225 切片点、129 剖面点、色标、差分与部分渲染/冷重开/重建；此前有 VASP 变体 | 最新 sampling-layout 冷重开、其他渲染、当前候选专业变体/不可用源与处理器恢复、正文/包/人工门槛 |
| T17 导出 | run-006 13 格式 CLI 和 Prepare GUI 正向回执、字段/损失检查；修复 MOL/SDF 立体标记与 PQR 问题 | 不应仍写 not_run；当前候选适用性与完整交接/人工验收 |
| T18 生命周期 | Save As 懒加载路径缺陷修复；run-007 安装态 Save As、GUI Relink、错误目标拒绝、冷重开、若干损坏/取消/过期及旧工程迁移检查 | 不应仍写 not_run；分离取消类型、View 过期与 Worker 过期、运行时/OS 隔离；其余 GUI/新 profile/人工门槛 |
| P1/P2 | T03、T05、T08–T16、T19、T20、B01 没有当前完整新案例实操记录 | 仍是待执行范围，不能由历史科学语料或单元测试代替 |

T07 最新回执的状态是 `rendered`，并明确 `gui_creation: not_run_new_candidate`、人工审阅未做，证明其没有把最新渲染自动写成新 GUI 成功。T06 也区分公开 FRAME/render 重放、真实 Play/Pause 和人工复做。[R06–R08]

### 当前候选与回归记录

| 项目 | 仓库记录 |
|---|---|
| Extension SHA-256 | `a1e2da79253d505b60daa42aa465eb725cdd1eba00e6c81ce4082102a62d0f28` |
| prepare wheel SHA-256 | `b736bc61ecdbee77f61696576c98092afc7352a9af16b4367bfd3c2e3159af3a` |
| prepare 源提交 | `32d96303b2c0e16260b32b470c2d5601226d9318` |
| 构建/双安装 Python 文件比较 | 165 个文件一致 |
| 全量测试 | 2564 项；2527 Passed；37 Skipped；0 Failure；0 Error |
| 独立人工接纳 | Not Run |

37 个 skip 包括 IOData/GBasis、cclib、phonopy、pymatgen、pyprocar、spglib 相关条件以及 OS 符号链接权限；不能用主环境全量测试的通过代替专业路线的正向验收。其他环境存在部分专项结果，需要分别关联，不能把所有 skip 一律当成缺陷或一律当成已覆盖。[R09]

## 值得保留的推进方式

根 AGENTS 已从旧 RDKit wheel/import 口径改为 wheel-free Viewer，科学依赖留在外部。抽查的 T02 提交确实修改源 View 恢复、任务完成重绘和 CalculationStatus→QualityStatus 映射，并补测试，不是仅更新成功文案。T04 晶胞显示和 T18 Save As 修复与案例中的失败路径一致。这些是原任务允许的必要修复，不是方向漂移。[R10–R12]

分支记录显示，用户另行批准原生 JPEG 与已验证操作的 MCP 重放，并要求展示细化。因此 JPEG、MCP 和细化本身不能判为偏航。关键是保留真实 GUI 与重放的证据分类，以及显示细分不等于科学采样加密的边界。多份回执和当前教程明确保留了这些区分。[R04、R07、R08]

大产物留本地、review_only 不等于最终发布、人工不自签，是正确约束。远端存在此工作分支不能单独证明 Codex 擅自 push；本次未调查是谁执行了同步，不能据此定责。[R02–R05]

## 发现与纠正

### F01：当前状态来源失真（高优先级）

active 顶部仍标 run-003/current phase M1，末尾已在 run-009/T07。README 的运行/工程/校验命令仍指 run-002。status.json 中 T07 只记录 run-004 的初始转换，T17/T18 仍是 not_run。T01/T02 的“final candidate”叙述也绑定较早哈希。这些并非单纯缺少美化，而是会改变 agent 的下一任务选择与验收判断。[R02–R05]

纠正：保持单一当前状态汇总，逐项引用 receipt、案例、制品和适用范围；把历史长记录移入已有 progress/历史目录并保留链接。active 顶部改为真正当前快照，plan 保留门槛，不在多个文件反复复制流水账。保留设计基线的含义，另记录实际构建与运行身份。不将已运行但未接纳记成 not_run，也不将人工等待混作技术未执行。

### F02：未完成运行绕过检查器主要审计（高优先级）

执行版 `validate_evidence.py::_audit` 在 `m.status != passed` 时返回 incomplete。此返回发生在制品 SHA、实际文件哈希、事件/步骤绑定、科学断言与生命周期检查之前。因此它不能在案例未完成时帮助发现已经声明的证据被误换、缺失或篡改。[R13]

这是原研究模板带来的限制，不应归咎为 Codex 单方面偷工减料；目前也没有证据证明实际产物已经损坏。单独的回执仍可能执行了自己的哈希检查。问题在于统一工具存在盲区。

纠正：保留原研究包，改执行版。无论总状态如何，都检查已声明产物和已完成步骤；尚未执行的内容保持 incomplete。分别输出完整性、技术门槛和独立接纳。增加 blocked/running/failed 场景下的损坏文件、缺失文件、错误基线、事件断链测试。不能靠提前标 passed 来触发审计，更不能取消人工门槛。

### F03：跨环境 .pth 复用不满足正式专业部署资格（高优先级）

run008 scientific 回执明确写 `read-only .pth references to existing environments; no dependency install`，并承认依赖本机环境、不可移植；run009 仍标 `local dependency reuse; not portable`。原任务书禁止靠注入源码/site-packages/PYTHONPATH 补足候选环境。已检查记录中没有看到将该方式纳入正式用户部署契约的批准。[R09、R14、R15]

`-I` 隐含 -E/-P/-s，不等于 -S；site 仍可处理解释器环境内的 .pth。所以 `-I` 与 prepare 自身来自新环境，不能单独证明所有后端都来自完整隔离环境。[R16、R17]

纠正：保留本机数值和集成通过记录，但把它们与 clean/user-install/deployment 门槛分开。使用已有、获准、自身依赖完整的专业环境和固定 wheel。需要未授权安装/更新时阻塞相关部署门槛，列出最小授权需求，继续 Standard/Viewer 案例；不扩大环境注入，也不把科学通过全部抹掉。

### F04：混合执行批准未落到验收规格（中高优先级）

计划允许已验证 UI 使用 MCP。T01 spec 的 s01–s07 却全部要求真实 GUI，执行检查器仅接纳 os_gui/human_gui，也没有历史 GUI 基线→当前差异→公开重放的适用性模型。正文诚实地说截图展示重放结果，但机器门槛仍未衔接。[R04、R13、R18、R19]

纠正：用最小的版本化执行补充规则表达批准范围，冻结旧证据与旧规格。每个复用步骤关联历史真实 GUI、原制品、授权、当前 UI/代码差异和当前语义重放。新/变更/从未验证的操作仍必须真实 GUI。不能将所有 MCP 写成 GUI Passed，也不能仅为过检删除 required_steps。

### F05：当前用户正文混入多代审核历史（中高优先级）

首课和乙醇正文仍绑定 bb436e22/3f1d93ac。T06 顶部是 a1e2da79/b736bc61 的 run-009，后面的前提又出现旧 963b905f，并叠加旧图、旧节点方式和旧恢复说明。它已提示历史边界，不能据此称为造假；但普通用户仍要自己选择哪部分适用于手中制品。[R19–R21]

T06 的当前平滑节点由 MCP 搭建，正文也明确手动搭建尚未验证；细分/平滑在 Rebuild 后丢失。这些不是必须扩大产品架构的理由，但必须成为可照做步骤或合法工程中的现成内容，不能只靠“知道内部脚本的人”重现。[R08、R21]

纠正：正文只保留一套当前路线；旧图与失败历史进验证附录，原哈希不改。更新目录、示例命令、配套工程入口与中英文版本。开发缓存绝对路径不作为普通用户安装前提。未发布时提供本地交接包与包内相对路径，不虚构公开下载。

### F06：反复重验与润色存在拖延收口风险（执行策略建议）

多轮 run 由真实缺陷和新制品触发，不能一概称为浪费。但现在 8 个 P0 均有实操，而首课/乙醇的当前候选门槛和状态归一尚未关闭；自定义外观、渲染、重建、再冷开反复追加。若继续缺少明确变更影响表与案例关闭条件，容易让“增加证据”替代“交付一课”。[R03–R05、R08]

纠正：冻结当前候选及组件级影响范围。改变科学解释、GUI、缓存/生命周期时重跑对应项；文档或相机变化不自动触发所有计算重跑。任何复用都须符合批准的规则与明确适用性，不能给旧截图换哈希。每次推进一个案例到技术/文档 ready-for-human-review 或明确阻塞，人工等待独立排队。继续 P0→P1→P2，而非因整改永久取消高级案例。

## 对当前总目标的评价

用户提供的总目标保留了全部案例、真实执行、双语交付、依赖权限、串行 Blender 和人工门槛，方向正确，不建议删除任何核心要求。需要增加一个优先整改阶段，先修复 F01–F04，并把“重复修复 T02”改成“核查既有修复及当前候选复验”。

技术可复做与人工最终接纳是不同状态。等人工不等于 agent 可以自行签字，也不等于所有其他案例必须停工；把两者分开可避免既不关闭又反复执行同一步的循环。

可直接执行的纠偏任务见同目录 `codex-correction-task.md`。该文件不授权安装新依赖、覆盖用户环境或远端发布。

## 来源索引

除 Python 官方文档外，下列文件均在固定提交 `c1fa7584f56d6df387617406958065573e9b56c1` 读取。引用是已提交证据，不替代本机原始产物审计。

- R01：GitHub commits API，feat/2.5-real-user-tutorials 最新提交查询；两次同为 c1fa7584。
- R02：`examples/tutorials/2.5.0/README.md`。
- R03：`examples/tutorials/2.5.0/status.json`。
- R04：`.planning/2026-09-10-2.5-real-user-tutorials/task_plan.md`。
- R05：`.agents/active/2.5-real-user-tutorials.md`，开头及 115–310 行分段核查。
- R06：`examples/tutorials/2.5.0/T07-run009-sampling-render-check.json`。
- R07：`examples/tutorials/2.5.0/T06-run009-animation-check.json`，环境与逐帧记录；结合 R05/R21 的完整序列说明。
- R08：`docs/user/zh-CN/aspirin-trajectory.md`。
- R09：`examples/tutorials/2.5.0/run009-candidate-check.json`，候选、GUI、完整测试及 skip 原因。
- R10：`AGENTS.md`。
- R11：提交 `23e46b5be7918452165367f8a322acc8c05f8c58` 的 diff。
- R12：R05 中 T04 源码修复、T18 Save As 缺陷/修复/安装态复验段落。
- R13：`examples/tutorials/2.5.0/validate_evidence.py`，特别是 `_audit()`、GUI_TYPES 与 required_steps 校验。
- R14：`examples/tutorials/2.5.0/run008-scientific-route-check.json`。
- R15：`docs/chemblender25-research/local-agent-task.md`；与本次环境中保留的原任务书对照阅读。
- R16：Python 3.12 官方 Command line and environment，`-I`、`-s`、`-S` 条目；`https://docs.python.org/3.12/using/cmdline.html`。
- R17：Python 3.12 官方 site 文档，自动导入与 .pth 路径配置；`https://docs.python.org/3.12/library/site.html`。
- R18：`examples/tutorials/2.5.0/T01.case-spec.json`。
- R19：`docs/user/zh-CN/first-aspirin.md`。
- R20：`docs/user/zh-CN/ethanol-conformers.md`。
- R21：R08；重点为 run-009 当前候选与后部旧候选前提/步骤并列。
