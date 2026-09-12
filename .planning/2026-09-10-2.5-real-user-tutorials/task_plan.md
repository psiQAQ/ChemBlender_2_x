# ChemBlender 2.5 真实用户教程纠偏与全量验收计划

PLAN_ID: `2026-09-10-2.5-real-user-tutorials`

Goal: 完成 T00–T20/B01 的真实用户教程纠偏、技术验收、独立人工验收和本地交付。

Success Criteria: 每项操作、验证和证据路径写入 `progress.md` 后才勾选；人工独立验收只由独立复做者签署；所有技术门槛通过且没有 failure/error。

Constraints: 不安装或升级依赖；不删除或换标历史证据；不 push、tag、Release 或发布 PyPI；同时最多一个 Agent-owned Blender 进程；保持 `docs/chemblender25-research/` 字节不变。

Verification: 逐案证据检查器、状态一致性测试、文档与离线 QA、Extension validate/build、隔离与真实 profile、全量测试、`git diff --check`、planning `check-complete.ps1`。

## Control

- Current Phase: Phase 5 — 逐个实施 P1/P2 案例；Phase 3/4 的明确 Blocked 项并行保留
- Next Step: P5.3–P5.11 的未完成门槛保持 Blocked；继续 P5.12 T20 QCSchema 真实 compute 边界
- Checklist rule: 只有操作、验证和证据路径均写入 `progress.md` 后才能标记 `[x]`。
- Blocked rule: 失败或缺少授权的项目保持 `[ ]`，并在 `progress.md` 记录 `Blocked` 及原因。
- Human rule: Agent 不得代签 `human_review`。
- Commit rule: 每个阶段形成一个本地逻辑 commit；Phase 5 每个完成案例形成独立逻辑 commit。

## Interfaces

- `task_plan.md`：唯一执行清单，只保留阶段、状态、复选项和当前下一步。
- `progress.md`：追加命令、结果、错误、证据路径和 commit。
- `findings.md`：只保存稳定结论、限制和可复用发现。
- `.agents/active/2.5-real-user-tutorials.md`：只保留当前候选、当前案例、进程、阻塞和下一步。
- `status.json`：逐案汇总 scientific processing、直接 GUI、授权重放、render、recovery、tutorial、review package、human review、distribution 和证据引用。
- `validate_evidence.py`：保留现有 CLI/退出码，增加可选 `--execution-supplement` 和四类分离状态字段。

### Phase 1 — 统一计划与当前事实

**Status:** complete

- [x] P1.1 固定 `PLAN_ID`，记录当前分支、HEAD、工作区、Blender/Prepare 进程和候选制品哈希。
- [x] P1.2 逐项核对 T00–T20/B01 的 receipt、run manifest、本地产物和适用候选；聊天记录不能单独作为通过依据。
- [x] P1.3 把 `task_plan.md` 与 active 文件中的唯一历史记录补入 `progress.md`，随后缩短二者，确保无证据丢失。
- [x] P1.4 将本计划写入 `task_plan.md`，增加 `Current Phase`、`Next Step` 和本 checklist。
- [x] P1.5 更新 `status.json`：T07 指向 run-009；T17/T18 不再写 `not_run`；T01/T02 明确历史候选与当前候选的适用范围。
- [x] P1.6 更新教程 README，移除 run-002 作为当前入口，改为当前状态、当前 receipt 和 review-only 边界。
- [x] P1.7 纳入审查目录的两份文档，保持 `docs/chemblender25-research/` 字节不变。
- [x] P1.8 增加状态一致性测试：有已接纳 receipt 的案例不能无解释地汇总为 `not_run`，人工、技术和分发状态不能互相代证。
- [x] P1.9 运行状态/文档测试、`git diff --check`，提交“统一教程计划与当前事实”。

### Phase 2 — 修复证据检查与 GUI/MCP 复用规则

**Status:** complete

- [x] P2.1 先增加失败测试，证明 blocked/running/failed manifest 中的损坏、缺失、路径逃逸、错误哈希和事件断链目前会被提前返回漏掉。
- [x] P2.2 删除 `_audit()` 的未通过状态提前返回；无论总体状态如何，都审计已经声明的 baseline、artifact、event、step、check 和 lifecycle。
- [x] P2.3 未执行项目不要求伪造文件；已声明文件必须通过完整性审计。完整性通过但门槛未完成时返回 `incomplete`。
- [x] P2.4 增加四类分离状态字段；`invalid` 只表示证据完整性或结构错误，不能被 `status=blocked` 掩盖。
- [x] P2.5 增加合法未完成、缺失 GUI、缺失科学检查、缺失人工审阅、错误候选哈希、历史截图换标等回归测试。
- [x] P2.6 定义并测试 execution supplement v1；直接 GUI 仍使用 `os_gui/human_gui`，授权 MCP 重放使用单独类型和完整复用链。
- [x] P2.7 为 T01 建立首个补充规格；新面板、变化按钮和未验证步骤继续要求真实 GUI。
- [x] P2.8 用真实 T01/T02 blocked manifest 验证：损坏证据会失败，完整但未人工验收仍为 incomplete。
- [x] P2.9 运行证据测试、相关文档测试和 `git diff --check`，提交“审计未完成运行并记录授权重放”。

### Phase 3 — 专业环境资格分层

**Status:** complete

- [x] P3.1 重新记录 Standard、scientific、wavefunction、fermi 环境的解释器、依赖版本、实际 import origin、prepare wheel 和 route 配置。
- [x] P3.2 将环境状态明确分为 `development_reuse`、`isolated_install`、`distribution_ready`；`.pth` 跨环境引用只能是第一类。
- [x] P3.3 对 run008/run009 receipt 保留数值与集成结果，但删除或纠正任何“可移交隔离环境”暗示。
- [x] P3.4 使用现有且已授权、依赖自足的环境重放可用专业路线；不新增 `.pth`、`PYTHONPATH` 或源码注入。当前唯一符合条件的 critic2 路线已用 run-009 Standard + 既有 WSL ELF 重放；其余路线按 P3.5 保持 Blocked。
- [x] P3.5 缺少依赖的专业路线标记 `Blocked: dependency authorization required`，列出最小安装需求，同时继续 Standard/Viewer 项目。
- [x] P3.6 更新状态、环境说明和部署边界测试，运行 `git diff --check`，提交“区分开发复用与部署资格”。

### Phase 4 — 按顺序关闭全部 P0 案例

**Status:** in_progress

每个案例只有在当前候选身份、输入/许可、科学检查、直接 GUI 或合规授权重放、渲染、配对工程、移动/冷重开/恢复、中英教程、离线 QA、review package 和检查器结果均有证据时，才能勾选技术完成；人工验收单列。

- [x] P4.1 T00：核对当前候选安装、Test Processor、doctor/capabilities、失败恢复和教程入口。
- [x] P4.2 T01：完成当前候选适用性、execution supplement、剩余缓存恢复、正文单一路线和 review package。
- [x] P4.3 T02：复用已验证产品修复，补当前候选适用性与缓存恢复；无新失败不重复改产品。
- [x] P4.4 T04：补可读侧栏截图、准确手动步骤和当前候选映射；保留 CIF/POSCAR/ASE、渲染、移动与重建证据。
- [ ] P4.5 T06：补帧 0/15/31 的 energy/source index 可见检查、实际 UI 录制、手动渲染/节点步骤和完整恢复。Blocked：新标量行属于新面板，仍需真实 GUI 截图；当前会话无 OS GUI 操作工具。
- [x] P4.6 若现有 UI 无法显示 T06 冻结规格要求的逐帧标量，复用现有 FrameProperty 数据，在现有面板增加最小只读当前帧值，不增加新数据模型；补单元测试、构建和受影响案例复验。
- [x] P4.7 T07：补 sampling-layout 冷重开、volume/remaining render、当前候选 GUI、真实缺源/缺处理器恢复、VASP 适用范围和 review package。
- [x] P4.8 T17：核对 13 格式正向导出、loss gate、科学字段比较、GUI 回执、项目交接和当前候选回归；保留正确拒绝案例。
- [ ] P4.9 T18：在隔离副本上用不存在的 processor 路径和移除的副本源文件实际证明离线重建；补 GUI legacy migration、第二干净 profile、取消/错误 relink/损坏/过期恢复。Blocked：自动恢复、故障拒绝和 legacy 原生迁移已通过；当前无 OS GUI 工具，且用户自有 Blender PID 26228 在运行，不能启动第二 profile。
- [x] P4.10 对 T00/T01/T02/T04/T06/T07/T17/T18 分别运行检查器并更新状态为 `ready_for_human_review` 或明确 `Blocked`。
- [x] P4.11 运行 P0 聚合测试、Extension validate/build、当前候选安装检查和 `git diff --check`，提交 Phase 4 P0 资格证据（未关闭的门槛保持 Blocked）。

### Phase 5 — 逐个实施 P1/P2 案例

**Status:** in_progress

每个案例依次执行：冻结 case spec → 固定输入/许可/哈希 → CLI/Worker → Prepare GUI → Blender View → 独立科学断言 → render → save/move/cold/rebuild/recovery → 中英教程和离线 QA → review package → 状态更新。

- [ ] P5.1 T03：SMILES 三维化、力场优化、SDF 记录与构象分组。Blocked：复用了 T02 的哈希关联 SMILES/MMFF94 适用性；Standard SDF 分组、导出、负例和取消已通过，但缺 Prepare GUI、Blender render/lifecycle、教程包和人工验收。
- [ ] P5.2 T05：PDB 多模型、PQR 电荷/半径和 MOL2 层级展示。Blocked：Standard PDB/PQR/MOL2 转换、科学比对、负例、validation 和取消已通过，但缺 Prepare GUI、Blender Views/render/lifecycle、教程包和人工验收。
- [ ] P5.3 T08：真实 FCHK/Molden 轨道正负相位。Blocked：当前 Standard 的 wavefunction route 未配置；现有 IOData/GBasis cache 含 8 个非当前 Prepare/Core 文件且未配置 route，需授权安装冻结 wheel 后才能执行。
- [ ] P5.4 T09：电子密度、自旋密度和 RDM 网格，严格区分来源与密度层级。Blocked：复用 T08 的 current-candidate wavefunction 环境阻塞；输入与密度层级边界已冻结，未运行科学处理。
- [ ] P5.5 T10：同结构同网格的密度表面 ESP 着色。Blocked：复用 T08 的 current-candidate wavefunction 环境阻塞；同计算/同结构/同网格边界已冻结，未生成 density/ESP grid。
- [ ] P5.6 T11：Gaussian/ORCA 振动、IR/Raman 和模式动画。Blocked：输入与科学边界已冻结；scientific route 依赖跨环境 `.pth`，未在隔离环境运行。
- [ ] P5.7 T12：TD 输出、UV–Vis/ECD 图与 gauge/强度边界。Blocked：输入与 gauge/强度边界已冻结；scientific route 依赖跨环境 `.pth`，未在隔离环境运行。
- [ ] P5.8 T13：能带、DOS、投影和能量参考。Blocked：band/DOS 独立计算及能量参考边界已冻结；scientific route 依赖跨环境 `.pth`，未在隔离环境运行。
- [ ] P5.9 T14：NaCl q 点声子模式与周期相位动画。Blocked：NaCl 六文件输入与相位边界已冻结；scientific route 依赖跨环境 `.pth`，未在隔离环境运行。
- [ ] P5.10 T15：critic2 QTAIM/NCI；不虚构缺失路径或键能。Blocked：当前 Standard CLI/Worker + 既有 critic2 1.3.15 已生成并验证 5 CP/4 有序路径与配对 40³ NCI 网格，取消及错误 Structure 绑定不发布输出；仍缺 Prepare GUI、Blender View/render/lifecycle、教程/review package 和人工验收，critic2 路线仅为 `development_reuse`。
- [ ] P5.11 T19：Reader API 外部 Python 集成；不承诺自动进入普通导入界面。Blocked：当前 Standard 外部 Python 显式注册/discovery/unregister、conformance、非法输入拒绝、CBQ 发布/validate/注销后重开均通过；普通 CLI/Tk GUI 仍仅有 22 个内置 reader。缺 Viewer GUI/render/lifecycle、教程/review package 和人工验收。
- [ ] P5.12 T20：QCSchema 真实 compute；交换成功不能替代实际计算成功。
- [ ] P5.13 T16：Fermi surface；许可未关闭前不分发 POTCAR、pickle 或不合规输入。
- [ ] P5.14 B01：验证 provider unavailable 的真实诊断边界；没有 live transport 时不伪造在线成功。
- [ ] P5.15 每完成一个案例立即更新 checklist、`status.json`、教程索引和 `progress.md`，并作独立逻辑 commit。
- [ ] P5.16 所有未获依赖或许可授权的项目保持未勾选并记录阻塞，不用 skip 冒充通过。

### Phase 6 — 教程收口、人工验收与本地交付

**Status:** pending

- [ ] P6.1 T01/T02/T06 等正文仅保留一套当前用户流程；旧候选、失败调试、PID 和长哈希移入验证附录。
- [ ] P6.2 所有教程包含固定输入、准确按钮/参数、逐步可见结果、原始截图、最终渲染、工程入口、恢复步骤和科学边界。
- [ ] P6.3 本地交接包只使用包内相对路径；开发缓存绝对路径只出现在验证附录。
- [ ] P6.4 重新生成中英离线 HTML，实际断网检查图片、锚点、语言导航、输入、脚本、工程和 receipt 下载。
- [ ] P6.5 为每个案例生成独立人工复做清单；第二干净 profile 按教程盲走并记录操作、结果、缺陷、修复和复测。
- [ ] P6.6 只有独立复做者签署后，勾选对应 `human_review`；否则保持 `ready_for_human_review`。
- [ ] P6.7 冻结最终本地 Extension ZIP 与 prepare wheel/sdist，记录源码提交、SHA-256、内容清单和依赖来源。
- [ ] P6.8 运行全量测试并分别报告 Passed/Failed/Skipped/Error；任何 failure 或 error 都阻止技术完成。
- [ ] P6.9 执行 Extension validate/build、ZIP 内容审计、隔离 profile 安装、真实 `user_default` 冷启动、无 RDKit/Gemmi/prepare Viewer 验证和专业后端验证。
- [ ] P6.10 运行所有案例检查器、状态一致性测试、文档测试、离线 QA、`git diff --check` 和 planning `check-complete.ps1`。
- [ ] P6.11 更新 active/current status 和最终本地交付报告；明确远端 CI、push、Release、PyPI 均未获授权且不属于本地完成。
- [ ] P6.12 最终逻辑 commit 后，仅在所有阶段和人工门槛确实完成时把 M0–M5 与 Phase 1–6 标为 complete。

## Assumptions and Defaults

- 范围包含原总目标 T00–T20/B01，不仅是 F01–F06 纠偏。
- 实施起点和审查锚点均已复核为 `c1fa7584f56d6df387617406958065573e9b56c1`；后续候选适用性以 receipt 记录的源码与制品哈希为准。
- 缺失依赖只阻塞对应专业路线，Standard/Viewer 工作继续。
- 历史截图、失败日志、旧制品和原研究包保留，不删除、不换标。
- 优先复用现有代码、规格、测试和证据结构；只对确认的产品缺口做最小修复。
