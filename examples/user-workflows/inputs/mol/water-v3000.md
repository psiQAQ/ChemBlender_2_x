# 水分子 V3000 MOL 合同样例

## 用途与选择理由

这是与 V2000 水样例对应的最小 V3000 合同，用来验证 `M  V30` 分块和版本分派。两者表达同一个三原子结构，便于判断格式版本差异是否改变了导入语义。

## 来源与许可

- 取得日期：`2026-08-07`。

- 来源标识：`tests/fixtures/mol/water-v3000.mol@3e1d02e046851c6c89a81ac8dce42b435bb25509`。
- 来源路径：仓库测试夹具 `tests/fixtures/mol/water-v3000.mol`，逐字节复制。
- 许可：`GPL-3.0`。

## 规模与分辨率

文件大小 `331` bytes，含 3 个原子和 2 条键。它用于语法精度和版本兼容测试，不包含复杂 V3000 collection、query 或反应字段。

## 字段说明

| 字段 | 内容 | 含义 |
| --- | --- | --- |
| `M  V30 BEGIN CTAB` | 结构块开始 | V3000 容器 |
| `M  V30 COUNTS` | 3 atoms、2 bonds | 记录规模 |
| `BEGIN ATOM` | O、H、H 及 xyz | 原子表 |
| `BEGIN BOND` | 两条单键 | 拓扑表 |
| `END CTAB` / `M  END` | 结束标记 | 结构终止 |

## ChemBlender 支持边界

ChemBlender 通过 RDKit 读取 V3000 基本结构并保留原始 MolecularRecord。这个合同只证明基础 ATOM/BOND 路径；更复杂的 V3000 支持应使用 TA1 代表样例并检查导出损失。

## 操作流程

1. 用 `Quick Import` 选择 [`water-v3000.mol`](water-v3000.mol)。
2. 在 Preview 核对版本、3 个原子和 2 条键，再确认导入。
3. 与 V2000 水样例比较 Structure 和 Topology。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，先读取 Operator RNA，再用 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/mol/water-v3000.mol 的绝对路径。只使用公开的 bpy.ops.chemblender.*；先报告 V3000、3 个原子、2 条键、项目实体和 Preview 诊断，等我确认后调用 bpy.ops.chemblender.confirm_import。可与 V2000 水样例比较，但不得直接改 .cbq；保存 .blend 与相邻 .cbq。
```

## 完整性与验证

- SHA-256：`ea321b6296d22e787889780b5a4a62183a45652aa9b7c8a5eda7e5d3262c7a01`
- 精确大小：`331` bytes
- 自动检查：3 atoms、2 bonds、V3000。

## 参考资料

- [BIOVIA CTfile 格式入口](https://3dswym.3dexperience.3ds.com/post/biovia-laboratory-informatics/can-i-store-molfiles-of-chemical-structures-in-my-database_FXvWcYPER3KN7sxun8F6SA)
- [ChemBlender 许可证](https://github.com/psiQAQ/ChemBlender_2_x/blob/main/LICENSE)
