# MOL V2000 Reader Design

## Goal

增加第二种无第三方依赖的结构 reader，并用同一水分子 fixture 证明 XYZ 与 MOL V2000 会得到一致的原子序数、笛卡尔坐标和单位。

## Scope

- 读取单个 MOL V2000 记录的 counts line 和 atom block。
- 将元素与三维坐标归一化为现有 `Structure`，坐标单位为 `angstrom`。
- 计算来源 SHA-256，返回 `ProvenanceRecord` 与 `ParserReport`。
- 读取 bond block 的边界，但在语义核心具备 `Topology` 前不导入键；存在键时显式报告 `unsupported/topology`。
- 通过扩展名 `.mol` 和 V2000 内容探测注册 reader。

本切片不支持 V3000、SDF 多记录、原子电荷、同位素、立体化学和拓扑数据集，不修改旧 Blender/RDKit 导入路径。

## Reader Contract

reader ID 为 `mol-v2000`，version 为 `1`，capability 为：

```text
structure = supported
topology  = unsupported
```

`sniff_mol_v2000()` 解码 UTF-8 文本，并检查：

1. 至少存在四行 header/counts 内容；
2. counts line 可读取非负 atom/bond count；
3. counts line 声明 `V2000`；
4. 已进入 prefix 的 atom 行具有有限坐标和已知元素。

完整记录返回 `EXACT`；64 KiB prefix 截断但已有合法内容时返回 `PROBABLE`。不把普通文本或 V3000 误判为 V2000。

`parse_mol_v2000()` 使用 MOL 固定列读取：

- counts line：atom count、bond count；
- atom line：`x[0:10]`、`y[10:20]`、`z[20:30]`、`symbol[31:34]`；
- bond block：只验证声明的行数存在；
- property block：扫描到 `M  END`，遇到已知但未映射的记录时写入 issue；
- `$$$$` 或 `M  V30` 触发明确错误，不返回部分 batch。

成功结果只包含一个 `Structure`、一个 provenance record 和一个 report。标题进入 provenance parameters，不成为新的模型字段。

## Error Boundary

以下输入抛出 `ValueError`：

- 不是 V2000 或包含多个 SDF 记录；
- atom count 非正数、bond count 为负数；
- atom/bond block 截断；
- 元素未知，或坐标无效、非有限；
- 缺少 `M  END`。

存在 bond、charge、isotope 或其他未映射属性时不静默丢弃：能安全保留结构的输入继续返回，并在 `ParserReport` 中说明未导入语义。

## Cross-format Acceptance

新增水分子 MOL fixture，原子顺序和坐标与现有 `water.xyz` 相同。测试直接比较两个 batch 的：

- `atomic_numbers`；
- `coordinates.data.shape` 与逐项数值；
- `coordinates.dims`；
- `coordinates.unit`。

不新增通用“结构相等”抽象；有第三种实际 reader 需要复用时再提取。

## Verification

- registry 能按 `.mol` 与内容选择 reader，拒绝 V3000；
- golden fixture 生成完整 `Structure`、provenance 和显式 topology issue；
- XYZ/MOL normalized structure 核心字段一致；
- 截断、未知元素、非有限坐标、多记录输入被拒绝；
- 普通 CPython import 不加载 `bpy`；现有 reader/core tests 不回归。

## Rejected Alternatives

- POSCAR：XYZ 不含晶胞，当前无法完成同一 normalized structure 的完整核心字段对照。
- PDB：altloc、occupancy、residue 和 model 边界会扩大当前最小切片。
- 立即增加 `Topology`：只有一个 reader 消费者，属于未经当前验收要求证明的抽象。
