# 首课：阿司匹林，从 MOL 到可重开的科研图

本课已完成 Agent 的真实 GUI 操作、科学核对、Cycles 渲染与独立进程冷重开，仍待人工仅凭教程复做。截图来自安装了教程候选修复的 Blender 5.1.1；它们不代表旧发布 ZIP 的操作证据。

![阿司匹林实际 Cycles 渲染](../assets/2.5-tutorials/aspirin-cycles.png)

图中灰色为 C、红色为 O、白色为 H，双杆表示原文件的双键。球的大小用于显示，不代表电子密度。这里保留默认网格的可见面片；这是一张首课操作成图，尚未经人工图像质量验收。

## 前提与固定输入

先完成[安装与诊断](installation.md)。本课只需 Standard 处理环境，不需要专业计算后端。教程候选 ZIP 的 SHA-256 为 `a5556df69ce1a94cf10ad112babe7611213017e9998083a8d1b2560b7a38eef8`；prepare 0.1.0 wheel 为 `3f1d93acd0eefd29bc304527007b8d53bd0aa3b508e97aea0a18f4624ee62c3e`。

下载[固定的 AIN MOL 输入](../../../examples/user-workflows/inputs/mol/ain-aspirin-v2000.mol)，放入自己的课程目录，例如 `D:\ChemBlenderLessons\T01\`。输入采用 CCD AIN 的 ideal coordinates；来源与许可见[输入语料说明](../../../examples/user-workflows/README.md)。它不包含量子计算或实验电子密度。

| 检查项 | 固定值 |
| --- | --- |
| 输入 SHA-256 | `32bd93a45508c66d28205bfd423068a41434022a7cc7c312cb0a983c17178bf4` |
| 原子数 | 21：C 9、O 4、H 8 |
| 原文件键数 | 21 |
| 科学坐标单位 | Å（`angstrom`） |
| 转换坐标绝对容差 | `1e-7` Å；本次实测最大差为 0 |

## 用 Prepare 检查和转换

1. 打开 `chemblender-prepare-gui`。在“操作”选择 `doctor`，点击“执行”。预期显示“诊断完成”，报告 `status: passed`。未配置专业环境的 warning 不影响本课。
2. 选择 `inspect`，在“输入文件 / CBQ：每行一个路径”填入 MOL 的完整路径，点击“执行”。预期 `status: success`，Reader 为 `mol`，识别到一个 `AIN` 记录。该步骤不创建 CBQ。
3. 将“操作”改为 `convert`。保留输入，在“新输出文件 / CBQ 路径”填入新目录，如 `D:\ChemBlenderLessons\T01\aspirin.cbq`。不要选择已有输出。
4. 输入类型保留 `files`，Reader ID 留空，校验模式保留 `balanced`，不勾选“转换时推断缺失的键”。点击“执行”，等待“完成”和 `status: success`。磁盘上应出现 `aspirin.cbq\manifest.json` 与 `arrays\`。

![Prepare 的实际转换完成报告](../assets/2.5-tutorials/aspirin-prepare-convert.jpg)

## Preview、Import 与 View

1. 在新 Blender 场景进入 `Layout`。将鼠标放进 3D 视口，按 `N`，点击侧栏 `ChemBlender`。如果标签被截断，向左拖动侧栏左边缘。
2. 在 `CBQ Package` 填入刚生成的 `aspirin.cbq` 完整路径，按 Enter，再点击 `Preview CBQ`。新场景预期显示 7 个新实体：Sources 1、Source Revisions 1、Structures 1、Topologies 2、Molecular Records 1、Provenance 1。

![实际 CBQ 预览](../assets/2.5-tutorials/aspirin-cbq-preview.jpg)

3. 点击 `Import CBQ`，核对确认框后点 `OK`。Project Browser 中选中 `Structure`；视口此时还不一定有分子。
4. 向下滚动到 `Scientific Representation`，保留 `Representation: Automatic`、`Template: Research`，点击 `Create View`。出现 `ChemBlender Structure`。
5. 在 `Topology` 中，对 `Explicit File · Complete · 21 bonds` 点击 `Show`。分子应出现键；这个按钮只改变 View 的拓扑显示。不要为了显示键点击 `Accept` 或执行 `Apply`。
6. 在 Outliner 选中本课新场景的默认 `Cube`，按 Delete 移除它。保留 Camera 和 Light。不要在自己的已有工程中照此删除对象。

## 构图、照明与 Cycles

1. 点击分子选中 View，将鼠标放进 3D 视口，按 `N` 收起侧栏，再按数字小键盘 `1` 到正面。使用 `Ctrl+Alt+数字小键盘 0` 将现有 Camera 对齐到当前视图。没有数字小键盘时，通过 `View` 菜单使用 Front 和 Align Active Camera to View 对应操作。
2. 打开 Output Properties，将 `Resolution X` 设为 `2400`、Y 设为 `1800`、比例为 `100%`。编辑数值时先 `Ctrl+A` 全选，再输入；Enter 确认。核对全部原子在相机框内，必要时调整相机距离。
3. 选中 Light，在 Object Properties 将 `Location Y` 改为 `-5`，其他默认位置保留（本次 X≈4.0762、Z≈5.9039）。在 Light Data Properties 将 `Power` 设为 `5000`。这些是 Blender 显示空间中的灯光参数，不是分子的科学坐标。
4. 在 Render Properties 选择 `Cycles`，将 Render 下的 `Max Samples` 设为 `256`。本次使用 CPU，默认降噪开启。
5. 按 `F12` 渲染。在独立 `Blender Render` 窗口内按 Home 完整显示图片。通过 `Image → Save As…` 保存 `aspirin-cycles.png` 到课程目录；确认目录、文件名和 PNG 格式后点 `Save As Image`。

`Cycles · Scientific Images` 面板的报告导出目前要求物理量数据集，本课的纯 Structure 使用 Blender 原生渲染。默认灯光位于分子背面时，碳原子会很暗；先检查灯的位置，再增加功率，不要改科学数组来补偿照明。

## 保存、交接和冷重开

1. 回到 Blender 主窗口，按 `Ctrl+S`，将工程保存为课程目录内的 `aspirin.blend`。确保它与 `aspirin.cbq\` 相邻且同名。
2. 正常退出本课 Blender 进程。重新启动 Blender，再打开 `aspirin.blend`；仅重新加载当前文件不算冷重开。
3. 核对分子 View、原文件 21 条键以及 Project Browser 中的 Structure。新建工程副本时，同时带走 `.blend` 和整个 `.cbq` 目录。整体移动与缓存重建是后续 T18 验收项，本课当前记录只证明原位置冷重开。

![新进程冷重开后实际 Project Browser](../assets/2.5-tutorials/aspirin-cold-reopen.jpg)

截图是 Computer Use 返回的原生 JPEG，未标注或重绘；成图是 Blender 保存的原生 PNG。[资源来源与哈希](../assets/2.5-tutorials/provenance.json)单独记录。2026-09-10 已确认执行版检查器接受原生 GUI JPEG，并检查文件签名、后缀与哈希；原研究包保持完整。格式检查不代替截图真实性或人工审阅。

## 错误恢复与科学边界

- `No project data`：先核对 CBQ 路径，执行 Preview，再 Import；导入后再选 Structure 创建 View。
- 只有球没有键：在正确的 Explicit File 拓扑行点击 `Show`。RDKit 整理拓扑和原文件拓扑是两个保留记录，不能混称。
- 图片局部被截掉：在 Render 窗口按 Home。如果完整图片仍截断，调整 Camera 构图后重新渲染。
- 重开缺少科学数据：检查相邻 `aspirin.cbq\manifest.json` 和 `arrays\` 是否完整。先恢复备份，不要删除权威数组。
- 原生渲染结果不会自动保存到 `.blend` 的 Render Result；交接时保留单独 PNG，重开后可再次渲染。

阿司匹林原子数、顺序、原文件键级和坐标已核对通过。显示球棒、灯光、相机、采样数只用于呈现；本课不声称完成能量优化、构象筛选或量子计算。人工复做与最终图像审阅尚未完成。
