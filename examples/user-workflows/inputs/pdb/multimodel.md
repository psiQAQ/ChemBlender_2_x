# PDB 不相容 MODEL 合同样例

## 用途与选择理由

这个合同专门验证多模型原子身份不一致时不能硬拼成完整轨迹。第一个模型含 GLY N 与水 O，第二个模型只有 GLY N；正确行为是保留两个 Structure，并给出 MODEL identity mismatch 诊断。

## 来源与许可

- 取得日期：`2026-08-07`。

- 来源标识：`tests/fixtures/pdb/multimodel.pdb@3e1d02e046851c6c89a81ac8dce42b435bb25509`。
- 来源路径：仓库测试夹具 `tests/fixtures/pdb/multimodel.pdb`，逐字节复制。
- 许可：`GPL-3.0`。

## 规模与分辨率

文件大小 `316` bytes，含 MODEL 4 和 MODEL 7，共 3 个 ATOM/HETATM 记录；只有 1 个模型满足首个身份集合的完整轨迹条件。它用于错误与恢复路径，不代表实际结构规模。

## 字段说明

| record | 内容 | 含义 |
| --- | --- | --- |
| `MODEL` | 4、7 | 保留非连续模型编号 |
| `ATOM` | GLY N | 两模型共有的原子 |
| `TER` | 第一模型中 1 行 | 聚合物链终止 |
| `HETATM` | 第一模型中的 HOH O | 导致模型身份集合不一致 |
| `ENDMDL` | 两行 | 模型边界 |

## ChemBlender 支持边界

ChemBlender 保留两个 Structure、biological hierarchy 和原始 PDB 记录，但不会虚构第二帧缺失的水原子。因此 `compatible_trajectory_frames=1`，Preview 应显示 MODEL identity mismatch；用户可检阅各 Structure，不能把它当两帧完整轨迹。

## 操作流程

1. 用 `Quick Import` 选择 [`multimodel.pdb`](multimodel.pdb)。
2. 在 Preview 核对两个 Structure 与 identity mismatch 诊断。
3. 确认后分别检查 MODEL 4、MODEL 7；导出时保留模型差异或明确接受损失。

## Agent 提示词

```text
通过 Blender MCP 连接 Blender 5.1，先读取 Operator RNA，再用 bpy.ops.chemblender.quick_import 导入 examples/user-workflows/inputs/pdb/multimodel.pdb 的绝对路径。只使用公开的 bpy.ops.chemblender.*；先报告 MODEL 4/7、3 条原子记录、两个 Structure、compatible_trajectory_frames=1 和 MODEL identity mismatch 诊断，等我确认后调用 bpy.ops.chemblender.confirm_import。不得补造缺失原子或声称是完整两帧轨迹；有损导出必须停下请求确认。保存 .blend 与相邻 .cbq。
```

## 完整性与验证

- SHA-256：`45ccec78bcdaa1a1bfe877fea3d9b41f40e5ffa7833fb47a76439184209ec679`
- 精确大小：`316` bytes
- 自动检查：2 models、2 Structures、1 compatible trajectory frame、3 atom records。

## 参考资料

- [wwPDB PDB 格式 3.30](https://www.wwpdb.org/documentation/file-format-content/format33/sect1.html)
- [ChemBlender 许可证](https://github.com/psiQAQ/ChemBlender_2_x/blob/main/LICENSE)
