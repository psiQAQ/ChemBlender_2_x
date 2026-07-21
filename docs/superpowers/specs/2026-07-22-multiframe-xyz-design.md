# Multi-frame XYZ and FrameSet Design

## Goal

在不增加 `QCProject` registry 的前提下，用现有语义核心表达共享原子身份的多帧 XYZ，并让单帧 XYZ 行为保持不变。

## Scope

- 基础多帧 XYZ：每帧包含 atom count、comment 和固定顺序的原子坐标。
- 坐标单位固定为 `angstrom`。
- 所有帧共享首帧 `Structure` 的原子数、元素顺序和原子身份。
- 逐帧 comment 原样保留。
- parser 继续返回一个可原子提交的 `ImportBatch`。

本切片不解析 extXYZ `Properties`、晶胞、每原子属性、可变拓扑，也不实现 Blender frame handler。

## Model Decision

`FrameSet` 继承 `PropertyDataset`，存入现有 `QCProject.datasets` registry：

```text
FrameSet(PropertyDataset)
├── semantic_role = "coordinates"
├── domain = "frame"
├── data.dims = ("frame", "atom", "xyz")
├── data.unit = reference_structure.coordinates.unit
├── structure_id → 首帧 Structure
└── comments = tuple[str, ...]
```

首帧 `Structure` 继续提供结构身份和现有 Blender adapter 可消费的 `(atom, xyz)` 坐标。`FrameSet.data` 保存包括首帧在内的完整三维坐标数组；这会重复一帧，但避免引入切片视图、特殊索引和新的 registry。

`FrameSet` 自身验证：

- `semantic_role` 必须为 `coordinates`，`domain` 必须为 `frame`；
- `data.dims` 必须为 `("frame", "atom", "xyz")`，且三个维度均为正数；
- 坐标单位不能为 `dimensionless` 或 `unknown`；
- `comments` 数量必须等于 frame 数量，每项必须是字符串，允许空 comment；
- `structure_id` 必须是 UUID。

`QCProject.commit()` 在原子提交前进一步验证：

- `structure_id` 指向现有或同一批次中的 `Structure`；
- atom 维长度等于参考结构的原子数；
- `FrameSet` 与参考结构使用相同坐标单位。

## Reader Behavior

`parse_xyz()` 顺序读取全部帧：

1. 首帧生成现有 `Structure`；
2. 只有一个 frame 时保持当前返回结果，不创建 `FrameSet`；
3. 多于一个 frame 时生成一个 `FrameSet`，并把 `trajectory` 加入 `parsed_capabilities`；
4. 后续 frame 的 atom count 或规范化元素顺序不同会使整个解析失败；
5. 任一 frame 的额外原子列产生一个 `unsupported/atom_properties` issue；
6. D/T 继续映射为 H，并产生 warning；
7. 不再把合法后续 frame 报告为 unsupported。

`XYZ_READER.capabilities["trajectory"]` 从 `unsupported` 改为 `supported`。`sniff_xyz()` 仍只需确认首帧，因为完整结构一致性由 parse 阶段验证。

## Error Boundary

以下情况抛出 `ValueError`，不返回部分 batch：

- frame 缺少 atom count、comment 或声明的原子行；
- atom count 非正整数；
- 元素未知、坐标非有限数；
- frame 间 atom count 或元素顺序不同；
- 第一帧之后出现不能构成完整 frame 的非空内容。

空 comment 合法；文件末尾空行忽略。额外原子列不阻止坐标导入，但必须进入 `ParserReport`。

## Verification

- model tests 构造合法 `FrameSet`，并拒绝错误 dims、comment 数量和 dangling `structure_id`；
- golden multi-frame XYZ 归一化为一个 `Structure`、一个 `FrameSet` 和一个 provenance record；
- frame 坐标 shape 为 `(frame, atom, xyz)`，comments 顺序与来源一致；
- 元素顺序变化和截断的后续 frame 被拒绝；
- 现有单帧 fixture 仍不生成 trajectory dataset；
- 普通 CPython import 不加载 `bpy`；仓库与 Blender Extension lifecycle tests 继续通过。

## Rejected Alternatives

- 新增 `frame_sets` registry：会扩大 `QCProject`、`ImportBatch`、引用校验和序列化边界，而现有 datasets registry 已能承载数组实体。
- 允许 `Structure.coordinates` 同时接受二维与三维：会破坏现有 `(atom, xyz)` 契约和 Blender 消费方假设。
- 每个 frame 创建独立 `Structure`：重复原子身份，不适合长轨迹，也不能直接表达一个连续 frame axis。
