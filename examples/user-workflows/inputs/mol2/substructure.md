# MOL2 substructure 合同样例

## 用途与选择理由

这是最小的受支持 MOL2 拓扑合同，专门验证 atom、bond 和 substructure 之间的引用。它与大型 5SUN 样例互补：这里的两条键都可解释，因此应生成可靠 Topology。

## 来源与许可

- 取得日期：`2026-08-07`。

- 来源标识：`tests/fixtures/mol2/substructure.mol2@3e1d02e046851c6c89a81ac8dce42b435bb25509`。
- 来源路径：仓库测试夹具 `tests/fixtures/mol2/substructure.mol2`，逐字节复制。
- 许可：`GPL-3.0`。

## 规模与分辨率

文件大小 `344` bytes，含 3 个原子、2 条键和 2 个 substructure。它只能验证字段映射和层级，不代表蛋白或配体的常见规模。

## 字段说明

| section | 内容 | 含义 |
| --- | --- | --- |
| `MOLECULE` | counts 与 molecule type | 记录头 |
| `ATOM` | 3 行坐标、类型、substructure id、charge | 原子和属性 |
| `BOND` | 2 行 | 显式连接与键型 |
| `SUBSTRUCTURE` | 2 行 | 原子所属的层级单元 |

## ChemBlender 支持边界

ChemBlender 为本文件生成 Structure、Topology、AtomicIdentity、substructure 层级和原始 MolecularRecord。该合同不覆盖大型文件、未知 section 或 `un` 键；这些边界由 5SUN 代表样例验证。

## 操作流程

1. 用 `Quick Import` 选择 [`substructure.mol2`](substructure.mol2)。
2. 在 Preview 核对 3 原子、2 条键、2 个 substructure，再确认导入。
3. 检查项目层级和分子 View；导出前查看 loss preview。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，先读取 Operator RNA，再用 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/mol2/substructure.mol2 的绝对路径。只使用公开的 bpy.ops.chemblender.*；先报告 3 个原子、2 条键、2 个 substructure、Topology 和 Preview 诊断，等我确认后调用 bpy.ops.chemblender.confirm_import。导出如有损失必须停下请求确认；保存 .blend 与相邻 .cbq。
```

## 完整性与验证

- SHA-256：`70b955ea460074b47110f59ba9b757aa61bfe5e2d62d0743a931e74df8ae9ef7`
- 精确大小：`344` bytes
- 自动检查：3 atoms、2 bonds、2 substructures。

## 参考资料

- [Tripos MOL2 格式概述](https://www.chemcomp.com/journal/mol2.htm)
- [ChemBlender 许可证](https://github.com/psiQAQ/ChemBlender_2_x/blob/main/LICENSE)
