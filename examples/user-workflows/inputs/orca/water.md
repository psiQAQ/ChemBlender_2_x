# 水分子 ORCA 输入样例

## 用途与选择理由

这是仓库自带的最小 ORCA inline XYZ 输入，用于验证 ChemBlender 能直接展示 `.inp` 中的 `* xyz charge multiplicity ... *` 分子结构。它不执行 ORCA，也不解释 `!` 或 `%` 计算设置。

## 来源与许可

- 取得日期：`2026-08-11`。
- 来源标识：`tests/fixtures/orca/water.inp@bfda26791449341fdac43bb172779a710305ed40`。
- 来源路径：仓库测试夹具 `tests/fixtures/orca/water.inp`，逐字节复制。
- 许可：`GPL-3.0`。

## 规模与分辨率

文件为 `122` bytes，包含 1 个 3 原子 O/H/H 结构。坐标以 angstrom 为单位并保留 6 位小数；这里的“分辨率”是原子数和坐标精度，不是图像分辨率。

## 字段说明

| 字段 | 本文件的值 | ChemBlender 语义 |
| --- | --- | --- |
| geometry header | `* xyz 0 1` | molecular charge `0`、multiplicity `1` |
| atom rows | O/H/H 与 Cartesian 坐标 | 3-atom Structure，unit `angstrom` |
| terminator | `*` | 关闭唯一的 inline Cartesian block |
| keywords | `! HF STO-3G TightSCF` | 只作为原始来源保留，不解释 method/basis |

## ChemBlender 支持边界

内置 `orca-input` reader 只支持唯一且闭合的 inline `* xyz` 坐标块以及严格四列 `Element x y z`。`xyzfile` 外部引用、多个坐标块、内部坐标或额外原子列会明确失败；ORCA 关键词不进入结构语义。

## 操作流程

1. 用 `Quick Import` 选择 [`water.inp`](water.inp)。
2. 在 Preview 确认 selected reader 为 `orca-input`，并显示 `structure` capability。
3. 确认导入后，在 Project Browser 查看 Structure，并检查可见的 Structure View。

3 atoms、charge `0` 和 multiplicity `1` 会保存在项目语义中并由自动合同验证；当前通用 Preview/Project Browser 行不会单独显示这三个字段。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，使用公开的 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/orca/water.inp。报告 Preview 中的 selected reader、capability、quality/diagnostics；确认后调用 bpy.ops.chemblender.confirm_import，并验证 Project Browser Structure 与可见 Structure View。3 atoms、charge 0、multiplicity 1 是自动合同预期，不得声称已由通用 UI 可见验证。不得执行 ORCA，也不得解析 xyzfile 外部引用。
```

## 完整性与验证

- SHA-256：`56932cbe71d614732db492297f23bb9d205f0fe9d3f3d1a9dbb773a3c7ffad8b`
- 精确大小：`122` bytes
- 自动检查：严格 inline XYZ、3 atoms、charge/multiplicity、Quick Import preflight/commit。

## 参考资料

- [ORCA coordinate input](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/coordinates.html)
- [ChemBlender 许可证](https://github.com/psiQAQ/ChemBlender_2_x/blob/main/LICENSE)
