# ADR 0043: Wave 3 Exchange Data Boundary

## Status

Accepted for `W3-EXCHANGE-PRE-GATE` on 2026-07-29.

## Context

MOL2、PDB、PQR 和 CJSON 带来的新增语义主要是外部标签、生物层级和外部
identifier，不是新的坐标或原子 identity 体系。把这些字段直接加入
`Structure` 或 `AtomicIdentityData`，或者为每种格式创建平行模型，会破坏
Wave 1/2 已冻结的统一项目图。

## Decision

- `ChemicalAnnotation` 只保存绑定到现有科学实体的不可变标量
  `str`、`int`、有限 `float` 或 `bool`。逐 atom、逐 frame 和向量值继续使用
  `PropertyDataset`、`AtomicProperty`、`FrameProperty` 或
  `CategoricalData`。
- `ExternalReference` 保存 namespace、identifier、source 和 provenance；
  外部 identifier 不参与 ChemBlender UUID identity，也不携带 credential
  或网络 client。
- 每个 `Structure` 至多绑定一个 `BiologicalHierarchy`。它以
  `BiologicalModel`、`BiologicalChain`、`BiologicalResidue` 和 atom-aligned
  `BiologicalAtomSiteData` 表达层级，不复制坐标或 atomic numbers。
- PDB atom name 继续进入 `AtomicIdentityData`。兼容的 `MODEL` 坐标进入
  `FrameSet`；identity 不兼容的 MODEL 产生独立 Structure/hierarchy。
- MOL2 atom type 和 substructure label 使用 categorical `AtomicProperty`，
  partial charge 使用 numeric `AtomicProperty`；molecule/charge type 等标量
  使用 `ChemicalAnnotation`。原始 record bytes 继续由 `MolecularRecord`
  保存。
- PDB occupancy/B-factor 与 PQR charge/radius 使用 `AtomicProperty`，缺失值
  以 `DatasetStatus.PARTIAL` 明示。`CONECT` 进入 `TopologyRecord`，
  `CRYST1` 进入已有 `Structure.cell`/`PeriodicSiteData`。
- CJSON 只映射明确 whitelist 中的科学字段。无法安全类型化或未知的 JSON
  保留在 `CJSONEnvelope` 并生成 diagnostic，不展开为任意 annotation graph。
- `ImportBatch`、`QCProject`、sidecar schema `1.0`、canonical document 和
  Reader API `1.0-rc1` 以三个带空默认值的 group 承载 hierarchy、annotation
  和 external reference。旧文档缺字段时按空 group 读取。
- Open Babel、Biopython、RDKit、Gemmi、spglib 或格式 parser 对象不得进入
  上述实体或公开 Reader API。

## Consequences

- Wave 3 reader 复用同一 `Structure`、topology、dataset、provenance 和
  sidecar transaction，不新增 `Mol2Structure`、`PDBStructure` 或通用 JSON
  metadata 容器。
- 生物层级是 Structure 的可选交换语义，不改变分子和晶体的核心模型。
- scalar annotation 保持可验证和可确定性序列化；数组不会被复制进 metadata。
- 本 ADR 只冻结数据边界，不实现任何 reader、exporter、UI 或第三方依赖。

## Verification Contract

模型必须保持 frozen/slotted，项目提交必须验证 target、provenance、唯一语义
键、每 Structure 单 hierarchy 和 atom count，并在失败时不修改任何 registry。
新 group 必须通过 sidecar/canonical/Reader API round-trip，旧 schema `1.0`
sidecar 和缺字段 canonical document 必须继续打开，cold core/API import 不得
加载 optional stack。
