# ChemBlender 2.4.0 Candidate Intake

## 结论

本轮不启动 `2.3.1`。选择 **2.4.0 Task 1 — Deterministic native
MOL2 export** 作为唯一后续任务，并保持 `not_started`，直到 Scope Discovery
checkpoint 完成且用户明确启动产品实现。

## Live feedback snapshot

2026-08-01 对 `psiQAQ/ChemBlender_2_x` 的 GitHub live query 得到：

- GitHub Issues: disabled；issue 总数为 0；
- GitHub Discussions: disabled；
- open Pull Requests: 0；open Milestones: 0；
- `v2.3.0` 于 `2026-08-01T07:16:07Z` 发布；查询时正式 ZIP 和 checksum
  下载数均为 0，Release 无 reaction；
- 发布后更新的 PR #6–#8 均为项目自身的 Wave 4、release preparation 和
  post-release checkpoint，不能当作外部用户反馈。

该快照说明当前未发现可复现的用户回归报告或证据，也说明正式版采用窗口仍过短；
“没有报告”不能被解释为稳定 API 的第三方采用证据。

## 2.3.0 known limits

`docs/quantum-visualization/2.3.0/usability-results-rc1.md` 记录 0 Blocker、
0 Major 和 3 Minor：

| ID | 观察 | 分类 |
| --- | --- | --- |
| M-01 | `mesh.py` 既有 invalid escape `SyntaxWarning` | 非功能 warning，不构成 2.3.1 门禁 |
| M-02 | 合成 SDF 的 RDKit 2D/nonzero-Z warning | 测试数据 warning，无数据损坏 |
| M-03 | Windows 已加载 Gemmi/RDKit DLL 的 profile cleanup warning | 进程 exit 0，fresh reinstall 通过 |

没有证据满足 Scope Discovery 规定的 2.3.1 条件：可复现回归、数据损坏、安装/
升级失败、安全问题或既有契约内兼容缺陷。因此版本分类保持 `2.4.0`。

## Capability and performance audit

`docs/user/format-capabilities.json` 当前包含 19 个 Reader：9 个 export F5、
1 个 F4、9 个 F0。无需额外依赖且仍为 F0 的内置格式是 Cube、MOL2、PDB 和
PQR；其中 MOL2、PDB、PQR 已有冻结的 export-readiness 契约，Cube 尚无等价
writer contract。

性能方面没有待修预算缺口：Wave 2 crystal、Wave 3 exchange 和 2.3.0 RC
reference 中记录的受控 benchmark 均通过各自预算。没有测量证据支持先做性能
重构、缓存层或新依赖。

Reader API 仍为 `1.0-rc1`。`docs/reader-api-v1/compatibility.md` 明确要求 stable
token 通过后续显式兼容门提升；当前没有第三方采用反馈，因此本轮不提前承诺
stable。

## Candidate comparison

| 候选 | 证据 | 最小结果 | 风险/限制 | 决策 |
| --- | --- | --- | --- | --- |
| Native MOL2 export | 内置 Reader 可导入但 export 为 F0；readiness 和 fixtures 已冻结 | dependency-free core writer、loss preview、semantic re-import | raw Tripos 细节不能假装无损；必须确认损失 | **选择** |
| Reader API v1 stable gate | 公开 token 仍为 `1.0-rc1` | stable compatibility decision | 无真实 adopter 证据，提升过早 | 暂缓 |
| Independent human usability gate | 2.3.0 验收没有独立参与者 | 首次使用和菜单发现证据 | 依赖外部参与者，本地工程任务无法闭环 | 暂缓 |

PDB/PQR export 与 MOL2 同为真实缺口，但它们共享更大的 hierarchy、MODEL、
fixed-field 和 PQR dialect 风险。本轮只选择 MOL2，不把三个 exporter 捆绑成一个
主题。

## Selected Task 1 boundary

后续 Task 1 新增纯 core `export_mol2(project_entities, ...)`，复用现有
`mol2_export_readiness`、`MolecularExport`、`ExportReport` 和原子写入/
cancellation 机制。输出使用确定性记录顺序、规范化 atom/bond/substructure
编号、locale-independent finite numeric formatting，并通过 native `parse_mol2`
做 semantic re-import。

readiness 为 `Unsupported` 时 fail closed；`Partial` 或 raw-only 信息会丢失时，
先返回明确 loss preview，只有 `confirm_loss=True` 才允许写入。Task 1 不宣称
byte-identical 或无损 Tripos round-trip。

Task 1 明确不包含：

- Blender export UI 或 registration；
- PDB/PQR/Cube exporter；
- 新科学模型、第三方依赖或 Reader API token 变更；
- manifest version、CHANGELOG、tag、Release 或远端操作。

实施步骤见
`docs/superpowers/plans/2026-08-01-chemblender-2.4.0-mol2-export.md`。
