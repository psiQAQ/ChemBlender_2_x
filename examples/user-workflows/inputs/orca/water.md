# 水分子 ORCA 输入样例

## 用途与选择理由

这是仓库自带的最小 ORCA inline XYZ 输入，用于验证 ChemBlender 能直接展示 `.inp` 中的 `* xyz charge multiplicity ... *` 分子结构。它不执行 ORCA，也不解释 `!` 或 `%` 计算设置。

## 来源与许可

- 取得日期：`2026-08-11`。
- 来源标识：`tests/fixtures/orca/water.inp@bfda267`。
- 来源路径：仓库测试夹具 `tests/fixtures/orca/water.inp`，逐字节复制。
- 许可：`GPL-3.0`。

## 规模与字段

- 3 个原子：O/H/H。
- Cartesian 坐标单位：angstrom。
- molecular charge：`0`。
- molecular multiplicity：`1`。

## ChemBlender 支持边界

内置 `orca-input` reader 只支持唯一且闭合的 inline `* xyz` 坐标块以及严格四列 `Element x y z`。`xyzfile` 外部引用、多个坐标块、内部坐标或额外原子列会明确失败；ORCA 关键词不进入结构语义。

## 操作流程

1. 用 `Quick Import` 选择 [`water.inp`](water.inp)。
2. 在 Preview 确认 selected reader 为 `orca-input`，结构为 3 atoms。
3. 确认导入后，在 Project Browser 查看 Structure，并检查 charge `0`、multiplicity `1`。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，使用公开的 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/orca/water.inp。报告 selected reader、3 个原子、charge 0、multiplicity 1 和 Preview 诊断；确认后调用 bpy.ops.chemblender.confirm_import，并验证 Project Browser 与可见 Structure View。不得执行 ORCA，也不得解析 xyzfile 外部引用。
```

## 完整性与验证

- SHA-256：`56932cbe71d614732db492297f23bb9d205f0fe9d3f3d1a9dbb773a3c7ffad8b`
- 精确大小：`122` bytes
- 自动检查：严格 inline XYZ、3 atoms、charge/multiplicity、Quick Import preflight/commit。

## 参考资料

- [ORCA coordinate input](https://orca-manual.mpi-muelheim.mpg.de/contents/essentialelements/coordinates.html)
- [ChemBlender 许可证](https://github.com/psiQAQ/ChemBlender_2_x/blob/main/LICENSE)
