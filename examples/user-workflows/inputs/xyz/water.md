# 水分子 XYZ 合同样例

## 用途与选择理由

这是仓库自带的最小 XYZ 合同，用于验证 atom count、comment 和笛卡尔坐标三段结构。它适合快速检查内置解析器，不覆盖多帧、晶胞、属性列或拓扑。

## 来源与许可

- 取得日期：`2026-08-07`。

- 来源标识：`tests/fixtures/xyz/water.xyz@3e1d02e046851c6c89a81ac8dce42b435bb25509`。
- 来源路径：仓库测试夹具 `tests/fixtures/xyz/water.xyz`，逐字节复制。
- 许可：`GPL-3.0`。

## 规模与分辨率

文件大小 `101` bytes，含 1 帧、3 个原子，坐标保留 6 位小数。这个大小足够精确表达该水分子文本坐标；它不能说明实验误差，也不能验证大型结构性能。

## 字段说明

| 行 | 内容 | 含义 |
| --- | --- | --- |
| 第 1 行 | `3` | 本帧原子数 |
| 第 2 行 | comment | 自由文本说明 |
| 后 3 行 | O/H/H 与 x/y/z | 元素和笛卡尔坐标 |
| 未提供字段 | bond、charge、cell | 普通 XYZ 不表达这些语义 |

## ChemBlender 支持边界

ChemBlender 内置 XYZ reader 生成 Structure，并保留帧注释。这个合同不提供 source topology；显示上的连线不应当作文件声明键。带属性和多帧轨迹请使用 extXYZ 样例。

## 操作流程

1. 用 `Quick Import` 选择 [`water.xyz`](water.xyz)。
2. 在 Preview 核对 1 frame、3 atoms 和 no source topology，再确认导入。
3. 创建原子 View；若需保存连接关系，选择能表达 Topology 的目标格式并检查来源。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，先读取 Operator RNA，再用 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/xyz/water.xyz 的绝对路径。只使用公开的 bpy.ops.chemblender.*；先报告 1 帧、3 个原子、6 位坐标、无来源 Topology、项目实体和 Preview 诊断，等我确认后调用 bpy.ops.chemblender.confirm_import。不得把显示用连线当来源键；保存 .blend 与相邻 .cbq，有损导出停下请求确认。
```

## 完整性与验证

- SHA-256：`f10d94aaa2bf5bd2e15b2b1cd996e95b7ca6fbd3255f62195707d3d3ff1da6b8`
- 精确大小：`101` bytes
- 自动检查：1 frame、3 atoms、6 coordinate decimals。

## 参考资料

- [Open Babel XYZ 格式说明](https://openbabel.org/docs/FileFormats/XYZ_cartesian_coordinates_format.html)
- [Atomsk XYZ 约定说明](https://atomsk.univ-lille.fr/doc/en/format_xyz.html)
- [ChemBlender 许可证](https://github.com/psiQAQ/ChemBlender_2_x/blob/main/LICENSE)
