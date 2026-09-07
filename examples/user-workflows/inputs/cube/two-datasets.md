# 双数据集 Cube 合同样例

## 用途与选择理由

这个 `contract` 文件专门测试 Gaussian Cube 的负 atom count、多 dataset ID 和交错标量值。它只有 `2 × 2 × 1` 网格，不适合判断等值面质量。

## 来源与许可

- 取得日期：`2026-08-07`。

- 来源标识：`tests/fixtures/cube/two-datasets.cube@3e1d02e046851c6c89a81ac8dce42b435bb25509`
- 平台：ChemBlender repository；从测试夹具逐字节复制。
- 许可：`GPL-3.0`，见 [仓库许可证](https://github.com/psiQAQ/ChemBlender_2_x/blob/main/LICENSE)。

## 规模与分辨率

大小为 `354` bytes，1 个原子、2 个 dataset、空间网格为 `2 × 2 × 1`，每个 dataset 有 4 个点。它只验证语法和 dataset 选择；用于展示时会明显块状。

## 字段说明

| 位置 | 本文件的值 | 含义 |
| --- | --- | --- |
| 两行标题 | `two datasets` 等 | 人类可读注释，不可靠地定义场语义 |
| origin 行 | atom count `-1`、origin `(0.1,0.2,0.3)` | 负计数表示后面有 dataset ID 区段 |
| 三条 axis 行 | counts `-2,2,1` | 绝对值给出 `2 × 2 × 1`；本 reader 保留 bohr，并对负 voxel count 报 warning；不能将此符号当作已完成 Å 转换 |
| atom 行 | H、charge 1 | 核位置与 nuclear charge |
| dataset ID 行 | `2 5 7` | 2 个 dataset，ID 为 5 和 7 |
| scalar 行 | 交错的 10–13 与 100–103 | 两个场的数据值 |

## ChemBlender 支持边界

ChemBlender 2.4.0 可拆分 dataset axis，创建 Grid3D 和 nuclear-charge 属性。Cube 标题通常不足以证明场是电子密度、轨道还是别的量，所以 semantic role 和 unit 默认保持 ambiguous；用户要通过 `resolve_grid_semantics` 明确选择。导出多个 dataset 时必须指定 dataset index。

## 操作流程

1. `Quick Import` [`two-datasets.cube`](two-datasets.cube)，在 Preview 核对两个 dataset ID。
2. 确认导入后选择一个 Grid3D，明确 semantic 与 unit，再创建 Volume 或 Signed Surface。
3. 导出时选择 dataset index，核对另一个 dataset 不会被静默写入。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，读取 Operator RNA 后，用 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/cube/two-datasets.cube 的绝对路径。只调用公开 bpy.ops.chemblender.*。先报告两个 dataset ID、shape、origin、step vectors、单位/semantic ambiguity 和诊断，等我确认 bpy.ops.chemblender.confirm_import。创建视图前用 bpy.ops.chemblender.resolve_grid_semantics，再用 bpy.ops.chemblender.create_grid_view；不得猜电子密度。导出必须指定 dataset index 并停在 loss confirmation。保存相邻 .blend/.cbq。
```

## 完整性与验证

- SHA-256：`cba9356dbd6901a725810aab63a17c79eb2508f178b7b8b77ee306de2f0b31ba`
- 精确大小：`354` bytes
- 自动检查：1 atom、2 datasets、空间 grid `[2,2,1]`，解析数组另含长度为 2 的 dataset 维，逐字节受 manifest 约束。

## 参考资料

- [h5cube 对 Gaussian Cube 的字段说明](https://h5cube-spec.readthedocs.io/en/latest/cubeformat.html)
- [ChemBlender 网格展示流程](../../../../docs/user/workflows/03-visualize.md)
