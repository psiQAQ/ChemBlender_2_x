# QCSchema 交换边界

QCSchema 是外部交换格式，不是 ChemBlender 内部权威模型。adapter 根据
`schema_name/schema_version` 选择显式路径：

| 文档 | QCSchema identity | ChemBlender 结果 |
| --- | --- | --- |
| v1 AtomicResult | `qcschema_output/1` | `Structure`、`CalculationRecord`、数值 `PropertyDataset`、raw envelope |
| v2 AtomicResult | `qcschema_atomic_result/2` | input/result `Structure`、`CalculationRecord`、数值 `PropertyDataset`、raw envelope |
| v1 Molecule | `qcschema_molecule/2` | `Structure`、raw envelope |
| v2 Molecule | `qcschema_molecule/3` | `Structure`、raw envelope |

坐标按 QCSchema 约定映射为 `bohr`。energy、gradient、hessian 分别映射为
`hartree`、`hartree_per_bohr` 和 `hartree_per_square_bohr`。没有经过审阅的数值
property 使用 `unknown` 单位与 `AMBIGUOUS` 状态；非数值 property 进入
`ParserReport`。

`QCSchemaEnvelope` 保存规范化 JSON 的完整内容，因此 `extras`、`native_files`、
尚未映射的 properties 以及上游扩展字段仍可字段级导出。内部对象只保存稳定、
可验证的常用语义。QCElemental 作为固定源码与可选验证依赖，不进入 Blender
Extension，也不要求 Pydantic 才能读取本地结果。

计算执行采用独立的 [`qcschema.compute@1`](../specs/qcschema-compute-worker-v1.md)
worker operation。QCEngine/PySCF 只产生 QCSchema AtomicResult；结果仍通过本 adapter
归一化，执行后端不能直接修改内部 project model。
