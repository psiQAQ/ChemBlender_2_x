# Avogadro 酞菁 CJSON 代表样例

## 用途与选择理由

这个 `representative` 文件来自 Avogadro 仓库，用于检查较大平面共轭分子的 CJSON 原子、键和形式电荷字段。57 个 sites 中包含一个原子序数为 0 的占位中心，正好覆盖真实文件里的非普通元素标记。

## 来源与许可

- 来源标识：`OpenChemistry/avogadrolibs@e32739bed4b9d79db080a32a0026947e15b240d9:4-phthalocyanine.cjson`
- 2026-08-08 从 [固定 Avogadro commit 的原始文件](https://raw.githubusercontent.com/OpenChemistry/avogadrolibs/e32739bed4b9d79db080a32a0026947e15b240d9/avogadro/qtplugins/templatetool/ligands/4-phthalocyanine.cjson) 逐字节取得。
- 许可：`BSD-3-Clause`，见 [固定 commit 的 LICENSE](https://raw.githubusercontent.com/OpenChemistry/avogadrolibs/e32739bed4b9d79db080a32a0026947e15b240d9/LICENSE)。

## 规模与分辨率

文件大小 `2708` bytes，含 57 个 sites、68 条键和 1 组 `formalCharges`。坐标约写到 4 位小数，足够做交互结构展示；文件没有体网格或轨迹，因而不存在体素/帧“分辨率”。

## 字段说明

| 字段 | 本文件内容 | 含义 |
| --- | --- | --- |
| `chemicalJson` | `1` | Chemical JSON 版本 |
| `atoms.coords.3d` | 171 个数字 | 57 组 Cartesian 坐标 |
| `atoms.elements.number` | C、N、H 与一个 `0` | 原子序数；0 是占位/未知中心 |
| `atoms.formalCharges` | 57 个 0 | 形式电荷属性，不是 partial charge |
| `bonds.connections.index` | 136 个索引 | 68 对零基 atom index |
| `bonds.order` | 68 个键级 | 单键和双键 |

## ChemBlender 支持边界

ChemBlender 2.4.0 创建 Structure、一个显式 Topology、`formal_charge` AtomicProperty 和 CJSONEnvelope。原子序数 0 会按源语义保留，不能冒充化学元素。文件没有晶胞、轨迹或计算结果；导入器不会从平面几何推断额外键。

## 操作流程

1. 用 `Quick Import` 选择 [avogadro-phthalocyanine.cjson](avogadro-phthalocyanine.cjson)，在实际 Preview 检查 CJSON reader、Complete 与默认 Structure View。
2. 确认导入后，在 Project Browser 和保存项目中核对 57 sites、68 条来源键、formal_charge、CJSONEnvelope 和 atomic number 0 占位中心。
3. 查看默认 Structure View；默认原子视图不代表已接受显示拓扑。需要连接显示时明确选择并接受相应拓扑，导出前检查损失提示。

Preview只显示该格式当前实现的摘要。未出现的原子/键数、计算参数和详细诊断，应在确认后的项目实体或来源文件中核对，不能报告为Preview已显示。保存时让 `.blend` 与同名 `.cbq` 相邻。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，先读取 Operator RNA。用公开 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/cjson/avogadro-phthalocyanine.cjson 的绝对路径。先报告实际 preview_json 中的 reader、quality、可用摘要和诊断，等我确认再调用 confirm_import；不要把文档中的预期计数说成 Preview 已显示。确认后用公开状态和保存的项目核对：57 sites、68 条来源键、formal_charge、CJSONEnvelope 和 atomic number 0 占位中心。查看默认 View，并说明原子显示与科学拓扑的区别；有损导出停在确认边界。保存 .blend 与相邻 .cbq 并报告路径。
```

## 完整性与验证

- SHA-256：`310cb5b4d48a08662d9e956b1a7ac778a05ea9060be6cffcdfaedecfd390097e`
- 精确大小：`2708` bytes
- 自动检查：57 atoms、68 bonds、1 formal-charge AtomicProperty；解析无 blocking diagnostic。

## 参考资料

- [固定来源文件](https://raw.githubusercontent.com/OpenChemistry/avogadrolibs/e32739bed4b9d79db080a32a0026947e15b240d9/avogadro/qtplugins/templatetool/ligands/4-phthalocyanine.cjson)
- [OpenChemistry Chemical JSON](https://github.com/OpenChemistry/chemicaljson)
- [Chemical JSON schema](https://github.com/OpenChemistry/chemicaljson/blob/main/cjson.schema)
