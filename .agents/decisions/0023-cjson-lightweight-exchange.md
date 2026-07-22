# ADR 0023: CJSON lightweight exchange

## Status

Accepted on 2026-07-22.

## Decision

- 支持 Avogadro `chemicalJson` 0/1，未知版本明确失败。
- 以 `MolecularTopology` 保存结构内的 bond indices 和 orders。
- 稳定的 atom/trajectory/electronic-spectrum 字段进入现有语义对象。
- 未自描述单位或 basis convention 的 vibration vectors、cube 与 orbitals 保留在 `CJSONEnvelope`，并产生明确 issue。
- CJSON 只用于轻量交换；`.cbq` 继续承担大型数组与缓存的权威存储。

## Consequences

ChemBlender 可以与 Avogadro 交换结构和轻量结果而不静默丢失扩展字段，同时不会
因 CJSON 的开放字段集合削弱内部单位与 shape 契约。
