# 导出数据

Project Browser 从当前选中的科学实体解析 export selection，再显示格式、目标路径和 loss preview。导出不会以场景中“看起来像什么”为依据。

## 要完成什么

- 从 Structure、FrameSet、MolecularRecord/ConformerSet 或 Grid3D 选择正确的导出闭包。
- 检查格式特有选项、质量和不可表示内容。
- 只在理解损失后勾选 `Confirm Loss/Partial/Ambiguous Export`。
- 取消导出时不接受半成品；完成后做语义回读。

## 示例

可用 [carbon-trajectory.extxyz](../../../examples/user-workflows/inputs/extxyz/carbon-trajectory.extxyz)练习 extXYZ round-trip；用 [with-chain.pqr](../../../examples/user-workflows/inputs/pqr/with-chain.pqr)检查 charge/radius；用 [two-datasets.cube](../../../examples/user-workflows/inputs/cube/two-datasets.cube)检查显式 dataset index。

## 操作前检查

1. 在 Project Browser 选中要导出的实体，核对 Structure revision、topology、properties、quality 和 provenance。
2. 保存项目，避免把尚未确认的 View 编辑误认为 scientific edit。
3. 选择新的输出目录和文件名，不覆盖唯一输入或唯一备份。
4. 阅读[格式与支持范围](formats.md)。“能导入”不等于“可无损导出”。

## UI 操作

1. 在 Project Browser 选中目标行，选择 `Export Selected Data`。
2. 选择格式。当前通用 UI 列出 `XYZ`、`extXYZ`、`Cube`、`MOL`、`MOL2`、`PDB`、`PQR`、`SDF`、`SMILES`、`CIF` 和 `POSCAR/CONTCAR`。
3. 选择 destination。Cube 多 dataset 必须指定 `Dataset Index`；CIF 要选 `Preserve` 或 `Normalized`；POSCAR 要核对 coordinates、scale、Selective Dynamics 和 velocity settings。
4. 阅读完整 `Loss Preview`。它会列出 target、selection closure、缺失字段、被省略/归一化的语义和质量状态。
5. 无损且完整时直接执行。有 loss、Partial 或 Ambiguous 时，只有在逐项接受后才勾选 `Confirm Loss/Partial/Ambiguous Export`。
6. 等后台 job 完成。取消时等待 job 停止，并确认 destination 没有被当成成功结果使用。

### 选择与格式

| 选择 | 常用格式 | 需要特别核对 |
| --- | --- | --- |
| 单个 Structure | XYZ、MOL、MOL2、PDB、PQR、SMILES、CIF、POSCAR | topology、层级、charge/radius、periodic cell 等是否可表示 |
| FrameSet / trajectory | extXYZ | frame count、cell/PBC、typed properties 和 missing-value policy |
| MolecularRecord / ConformerSet | SDF | record/conformer 数、ordered properties、坏记录诊断 |
| Grid3D | Cube | dataset index、shape、origin/step vectors、unit 和 semantic role |

XYZ 只写一个 Structure 的坐标范围，不能替代 extXYZ 的 trajectory/property 语义。SMILES 不含 3D coordinates。Normalized CIF、MOL2、PDB、PQR 和 Cube 都可能改变源文件排版或省略当前 exporter 不表示的记录。

### 当前没有通用 UI writer 的格式

CJSON 和 QCSchema reader 都能保留 source envelope，core 也有受控 exporter。但 2.4.0 的 `Export Selected Data` 没有通用 CJSON/QCSchema writer。普通用户应保留原 envelope 或导出当前 UI 明确支持的目标格式；Agent 不得把 core 函数描述成 Project Browser 按钮。

## 屏幕上应看到什么

- 导出对话框根据选择建议格式，并显示格式专用选项。
- `Loss Preview` 会随格式、目标、dataset index 或 POSCAR/CIF 设置更新；修改选项后原确认会被清除。
- 需要确认而未勾选时，操作应拒绝继续。
- 成功后目标文件存在，且原 Project 的 source/entity revision 不变。

## 成功判据

1. destination 是所选路径，输入文件未被覆盖。
2. 文件大小大于零，且不存在被误当成成功结果的临时文件。
3. 用 Quick Import 重新导入导出文件，比较 atom count、cell、topology、frame/dataset count 和格式承诺保留的属性。
4. 比较的是语义 round-trip，不是字节相同；所有已知 omission 都与 Preview 一致。
5. 取消或失败后，Project 和原 View 保持可用。

## Agent 提示词

> 在 Blender 5.1 的 ChemBlender Project Browser 中选中当前 Structure，调用公开 `Export Selected Data` Operator 导出到一个新的临时目录。先从公开 RNA 读取 format、selection closure 和 loss preview；有任何 loss、Partial 或 Ambiguous 时停止并把预览交给我，不要自动确认。成功后用同一 Quick Import/Import Preview 公共流程回读，并比较该格式承诺保留的语义。不要直接调用 exporter 私有函数或覆盖输入文件。

## 常见问题

| 现象 | 处理 |
| --- | --- |
| 导出按钮不可用 | 检查 Project Browser 的 active entity。普通 Blender object 不是 export selection |
| Preview 要求确认 | 逐项判断 omission 是否可接受；不要把勾选确认当成消除损失 |
| Cube 提示 `Select Dataset Index` | 明确选择一个 dataset；多 dataset Cube 不能靠默认值猜测 |
| POSCAR/CIF 导出结果与源文件文字不同 | 比较 cell、site、坐标、选择性约束、velocity 和 envelope policy；normalized export 不承诺字节保真 |
| CJSON/QCSchema 不在格式列表 | 这是当前 UI 边界，不是 reader 失败。保留原 envelope，或使用明确支持的目标格式 |

继续：[保存、重开、恢复与迁移](05-project-lifecycle.md)。
