# SDF 混合属性合同样例

## 用途与选择理由

这个仓库合同用三个相同水分子记录制造不同的属性缺失模式：第一条有 `State` 和 `Flag`，第二条只有 `State`，第三条没有属性。它用于验证 record property 的类型推断与缺失掩码。

## 来源与许可

- 取得日期：`2026-08-07`。

- 来源标识：`tests/fixtures/sdf/mixed-properties.sdf@3e1d02e046851c6c89a81ac8dce42b435bb25509`。
- 来源路径：仓库测试夹具 `tests/fixtures/sdf/mixed-properties.sdf`，逐字节复制。
- 许可：`GPL-3.0`。

## 规模与分辨率

文件大小 `1061` bytes，含 3 个 V2000 records 和 2 个唯一属性 key。它只验证表格属性与缺失值，不代表化学多样性或大规模 SDF 性能。

## 字段说明

| 字段 | 三条记录中的值 | 含义 |
| --- | --- | --- |
| mol block | 都是 3 原子、2 键的水 | 每条记录的结构 |
| `State` | `solid`、`liquid`、缺失 | categorical record property |
| `Flag` | `true`、缺失、缺失 | logical property 与 validity mask |
| `$$$$` | 3 个 | 记录边界 |

## ChemBlender 支持边界

ChemBlender 保留三条 MolecularRecord，并生成 `sdf_state` 分类列和 `sdf_flag` 布尔列；缺失值通过分类 missing code 或 validity mask 表达。该合同不覆盖重复 property name、任意二进制属性或复杂分子。

## 操作流程

1. 用 `Quick Import` 选择 [`mixed-properties.sdf`](mixed-properties.sdf)。
2. 在 Preview 核对 3 records、`State`/`Flag` 两个属性和缺失模式。
3. 确认后在项目数据中查看 typed columns；导出时确认目标格式是否保留属性表。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，先读取 Operator RNA，再用 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/sdf/mixed-properties.sdf 的绝对路径。只使用公开的 bpy.ops.chemblender.*；先报告 3 个 V2000 record、State/Flag 两个唯一 property key、每列的缺失模式、项目实体和 Preview 诊断，等我确认后调用 bpy.ops.chemblender.confirm_import。不得把缺失值填成来源值；有损导出停下请求确认。保存 .blend 与相邻 .cbq。
```

## 完整性与验证

- SHA-256：`c37ff47810613f7eca3cc22ab27397812ab32bd3afef7c1dd4d72875fb5a22cf`
- 精确大小：`1061` bytes
- 自动检查：3 records、2 property keys、V2000；`State` 为分类列，`Flag` 为带有效性掩码的布尔列。

## 参考资料

- [BIOVIA SDfile / CTfile 规范入口](https://3dswym.3dexperience.3ds.com/post/biovia-laboratory-informatics/can-i-store-molfiles-of-chemical-structures-in-my-database_FXvWcYPER3KN7sxun8F6SA)
- [ChemBlender 许可证](https://github.com/psiQAQ/ChemBlender_2_x/blob/main/LICENSE)
