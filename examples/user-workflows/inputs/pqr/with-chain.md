# PQR chain 字段合同样例

## 用途与选择理由

这个最小合同验证 PQR 可选 chain id、插入码样式 residue id、partial charge 和 radius。它与无 chain 的 APBS 大样例互补，用来区分“来源明确给出 chain”和“解析器推断 segment”。

## 来源与许可

- 取得日期：`2026-08-07`。

- 来源标识：`tests/fixtures/pqr/with-chain.pqr@3e1d02e046851c6c89a81ac8dce42b435bb25509`。
- 来源路径：仓库测试夹具 `tests/fixtures/pqr/with-chain.pqr`，逐字节复制。
- 许可：`GPL-3.0`。

## 规模与分辨率

文件大小 `105` bytes，含 2 个原子、2 条 chain 标识、2 个 charge 和 2 个 radius。它只验证字段分派，不代表生物大分子或静电计算规模。

## 字段说明

| 字段 | 内容 | 含义 |
| --- | --- | --- |
| record | `ATOM`、`HETATM` | 聚合物与非聚合物原子 |
| atom/residue | N ARG、O HOH | 原子名和残基名 |
| chain | A、W | 来源明确给出的链标识 |
| residue id | `1A`、`2` | residue number 与可选 insertion code |
| xyz / charge / radius | 每行各 3+1+1 值 | 坐标、部分电荷、半径 |

## ChemBlender 支持边界

ChemBlender 导入 Structure、biological hierarchy、chain、charge 和 radius。该合同没有多残基连接、segment 推断或大型选择性能；这些由 APBS 代表样例覆盖。

## 操作流程

1. 用 `Quick Import` 选择 [`with-chain.pqr`](with-chain.pqr)。
2. 在 Preview 核对两个原子、chain A/W、charge 和 radius，再确认导入。
3. 用 biological selection 分别选择 A 与 W，核对项目层级。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，先读取 Operator RNA，再用 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/pqr/with-chain.pqr 的绝对路径。只使用公开的 bpy.ops.chemblender.*；先报告两个原子、chain A/W、residue id、两组 charge/radius、项目实体和 Preview 诊断，等我确认后调用 bpy.ops.chemblender.confirm_import。随后可用 bpy.ops.chemblender.select_biological_atoms 分别选择两条 chain；保存 .blend 与相邻 .cbq。
```

## 完整性与验证

- SHA-256：`7abdc850d0ae2bbf58de9ebeb8e4ddf6f51715290c011531e8ca02ec15a12c93`
- 精确大小：`105` bytes
- 自动检查：2 atoms、2 chains、2 charge rows、2 radius rows。

## 参考资料

- [APBS PQR 格式说明](https://apbs.readthedocs.io/en/latest/formats/pqr.html)
- [ChemBlender 许可证](https://github.com/psiQAQ/ChemBlender_2_x/blob/main/LICENSE)
