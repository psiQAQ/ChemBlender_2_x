# ChemBlender 2.4.0 Task 4 Candidate Intake

## 结论

选择 **Task 4 — PDB Export UI** 作为唯一后续任务。它保持 `not_started`，
直到本 Scope Discovery checkpoint 完成后被显式激活。

本轮不修改 runtime，不实现 PQR/Cube writer，也不提升 Reader API token。

## Live evidence snapshot

2026-08-02 对 `psiQAQ/ChemBlender_2_x` 的现场复核结果：

- PDB core export PR #11 已用普通 merge commit 合并；精确 feature head 为
  `2995386744768b424e8276db7cd72a90154edf25`；
- `extension-package` run `30724971581` 与 `optional-qc-core` run
  `30724971598` 均为 `success`，两者 `headSha` 都等于精确 feature head；
- merge commit 为 `79a93f52053fdf809c28c24800366010577a1984`，feature
  head 是其祖先；
- open PR 为 0；repository Issues 与 Discussions 均未启用；
- `v2.3.0` ZIP 与 checksum 当前下载数均为 0；这不是缺少需求的证据，也
  不能作为 Reader API 外部采用证据。

## Current capability facts

- PDB: F5 / core / preview_confirmation。
- PDB UI: absent；`ChemBlender.ui.export._FORMAT_ITEMS` 和文件过滤器没有
  `pdb`，preview/job dispatcher 也没有 PDB branch。
- PQR: F0；现有 `pqr_export_readiness()` 只冻结可表示性，不写文件。
- Cube: F0；现有 Structure/Grid3D import 与 derived-cache 边界成熟，但没有
  writer/readiness contract。
- Reader API: 1.0-rc1；public snapshot 与 conformance tests 已冻结，stable
  promotion 仍要求独立 compatibility gate。

## Candidate comparison

| 候选 | 最小可交付结果 | 主要风险 | 决策 |
| --- | --- | --- | --- |
| PDB Export UI | 在现有 Project Browser operator 中选择、预览、确认并后台导出 PDB | 精确投影一个 Structure 的 hierarchy/datasets/topology | **选择** |
| Native PQR export | 单 Structure whitespace writer、强制 charge/radius、native re-import | 更窄 dialect，尚无 core writer | 暂缓 |
| Native Cube export | Structure + Grid3D writer 与 dataset round-trip | writer/readiness、native unit 与 multi-dataset 尚未冻结 | 暂缓 |
| Reader API v1 stable gate | stable token 与 compatibility qualification | 没有外部 adopter 证据 | 暂缓 |

## Selection rationale

PDB Export UI 是当前最小的用户可见闭环：

- core `preview_pdb_export()` / `export_pdb()` 已经通过纯 Python、Blender
  安装 smoke、精确 HEAD CI 和独立复审；
- 通用 `ui.export` 已拥有 selection、loss confirmation、background job、
  cancellation、progress cleanup 和 atomic publication；
- `ui.export` 已是显式 registration root，不需新增 operator 或注册路径；
- 单选 Structure 的投影只需要 Structure、BiologicalHierarchy、相关 datasets
  与可选 topology；无需新模型、schema、API token 或依赖；
- native `parse_pdb()` 可用于 installed product semantic re-import。

明确延后：

- **PQR: deferred** — 仍缺 core writer，且 mandatory charge/radius 与单结构
  whitespace dialect 是独立科学边界。
- **Cube: deferred** — 仍须先冻结 writer/readiness、native-unit 与多 dataset
  selection；VDB derived cache 不能替代 Grid3D scientific export。
- **Reader API stable: deferred** — 没有外部 adopter 证据支持从 `1.0-rc1`
  提升，不能用格式 UI 工作顺手扩大兼容承诺。

## Selected Task 4 boundary

Task 4 只扩展现有 `ChemBlender.ui.export`：

- add `pdb` format item and `*.pdb` filter;
- project exactly one selected Structure, its one BiologicalHierarchy, related
  datasets and optional topology into the existing core exporter contract;
- delegate preview to `preview_pdb_export()` and background publication to
  `export_pdb()`;
- keep explicit loss confirmation, cancellation and destination preservation;
- update generated capability from `core` to `project_browser` after real
  installed Blender export/re-import passes.

No new operator, registration root, RNA collection, PDB writer, CONECT/CRYST1
support, model/schema/dependency/version/workflow or release work belongs to
this task.

Implementation steps are in
`docs/superpowers/plans/2026-08-02-chemblender-2.4.0-pdb-export-ui.md`.
