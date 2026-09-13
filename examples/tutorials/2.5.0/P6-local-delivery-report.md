# ChemBlender 2.5 真实用户教程本地交付报告

PLAN_ID: `2026-09-10-2.5-real-user-tutorials`

结论：所有当前工具可自动完成的本地科学处理、Viewer、恢复、教程、离线 QA、构建和测试工作均已完成；整体仍为 **Blocked**，因为当前环境不能产生真实鼠标/键盘 GUI 事件，且 Agent 不能代签独立人工复做。本报告不是 Release notes 或分发批准。

## 已完成

- Phase 1–3 完成；Phase 4 的 T00/T01/T02/T04/T07/T17 和所有 P0 自动化门槛完成。
- scientific、wavefunction、fermi、QCSchema 环境均为隔离安装；T03/T05/T08–T16/T19/T20 的科学结果、24 个 native render、22 个 `.blend/.cbq` 配对工程、无源冷重建均通过。
- T16 使用具备 MIT 许可记录的六文件输入；POTCAR、WAVECAR 和 pickle 未进入教程或离线包。T15 critic2 仅声明为 `development_reuse`。
- 全部 T00–T20/B01 均有中英教程路线。最终共享 review ZIP 为 47,045,777 bytes、336 个安全成员、22 个工程对和 24 个 render；工作 manifest 不含开发机绝对路径。
- 中英离线 HTML 各包含 55 张内嵌图片和一个真实 review ZIP 下载；Edge 在 DNS 被映射到 `0.0.0.0` 时完成两种语言的实际加载截图。
- Extension 原生 validate/build 通过。最终 wheel-free 109-member ZIP 为 2,831,887 bytes，SHA-256 `73fe2c248a7c1ad939018ce21a4ae44c52855abbdaff124af581bd34ffe469c8`；新 r25 profile 安装与冷 import 通过，且 109 个成员与此前已完成工程/恢复资格的 r15 候选逐字节一致。
- Prepare wheel/sdist 已本地冻结；未发布。最终工作树完整复测为 2,616 total：2,579 passed，37 skipped，0 failures，0 errors，耗时 220.592s。
- 首次全量测试暴露新增科学图片断言的路径口径错误（1 failure）；修复后公共文档测试 5/5 和全量套件均通过，失败历史保留在 `progress.md`。

## 仍未关闭

- T06 新只读逐帧标量行仍缺直接 GUI 截图/连续操作录制；T18 legacy migration/relink 仍缺直接 GUI 录制。
- T03/T05/T08–T16/T19/T20/B01 缺当前直接 GUI 事件与 conforming per-case run manifest。后台 Blender 验证没有被换标为 GUI。
- 22 个案例的 `human_review` 全部为 `not_run`；独立复做清单已经生成，但尚无第二位复做者签署。
- 因上述门槛，Phase 4–6、P6.12 和整体计划保持 `in_progress`/Blocked。

## 当前证据入口

- 执行清单：`.planning/2026-09-10-2.5-real-user-tutorials/task_plan.md`
- 逐案状态：`examples/tutorials/2.5.0/status.json`
- 全量测试：`examples/tutorials/2.5.0/P6-full-test-check.json`
- 检查器与离线门槛：`examples/tutorials/2.5.0/P6-offline-gate-summary.json`
- 教程完整性：`examples/tutorials/2.5.0/P6-tutorial-completeness-audit.json`
- 制品冻结：`examples/tutorials/2.5.0/P6-final-artifact-freeze-audit.json`
- Extension 资格：`examples/tutorials/2.5.0/P6-current-extension-qualification.json`
- portable review ZIP：`docs/offline/artifacts/scientific-viewer-review.zip`
- 独立人工清单：`examples/tutorials/2.5.0/independent-human-review-checklists.md`

## 外部写入边界

未执行：`git push`、tag、GitHub Release、PyPI、远端 CI 或 remote 修改。它们不属于本地完成范围。只有具备 OS GUI 输入能力的复做者补齐直接 GUI 证据、生成合规 manifest，并由独立复做者签署后，才能继续勾选剩余验收项。
