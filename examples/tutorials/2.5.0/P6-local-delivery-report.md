# ChemBlender 2.5 真实用户教程本地交付报告

PLAN_ID: `2026-09-10-2.5-real-user-tutorials`

结论：当前环境已能产生并核验真实鼠标/键盘 GUI 事件，T06 新标量面板及 T18 legacy restore/relink 已直录；整体仍为 **Blocked**，因为 Phase 5 各案例的当前直接 GUI/conforming manifests 尚未全部完成，且 Agent 不能代签独立人工复做。本报告不是 Release notes 或分发批准。

## 已完成

- Phase 1–3 完成；Phase 4 已完成现状审计、P0 聚合测试、Extension build/install 与阻塞分类，但这不等于 P0 案例技术验收完成。
- scientific、wavefunction、fermi、QCSchema 环境均为隔离安装；T03/T05/T08–T16/T19/T20 的科学结果、24 个 native render、22 个 `.blend/.cbq` 配对工程、无源冷重建均通过。
- T16 使用具备 MIT 许可记录的六文件输入；POTCAR、WAVECAR 和 pickle 未进入教程或离线包。T15 critic2 仅声明为 `development_reuse`。
- 全部 T00–T20/B01 均有中英教程路线。最终共享 review ZIP 为 47,045,777 bytes、336 个安全成员、22 个工程对和 24 个 render；工作 manifest 不含开发机绝对路径。
- 中英离线 HTML 各包含 69 张内嵌图片和一个真实 review ZIP 下载；其中新增 3 张 T06 当前帧标量截图、4 张 T18 当前迁移/重链截图、4 张 T03 当前 SDF 分组/拒绝/Project Browser/F12 截图，以及 5 张 T05 当前 PDB/PQR/MOL2/F12 截图。此前 Edge 断网加载通过；本次资源图、锚点和下载完整性由生成器与离线测试复核。
- Extension 原生 validate/build 通过。最终 wheel-free 109-member ZIP 为 2,831,887 bytes，SHA-256 `73fe2c248a7c1ad939018ce21a4ae44c52855abbdaff124af581bd34ffe469c8`；新 r25 profile 安装与冷 import 通过，且 109 个成员与此前已完成工程/恢复资格的 r15 候选逐字节一致。
- Prepare wheel/sdist 已本地冻结；未发布。最终工作树完整复测为 2,617 total：2,580 passed，37 skipped，0 failures，0 errors，耗时 220.437s。
- 首次全量测试暴露新增科学图片断言的路径口径错误（1 failure）；修复后公共文档测试 5/5 和全量套件均通过，失败历史保留在 `progress.md`。
- T01 review ZIP v4 与 T02 current addendum v3 已绑定最终候选 execution supplement、current manifest、技术回执与当前可见状态截图；旧 ZIP 保留为历史证据，没有换标。T01 的失败控制台录屏仅保留在 `failures/`，未进入验收 artifact 列表。
- T06 当前候选侧栏已在 source frame 0/15/31 显示完整 Energy、Source Index、Step，三张可读截图和连续 Game Bar 操作录制均已按哈希保留；原工程以“不保存”退出，字节未改变。

## 仍未关闭

- P0 当前 checker 结论是：T01/T02 `integrity_status=passed`、`technical_status=passed`，但独立审阅未完成，所以总 verdict 仍为 `incomplete`；T06 历史 manifest `invalid`，T00/T04/T07/T17/T18 无 conforming manifest。完成审计并记录这些阻塞，不能替代案例技术验收。
- T18 当前候选 direct GUI legacy restore 与 missing/wrong/correct relink 已通过；仍缺 conforming run manifest 和独立人工复做。
- T03/T05 当前直接 Prepare/Blender GUI 与 conforming manifest 已通过技术门槛，进入 `ready_for_human_review`；相机恢复的 MCP 辅助与后台 lifecycle 均单独披露，没有换标为 GUI。T08–T16/T19/T20/B01 仍缺当前直接 GUI 事件与 conforming per-case run manifest。
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

未执行：`git push`、tag、GitHub Release、PyPI、远端 CI 或 remote 修改。它们不属于本地完成范围。剩余直接 GUI 证据与合规 manifest 将继续逐案补齐；只有独立复做者签署后才能勾选 `human_review`。
