# ChemBlender 2.5 真实用户教程本地交付报告

PLAN_ID: `2026-09-10-2.5-real-user-tutorials`

结论：本地实施形成了可审计的计划、状态、检查器、阶段证据和逻辑提交，但当前结果为 **Blocked**，不具备最终用户验收或分发条件。本报告记录截至 `abfebd36125e669e4164ceb1316d058915b0ab9f` 的状态；它不是 Release notes，也不是发布批准。

## 已完成

- Phase 1–3 完成：统一计划和当前事实、修复未完成证据审计、区分开发复用/隔离安装/分发资格。
- Phase 4/5 已按案例保存当前候选验证或明确阻塞；未把缺依赖、缺 GUI、缺许可、缺人工验收或负向能力边界改写成通过。
- T01/T02/T06 主教程只保留一条用户路线；全部 22 个案例均有独立、未签署的人工复做清单。
- 在 `c950757` 源状态运行的完整仓库测试：2,603 total，2,566 passed，37 skipped，0 failures，0 errors；后续交付状态/测试收据变更另以定点测试复验。
- 现存 5 个 run manifest 全部执行检查器；状态、文档生成、离线静态资源、`git diff --check` 和 planning 检查均已运行。
- `docs/chemblender25-research/` 相对审查锚点 `c1fa758` 无改动。

## 未关闭门槛

- Phase 4、Phase 5、Phase 6 仍为 `in_progress`。T06 新只读标量行缺真实 GUI 证据；T18 缺第二干净 profile 和完整 GUI 恢复复做。
- 14 个案例没有中英双语案例章节；已有教程也仍缺部分 GUI、render、recovery 或独立人工证据。
- T01/T02 检查器为 `incomplete`；T06 manifest 为 `invalid`；其余 19 个案例没有合规 run manifest。
- 离线 HTML 的静态资源、锚点和下载链接有效，但没有 `.blend`、`.cbq` 或 review ZIP 工程下载。
- scientific、wavefunction、fermi、QCSchema compute 路线需要依赖/配置授权；T16 输入许可未关闭；B01 无 live provider transport。
- 22 个案例的 `human_review` 全部为 `not_run`，Agent 未代签。
- 当前源码 Extension 已重新 validate/build：ZIP SHA-256 `20ae86e47d317884fb1e15b7ddfd7d6ccc07f6a256e2562d1c16df8e66e1aa1e`。第二干净 profile 的安装、独立冷进程、工程配对/重建和无科学依赖 Viewer 均通过；真实 `user_default` 冷启动及 109 个安装文件逐字节比对也通过。直接 GUI 与人工复做仍未因此升级。

## 当前证据入口

- 执行清单：`.planning/2026-09-10-2.5-real-user-tutorials/task_plan.md`
- 逐案状态：`examples/tutorials/2.5.0/status.json`
- 全量测试：`examples/tutorials/2.5.0/P6-full-test-check.json`
- 案例检查器与离线门槛：`examples/tutorials/2.5.0/P6-offline-gate-summary.json`
- 教程完整性：`examples/tutorials/2.5.0/P6-tutorial-completeness-audit.json`
- 制品冻结审计：`examples/tutorials/2.5.0/P6-final-artifact-freeze-audit.json`
- 当前 Extension 资格：`examples/tutorials/2.5.0/P6-current-extension-qualification.json`
- 独立人工清单：`examples/tutorials/2.5.0/independent-human-review-checklists.md`

## 外部写入边界

本轮未执行且未授权：`git push`、tag、GitHub Release、PyPI 发布、远端 CI 触发或修改。`origin/feat/2.5-real-user-tutorials` 仍停在 `c1fa758`；本地分支在本报告评估点领先 23 个提交。完成上述 Blocked 项并由独立复做者签署前，不得把 Phase 4–6、P6.12 或整体计划标记为 complete。
