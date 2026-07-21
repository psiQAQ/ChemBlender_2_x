# 0003：量子化学语义模型

## Status

Accepted for Phase 0 quantum visualization foundation.

## Context

ChemBlender 当前以 Blender Mesh、attributes 和 custom properties 表达结构与显示状态，无法稳定承接计算步骤、物理量数组、解析缺失信息和派生关系。解析器若直接创建 `bpy` 对象，也无法在普通 CPython 中独立测试。

本决策只确定 P0 语义边界。具体 Python 数据类库、存储后端、第三方 parser 和 Blender 映射由后续决策处理。

## Decision

### 项目所有权

`QCProject` 是唯一聚合根，以项目级 registry 管理实体：

```text
QCProject
├── structures:   UUID → Structure
├── calculations: UUID → CalculationRecord
├── datasets:     UUID → PropertyDataset | Grid3D
└── provenance:   UUID → ProvenanceRecord
```

实体通过 UUID 引用，不嵌套复制其他权威实体。UUID 是不透明且稳定的身份；名称、数组位置和文件路径不能作为身份。内容 hash 属于后续存储与缓存决策。

### P0 对象职责

| 对象 | 职责 | 不负责 |
| --- | --- | --- |
| `Structure` | 原子、坐标、可选晶胞和拓扑等结构事实 | 计算方法、基组和计算结果 |
| `CalculationRecord` | 计算状态，以及输入/结果结构、数据集和 provenance 的 UUID 引用 | 内嵌复制结构或大型数组 |
| `PropertyDataset` | 带物理语义、domain、维度、单位和来源的通用属性数组 | Blender 显示参数 |
| `Grid3D` | 在通用数据集约定上增加 origin、三个完整 step vectors 和网格 shape | 假设网格正交或决定等值面样式 |
| `ParserReport` | 记录一次解析生成的实体、缺失项、歧义、警告和不支持能力 | 充当科学数据集 |
| `ProvenanceRecord` | 记录来源、版本、父实体和派生操作 | 完整 provenance 图查询 |

`PropertyDataset` 至少具有 `semantic_role`、`domain`、`dtype`、`shape`、`dims`、`unit`、`source_calculation` 和 provenance 引用。`semantic_role` 与 `domain` 在 P0 使用受命名规范约束的非空字符串；只有真实用例证明封闭枚举稳定后才引入枚举。

`Grid3D` 与 `PropertyDataset` 共用 `datasets` registry。网格数值、物理语义和显示样式必须分离；多个网格 dataset 不能在归一化时静默截断。

### 数组与单位约束

- `shape` 必须与数值数组一致。
- `dims` 数量必须等于数组维数，各维名称在同一数据集中唯一。
- 自旋、轨道、基函数、帧、模态、态和 k-point 等索引通过命名维度表达，不依赖固定轴顺序的隐含约定。
- 数值必须有规范单位，或明确标记为 `dimensionless` 或 `unknown`；单位字段不能留空。
- 缺失物理量不能转换为空数组。

### 状态与问题表达

`CalculationRecord` 状态至少区分 `success`、`failed` 和 `incomplete`。`PropertyDataset` 状态至少区分 `complete`、`partial` 和 `ambiguous`。

`ParserReport` 的问题类型至少区分：

| 类型 | 含义 |
| --- | --- |
| `missing` | 来源通常可提供，但本文件没有该值 |
| `unsupported` | 当前 reader 尚未解析该能力 |
| `ambiguous` | 数值存在，但语义或单位不能唯一确定 |
| `invalid` | 数据违反 shape、引用或单位约束 |
| `warning` | 不阻止导入，但应向用户展示 |

解析采用“构建 → 校验 → 原子提交”流程。结构损坏、重复 UUID、dangling reference 或数组约束错误会阻止整个提交；一般缺失、未支持和可保留的歧义进入 `ParserReport`，不制造看似完整的数据。

### Provenance 边界

P0 provenance 保存来源标识、来源 hash、parser 或程序及其版本、父实体 UUID、操作名称和操作参数。内部模型不绑定某一版 QCSchema；QCSchema v1/v2 通过独立 adapter 转换。

## Consequences

- parser、worker 和 Blender adapter 可以共享同一实体身份与数组契约。
- core 可以脱离 `bpy` 在普通 CPython 中验证。
- 计算记录、结构和数据集可独立复用，但读取方必须解析 UUID 引用。
- 部分结果和失败计算会显式保留，不再依赖空数组或静默丢弃表达。

## Rejected Alternatives

- **按计算记录嵌套全部结构和数据集**：重复大型对象，跨计算共享和缓存失效困难。
- **混合嵌套与 registry**：同一对象可能出现两个权威位置，生命周期和序列化规则不清晰。
- **直接采用 Blender `PropertyGroup` 或第三方容器作为权威模型**：使 core 绑定运行时或外部 schema 版本。
- **立即定义全部专业对象和封闭枚举**：P0 尚无足够真实 fixture 支撑稳定边界。

## Deferred

- `dataclass`、Pydantic 或其他实现库。
- Zarr、HDF5、OpenVDB、`.cbq` 和 content hash 规则。
- 完整单位换算后端。
- cclib、IOData、ASE、QCSchema 等 adapter。
- `OrbitalSet`、`VibrationalModeSet`、`ExcitedStateSet` 等 P1 对象。
- Blender Mesh、Volume、Geometry Nodes 和 UI 映射。

## Verification Contract

后续最小实现必须证明：

1. 普通 CPython 可构造包含结构、计算记录和原子属性的 `QCProject`，且不导入 `bpy`。
2. 非正交 `Grid3D` 保留三个完整 step vectors。
3. 开放壳层数组可用 `dims=("spin", "orbital", "basis_function")` 表达。
4. shape/dims 不一致、重复 UUID 和 dangling reference 被拒绝。
5. 缺失物理量只进入 `ParserReport`，不生成空数据集。
