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

1. 用 `Quick Import` 选择 [openbabel-5sun-protein.mol2](openbabel-5sun-protein.mol2)，在实际 Preview 检查 MOL2: 1、6185 atoms、Interpreted bonds: 0、unsupported un 和四类未知 section。
2. 确认导入后，在 Project Browser 和保存项目中核对 6185 原子、6248 条原始声明键、390 个 substructure；解释拓扑仍为 0，不能补成权威键。
3. 查看默认 Structure View；默认原子视图不代表已接受显示拓扑。需要连接显示时明确选择并接受相应拓扑，导出前检查损失提示。

Preview只显示该格式当前实现的摘要。未出现的原子/键数、计算参数和详细诊断，应在确认后的项目实体或来源文件中核对，不能报告为Preview已显示。保存时让 `.blend` 与同名 `.cbq` 相邻。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，先读取 Operator RNA。用公开 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/mol2/openbabel-5sun-protein.mol2 的绝对路径。先报告实际 preview_json 中的 reader、quality、可用摘要和诊断，等我确认再调用 confirm_import；不要把文档中的预期计数说成 Preview 已显示。确认后用公开状态和保存的项目核对：6185 原子、6248 条原始声明键、390 个 substructure；解释拓扑仍为 0，不能补成权威键。查看默认 View，并说明原子显示与科学拓扑的区别；有损导出停在确认边界。保存 .blend 与相邻 .cbq 并报告路径。
```

## 完整性与验证

- SHA-256：`1ac476afd860c326995e28125cc4cf4007b33e022a8c9f397d9e350f3e5a4fbd`
- 精确大小：`779286` bytes
- 自动检查：6185 atoms、6248 declared bonds、390 substructures、unsupported bond type `un`、0 interpreted topologies、4 unknown section kinds。

## 参考资料

- [Open Babel 固定版本源文件](https://github.com/openbabel/openbabel/blob/0e94434fa75c9f61095023e3c12e0d5f2ac035ff/test/files/5sun_protein.mol2)
- [Tripos MOL2 格式概述](https://www.chemcomp.com/journal/mol2.htm)
- [Open Babel 许可证](https://github.com/openbabel/openbabel/blob/0e94434fa75c9f61095023e3c12e0d5f2ac035ff/COPYING)
