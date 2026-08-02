# ChemBlender 2.4.0 Task 5 Candidate Intake

## 结论

选择 **Task 5 — Deterministic native PQR export** 作为唯一后续任务。它保持
`not_started`，直到本 Scope Discovery checkpoint 完成后被显式激活。

本轮不修改 runtime，不实现 PQR UI/Cube writer，也不提升 Reader API token。

## Live evidence snapshot

2026-08-02 对 `psiQAQ/ChemBlender_2_x` 的现场复核结果：

- PDB Export UI PR #12 已用普通 merge commit 合并；精确 feature head 为
  `5756532077d8aca8cebc54becf411133af7f96d8`；
- `extension-package` run `30728969782` 与 `optional-qc-core` run
  `30728969751` 均为 `success`，两者 `headSha` 都等于精确 feature head；
- merge commit 为 `d5028aa5d8568a44181b822293fbe62462d9a496`，feature
  head 是 `origin/main` 的祖先；
- `main` 与 `origin/main` 均为该 merge commit；open PR 为 0；repository
  Issues 与 Discussions 均未启用。

## Current capability facts

- PDB: F5 / project_browser / preview_confirmation。
- PQR: F0 / none；已有 dependency-free whitespace reader、四个 tracked
  fixtures，以及 `pqr_export_readiness()`；没有 `preview_pqr_export()`、
  `export_pqr()` 或 exporter module。
- Cube: F0 / none；已有 Structure/Grid3D import、multi-dataset reader 与
  derived VDB cache，但没有 writer/readiness contract。
- Reader API: 1.0-rc1；public snapshot、compatibility policy 与 conformance
  suite 已冻结，stable promotion 仍要求独立 compatibility gate。

PQR readiness 已经要求：

- exactly one Structure and one matching BiologicalHierarchy；
- complete finite `partial_charge` in `elementary_charge`；
- complete finite positive `radius` in `angstrom`；
- no FrameSet；
- valid hierarchy labels/indices and the 10-field no-chain or 11-field
  with-chain label/width budgets；
- deterministic `Ready` / `ReadyWithRenumbering` / fail-closed tokens。

当前 readiness 尚未证明 native reader 从 atom name、residue 与 record kind
推断出的 element 与 Structure atomic number 相同。该缺口不需要新模型，但必须
作为 PQR writer Task 2 的显式 RED，在 publication 前 fail closed。

## Candidate comparison

| 候选 | 最小可交付结果 | 主要风险 | 决策 |
| --- | --- | --- | --- |
| Native PQR export | 单 Structure deterministic whitespace writer、loss preview、atomic cancellation、native semantic re-import | mandatory charge/radius、10/11-field dialect、element inference | **选择** |
| Native Cube export | Structure + Grid3D writer 与 multi-dataset round-trip | native-unit、dataset selection 和 writer/readiness 尚未冻结 | 暂缓 |
| Reader API v1 stable gate | stable token 与 compatibility qualification | 没有外部 adopter 证据，兼容承诺过早 | 暂缓 |

## Selection rationale

Native PQR export 是当前最小、证据最完整的 core 缺口：

- 科学输入边界已经由 PQR reader 和 `pqr_export_readiness()` 冻结；
- 两种允许的 whitespace dialect 与 malformed/ambiguous cases 已有 fixture；
- `Structure`、`BiologicalHierarchy`、charge/radius datasets 均已进入统一模型，
  无需扩展 model 或 sidecar schema；
- 可复用现有 `ExportReport`、`MolecularExport`、短 sibling atomic writer、
  cancellation cleanup 和 native `parse_pqr()` semantic re-import；
- 不需要 RDKit、Gemmi、ASE、Open Babel 或新依赖。

明确延后：

- **Cube: deferred** — 仍须先冻结 writer/readiness、native-unit 保留与
  multi-dataset selection；derived VDB cache 不能作为科学 Grid3D exporter。
- **Reader API stable: deferred** — 当前没有外部 adopter 证据支持从
  `1.0-rc1` 提升，不能用格式 exporter 顺手扩大兼容承诺。
- **PQR UI: deferred** — core writer、loss preview 和 semantic re-import
  通过独立 gate 后再复用 Project Browser workflow；本 Task 不同时实现 UI。

## Selected Task 5 boundary

Task 5 只新增纯 core `preview_pqr_export(project_entities)` 与
`export_pqr(project_entities, ...)`：

- 输出确定性的 ASCII whitespace `ATOM`/`HETATM` records；chain 非空使用
  11 fields，chain 为空使用 10 fields；
- exactly one Structure；不输出 MODEL/ENDMDL/CONECT/CRYST1；
- charge/radius 只来自 readiness 已验证的 authoritative datasets；
- 必要时按 Structure atom order 确定性重编号 serial；
- 未表达的 topology、periodic cell、identity/source-only data 进入稳定 loss
  preview，并在 `confirm_loss=True` 前阻止写入；
- destination 使用现有短 sibling temporary file、flush/fsync/replace/cancel
  cleanup；
- native `parse_pqr()` semantic re-import 比较 Structure、hierarchy、charge 和
  radius，不比较 UUID、provenance 或 whitespace。

Task 5 明确是 **No UI**、**No FrameSet**、**No Cube**、**No API token change**。
实施步骤写入
`docs/superpowers/plans/2026-08-02-chemblender-2.4.0-pqr-export.md`。
