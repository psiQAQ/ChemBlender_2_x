# 导入数据

Quick Import 会先解析到临时 staging，再打开 Import Preview。只有确认 Preview 后，科学实体和默认 View 才会一次性写入 Project。

## 要完成什么

- 导入一个文件、同一文件选择器中的多个文件，或拖放支持的文件。
- 直接输入 SMILES。
- 在提交前检查 reader、依赖、质量、冲突、归组、诊断和默认 View。
- 安全取消，不留下半个 Project 或半个 View。

## 示例

第一次操作用 [water.xyz](../../../examples/user-workflows/inputs/xyz/water.xyz)。多文件选择可同时选它和 [carbon-trajectory.extxyz](../../../examples/user-workflows/inputs/extxyz/carbon-trajectory.extxyz)。SMILES 可打开 [ethanol.smi](../../../examples/user-workflows/inputs/smiles/ethanol.smi)，复制其中的 `CCO`。

RDKit 流程可用 [water-v2000.mol](../../../examples/user-workflows/inputs/mol/water-v2000.mol)或 [mixed-properties.sdf](../../../examples/user-workflows/inputs/sdf/mixed-properties.sdf)。CIF 需要 Release 中随附的 Gemmi，可用 [nacl.cif](../../../examples/user-workflows/inputs/cif/nacl.cif)。

## 操作前检查

1. 在 Blender 5.1 的 `Edit > Preferences > Get Extensions` 中确认 ChemBlender 已启用。
2. 打开 3D View 右侧边栏的 `ChemBlender > Quick Import`。
3. 查看顶部 `Project` 状态和 `Project is clean` / `Unsaved changes`。
4. 默认 validation mode 是 `Balanced`。只有格式说明或诊断要求时才改为 `Strict` 或 `Maximum`；模式不会把无效的原子身份修成有效 Structure。
5. 多文件导入只处理你在文件选择器中明确选中的文件，不会扫描整个目录。

## UI 操作

### 单文件与多文件

1. 在 `Quick Import` 中选择 `Select Files`。
2. 选择一个或多个文件并确认。也可以把支持的文件拖到 3D View 或 Project Browser；File Handler 会进入同一条 Quick Import 流程。
3. 等待进度行完成。运行中可见 stage、百分比和状态。
4. 选择 `Review` 打开 `Import Preview`。
5. 逐个来源检查 selected reader、availability、capabilities、quality badge 和 scientific summary。
6. 如有重复或 revision conflict，明确选择目标 revision。归组没有充分证据时保留 `Keep Independent`；只有映射正确时才选 `Accept Group`。
7. 检查 `Default View`。系统只会按本次 staging 中的数据建议 `Structure`、`Grid Volume` 或 `Signed Isosurface`。
8. 所有可见决定完成后确认 `Import Preview`。

### SMILES 文本

1. 在 `Quick Import` 中选择 `Import SMILES`。
2. 输入 `CCO`，保留需要的 validation mode。
3. 在 Preview 中确认 RDKit availability、派生 3D Structure、topology 和质量状态。
4. 确认后再到 Project Browser 查找新记录。

### 取消

在 Quick Import 或 Import Preview 中选择 `Cancel`。大文件的 reader 可能要到下一个 cancellation checkpoint 才能停止；等活动 job 消失后再开始下一次导入。确认之前取消不会把 staging 实体或默认 View 写入 Project。

## 屏幕上应看到什么

- Quick Import 运行时显示 stage、进度百分比和 `Cancel`。
- Import Preview 为每个 source 显示 reader、依赖状态、能力、质量 badge 与格式相关摘要。
- POSCAR 可显示 species、cell、Selective Dynamics 或 velocity 摘要；Cube 可显示 Grid3D 和 dataset 语义；多记录分子文件可显示 records、topology 和 conformer 决策。
- 确认后，Project Browser 的 `By Source` 下出现 source revision、科学实体和 View；`By Data` 下能找到对应 Structure 等类型。

## 成功判据

1. Project Browser 中的 source 路径与所选文件一致。
2. 新 Structure 的 atom count 和示例预期一致；`water.xyz` 应有 3 个原子。
3. quality badge 与 Preview 一致，Diagnostics 没有被静默清除。
4. 如果 Preview 计划了默认 View，3D View 出现对应对象；删除或变换该对象不会删除 Project 中的科学实体。
5. 取消测试后，Project Browser 中没有本次未确认来源。

## Agent 提示词

### 单文件与 Import Preview

```text
使用当前 Blender MCP。一次查询 Blender >= 5.1、executable、bundled Python、runtime system、Extension repositories、active file/dirty state 和 enabled key `bl_ext.user_default.chemblender`。检查 Operator RNA 与 poll 后，只调用 live registered `bpy.ops.chemblender.quick_import` 和 `bpy.ops.chemblender.confirm_import`，以 Balanced 导入 `examples/user-workflows/inputs/xyz/water.xyz`。先停在 Import Preview，报告 reader、quality、diagnostics、Default View 和所有 confirmation；无冲突/歧义且与 3 原子 water 预期一致时再确认。完成后从公开 Scene RNA/Project Browser 状态验证 source、Structure 和 View。不得 import private modules、直接编辑 `.cbq`/cache/`cb_` state，或 bypass confirmation。
```

### 多文件

```text
使用当前 Blender MCP，先完成 Blender 5.1/Extension/active-file 预检并检查 Operator RNA。通过 live `bpy.ops.chemblender.quick_import` 一次选择 `examples/user-workflows/inputs/xyz/water.xyz` 与 `examples/user-workflows/inputs/extxyz/carbon-trajectory.extxyz`，不得扫描目录。等待公开 job state 完成，停在 Preview，逐来源返回 reader、quality、frame/cell 摘要、grouping/conflict confirmation；不要自动 Accept Group。只在决定明确后调用 `bpy.ops.chemblender.confirm_import`。验证两个 source revision 和对应实体/View。不得 import private modules、写 `.cbq` 或 bypass confirmation。
```

### SMILES

```text
使用当前 Blender MCP，确认 Blender >= 5.1、`bl_ext.user_default.chemblender`、RDKit availability 和 clean Project。检查 Operator RNA 后调用 live `bpy.ops.chemblender.import_smiles_text` 导入 `CCO`（来源样例 `examples/user-workflows/inputs/smiles/ethanol.smi`），使用 Balanced。停在 Import Preview，报告 3D derivation、Structure、topology、quality 和 confirmation，再调用 `bpy.ops.chemblender.confirm_import`。验证 Project Browser 中的 MolecularRecord/Structure/View；不要 import private modules、直改 `.cbq` 或 bypass confirmation。
```

### 取消

```text
使用当前 Blender MCP，先检查 Operator RNA。通过 `bpy.ops.chemblender.quick_import` 启动 `examples/user-workflows/inputs/cube/two-datasets.cube` 的 staging，在确认前调用 live `bpy.ops.chemblender.cancel_import`。条件轮询公开 job/Preview state，直到活动任务消失；验证 Project Browser 没有本次 source/entity/View，且没有半成品被报告为成功。不得 import private modules、操作 `.cbq`/cache 或调用 `bpy.ops.chemblender.confirm_import` 绕过取消；任何 confirmation 都保持未确认。
```

## 常见问题

| 现象 | 处理 |
| --- | --- |
| Reader unavailable | 先看 availability reason。基础 Release 的 MOL/SDF/SMILES 应有 RDKit，CIF 应有 Gemmi；可选 adapter 缺失时不要改用名称相似的 reader |
| `Ambiguous` 或 `Partial` | 打开 Diagnostics，核对假设、缺失字段和 scientific consequence；不确定时取消并换更完整来源 |
| POSCAR 元素不明确 | 在 Preview 中填写并应用 species，确认原子计数与顺序；不要从文件名猜元素 |
| 导入没有生成对象 | 先在 Project Browser 查科学实体。可能是 Default View 未选择、View 失败或该数据没有自动 View |
| 取消后按钮仍忙 | 等 job 状态消失；不要同时启动第二个 Quick Import |

继续：[处理数据](02-process.md)。更完整的 Preview 行为见 [Quick Import 指南](../quick-import.md)和[数据质量说明](../data-quality.md)。
