# APBS 蛋白–RNA PQR 代表样例

## 用途与选择理由

这个 APBS 官方示例用于检查接近实际静电计算输入规模的 PQR：998 个原子、逐原子电荷与半径，以及没有 chain 字段时的分段恢复。它也覆盖半径为 0 的合法记录。

## 来源与许可

- 取得日期：`2026-08-08`。

- 来源标识：`Electrostatics/apbs@4613d0d547c3c71df8815dcb85e9e19abf61822c:examples/protein-rna/model_outNB.pqr`。
- 源文件：[APBS 固定提交中的 model_outNB.pqr](https://raw.githubusercontent.com/Electrostatics/apbs/4613d0d547c3c71df8815dcb85e9e19abf61822c/examples/protein-rna/model_outNB.pqr)，逐字节取得。
- 许可：`BSD-3-Clause`，见该固定提交的 [LICENSE](https://github.com/Electrostatics/apbs/blob/4613d0d547c3c71df8815dcb85e9e19abf61822c/LICENSE.md)。

## 规模与分辨率

文件大小 `70047` bytes，含 998 个原子、41 个残基、998 个 charge、998 个 radius，其中 22 个 radius 为 0。PQR 没有体素分辨率；它表达原子坐标和静电参数，后续 APBS 网格精度由计算设置决定。

## 字段说明

| 字段 | 本文件内容 | 含义 |
| --- | --- | --- |
| `REMARK` | PDB2PQR 版本、forcefield、总电荷 | 生成和参数化说明 |
| `ATOM` | serial、name、residue、resid、xyz、charge、radius | 空白分隔的 PQR 原子记录 |
| charge | 每个原子 1 值 | 部分电荷，单位为基本电荷 |
| radius | 每个原子 1 值 | APBS 使用的原子半径；0 也可合法出现 |
| residue numbering | 蛋白后重新起始 | 文件无 chain 时用于推断第二 segment |

## ChemBlender 支持边界

ChemBlender 保留 Structure、biological hierarchy、partial charge 和 radius。该文件没有 chain id；解析器在 residue number 下降时推断新 segment，共得到 2 段，而不会丢弃后半部分。PQR 没有独立 element 列；解析器只接受能从 atom name 与 residue context 明确推断的元素，并在导入后 Project Browser 的 Import Diagnostics 中把 998 条逐原子证据汇总为 1 条 warning。推断 segment 不是来源 chain 声明，UI 和导出必须保留这一 provenance 区别。

## 操作流程

1. 用 `Quick Import` 选择 [`apbs-protein-rna-nb.pqr`](apbs-protein-rna-nb.pqr)。
2. 在 Preview 核对 pqr reader、Partial 和默认 Structure View；Preview 未显示完整计数或 warning 正文。
3. 确认后在 BiologicalHierarchy 核对 998 atoms、41 residues、2 chain/segment entries 与 2 blank source chain IDs；Import Diagnostics 显示 1 条元素推断 warning。当前选择器按源 chain ID、residue 或属性筛选，没有独立 segment 选择器。选择 PQR Radius、At Most、0，应报告 22 个原子；charge/radius 的 998 个值通过保存项目核对。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，先读取 Operator RNA，再用 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/pqr/apbs-protein-rna-nb.pqr 的绝对路径。只使用公开的 bpy.ops.chemblender.*；先报告实际 preview_json 的 reader、Partial、能力和默认 View，等我确认后调用 bpy.ops.chemblender.confirm_import。提交后从公开 Browser 与保存项目核对 998 个原子、41 个残基、998 行 charge/radius、22 个合法零半径、空源 chain IDs、2 个 inferred segment，以及 1 条元素推断汇总 warning。可用 bpy.ops.chemblender.select_biological_atoms 做公开选择，但不得把 inferred segment 写成源 chain。保存 .blend 与相邻 .cbq；有损导出停下请求确认。
```

## 完整性与验证

- SHA-256：`44f78c804e4f006f74a9f2b439094063e1046735106e2c8436543ba7e7578a68`
- 精确大小：`70047` bytes
- 自动检查：998 atoms、41 residues、2 inferred segments、998 charge/radius rows、22 zero-radius rows。

## 参考资料

- [APBS PQR 格式说明](https://apbs.readthedocs.io/en/latest/formats/pqr.html)
- [APBS 示例源文件](https://github.com/Electrostatics/apbs/blob/4613d0d547c3c71df8815dcb85e9e19abf61822c/examples/protein-rna/model_outNB.pqr)
- [APBS BSD-3-Clause 许可](https://github.com/Electrostatics/apbs/blob/4613d0d547c3c71df8815dcb85e9e19abf61822c/LICENSE.md)

筛选反馈：Biological hierarchy 分行显示 MODEL、chain/segment entries、空源 chain ID 数、residue 和 atom 数；执行 Select Biological Atoms 后状态栏报告选中数量。筛选写入 View 的 `cbq_selected`，不改写来源坐标或层级，也不等同于隐藏其余原子。
