# Open Babel 5SUN 蛋白 MOL2 代表样例

## 用途与选择理由

这个 Open Babel 测试文件用于检查大型 MOL2、390 个 substructure 和真实扩展 section。它还故意暴露一个重要边界：文件含 `un`（unknown）键类型，ChemBlender 不能把整套声明键无依据地解释成权威拓扑。

## 来源与许可

- 取得日期：`2026-08-08`。

- 来源标识：`openbabel/openbabel@0e94434fa75c9f61095023e3c12e0d5f2ac035ff:test/files/5sun_protein.mol2`。
- 源文件：[Open Babel 固定提交中的 5SUN MOL2](https://raw.githubusercontent.com/openbabel/openbabel/0e94434fa75c9f61095023e3c12e0d5f2ac035ff/test/files/5sun_protein.mol2)，逐字节取得。
- 许可：`GPL-2.0-only`，按该固定提交的 Open Babel 许可分发。

## 规模与分辨率

文件大小 `779286` bytes，声明 6185 个原子、6248 条键、390 个 substructure，并带 4 类 ChemBlender 尚未解释的扩展 section。它足以验证大型生物分子导入与层级数据，不代表实验测量分辨率。

## 字段说明

| section / 字段 | 本文件内容 | 含义 |
| --- | --- | --- |
| `@<TRIPOS>MOLECULE` | counts、`BIOPOLYMER`、`NO_CHARGES` | 记录类型和规模 |
| `@<TRIPOS>ATOM` | id、name、xyz、Tripos type、substructure、charge、status | 原子、坐标和层级引用 |
| `@<TRIPOS>BOND` | 端点和 bond type | 声明连接；其中出现 `un` |
| `@<TRIPOS>SUBSTRUCTURE` | 390 项 | 残基/子结构层级 |
| 其他 section | 4 类 | 原样保留并给出未知 section 诊断 |

## ChemBlender 支持边界

ChemBlender 可导入 6185 原子的 Structure、4 组原子属性、substructure 层级和原始 MolecularRecord。由于一条 `un` 键无法忠实映射，本文件不会生成“权威解释拓扑”（`interpreted_topologies=0`）；6248 条声明键仍保留在原始记录和诊断中。小型 `substructure.mol2` 用于验证受支持的拓扑路径。

## 操作流程

1. 用 `Quick Import` 选择 [`openbabel-5sun-protein.mol2`](openbabel-5sun-protein.mol2)。
2. 在 Preview 核对 6185 原子、390 个 substructure、`un` 键和 4 类未知 section 诊断。
3. 确认后创建结构 View；不要把自动显示的几何关系当作来源拓扑。
4. 若导出，必须保留原记录或明确接受键/section 损失。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，先读取 Operator RNA，再用 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/mol2/openbabel-5sun-protein.mol2 的绝对路径。只使用公开的 bpy.ops.chemblender.*；先报告 6185 个原子、6248 条声明键、390 个 substructure、un 键、4 类未知 section、interpreted_topologies=0 和 Preview 诊断，等我确认后调用 bpy.ops.chemblender.confirm_import。不要声称已有权威解释拓扑；任何有损导出停下请求确认。保存 .blend 与相邻 .cbq。
```

## 完整性与验证

- SHA-256：`1ac476afd860c326995e28125cc4cf4007b33e022a8c9f397d9e350f3e5a4fbd`
- 精确大小：`779286` bytes
- 自动检查：6185 atoms、6248 declared bonds、390 substructures、unsupported bond type `un`、0 interpreted topologies、4 unknown section kinds。

## 参考资料

- [Open Babel 固定版本源文件](https://github.com/openbabel/openbabel/blob/0e94434fa75c9f61095023e3c12e0d5f2ac035ff/test/files/5sun_protein.mol2)
- [Tripos MOL2 格式概述](https://www.chemcomp.com/journal/mol2.htm)
- [Open Babel 许可证](https://github.com/openbabel/openbabel/blob/0e94434fa75c9f61095023e3c12e0d5f2ac035ff/COPYING)
