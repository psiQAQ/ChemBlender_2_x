# 0004：Grid3D 与单位约定

## Status

Accepted for Phase 0 quantum visualization foundation.

## Context

Cube、电子密度、静电势、ELF、NCI 和周期体数据都需要三维网格，但它们的网格可能非正交，并可能在同一坐标框架中包含多个 dataset。文件格式只决定数据布局，不能决定物理语义或 Blender 显示样式。

本决策建立足以无损归一化和验证的逻辑约定，不决定数组存储、压缩、OpenVDB 或等值面算法。

## Decision

### Grid3D 坐标模型

`Grid3D` 使用完整仿射网格。索引到笛卡尔坐标的映射为：

```text
r(i, j, k) = origin + i * step_x + j * step_y + k * step_z
```

`origin` 是索引 `(0, 0, 0)` 采样点的位置，不是体素外边界角点。`step_x`、`step_y` 和 `step_z` 是三个完整三维向量，不拆成标量 spacing，也不自动正交化、旋转或改变 handedness。

最小字段约定：

| 字段 | 约束 |
| --- | --- |
| `origin` | shape 为 `(3,)` 的有限数值 |
| `step_vectors` | shape 为 `(3, 3)`；三行依次对应 x、y、z 索引步长 |
| `grid_shape` | 三个正整数 `(nx, ny, nz)` |
| `dims` | 末三维必须为 `("x", "y", "z")` |
| `shape` | 末三维必须等于 `grid_shape` |
| `coordinate_unit` | `origin` 与 `step_vectors` 共用的长度单位 |
| `unit` | 网格 values 的物理单位，与坐标单位独立 |

`step_vectors` 必须线性独立；零体积网格无效。负 determinant 表示 handedness，不自动修正。索引范围是 `0 <= i < nx`、`0 <= j < ny`、`0 <= k < nz`，周期 wrap 只能由上层操作明确请求。

### 多 dataset

空间轴固定为 values 的末三维；前导维表达 dataset、spin、orbital、state 或其他索引。例如：

```text
dims  = ("orbital", "x", "y", "z")
shape = (norb, nx, ny, nz)
```

reader 必须保留全部前导维和索引标签，不能只保留第一个 dataset。`semantic_role` 说明网格是什么，surface style、isovalue、颜色和材质不进入 `Grid3D`。

### 单位 token

所有数值字段使用非空单位 token。P0 token 采用稳定的 ASCII `lower_snake_case` 名称，例如 `angstrom`、`bohr`、`hartree`、`electron_volt`、`inverse_centimeter` 和 `elementary_charge`。

- 无量纲值使用 `dimensionless`。
- reader 无法可靠判断单位时使用 `unknown`，同时将数据集标为 `ambiguous`，并在 `ParserReport` 中记录 `ambiguous` issue。
- `unknown` 不是可参与任意派生计算的通配单位；计算操作必须明确拒绝或声明支持。
- 不从文件后缀、变量名或默认显示方式推断单位。

P0 不引入单位对象或全量换算表。reader adapter 负责将来源单位映射为规范 token；发生数值转换时，provenance 至少记录 `from_unit`、`to_unit`、`scale` 和 `offset`，并满足：

```text
target_value = source_value * scale + offset
```

同一转换不得重复应用。未转换的原始单位仍记录在 parser/provenance metadata 中。

### 验证与错误

以下情况使 `Grid3D` 无效并阻止项目事务提交：

- `origin`、`step_vectors` 或 values 含非有限值，且 parser 未按格式规则显式表示缺失值；
- step vectors 线性相关；
- `grid_shape` 含零、负数或非整数；
- values 的末三维与 `grid_shape` 不一致；
- `dims` 的末三项不是 `("x", "y", "z")`；
- `coordinate_unit` 或 `unit` 为空。

单位未知但数组和坐标结构有效时允许提交为 `ambiguous`，不得静默改成猜测单位。

## Consequences

- 正交、斜网格和反手坐标系都可无损表达。
- 多轨道、多自旋或多 dataset 网格不需要复制坐标框架。
- 数值、语义和显示样式保持独立，可分别缓存和调整。
- 在采用 QCElemental 或其他单位后端前，adapter 只能使用经过测试的显式换算。

## Rejected Alternatives

- **只保存 origin 与三个标量 spacing**：无法表达 sheared/oblique axes。
- **为每个采样点保存完整坐标**：规则网格重复数据过多，也掩盖其仿射结构。
- **把每个 dataset 拆成独立 Grid3D**：重复坐标元数据，并丢失来源文件中的 dataset axis 关系。
- **立即采用单位库作为权威模型**：依赖尚未批准，P0 只需要稳定交换契约。

## Deferred

- Zarr/HDF5 chunk、memory order、压缩和 lazy loading。
- OpenVDB 转换、marching cubes、切片和体渲染。
- semantic role 到首选显示单位的完整注册表。
- 周期插值、重采样和不同网格之间的对齐。

## Verification Contract

后续最小实现必须证明：

1. 正交和斜网格的索引坐标映射正确。
2. 多 dataset values 的前导维完整保留。
3. shape/dims、奇异 step vectors 和空单位被拒绝。
4. `dimensionless` 可正常使用，`unknown` 产生 ambiguous 状态和 parser issue。
5. 单位换算 round-trip 不重复应用 scale 或 offset。
