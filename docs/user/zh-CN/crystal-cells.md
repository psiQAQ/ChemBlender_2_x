# T04：晶体位点、占位与已有金刚石超胞

本课为执行中草稿。保存后的科学数据、ASE 转换和原位／移动后冷重开已通过验证。Blender 导入和构图复用了此前验证过的操作，通过 MCP 重放；晶胞截图来自实际运行。完整逐步 GUI 留证、视觉质量和人工独立复做尚未通过。

![声明晶胞中的共晶源位点](../assets/2.5-tutorials/crystal-cocrystal.png)

晶胞中的大片空白是当前表示的结果：这里显示 64 个源文件不对称位点，没有按对称操作展开完整晶体。部分占位使用透明度表达，无序重叠位点保留。草稿成图仍有局部棱面。

## 前提与固定输入

先完成[安装](installation.md)和[首课](first-aspirin.md)。本课使用 Blender 5.1.1、prepare 0.1.0，Extension ZIP SHA-256 为 `963b905f3e5ee3c5fc1fa53a1ccefd5c60616d89ac77977efe4afdbed066426a`。此版本包含周期结构 Create View 修复，较早候选可能缺少晶胞显示。prepare wheel 保持 `3f1d93acd0eefd29bc304527007b8d53bd0aa3b508e97aea0a18f4624ee62c3e`。

下载 [COD 4503272 CIF](../../../examples/user-workflows/inputs/cif/cod-4503272-caffeine-cocrystal.cif) 与[金刚石 CONTCAR](../../../examples/user-workflows/inputs/poscar/cod-9012293-diamond-2x2x2.CONTCAR)，同时保留含输入哈希和容差的[案例规格](../../../examples/tutorials/2.5.0/T04.case-spec.json)。CIF 是 CC0 的 COD 输入；金刚石输入是仓库已有的 COD 9012293 常规晶胞 2×2×2 派生结构，并非本课新算的模拟结果。

| 核对项 | 共晶 | 金刚石 |
| --- | --- | --- |
| 源位点 | 64 个不对称位点 | 64 个碳原子 |
| 晶胞边长，Å | 6.6439、23.2514、33.5615 | 三轴均为 7.1338 |
| 晶胞角度 | 三角均为 90° | 三角均为 90° |
| 占位／无序 | 23 个部分占位；9 个有无序组的位点 | 完全占位 |
| 源文件含义 | 声明 C m c a、编号 64、16 个操作 | Direct 分数坐标；常规晶胞 8 原子 × 8 晶胞 |
| 速度边界 | 不作速度声明 | 人工写入的 64×3 零数组；原生 Reader 保留 unknown 单位 |

## Prepare 与检查

新建目录，例如 `D:\ChemBlenderLessons\T04`。以下公开 CLI 路线已用固定输入实际执行。替换为本机输入路径，每次转换指定新的输出目录。

```powershell
chemblender-prepare inspect "D:\ChemBlenderLessons\T04\cod-4503272-caffeine-cocrystal.cif" --reader cif --json
chemblender-prepare convert "D:\ChemBlenderLessons\T04\cod-4503272-caffeine-cocrystal.cif" --reader cif -o "D:\ChemBlenderLessons\T04\cocrystal.cbq" --json
chemblender-prepare validate "D:\ChemBlenderLessons\T04\cocrystal.cbq" --json
chemblender-prepare inspect "D:\ChemBlenderLessons\T04\cod-9012293-diamond-2x2x2.CONTCAR" --reader poscar --json
chemblender-prepare convert "D:\ChemBlenderLessons\T04\cod-9012293-diamond-2x2x2.CONTCAR" --reader poscar -o "D:\ChemBlenderLessons\T04\diamond.cbq" --json
chemblender-prepare validate "D:\ChemBlenderLessons\T04\diamond.cbq" --json
```

预期 `status: success`。原生转换保留了 CIF 行顺序、标签、占位、无序和源文件字节。独立以源分数坐标乘晶格矩阵，结果与保存的笛卡尔坐标完全一致；预先固定的绝对容差为 `1e-7` Å。Blender 显示顶点精度较低，冷重开时低于 `1e-6` 的显示误差不意味着权威数组被改写。

以下 Prepare GUI 步骤已用 wheel SHA-256 `b736bc61ecdbee77f61696576c98092afc7352a9af16b4367bfd3c2e3159af3a` 验证。本文其他 Blender 图片和保存工程仍保留各自较早的制品归属。

1. 在 **操作** 中选择 `inspect`，将 **输入文件 / CBQ** 设为下载的 CIF，**Reader ID** 设为 `cif`，点击 **执行**。预期显示一个 CIF block 和上表晶胞值。
2. 选择 `convert` 后布局会变化：在 **新输出文件 / CBQ 路径** 填入新的 `cocrystal.cbq`，确认 Reader ID 仍为 `cif`，点击 **执行**。预期 `status: success`，并提示无序组、部分占位已保留，对称性派生被禁用。

![实际 CIF 转换保留占位和无序信息](../assets/2.5-tutorials/crystal-prepare-cif.jpg)

3. 对 CONTCAR 重复 `inspect` 与 `convert`，Reader ID 使用 `poscar`，输出另设为 `diamond.cbq`。产物包含 64 个碳原子，人工写入的零速度数组保留 `unknown` 单位。
4. 对照 ASE 前，先按下节配置科学 route。保留 CONTCAR 输入，将 Reader ID 改为 `ase-structure`，输出另设为 `diamond-ase.cbq`，点击 **执行**。保留不支持 atom-array 的诊断：这个产物包含结构和晶胞，没有规范化的速度数据集。

![实际 ASE 转换报告原子数组边界](../assets/2.5-tutorials/crystal-prepare-ase.jpg)

检查记录：[CIF GUI 与科学核对](../../../examples/tutorials/2.5.0/T04-run009-cif-gui-check.json)、[CONTCAR GUI 与科学核对](../../../examples/tutorials/2.5.0/T04-run009-diamond-gui-check.json)、[ASE GUI 与科学核对](../../../examples/tutorials/2.5.0/T04-run009-ase-gui-check.json)。源文件哈希与坐标比对均通过；独立人工复做仍待完成。

## 导入并取景完整晶胞

1. 在新的教程场景中打开 `ChemBlender` 侧栏，将 `CBQ Package` 设为 `cocrystal.cbq` 并确认路径，依次使用 `Preview CBQ`、`Import CBQ`。
2. 在 Project Browser 选择 Structure。进入 `Scientific Representation`，使用 `Automatic`、`Research`，点击 `Create View`。预期生成 `ChemBlender Periodic Structure`，以及 Cell、Site Occupancy、Thermal Ellipsoids 显示子对象。源位点表示保留声明的晶胞和占位，不生成对称复制。
3. 同时关闭默认 Cube 的视口和渲染可见性。在 Outliner 展开周期结构对象，选中父对象及三个显示子对象；鼠标移至视口，按小键盘 `.` 取景。只对原子取景可能裁掉晶胞。

![Operator 重放后实际截取的完整晶胞取景](../assets/2.5-tutorials/crystal-cell-view.jpg)

4. 将 `cocrystal.blend` 保存到完整 `cocrystal.cbq` 目录旁。在同一个教程进程中新建场景，对 `diamond.cbq` 重复操作，保存为 `diamond.blend` 和 `diamond.cbq` 配对工程。

## 显示细化与渲染

本次选中的是 **Site Occupancy 显示子对象**，在 Object Mode 按 `Ctrl+2`，在 Geometry Nodes 之后添加原生 Subdivision Surface，视口与渲染级别均为 2。这个操作先通过 Computer Use 实际尝试，再为另一结构重放。它只修改派生显示网格；不要为外观细化点击 Apply Mesh as New Structure。

将占位材质的 Principled roughness 设为 `0.35`，保留元素颜色和占位 alpha 的连接。这与 Ball and Stick 节点的 Subdivision 控件不同。当前成图仍有棱面，添加细分本身并不能证明平滑着色或科学准确性。

| 渲染设置 | 共晶 | 金刚石 |
| --- | --- | --- |
| 相机位置 | (46.5121, -6.6301, 39.4282) | (18, -24, 18) |
| 相机朝向 | XYZ 欧拉角弧度 (1.108752, 0, 1.154878) | 对准晶胞中心 (3.5669, 3.5669, 3.5669) |
| 焦距 | 35 mm | 50 mm |
| Point 灯 | 与相机同位置，Power 100000，Radius 5 | 与相机同位置，Power 100000，Radius 2 |
| World Background | 线性 RGB (0.12, 0.12, 0.12)，Strength 1 | 线性 RGB (0.25, 0.25, 0.25)，Strength 1 |
| 输出 | 2400×1800、100%、PNG | 2400×1800、100%、PNG |
| 引擎 | Cycles CPU、256 samples、降噪 | Cycles CPU、256 samples、降噪 |

这些是 Blender 显示数值，World 线性 RGB 不等于拾色器中的 Perceptual HSV Value。在按 F12 前，通过相机视图检查所有晶胞边缘。完成后用 `Image → Save As…` 单独保存图像，再保存配对工程。构图与材质参数使用 MCP 重放，完整手动面板路径仍待验证。

![已有的 64 碳原子金刚石超胞](../assets/2.5-tutorials/crystal-diamond.png)

图像显示的是给定超胞，不能据此声称验证了超胞生成器、键推断、分子动力学或更高分辨率科学计算。

## ASE 对照与科学边界

可选后端路线是本案例必测项。GUI 实测在配置的 `scientific` Python route 中独立安装同一 prepare wheel，复用现有 ASE 3.29.0／NumPy 2.2.6 依赖。本地测试环境引用已有依赖目录，不能当作可移动环境。将 `CHEMBLENDER_PREPARE_CONFIG` 中的 `python.scientific` 指向已核验的处理器环境；转换前运行 `doctor`，确认 `inspect` 显示 `scientific: available`。Standard 本身不提供 ASE。[route 验证记录](../../../examples/tutorials/2.5.0/run008-scientific-route-check.json)说明依赖复用边界；最新 wheel 与 GUI 的对应关系见上方记录。

[ASE 数值检查](../assets/2.5-tutorials/crystal-ase-science.json)记录晶胞与坐标误差均为零。保留 `ase-structure.unsupported` atom-array 诊断：这条路线没有验证速度单位归一化。本案例的 unknown 单位零速度边界由原生 Reader 结果验证。

更多显示多边形可以改善轮廓，但不会增加科学采样点。更细的体数据必须来自单独记录的后端计算，固定单位、范围、间距并检查收敛。本课两个晶体输入都不是体网格。不要为外观消除无序、修改占位、静默补键，也不要把声明的对称性写成独立测定结果。

## 工程交接与恢复

正常退出教程进程，再以新进程打开保存的配对工程。移动时同时带走 `.blend` 与完整同名 `.cbq` 目录。原位与移动副本的四次串行冷检查通过：64 原子、12 条晶胞边、保留的 2 级细分、指向新目录的数组路径，以及未改变的科学哈希。见[恢复记录](../assets/2.5-tutorials/crystal-cold-recovery-refined.json)。

若没有晶胞，检查候选版本，并在创建 View 前选中周期 Structure。若晶胞被裁切，将全部显示子对象纳入取景。若移动后缺少数组，恢复完整配对目录。保留单独保存的 PNG；冷重开出现空 Render Result 不代表 PNG 丢失。

在独立副本中清空四个所属显示网格后，公开 `REBUILD` Operator 恢复了 64 个位点和 12 条晶胞边，科学数组未变；两个重建工程再次冷重开也通过。见[派生几何恢复记录](../assets/2.5-tutorials/crystal-cache-recovery.json)。这是原生 Operator 重放，不是 GUI 删除演示。重建会替换显示对象，手工添加的 Subdivision modifier 随后不再存在。重建后按本课重新设置外观细化，并保留原始细化工程作为视觉参照。

完整 GUI 留证、视觉质量、人工独立复做和可分发案例包仍待完成。在这些门槛及视觉审阅通过前，本课保持草稿。[媒体来源](../assets/2.5-tutorials/provenance.json)将本候选与较早课程分别记录。

## 更新后的本地审阅工程（run-009）

以下成图使用 prepare wheel `b736bc61…` 与 Extension ZIP `a1e2da79…`；上方早期截图保留原制品绑定。为派生的占位与热椭球显示添加了平滑面法线，保留元素颜色和占位透明度，同时保留二级细分、粗糙度 0.35 及上表渲染参数。这项场景编辑通过 MCP 完成，尚未验证手工节点编辑器操作路径。

![COD 4503272：64 个非对称位点，保留部分占位与无序](../assets/2.5-tutorials/crystal-cocrystal-run009.png)

咖啡因–丁二酸–氯仿共晶：64 个非对称位点，其中 23 个部分占位、9 个带无序组；晶胞 6.6439 × 23.2514 × 33.5615 Å。显示源位点，未展开对称等价位置，未推断键。

![COD 9012293 派生金刚石：输入已有的 64 碳原子超胞](../assets/2.5-tutorials/crystal-diamond-run009.png)

输入已有的 2×2×2 常规晶胞超胞：64 个碳原子、7.1338 Å 立方晶胞。人工附加零速度单位未知，不是生成超胞演示或分子动力学结果。两图均为 2400×1800、Cycles 256 samples；平滑不提高科学数据分辨率。

原工程、搬移副本和 ZIP 解压副本均通过独立进程冷检查，科学数组未变。参见[共晶检查](../../../examples/tutorials/2.5.0/T04-run009-render-cold-check.json)、[金刚石检查](../../../examples/tutorials/2.5.0/T04-run009-diamond-render-cold-check.json)与[本地包记录](../../../examples/tutorials/2.5.0/T04-run009-package-check.json)。本地 `run-009/T04-review.zip` 包含两套配对工程、原始输入及许可说明、成图和双语交接说明；它是审阅包，不代表最终验收通过。

[新版重建检查](../../../examples/tutorials/2.5.0/T04-run009-rebuild-check.json)仅清空副本的派生网格。REBUILD 恢复 64 个位点和 12 条晶胞边，但移除了手工细分和平滑节点。显式重建后重新施加外观编辑；普通冷重开会保留这些设置。原精修工程未变，人工独立复做与剩余 GUI 证据仍待完成。
