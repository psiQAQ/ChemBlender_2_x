# T07：密度网格、切片与正负等值面

执行草稿。公开转换、五种主网格 View 的实际 GUI 创建、正负显示、数值采样、渲染及串行冷重开/缓存恢复已有证据。Prepare GUI、VASP 输入、其余配图及人工独立复做仍待完成。

![解析密度重分布成图：蓝色为正，橙色为负](../assets/2.5-tutorials/grid-difference-refined.png)

这是解析教学模型的密度差，不是分子轨道或 HF/DFT 计算。细化后轮廓更密，但仍有插值条带。照明会改变视觉颜色，此图不能作为定量色标。

## 固定输入

先完成[安装](installation.md)和[首课](first-aspirin.md)。使用 Blender 5.1.1、prepare 0.1.0；候选 Extension SHA-256 为 `963b905f3e5ee3c5fc1fa53a1ccefd5c60616d89ac77977efe4afdbed066426a`。

下载 [h2-lcao-1s-density-64.cube](../../../examples/user-workflows/inputs/cube/h2-lcao-1s-density-64.cube)、[来源与许可说明](../../../examples/user-workflows/inputs/cube/h2-lcao-1s-density-64.md)及[冻结规格](../../../examples/tutorials/2.5.0/T07.case-spec.json)。来源说明中的旧导入流程不能代替以下 CBQ 路线。

| 项目 | 参考值 |
| --- | --- |
| SHA-256 | `51fcb06343132c4b75f340aa5824434c9c622b51df7ea1ad3742920c78af66b4` |
| 模型 | 仓库解析 H2 成键 1s LCAO 密度；GPL-3.0 |
| 形状 | 64 × 64 × 64，共 262144 个样本 |
| 坐标 | bohr；原点 (-6,-6,-6)，对角步长 0.1904761905 |
| 原子 | H 位于 z = -0.7 和 +0.7 bohr |
| 数值 | electron_per_cubic_bohr；最小 7.75746861e-10，最大 0.229296377 |
| 矩形求和积分 | 按文件步长为 1.9996717595939106，约 2 个电子 |

Cube 核电荷列中的零是占位值，不应解释为真实核电荷。

## 准备与导入

新建教程文件夹，输出使用新路径。以下公开命令已验证，请替换示例目录。这是 CLI 证据，尚不是 Prepare GUI 操作记录。

```powershell
chemblender-prepare inspect "D:\ChemBlenderLessons\T07\h2-lcao-1s-density-64.cube" --reader cube --json
chemblender-prepare convert "D:\ChemBlenderLessons\T07\h2-lcao-1s-density-64.cube" --reader cube --preset electron_density --unit electron_per_cubic_bohr -o "D:\ChemBlenderLessons\T07\h2-density.cbq" --json
chemblender-prepare validate "D:\ChemBlenderLessons\T07\h2-density.cbq" --json
```

预期成功，保留原始 ambiguous 的 `scalar_field` / `unknown` 网格，并追加 complete 的 `electron_density` 网格。显式语义来自固定输入的来源说明；Cube 本身不能可靠确定物理量。[独立检查](../assets/2.5-tutorials/grid-science-check.json)核对全部标量、原点和步长，误差为零。

1. 在 Blender 的 ChemBlender 侧栏设置 `CBQ Package`，依次使用 `Preview CBQ`、`Import CBQ`。本次通过 MCP 重放已验证操作。如果浏览器尚未绘制，先打开 ChemBlender 标签，不要重复导入。
2. 在 Project Browser 选择 complete 的 Electron Density。在 `Scientific Representation` 核对 `Coordinates: bohr` 和 `Values: electron_per_cubic_bohr`。
3. `Automatic` 对应 Grid volume 时点击 `Create View`。记录中的 Density Scale 为 10；它改变显示，不修改科学密度。
4. 选择 `Signed scalar isosurface`，保留 `Dataset Index` 0，将 `Isovalue` 设为 0.05，点击 `Create View`。在视口和渲染中隐藏先前体积，单独查看曲面。

![实际主密度曲面及物理量标签](../assets/2.5-tutorials/grid-primary-surface.jpg)

主密度全部为正，正曲面有 882 个顶点、880 个面，负曲面为空。这符合输入，不是正负渲染失败。

## 采样切片、剖面与色标

每次 Create 前选择完整主密度。以下三种创建均经过实际 GUI 操作。保留独立 View，检查时隐藏重叠的其他 View。

| Representation | 设置 | 预期检查 |
| --- | --- | --- |
| Scientific plane slice | 原点 (-1,-1,0)，U (2,0,0)，V (0,2,0)，65 × 65；关闭对称范围，颜色范围 0 至 0.25 | 4225 个有效样本，相对独立三线性插值最大误差 7.404e-9 |
| Scientific line profile | 起点 (-1,0,0)，终点 (1,0,0)，129 样本 | 距离标签 0–2 bohr；数值 0.0630902003 至 0.176022212，最大误差 7.951e-9 |
| Scientific colorbar | 关闭对称范围，颜色范围 0 至 0.25；宽 2、高 0.2，显示单位 angstrom | 端点 0、0.25，标签 electron_per_cubic_bohr |

每种设置完成后点击 `Create View`。上述切片/剖面坐标单位为 bohr。增加显示样本是在同一 64³ 场上插值，不会增加科学信息。参见[切片检查](../assets/2.5-tutorials/grid-slice-check.json)和[剖面/色标检查](../assets/2.5-tutorials/grid-profile-check.json)。这三种 View 的清晰组合配图仍待补齐。

## 从固定输入重算

将 [recompute_t07_difference.py](../../../examples/tutorials/2.5.0/recompute_t07_difference.py)、[generate_t07_density_pair.py](../../../examples/tutorials/2.5.0/generate_t07_density_pair.py) 和主 Cube 下载到同一教程目录。使用现有 Python 3 解释器，这两个脚本只需要标准库。`--prepare` 指向已安装的处理器可执行文件，不是 Blender。替换以下路径，且 `recomputed` 目录必须尚不存在。

```powershell
python "D:\ChemBlenderLessons\T07\recompute_t07_difference.py" --prepare "D:\Tools\chemblender-prepare.exe" --source "D:\ChemBlenderLessons\T07\h2-lcao-1s-density-64.cube" --output "D:\ChemBlenderLessons\T07\recomputed"
```

脚本核对源文件 SHA-256，然后依次执行以下公开操作：

1. 生成双数据集教学 Cube，预期 SHA-256 为 `8902b35f01edee818cd794793c152c7bfc766b8d0d08cb794077c9e0deef3b7c`。
2. `convert --reader cube --preset electron_density --unit electron_per_cubic_bohr --dataset-index 0` 创建 `pair-first.cbq`，保留原始 ambiguous 双数据集网格，并追加 complete 成键密度。
3. `derive --operation grid.resolve_semantics` 接收该 ambiguous 网格 UUID，使用参数 `{"dataset_index":1,"preset_id":"electron_density","value_unit":"electron_per_cubic_bohr"}` 创建 `pair-both.cbq`。两份密度共享同一个 Structure。索引从零开始，使用 0/1；Cube 源 ID 1/2 不是 CLI 索引。
4. `derive --operation grid.difference --input LEFT --input RIGHT` 写出 `pair-difference.cbq`。LEFT 为成键密度，RIGHT 为孤立原子密度；脚本从本次 WorkerResult 读取 UUID，不硬编码旧运行的编号。
5. `validate` 必须成功。将最终 CBQ 导入 Blender，选择 `Difference` / `difference_density` 数据集，再按下节设置正负等值面。

每步保存实际 CLI 参数列表 `*.argv.json`、原始 WorkerResult `*.stdout.json` 和 stderr。命令失败时脚本停止；检查这些文件，修正原因后使用新的输出目录。不要交换相减顺序。[重放检查](../assets/2.5-tutorials/grid-recompute-check.json)验证了全部 262144 个值、独立下载脚本运行以及拒绝覆盖已有结果。这是公开 CLI 重算路线，GUI 派生路线仍未验证。

## 正负差分结果与细化

记录中的扩展示例在同一 Structure 和仿射网格上，用成键密度减去两个孤立解析 1s 原子密度之和。[可复现输入生成器](../../../examples/tutorials/2.5.0/generate_t07_density_pair.py)和冻结规格定义了两个数据集。公开 `grid.resolve_semantics` 与 `grid.difference` 处理已通过；下述 CLI 重算步骤已通过，GUI 派生路线仍待补齐。

对记录中的差分数据集，选择 `Signed scalar isosurface`，设置 Isovalue 0.005，点击 `Create View`。蓝色表示正重分布，橙色表示负重分布。[差分检查](../assets/2.5-tutorials/grid-difference-check.json)核对了全部 262144 次相减，范围为 -0.0345176831 至 0.0204030833。仅在一次性副本中将右侧网格平移 0.1 bohr 后，处理器因仿射几何不兼容而拒绝，输入不变且没有输出。

![实际等值 0.005 的正负差分曲面](../assets/2.5-tutorials/grid-signed-surface.jpg)

实际 `Separate Positive / Negative Volume` 控件也已测试：使用一个有符号 VDB 和两个着色分支，不是两个独立科学网格。全部 VDB 数值与科学差分在 float32 精度下误差不超过 1.122e-9；最终体积成图仍待完成。

预览图记录的设置为 Cycles CPU、2400 × 1800、256 samples、降噪；Principled 材质 Roughness 0.32；正交相机 (4,-8,3) 朝向原点、scale 3.2；面光源 (2,-4,5)、450 W、size 4；世界颜色 (0.12,0.12,0.12)、strength 0.7。在视口和渲染中隐藏无关 View。

在 Geometry Nodes 中选中各正负曲面的 `Volume to Mesh` 节点，将 `Resolution Mode` 从 `Grid` 改为 `Size`，设置 `Voxel Size` 0.025，保持 Threshold 0.005。正曲面的新控件通过 Computer Use 验证，负曲面重放相同操作。顶点数由 490/612 增至 8464/9972。Blender 原生长度标签跟随场景设置；这里数值 0.025 个显示单位对应 0.025 angstrom。源网格步长仍约 0.1007956592 angstrom。这属于显示重采样，不是更细的科学计算。

## 保存、交接与恢复

保存 `h2-grid.blend` 及旁边的 `h2-grid.cbq` 文件夹，移动时携带整对文件。记录中的工程包含七个 View 根对象。原工程和移动副本分别在独立进程中冷重开，本地 VDB 路径、科学哈希及曲面细化设置均保留。当前教程进程退出前不要另开 Blender。

仅在新的一次性副本中删除八个 `cache/render` VDB 文件，再对七个 View 使用 `Rebuild Selected View`：公开 Operator 重放和随后独立冷重开均通过。不要删除权威 `.npy` 数组。参见[恢复记录](../../../examples/tutorials/2.5.0/T07-recovery-check.json)。

Rebuild 会恢复生成时的 `Grid` 分辨率，需要随后重新应用 Size 0.025 及自定义材质细化。原始细化工程不变。这些检查尚不能证明 GUI 恢复，或源文件与处理器均不可用时的重建；不能据此标为完整离线可用。可分发案例包和人工独立验收仍待完成。
