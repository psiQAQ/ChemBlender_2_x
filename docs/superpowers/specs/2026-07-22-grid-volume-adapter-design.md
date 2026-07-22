# Grid3D to OpenVDB Volume Adapter Design

## Goal

把一个 normalized `Grid3D` dataset 转换为可重建的 OpenVDB cache 与 Blender Volume object，同时保留 dataset 身份、revision、选择索引和坐标单位转换信息。

## Runtime Decision

Blender 5.1.2 实际运行时已验证：

- bundled Python 可 import `openvdb` 与 NumPy；
- `openvdb.FloatGrid.copyFromArray()` 可写三维数组；
- `openvdb.createLinearTransform()` 接受 4×4 affine matrix；
- `openvdb.write()` 生成的文件可由 `bpy.types.Volume.grids.load()` 重新加载；
- `Volume.grids` 是只读集合，因此不能绕过 VDB 文件直接填充。

首版只实现 OpenVDB Volume adapter。阈值 voxel mesh 与 marching-cubes fallback 在真实运行环境缺少 OpenVDB 或需要等值面导出时再进入设计。

## Public Contract

新增 `ChemBlender/grid_volume.py`，只提供一个公共入口：

```python
create_grid_volume(
    grid: Grid3D,
    cache_path: Path,
    *,
    dataset_index: int = 0,
    name: str = "ChemBlender Grid",
    collection=None,
) -> bpy.types.Object
```

调用方负责给出明确的 `.vdb` cache path；adapter 不决定项目目录、sidecar 布局或缓存淘汰策略。目标父目录必须已存在，避免函数隐式创建任意目录。

## Supported Data

首版支持 Cube reader 当前产生的两种 shape：

```text
("x", "y", "z")
("dataset", "x", "y", "z")
```

三维数据只接受 `dataset_index=0`；四维数据验证索引范围并选取一个 dataset。其他前导维明确失败，直到对应 orbital/spin/state 选择契约进入实施。

`Grid3D.data.unit` 和 `semantic_role` 不影响 VDB 数值；adapter 不把 `unknown` 猜成 density、MO 或 ESP。VDB grid 使用技术名称 `density` 以便 Blender Volume viewport 消费，但 object custom properties 保留原始 semantic role 与 value unit。

## Coordinate Transform

ChemBlender 现有 Blender 场景约定以 angstrom 数值作为对象空间长度。adapter 支持：

```text
angstrom → scale 1.0
bohr     → scale 0.529177210903
```

其他 coordinate unit 明确失败。OpenVDB 使用 row-vector 4×4 matrix：

```text
[
  [step_x.x, step_x.y, step_x.z, 0],
  [step_y.x, step_y.y, step_y.z, 0],
  [step_z.x, step_z.y, step_z.z, 0],
  [origin.x, origin.y, origin.z, 1],
] * coordinate_scale
```

只缩放前三行的空间分量与最后一行 origin，不改变齐次分量。这样斜网格、handedness 和采样点 origin 均保持不变。

## Cache Write

选中数据通过 `numpy.asarray(..., dtype=float32)` 进入 `FloatGrid.copyFromArray()`。VDB 是可重建显示 cache，float64 → float32 是允许的派生精度变化；权威 `Grid3D` 不修改。

写入使用同目录临时文件和 `os.replace()`：

```text
target.vdb.tmp → target.vdb
```

避免写入中断留下被误认为有效的 target。VDB metadata 与 Blender object properties 至少保存：

- dataset UUID；
- dataset revision；
- dataset index；
- semantic role；
- value unit；
- source coordinate unit；
- display coordinate unit `angstrom`；
- coordinate scale；
- cache format version `1`。

## Blender Object

adapter 创建一个 Volume datablock 和一个 Object，设置 cache filepath、加载 `density` grid，并链接到显式 collection 或当前 context collection。Object transform 保持 identity，因为 affine transform 已写入 VDB。

viewport display 使用线性插值和默认 density multiplier。首版不创建 Material、Volume to Mesh 节点、色标或 UI；这些需要先确定 scalar semantic 与显示参数。

如果 VDB 写入、Volume 加载或 object 链接失败，清理本次创建的 Blender datablock；已完成原子替换的有效 cache 可保留用于诊断和重建。

## Permissions

manifest 的 `files` 说明更新为“读取用户选择的结构/结果文件，并写入用户请求的可视化缓存”。不增加网络权限或依赖声明。

## Verification

在 `tests/blender_smoke.py` 中使用标准库 `array` 构造一个斜 `Grid3D`，在临时 `BLENDER_USER_RESOURCES` 下：

- 创建 VDB 与 Volume object；
- 从 `openvdb.read()` 验证 grid 名、float data 和 index-to-world transform；
- 验证 Blender Volume 已加载一个 `density` grid；
- 验证 object identity transform 与 custom properties；
- 删除测试 object/datablock/cache 后继续现有 repeated lifecycle。

普通 CPython core tests 继续证明 `ChemBlender.core` 不加载 `bpy`；adapter 只在 Blender runtime 测试。

## Rejected Alternatives

- 同时实现 mesh fallback：当前 OpenVDB runtime 已通过真实 round-trip，没有失败证据需要第二套后端。
- 把 VDB cache 写进 `.blend`：会让派生大型数据成为 Blender 权威存储。
- 自动推断 scalar semantic 或材质：Cube contract 已明确这些字段 ambiguous。
- 为单个 adapter 新建 factory、backend registry 或 cache manager：当前调用路径不需要这些抽象。
