# T02：乙醇构象、MMFF94 与显式网格编辑

本课只走一条路线：从 `CCO` 经三维化、MMFF94 操作和一次显式网格编辑，得到保存的配对工程。下图展示最终**手工编辑后**的结构，不是优化得到的能量极小结构。

![显式移动氢原子后的乙醇](../assets/2.5-tutorials/ethanol-cycles.png)

灰色为碳，红色为氧，白色为氢，可见 9 个原子和 8 根键。球体大小、灯光和 Blender 场景距离属于显示设置；科学坐标仍使用 angstrom。

## 前提与固定输入

先完成[安装](installation.md)，并通过[首课](first-aspirin.md)熟悉侧栏。本课需要带 RDKit 的 Standard processor。

下载 [ethanol.smi](../../../examples/user-workflows/inputs/smiles/ethanol.smi)，放入新目录，例如 `D:\ChemBlenderLessons\T02\`。文件内容为 `CCO` 加换行，是仓库编写、采用 GPL-3.0 许可的合成输入，不是实验结构。保留[冻结的案例规格](../../../examples/tutorials/2.5.0/T02.case-spec.json)供核对。

| 检查项 | 预期值 |
| --- | --- |
| 输入 SHA-256 | `5c9aa2a3024d56c903d547798cbd04ff743433ba0950dbfd8e19238e40651172` |
| 来源坐标 | 不包含坐标；SMILES 图有 3 个重原子 |
| 生成结构 | C2H6O，9 个原子、8 根键，angstrom |
| 生成参数 | ETKDGv3、MMFF94、勾选 Add Hydrogens、Maximum Iterations 200 |
| 已记录的生成默认值 | seed 12648430、单线程；它们是实现记录的默认值，不是此 GUI 的可编辑字段 |
| 优化参数 | MMFF94、不勾选 Add Hydrogens、Maximum Iterations 200 |
| 绝对比较容差 | 坐标 `1e-7` Å；能量 `1e-6` kcal/mol |

## 检查与转换

1. 打开 `chemblender-prepare-gui`，在操作中选择 `inspect`。在“输入文件 / CBQ：每行一个路径”填写 `ethanol.smi` 完整路径，点击“执行”。预期返回 `status: success`，Reader 为 SMILES。
2. 切换到 `convert`，保留输入类型 `files`、空 Reader ID 和 `balanced` 校验模式。在“新输出文件 / CBQ 路径”填写课程目录中尚不存在的 `ethanol.cbq`，然后执行。
3. 等待“完成”和 `status: success`。注意 `smiles.planar_2d_generated` 提示：平面坐标由连接关系生成，不是来源文件中的构象坐标。

![Prepare 转换及平面坐标诊断](../assets/2.5-tutorials/ethanol-prepare-convert.jpg)

## 导入并生成构象

1. 使用新的课程场景。在 `Layout` 的视口中按 `N`，打开 `ChemBlender` 侧栏。在 `CBQ Package` 填入 `ethanol.cbq` 并按 Enter 确认路径。点击 `Preview CBQ`，预期有 7 个新实体；再点击 `Import CBQ` 并确认。
2. 在 Project Browser 选择导入的 Structure。在 `Scientific Representation` 保留 `Automatic` / `Research`，点击 `Create View`。最初显示的是平面结构。
3. 在 Outliner 同时关闭默认 Cube 的视口眼睛与渲染相机图标，保留 Camera 和 Light。如果没有相机列，在 Outliner 的过滤弹窗中启用该限制列。
4. 选中原始分子 View，找到 `Local Processor · Molecular Operations`。设置 `Force Field: MMFF94`，勾选 `Add Hydrogens`，保留 `Maximum Iterations: 200`，点击 `Generate 3D (ETKDG)`，等待新 View 和完成状态。生成按钮出现在绑定原始 SMILES 的结构上，后续派生结构不一定显示该按钮。
5. 同时隐藏原始 View 的视口和渲染，仍把它留在工程中。选中的生成 View 应有 9 个原子和 8 根键。

![实际生成的乙醇 View 及分子操作控件](../assets/2.5-tutorials/ethanol-generated.jpg)

## 能量、优化和 Kekulize

1. 对生成的 View 取消勾选 `Add Hydrogens`，因为氢原子已经存在。点击 `Energy` 并等待完成。该操作创建计算记录，不创建新构象；Project Browser 中可见 `Complete` 标记。
2. 点击 `Optimize`，等待派生 View；再对优化结果点击 `Kekulize`。每个操作完成后再执行下一步。保留旧 View，但关闭其眼睛和渲染相机，避免重叠。
3. 本次优化尝试了 10 次迭代，`optimizer_status: 0`。生成构象记录的 MMFF94 能量为 `-1.3368570639005273` kcal/mol；使用保存的原子映射和坐标独立计算，结果完全一致。优化构象独立能量为 `-1.336857063955483` kcal/mol，差异低于规定容差。生成结构已接近极小值时，不应强求肉眼可见的形状变化。

![Project Browser 中已完成的能量记录](../assets/2.5-tutorials/ethanol-energy.jpg)

参见[本次数字核查记录](../assets/2.5-tutorials/ethanol-science-check.json)。这些数值是固定后端和输入下的参考，不是实验测量。本例乙醇只有单键，`Kekulize` 验证操作执行及连接关系保留，不覆盖芳香共振处理。

## 显式 Apply 一次编辑，并保留来源

1. 选中最新 View，用小键盘 `.` 聚焦，按 Tab 进入 Edit Mode，使用顶点选择。必要时通过视口工具栏启用 X-ray，取消其他顶点选择，再选一个氢原子顶点。本次选择的是索引 5，在当时视角中位于左上方；相机角度不同，屏幕位置会改变。
2. 依次按 `G`、`Z`，输入 `0.15`，按 Enter 确认。不要缩放或旋转分子对象。按 Tab 返回 Object Mode。
3. 在 `Molecular Mesh Editing` 点击 `Apply Mesh as New Structure`，等待派生 View。它发布新的 Structure，同时保留原 Structure 和 View。Apply 完成前，局部网格草稿还不是权威科学数据。
4. 隐藏前一个 View 的视口和渲染，只显示最新编辑结果，再关闭 X-ray。不要通过删除旧 View 来掩盖意外变化。

![实际 Apply 完成后选中的派生 View](../assets/2.5-tutorials/ethanol-apply.jpg)

工程现在包含 5 个 Structure 和 5 个匹配的 View。只有索引 5 的氢原子移动了约 `[0, 0, 0.15]` Å，浮点舍入在 `1e-7` Å 内；原始数组及前一个 View 的绑定和坐标均保持不变。最终成图属于编辑后的几何结构，此前能量记录属于此前构象，不能改标为这张图的能量。

## 样式、相机与图像

1. 选中编辑后的 View，进入 `Geometry Nodes`。鼠标放在节点编辑器中，按 `Ctrl+Space` 放大区域；节点不在视野内时按 Home。在已有 `CH_Ball and Stick` 节点将 `Subdivision` 改为 `5`。输入数字前用 `Ctrl+A` 全选文本，Enter 确认，再用 `Ctrl+Space` 恢复布局。
2. 回到 `Layout`，关闭侧栏。小键盘 `1` 切到 Front，再用 `Ctrl+Alt+小键盘 0` 对齐 Camera。选中 Camera，将焦距设为 `35 mm`。检查构图，让每个原子周围留有空间。
3. 输出设置为 `2400 × 1800`、`100%`。选择 Light：位置 `(0, -5, 0)`、Point 类型、Power `5000`、Radius `0.1`。在 World Surface 保留 Background Strength `1`；打开 Color，选择 HSV 的 **Perceptual**，将 Value 设为 `0.6`，Hue、Saturation 保持零。这些属于 Blender 显示设置，不是科学单位。
4. 选择 `Cycles`、CPU、Render `Max Samples: 256`，启用渲染降噪，保留默认噪声阈值 `0.01`。按 F12 等待完成，在 Render 窗口按 Home 查看全图。检查 9 个原子都可见；最初偏向一侧的灯光导致两个氢原子区域与背景难以区分。
5. 使用 `Image → Save As…` 将 `ethanol-cycles.png` 保存到工程旁边。核对 PNG 格式和目录，回主窗口后用 `Ctrl+S` 保存工程。

## 工程交接与恢复

将 `ethanol.blend` 与完整的 `ethanol.cbq` 目录放在一起。正常退出本教程 Blender 进程，再用新进程打开保存文件。同一时间只运行一个教程实例。检查选中的 View、5 个 Structure 和保留的 View；旧 View 被隐藏是有意的。

如果打开工程后出现空的 `Render Result` 窗口，关闭该辅助窗口即可看到主场景。Render Result 不等于已经保存的 PNG；查看持久化图像请打开 `ethanol-cycles.png`，或按 F12 重新渲染。

复制或移动时携带**整对文件**，包括 CBQ 的全部数组。派生 View 缺失时，选中它并使用 `Rebuild Selected View`；不要删除权威 NPY 数组。用新进程打开副本 `.blend`，核对所有数组路径均位于相邻的副本 CBQ 目录下。

可用以下公开命令检查完整性，请替换示例路径。预期 `status: success`；validate 不代表化学正确、图像质量通过或人工可复现。

```powershell
chemblender-prepare validate "D:\ChemBlenderLessons\T02\ethanol.cbq" --json
```

操作失败时，先保留诊断和上次保存的整对工程，再重试。没有 `Generate 3D` 时，选择绑定原始 SMILES 的 View。渲染中结构拥挤时，检查旧 View 的渲染相机图标。打开工程缺少数组时，恢复完整的相邻 CBQ 目录；不要编造坐标，也不要把删除权威数组当作缓存修复。

MMFF94 是分子力场；ETKDG 生成合理构象，不证明全局最低能量，也不是量子计算。能量比较必须使用同一分子、原子映射、单位和力场。

## 验证附录

当前重放使用 Blender 5.1.1、Standard Prepare 0.1.0 和 RDKit 2026.03.3。Extension SHA-256：`a1e2da79253d505b60daa42aa465eb725cdd1eba00e6c81ce4082102a62d0f28`；Prepare wheel SHA-256：`b736bc61ecdbee77f61696576c98092afc7352a9af16b4367bfd3c2e3159af3a`。[当前候选适用性记录](../../../examples/tutorials/2.5.0/T02-current-candidate-check.json)覆盖固定科学数值、Apply、渲染、processor 故意不可用时的移动工程重建，以及数组路径指向副本目录的干净冷重开。GUI JPEG 保持历史原生截图身份；[T02.current-execution-supplement.json](../../../examples/tutorials/2.5.0/T02.current-execution-supplement.json)记录当前 CLI/Operator 重放，不会把它改标为直接 GUI。[媒体来源与哈希](../assets/2.5-tutorials/provenance.json)单独保存。人工独立复做尚未完成；本地 review package 只供审阅，不是分发制品。
