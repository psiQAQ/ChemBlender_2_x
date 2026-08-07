# Si POSCAR 合同样例

## 用途与选择理由

这是仓库自带的最小周期结构合同，用于快速检查晶格、单元素 counts 和 Direct 坐标解析。它足以验证基础字段，但不能代表复杂晶体、缺陷、部分占位或大 supercell。

## 来源与许可

- 取得日期：`2026-08-07`。

- 来源标识：`tests/fixtures/poscar/si.POSCAR@3e1d02e046851c6c89a81ac8dce42b435bb25509`。
- 来源路径：仓库测试夹具 `tests/fixtures/poscar/si.POSCAR`，逐字节复制。
- 许可：`GPL-3.0`。

## 规模与分辨率

文件大小 `212` bytes，含 1 种元素和 2 个 Si 位点，使用 Direct 坐标。小文件仍完整表达给定晶胞和位点；它的限制是覆盖面，不是数值“像素”不足。

## 字段说明

| 行组 | 内容 | 含义 |
| --- | --- | --- |
| comment / scale | 标题、比例因子 | 结构说明与晶格缩放 |
| lattice vectors | 3 行 | 周期晶胞 |
| species / counts | Si / 2 | 元素顺序和位点数 |
| `Direct` | 坐标模式 | 后续为分数坐标 |
| positions | 2 行 | 两个 Si 位点 |

## ChemBlender 支持边界

ChemBlender 生成 periodic Structure、cell 和 fractional coordinates。该合同不含 selective dynamics、velocity、空间群或实验元数据；不能据此声称这些字段已由该文件验证。

## 操作流程

1. 用 `Quick Import` 选择 [`si.POSCAR`](si.POSCAR)。
2. 在 Preview 核对 2 个 Si 位点和 Direct 坐标，再确认导入。
3. 创建周期 View，导出前检查目标格式可表达的字段。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，先读取 Operator RNA，再用 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/poscar/si.POSCAR 的绝对路径。只使用公开的 bpy.ops.chemblender.*；先报告晶胞、2 个 Si 位点、Direct 坐标、项目实体和 Preview 诊断，等我确认后调用 bpy.ops.chemblender.confirm_import。创建周期 View；任何有损导出停在确认界面。保存 .blend 与相邻 .cbq。
```

## 完整性与验证

- SHA-256：`6f11b9ae550f7f2c570741d05c648691bdfe5d36b91c64c5c20dd8d5ee00f8d0`
- 精确大小：`212` bytes
- 自动检查：2 sites、1 species、Direct mode。

## 参考资料

- [VASP Wiki：POSCAR](https://vasp.at/wiki/POSCAR)
- [ChemBlender 许可证](https://github.com/psiQAQ/ChemBlender_2_x/blob/main/LICENSE)
