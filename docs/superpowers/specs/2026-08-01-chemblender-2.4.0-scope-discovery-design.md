# ChemBlender 2.4.0 Scope Discovery Design

## 目标

在 ChemBlender 2.3.0 已完成发布且当前没有开放缺陷的前提下，建立下一版本的证据收集、候选需求分流、优先级和激活边界。该阶段只形成可恢复的规划入口，不实现产品功能，也不预先承诺不存在真实需求支撑的 Wave 5。

## 已确认基线

- 权威维护线为 `origin/main@224155fa6986a4a51deaae3f9cf3d5f87ea0941a`。
- `v2.3.0` 已发布，最终发布与 post-release checkpoint 证据位于 `.agents/completed/`。
- `.agents/active/` 和 `.agents/queued/` 在权威 `main` 上均为空。
- GitHub 当前没有开放 Issue、Pull Request 或 Milestone。
- `docs/quantum-visualization/roadmap.md` 中 Phase 0–4 均已完成。
- 当前没有证据证明需要立即创建 `2.3.1` 修复版本。

这些事实是本阶段的输入快照，不是长期不变的结论。每次恢复任务时必须重新获取 Git 与 GitHub 状态。

## 版本边界

默认规划目标为 `2.4.0 Scope Discovery`，原因是当前没有已知的 2.3.0 回归，而下一步需要先收敛产品目标和工作范围。

仅在出现下列任一证据时切换到 `2.3.1`：

- 2.3.0 的可复现功能回归；
- 数据损坏、安装、升级或安全问题；
- 现有 2.3.0 契约内必须修复的兼容性问题。

缺少上述证据时，不创建空的 `2.3.1` maintenance 分支、版本提交或 Release 计划。新能力、模型扩展、格式扩展和平台扩展属于 `2.4.0` 候选范围，但只有通过本阶段的证据与优先级门禁后才能进入实施计划。

## 范围

本阶段只建立四项规划资产：

1. 本设计规格；
2. 一份可逐项执行的 `2.4.0 Scope Discovery` implementation plan；
3. `.agents/active/2.4.0-scope-discovery.md` 唯一 Execution Cursor；
4. 对应的文档契约测试。

Execution Cursor 使用 Goal ID `CB240-SCOPE-DISCOVERY`，状态为 `in_progress`，首项任务为 `Evidence-backed candidate intake`。它记录当前基线、版本分流规则、允许修改范围、恢复规则、验证要求和停止边界。

## 非目标

- 不修改 `ChemBlender/` 或 `worker/` 产品代码。
- 不修改 `blender_manifest.toml`、`CHANGELOG.md`、tag 或 GitHub Release。
- 不创建功能 Wave、依赖升级、格式实现或 UI 实现。
- 不根据旧计划、聊天记录或主观偏好直接承诺 2.4.0 功能。
- 不创建 PR、不 push、不修改 remote。

## 候选需求数据流

候选项只能来自可追踪证据：

1. 2.3.0 用户反馈、Issue、复现报告或审查 finding；
2. 已记录的 release known limitation；
3. capability matrix 中明确且仍有用户价值的缺口；
4. 性能基线中可量化的预算缺口；
5. Reader API 或 sidecar 公共契约的真实采用反馈。

每个候选项至少记录：来源、用户结果、当前能力、缺口、影响范围、依赖、风险、最小验收证据和版本类别。没有来源或不可验证结果的候选项保留为未采纳想法，不进入 queued 或 active。

候选分流顺序固定为：

```text
证据收集
→ 2.3.0 回归检查
→ 2.3.1 / 2.4.0 分类
→ 用户价值和风险排序
→ 选择一个最小 Task 1
→ 写入后续 implementation plan
```

同一时间只激活一个主题。Scope Discovery 未完成前，不激活 2.4.0 产品实现。

## 失败与恢复

- 若发现 2.3.0 回归，停止 2.4.0 候选选择，记录复现与影响，转入独立的 `2.3.1` maintenance 设计流程。
- 若 Git、GitHub 或发布证据与快照不一致，更新事实后重新做版本分流，不沿用旧结论。
- 若没有达到优先级门禁的候选项，Scope Discovery 保持 `in_progress`，不得用占位功能制造 Task 1。
- 若出现多个互不依赖且同优先级的候选项，先由用户选择产品目标；不并行激活多个主题。
- 上下文压缩或新会话后，按 `AGENTS.md`、`.agents/README.md`、active cursor、目标计划和 live state 的顺序恢复。

## Git 与隔离策略

- 本地 `main` 只允许 fast-forward 到权威 `origin/main`。
- 规划修改在 `docs/2.4.0-scope-discovery` 独立分支与 worktree 中完成。
- 一个完整逻辑阶段一个 commit：设计规格、实施计划与 cursor 分开提交。
- 禁止 rebase、force-push、tag 移动和 Release 重建。
- 本阶段只做本地提交；远端写入需要新的明确任务。

## 验证

- `tests.test_quantum_visualization_docs` 必须验证唯一 active 文件、规格和计划入口、恢复规则、版本分流和停止边界。
- 所有新增 Markdown 必须是 UTF-8 without BOM，本地链接必须可解析。
- 使用 Blender 5.1.2 bundled Python 运行文档契约测试。
- 运行 `git diff --check` 和 `git status --short`。
- 设计提交和最终规划提交后分别确认 worktree 状态。

不运行产品全量测试、Blender build 或运行时 smoke，因为本阶段不修改产品、构建或运行时契约；若实际 diff 超出文档和文档测试，则该豁免失效。

## 完成条件

当 implementation plan、唯一 active cursor 和文档契约测试均已提交并验证后，本 `POST-2.3.0-NEXT-RELEASE-PLANNING` 目标完成。此时 `CB240-SCOPE-DISCOVERY` 作为下一项可恢复任务保持 `in_progress`，产品实现仍未开始。
