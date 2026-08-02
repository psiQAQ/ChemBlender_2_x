# ChemBlender 2.4.0 Task 3 Candidate Intake

## 结论

选择 **Task 3 — Deterministic native PDB export** 作为唯一后续任务。它保持
`not_started`，直到本 Scope Discovery checkpoint 完成且用户明确启动实现。

本轮不实现 exporter，不激活 PQR/Cube，也不提升 Reader API token。

## Live evidence snapshot

2026-08-02 对 `psiQAQ/ChemBlender_2_x` 的现场复核结果：

- `main` 与 `origin/main` 的共同基线为
  `99548d8aff8bea162651273ff5d723e57be5279c`；
- MOL2 Export UI PR #10 已用普通 merge commit 合并；精确 feature head 为
  `819575f3210d9db92b33b2e5e11cc02590680564`；
- `extension-package` run `30708862898` 与 `optional-qc-core` run
  `30708862900` 均为 `success`，两者 `headSha` 都等于上述精确 feature head；
- merge commit 为 `99548d8aff8bea162651273ff5d723e57be5279c`，feature head 是其祖先；
- GitHub Issues 与 Discussions 均关闭，open PR 为 0；
- `v2.3.0` 发布资产查询时，ZIP 与 checksum 下载数均为 0；这不能解释为没有
  用户需求，也不能作为 Reader API 的第三方采用证据。

## Current capability facts

生成的 capability document 仍记录：

| 候选 | 当前 export | 已冻结的实现边界 |
| --- | --- | --- |
| Native PDB export | F0 / none | `pdb_export_readiness()`、固定列字段预算、PDB reader 与 6 组 fixtures |
| Native PQR export | F0 / none | `pqr_export_readiness()`、charge/radius 强制契约、PQR reader 与 4 组 fixtures |
| Native Cube export | F0 / none | Structure/Grid3D reader 与 product-flow 测试；无 writer/readiness contract |
| Reader API v1 stable gate | token `1.0-rc1` | public schema snapshot 与 conformance suite；stable promotion 明确留给兼容门 |

PDB 与 PQR 共用 readiness 模块只是代码组织事实，不是把两个 writer 捆绑实现的
理由。Cube 的 VDB 是 derived cache，不能替代科学 Grid3D exporter。

## Candidate comparison

| 候选 | 最小可交付结果 | 主要风险 | 决策 |
| --- | --- | --- | --- |
| Native PDB export | dependency-free deterministic core writer、loss preview、atomic cancellation、native semantic re-import | fixed columns、hierarchy、MODEL/altloc 与拓扑损失 | **选择** |
| Native PQR export | 单结构 whitespace writer、强制 charge/radius、semantic re-import | dialect 边界更窄，且无法承载 FrameSet | 暂缓 |
| Native Cube export | Structure + Grid3D writer 与多 dataset round-trip | writer/readiness、native-unit 和 dataset selection 尚未冻结 | 暂缓 |
| Reader API v1 stable gate | stable token 与 compatibility qualification | 没有外部 adopter 证据，兼容承诺过早 | 暂缓 |

## Selection rationale

Native PDB export 是当前四个候选中最小且证据最完整的纵向切片：

- 它是实际 F0 缺口，而 PDB import、hierarchy、multi-model、occupancy/B-factor
  和 fixed-column 解析已经存在；
- P1 readiness 已冻结关联、单位、shape、字段宽度、serial renumbering 与错误
  token；无需扩展科学模型或 sidecar schema；
- 6 组 fixtures 已覆盖 `ATOM/HETATM`、altloc、multi-model、`CONECT`、
  `CRYST1` 和 malformed 输入；
- 可复用现有 `ExportReport`、loss confirmation、atomic writer 与 native PDB
  parser 做 Semantic native re-import；
- 不需要 RDKit、Gemmi、ASE、Open Babel 或新依赖。

明确的延后理由：

- **PQR: deferred** — 强制 `partial_charge`/`radius` 且只允许单 Structure、无
  FrameSet；这是比 PDB 更窄的独立 dialect task，不与 PDB writer 捆绑。
- **Cube: deferred** — 尚无 writer/readiness contract；多 dataset 选择、原生单位
  与规范化输出必须先单独冻结。
- **Reader API stable: deferred** — compatibility 文档明确 stable token 需要显式
  gate；当前没有外部插件采用证据支持从 `1.0-rc1` 提升。

## Selected Task 3 boundary

Task 3 只新增纯 core `preview_pdb_export(project_entities)` 与
`export_pdb(project_entities, ...)`：

- 输出确定性的 fixed-column `ATOM`/`HETATM`，必要时输出 `MODEL`/`ENDMDL`，
  以 `END` 结束；
- 复用 source serial 或按 Structure atom order 确定性重编号；
- occupancy/B-factor 只按现有 readiness 允许的 complete/partial blank 语义输出；
- raw/source-only 内容、拓扑/`CONECT`、`CRYST1` 与其他未支持记录必须进入稳定
  loss preview，并在 `confirm_loss=True` 前阻止写入；
- destination 写入保持短 sibling temporary file、flush/fsync/replace/cancel 清理；
- 通过 native `parse_pdb()` 比较 Structure、hierarchy、frames 和已表达 properties，
  不比较 UUID、provenance 或原始空白。

Task 3 明确是 **No CONECT**、**No UI** 的 core slice。PDB Project Browser UI、
PQR、Cube、Reader API stable、模型/schema/依赖、版本和 Release 都不属于本任务。

实施步骤见
`docs/superpowers/plans/2026-08-02-chemblender-2.4.0-pdb-export.md`。
