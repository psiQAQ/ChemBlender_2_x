# 人工插件使用体验检阅

`UX-GATE` 是版本无关的发布前人工检查。它放在本地 installed-product 验证之后、创建 tag 或授权 Release 之前，检查用户能否按[工作流中心](../README.md)和同一组 Agent/Blender MCP 提示词完成任务。

当前代表样例的自动准备记录见 [`local-2.4.0-representative-corpus.md`](local-2.4.0-representative-corpus.md)。其中人工 UI 与 Agent/MCP 均为 `Not Run`，所以它是待执行清单，不是 2.4.0 的补发或 Passed 证明。

每个候选版本从 [template.md](template.md) 复制一份 `reviews/<version>.md`，例如 `reviews/2.5.0-rc.1.md`。结果文件必须随候选代码一起提交。这里不预先创建 2.4.0 或未来版本的“Passed”记录；只有实际执行后的证据才能填写。

## 门禁规则

- 每个 required case 都要有环境、UI result、Agent/MCP result、Duration、Evidence、Findings、Fix commit 和 Rerun result。
- 尚未执行的人工 UI 或 Agent/MCP 路径写 `Not Run`；对应 case 的最终状态仍是 `Incomplete`，继续阻止发布。
- required case 的最终状态只能是 `Passed`、`Failed`、`Blocked` 或 `Incomplete`。
- 任一 required case 为 `Incomplete`、`Failed` 或 `Blocked` 时，阻止 tag/Release。
- 修复问题后，在同一版本记录中保留原 finding、fix commit 和重跑证据；不要删除失败历史。
- 自动 runner 的 JSON 报告必须附在证据中，但它不能替代人工 UI 观察、可发现性、文案理解和恢复路径检查。
- `OUTSIDE` 必须证明材质、灯光、相机、collection 和 render 操作仍被清楚标为插件外能力。它不判定 scientific correctness。

## Required cases

| ID | 范围 | 必须验证的结果 |
| --- | --- | --- |
| `ENV` | Environment / install | Blender 5.1+、exact executable/Python、Extension repository、enabled key、RDKit/Gemmi、register/reload 状态 |
| `IMP` | Import | 单/多文件、SMILES、Preview、diagnostics、取消与依赖失败路径 |
| `DATA` | Process | scientific edit、topology、crystal/selective dynamics、biological hierarchy 和 revision validity |
| `VIEW` | Visualize | Structure、Volume、Signed Surface、property/trajectory/MODEL、cache reconstruction |
| `EXP` | Export | selection closure、loss preview/confirmation、取消、semantic re-import |
| `LIFE` | Lifecycle | `.blend`/`.cbq` save、cold reopen、Verify/Relink、revision prompt |
| `MIG` | Migration | legacy preview、explicit confirmation、backup、save/reopen |
| `AGENT` | Agent/MCP | live Operator RNA、public Operator、UI-visible verification、failure stop 和 crash recovery |
| `OUTSIDE` | Scope boundary | 通用 `bpy` 案例能完成场景呈现，但没有被写成 ChemBlender scientific capability |
| `REP-MOLECULAR` | Representative molecular | 8 种分子/exchange 输入的 Preview、实体、默认 View 与保存项目 |
| `REP-TRAJECTORY` | Representative trajectory | 32×21 extXYZ 属性、公开 playback、坐标变化与保存项目 |
| `REP-BIOLOGICAL` | Representative biological | 1D3Z MODEL、APBS PQR hierarchy/charge/radius、选择与播放 |
| `REP-CRYSTAL` | Representative crystal | COD CIF、diamond POSCAR/CONTCAR、周期 View 与可选 spglib 提示 |
| `REP-GRID` | Representative Grid3D | `64³` density 语义确认、Volume、signed Surface、VDB 与重开 |

## 执行顺序

1. 完成本地 unit、validate/build、isolated install 和真实 `user_default` install gate。
2. 从待发布的同一 ZIP 新建测试 profile，记录 package SHA-256 和 source Git commit。
3. 复制 template 为 `reviews/<version>.md`，按 `ENV` 到 `OUTSIDE` 顺序执行。
4. 人工 UI 与 Agent/MCP 使用同一份[不可变输入 manifest](../../../../examples/user-workflows/manifest.json)。输出只写到新的、清楚标记的目录。
5. 有 finding 时先最小复现、修复、测试，再从该 case 的干净前置状态重跑。需要冷重开的 case 必须真正退出并重新启动 Blender 5.1。
6. 检查代表性 `.blend`、`.cbq` 和 export 的大小、SHA-256、外部引用及 Reopen state。单文件目标小于 50 MiB，绝对不得超过 100 MiB。
7. 全部 required case 为 Passed 后，提交记录并继续 tag/Release 流程。

## 什么算证据

可接受证据包括截图或短录屏、Blender/MCP 控制台片段、runner JSON、导出文件 hash、Project Browser/Diagnostics 导出、`.blend`/`.cbq` 冷重开记录。每条证据要能对应具体 case 和步骤；只有 `FINISHED`、文件存在、监听端口或 manifest parse 不能单独判定 Passed。

发现问题时按[工作流文档](../README.md)复现。问题属于插件缺陷时，应先留下 RED，再修复并记录 fix commit；属于文档、样例或环境时也要写清分类，不能把它们记成插件 Passed。

## Agent 模拟用户记录

- [2026-09-07 双路径体验报告](2026-09-07-agent-experience-review.md)：14 项明细、失败与修复链、同包最终复验和原始安装阻断状态。
- [2026-09-08 实际用户安装恢复](2026-09-08-user-install-recovery.md)：后续授权后，实际 user_default 安装、完整 smoke、冷启动及 MCP 均 Passed；补充前一报告的安装阻断，不改写历史人工验收。
