# CJSON 交换边界

Avogadro CJSON 1 是轻量、可扩展的项目交换格式。ChemBlender 读取稳定字段并保留
完整文档，不将 CJSON 当作大型数组的权威存储。

| CJSON 字段 | 内部映射 | 单位/状态 |
| --- | --- | --- |
| `atoms.elements.number`、`coords.3d` | `Structure` + `AtomicIdentityData` | angstrom |
| `bonds.connections.index`、`order` | `TopologyRecord` | dimensionless |
| `formalCharges`、`partialCharges`、`selected` | `AtomicProperty` | charge 或 dimensionless |
| `coords.3dSets` | `FrameSet` | angstrom |
| `name`、`properties.method` | `ChemicalAnnotation` | whitelist 中的标量 |
| `spectra.electronic` | `ExcitedStateSet` 与 stick `Spectrum` | eV 显式换算为 inverse centimeter |
| `vibrations.frequencies` | partial `PropertyDataset` | inverse centimeter |
| `orbitals`、`cube`、surface 扩展 | raw envelope + `ParserReport` | 等待 basis/grid 单位和 convention 可无损表达 |

`CJSONEnvelope` 保存规范化 JSON 的完整内容，因此未知项目属性和延期字段可以
字段级回写，并在 import diagnostic 中列出。面向文件的 export 只内联不超过
显式 byte threshold 的轨道/体数组；超限字段先进入 `ExportReport`，确认后
省略，绝不隐式写入 base64 或 NPY。大型权威数组仍写入
`.cbq`/`.npy`/OpenVDB；Avogadro C++ 库仅作为固定源码参考，不进入 Blender
Extension。
