# 水分子 V2000 MOL 合同样例

## 用途与选择理由

这是仓库自带的最小 V2000 回归样例，用来快速验证 counts line、原子块和键块。它足以发现解析器语法回归，但不能代表复杂分子的规模、立体化学或实验质量。

## 来源与许可

- 取得日期：`2026-08-07`。

- 来源标识：`tests/fixtures/mol/water-v2000.mol@3e1d02e046851c6c89a81ac8dce42b435bb25509`。
- 来源路径：仓库测试夹具 `tests/fixtures/mol/water-v2000.mol`，逐字节复制。
- 许可：`GPL-3.0`。

## 规模与分辨率

文件大小 `326` bytes，含 3 个原子、2 条单键，坐标保留 4 位小数。约 1 KB 或更小并不表示坐标“低分辨率”；它只是一个离散小结构，覆盖面有限。

## 字段说明

| 字段 | 内容 | 含义 |
| --- | --- | --- |
| header | `water V2000`、`ChemBlender` | 名称与来源说明 |
| counts line | 3 atoms、2 bonds、`V2000` | CTAB 版本与规模 |
| atom block | O、H、H 及 xyz | 原子和笛卡尔坐标 |
| bond block | O–H 两条单键 | 显式拓扑 |
| `M  END` | 结束标记 | CTAB 终止 |

## ChemBlender 支持边界

ChemBlender 通过 RDKit 导入常见 V2000 结构，生成 Structure、Topology、AtomicIdentity 和原始 MolecularRecord。此合同样例没有形式电荷、属性块或复杂立体信息，因此只能证明基本路径可用。

## 操作流程

1. 用 `Quick Import` 选择 [`water-v2000.mol`](water-v2000.mol)。
2. 在 Preview 核对 3 个原子和 2 条键，再确认导入。
3. 创建分子 View，并在导出前查看 loss preview。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，先读取 Operator RNA，再用 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/mol/water-v2000.mol 的绝对路径。只使用公开的 bpy.ops.chemblender.*；先报告 V2000、3 个原子、2 条键、项目实体和 Preview 诊断，等我确认后调用 bpy.ops.chemblender.confirm_import。若导出，先显示损失报告；保存 .blend 与相邻 .cbq。
```

## 完整性与验证

- SHA-256：`44adc72cdd4e670a10f2d0c3c50da11b9044e08e9761f4c7135057bc59ca87f7`
- 精确大小：`326` bytes
- 自动检查：3 atoms、2 bonds、V2000。

## 参考资料

- [BIOVIA CTfile 格式入口](https://3dswym.3dexperience.3ds.com/post/biovia-laboratory-informatics/can-i-store-molfiles-of-chemical-structures-in-my-database_FXvWcYPER3KN7sxun8F6SA)
- [ChemBlender 许可证](https://github.com/psiQAQ/ChemBlender_2_x/blob/main/LICENSE)
