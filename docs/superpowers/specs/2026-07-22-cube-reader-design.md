# Cube Reader Design

## Goal

用 Python 标准库把 Gaussian Cube 的原子结构、完整仿射网格和全部 dataset 归一化为现有 `Structure` 与 `Grid3D`，不依赖 IOData、NumPy 或 Blender。

## Scope

- 支持 `.cube` 与 `.cub` 内容探测。
- 支持正、负 `NATOMS`，以及可选 `NVAL` 和 `DSET_IDS`。
- 保留三个完整 step vectors，包括非正交和反手网格。
- 保留每个 voxel 的全部值；多 dataset 使用前导 `dataset` 维。
- 原子结构、网格、SHA-256 provenance 与 `ParserReport` 进入同一 `ImportBatch`。

本切片不从 comment 或文件名猜测 density、MO、ESP 等物理语义，不实现表面、切片、OpenVDB、lazy loading 或 Cube 导出。

## Format Boundary

以公开的 [h5cube Gaussian CUBE 格式说明](https://h5cube-spec.readthedocs.io/en/latest/cubeformat.html) 作为本切片的字段布局依据。它明确说明该文档是流通 Cube 子集的 best-effort specification，不是 Gaussian 官方规范，因此 parser 对空白宽松，对字段组合严格。

读取顺序：

1. 两行 comment；
2. `NATOMS ORIGIN [NVAL]`；
3. 三行 `voxel_count step_vector`；
4. `abs(NATOMS)` 行原子数据；
5. `NATOMS < 0` 时读取 `DSET_IDS`；
6. 读取剩余全部数值。

`NATOMS` 不能为零。正值时 `NVAL` 省略则为 1；负值时 `NVAL` 必须省略或为 1，并由 `DSET_IDS` 的首个整数给出 dataset 数量。

## Units

规范说明 Cube 输出中的长度为 bohr。reader 因此令：

```text
Structure.coordinates.unit = "bohr"
Grid3D.coordinate_unit     = "bohr"
```

voxel count 使用绝对值作为 shape。负 voxel count 被接受但产生 warning；它不被解释为 angstrom，避免把 `cubegen` 输入选项的单位 flag 错当成 Cube 输出单位。

Cube 本身不可靠声明 scalar value 的物理语义或单位。因此：

```text
Grid3D.semantic_role = "scalar_field"
Grid3D.domain        = "grid"
Grid3D.data.unit     = "unknown"
Grid3D.status        = AMBIGUOUS
```

report 同时产生 `ambiguous/grid.semantic_role` 与 `ambiguous/grid.data.unit`。后续用户选择或外部 adapter 可以生成具有明确语义的新派生 dataset，不能原地猜测。

## Dataset Layout

单 dataset 使用：

```text
dims  = ("x", "y", "z")
shape = (nx, ny, nz)
```

多 dataset 使用：

```text
dims  = ("dataset", "x", "y", "z")
shape = (count, nx, ny, nz)
```

Cube 数据按 voxel 优先、dataset 在最内层排列。parser 将其去交错为 dataset-first 的 `ArrayData`。数据数量必须严格等于 `nx * ny * nz * count`，过少或过多都失败。

`DSET_IDS` 的整数顺序原样写入 provenance parameter `dataset_ids`；正 `NATOMS` + `NVAL` 只有 dataset count，没有来源 ID。当前不为一个 reader 增加通用 `axis_labels` 模型；出现第二个需要消费轴标签的真实格式时再评估提取。

## Atomic Data

每行读取 atomic number、nuclear charge 和三个坐标。atomic number 必须在 `0..118`，坐标与 charge 必须有限。

当前 `Structure` 不保存 nuclear charge。其值与 atomic number 不同时，结构仍可导入，但 report 产生 `unsupported/atom_nuclear_charge`；值相同时不重复保存。

## Reader Contract

reader ID 为 `cube`，version 为 `1`，capability 为：

```text
structure = supported
grid      = supported
```

`sniff_cube()` 在 bounded prefix 中验证 header、`NATOMS`、origin 和三条 axis line；完整 parse 负责 atom、dataset 与 data count 校验。

成功结果包含一个 `Structure`、一个 `Grid3D`、一个 provenance record 和一个 report。两个实体共享 source revision 与 provenance ID，report 的 parsed capabilities 为 `("structure", "grid")`。

## Error Boundary

以下情况抛出 `ValueError`，不返回部分 batch：

- header、axis、atom 或 dataset ID block 截断；
- `NATOMS == 0`，axis count 为零，或 `NVAL/DSET_IDS` 组合无效；
- 原子序数越界，或任一结构、网格、charge、data 数值非有限；
- step vectors 线性相关；
- dataset ID 数量或 data 数量不匹配；
- data block 含非数值 token。

## Verification

- 一个斜网格 fixture 验证 origin、step vectors、bohr 单位和索引坐标。
- 一个负 `NATOMS`、两个 dataset 的 fixture 验证 ID 顺序、`("dataset", "x", "y", "z")` 和去交错数值。
- `NVAL=2` fixture 验证无 ID 的多值路径。
- value unit 与 semantic role ambiguity 必须进入 report。
- 截断、奇异网格、无效组合、非有限值以及 data count 不匹配被拒绝。
- 普通 CPython import 不加载 `bpy`；全量 tests 与 Blender lifecycle 不回归。

## Rejected Alternatives

- 立即引入 IOData：新增依赖与打包边界尚未批准，本切片的格式逻辑可由标准库完成。
- 为 Cube 新增 `Grid3D.axis_labels`：当前只有一个消费者，dataset IDs 可无损保存在 provenance。
- 每个 dataset 创建独立 `Grid3D`：重复网格元数据，并违反多 dataset 不拆分的 ADR。
- 根据 comment 或文件名猜测物理量：Cube comment 没有可靠的语义或单位契约。
