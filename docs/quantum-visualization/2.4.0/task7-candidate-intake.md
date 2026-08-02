# ChemBlender 2.4.0 Task 7 Candidate Intake

## 结论

选择 **Task 8 — Deterministic native Cube export** 作为唯一后续任务。它保持
`not_started`，直到本 Scope Discovery checkpoint 完成后被显式激活。

本轮不修改 runtime，不实现 Cube writer/UI，也不提升 Reader API token。

## Live evidence snapshot

2026-08-02 对 `psiQAQ/ChemBlender_2_x` 的现场复核结果：

- PQR Export UI PR #14 已用普通 merge commit 合并；精确 feature head 为
  `3bab75429d37276e27dc158ba5bbf69d9085b9bd`；
- `extension-package` run `30741155445` 与 `optional-qc-core` run
  `30741155450` 均为 `success`，两者 `headSha` 都等于精确 feature head；
- merge commit 为 `eb3fc4ea6f86e8fc3f9475bd03d379445349db57`，feature
  head 是 `origin/main` 的祖先；
- `main` 与 `origin/main` 均为该 merge commit；open PR 为 0；GitHub Issues
  与 Discussions 均未启用；
- GitHub code search 未发现仓库外的 `chemblender.reader.json`；2.3.0 ZIP
  与 checksum 的下载数仍为 0。这些事实不构成 stable API 采用证据。

## Confirmed capability facts

- PQR: F5 / project_browser / preview_confirmation。
- Cube: F0 / none；已有 dependency-free reader、Structure/Grid3D 关联、
  nuclear-charge AtomicProperty、两类 tracked fixtures、sidecar/canonical
  round-trip、derived VDB cache 重建和产品性能基线。
- Reader API: 1.0-rc1；public schema snapshot、compatibility policy 与
  conformance suite 已冻结，stable promotion 明确保留给独立兼容门。
- 当前没有 `preview_cube_export()`、`export_cube()` 或 Cube
  writer/readiness module。

现有 Cube reader 已证明：

- scalar `xyz` 和 `dataset, x, y, z` 数组；
- 非正交 full step vectors；
- atomic number、nuclear charge 与 coordinates 分离；
- negative `NATOMS` 的 `DSET_IDS` 保存到 provenance；
- 当前所有导入几何规范化为 `bohr`，negative voxel counts 只产生 warning，
  不被当作可靠的 angstrom 声明；
- value semantic role 与 value unit 无法从 Cube 可靠判断，因此导入状态为
  `Ambiguous`。

## Candidate comparison

| 候选 | 最小可交付结果 | 主要风险 | 决策 |
| --- | --- | --- | --- |
| Native Cube export | Structure + selected Grid3D + nuclear charge 的确定性 writer、loss preview、native round-trip | writer/readiness、bohr 转换、dataset selection 与 dataset ID | **选择** |
| Reader API v1 stable gate | stable token、schema compatibility qualification | 没有外部 adopter 证据，兼容承诺过早 | 暂缓 |

## Selection rationale

Cube 是最后一个 dependency-free 且 export 为 F0 的内置 Reader。它不需要新模型、
sidecar schema、第三方依赖或 Blender cache 作为科学来源。可以复用已有：

- `ExportReport` 与稳定 loss entries；
- short-sibling atomic writer、flush/fsync/replace/cancellation cleanup；
- `Grid3D`、`AtomicProperty`、`Structure` 与 provenance；
- native `parse_cube()` semantic re-import；
- lazy array ownership 和 live-snapshot 验证模式。

**Reader API stable: deferred** — 当前没有第三方采用或兼容反馈，不能用格式
exporter 顺手把 `1.0-rc1` 提升为 stable。

## Selected Task 8 boundary

Task 8 只新增纯 core `preview_cube_export(project_entities, *,
dataset_index=None)` 与 `export_cube(project_entities, *, dataset_index=None,
confirm_loss=False, destination=None, is_cancelled=None)`：

- exactly one selected `Grid3D`、其 linked `Structure` 和 matching complete
  `nuclear_charge` AtomicProperty；
- scalar grid 不接受多余 dataset index；multi-dataset grid 必须显式提供有效
  dataset selection，绝不静默选择第一个 dataset；
- output geometry 统一写为标准 `bohr`；`angstrom` coordinates、origin 与 step
  vectors 使用同一冻结常数转换，源实体保持不变；其他 coordinate unit fail closed；
- 保留 non-orthogonal/negative-determinant affine axes，不重采样、不正交化；
- selected source dataset ID 可从可信 provenance 精确恢复时，写 one-entry
  `DSET_IDS`；缺失或不一致时使用确定性 ID 并报告 confirmation-required
  normalization loss；
- Cube 无法编码的 semantic role、value unit、project identity 和来源语义进入
  稳定 loss preview，只有 `confirm_loss=True` 才允许 publication；
- comments 使用经过验证的来源 comment 或稳定 fallback，不承诺 byte-identical
  source round-trip；
- authoritative arrays 只 snapshot 一次；destination 使用现有 short sibling
  temporary path，失败、取消或 live mutation 不替换已有文件；
- native `parse_cube()` 比较 atomic numbers、nuclear charges、coordinates、
  origin、step vectors、shape、selected values 和 dataset ID，不比较 UUID、
  provenance identity、comments whitespace、VDB 或 mesh cache。

Task 8 明确是 **No UI**、**No Reader API token change**、**No model/schema**、
**No dependency**。Cube UI 只能在 core writer 独立通过后另行选择。

实施步骤写入
`docs/superpowers/plans/2026-08-02-chemblender-2.4.0-cube-export.md`。
