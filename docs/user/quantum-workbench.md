# 波函数工作台

Project Browser 的 `Wavefunction` 控件把 FCHK/Molden 中的轨道、密度矩阵和核电荷连接到外部数值 worker，再将完整计算结果保存为项目中的 `Grid3D`。

当前实现包括轨道浏览、单轨道求值、电子/自旋密度和 ESP，以及任意切片、线剖面、数值导出和轨道批量出图。[水分子示例](../../examples/quantum-workbench/README.md)提供完整场景、科学数据和可重放验证脚本。

## 配置数值环境

展开 `Worker Setup`，选择已经准备好的独立 Python 环境和 ChemBlender 开发仓库。安装扩展本身不会安装 IOData、GBasis，也不会向 Blender 的 Python 自动添加这些包。

| 设置 | 内容 | 用途 |
| --- | --- | --- |
| Worker Python | 独立环境的 `python.exe` | 运行 IOData 和 GBasis |
| Worker Repository | 含 `worker/runner.py` 的 ChemBlender 仓库根目录 | 与扩展配套的 worker 实现 |
| Step (bohr) | 相邻采样点的距离 | 控制网格分辨率 |
| Origin / Grid Counts | 起点和三个方向的采样点数 | 控制计算区域 |
| Padding (bohr) | 分子包围盒向外扩展的距离 | `Fit Grid to Molecule` 的边界余量 |
| Memory Budget (MiB) | 提交任务前检查的估计内存预算 | 拒绝超过预算的网格 |

仓库的 Windows 数值基准使用 Python 3.12，以及[固定依赖清单](../../.github/constraints/gbasis-py312.txt)。使用当前项目已有环境时直接填写路径；创建环境或安装依赖需遵循仓库的授权规则。

本地开发环境已按该清单准备在 `.agents/cache/gbasis-py312/Scripts/python.exe`。它属于项目缓存，不随 Extension ZIP 分发。Windows 上若临时路径过长，导入会在启动 worker 前提示缩短 Blender Preferences 的 Temporary Files 路径；重开项目后再导入。

内存估计包括输出数组和常见临时数组，不包括已打开项目的数组、输入快照和第三方后端的额外开销。ESP 的 AO-pair 积分比单轨道求值需要更多工作内存；点块大小会随基组大小缩小。计算区间、步长和输入文件决定科学结果，不能只依据图像是否平滑选择网格。

## 导入与轨道选择

1. 点击 `Import FCHK / Molden`。该入口使用配置的外部 Python 解析，并保留原始文件名、路径、哈希和解析来源。
2. 在 Project Browser 选择 Orbital Set，查看编号、能量、占据、自旋、来源和科学网格缓存状态。界面编号从 `1` 开始，派生记录中的 `orbital_index` 从 `0` 开始。
3. unrestricted 轨道可切换 `alpha` / `beta`。`HOMO` / `LUMO` / `SOMO` 按钮仅在现有能量和整占据足以确定时出现；缺失或分数占据保留原数值，不补标签。不同自旋通道的相同编号不代表一对相同空间轨道。
4. 调整 Step 与 Padding，点击 `Fit Grid to Molecule`，检查起点、终点、点数和对应操作的内存估计。
5. 点击 `Evaluate Selected MO`。每次只计算当前轨道；成功后在 Grid3D 控件创建 `Signed Surface`，分别显示正负相位。

复数轨道和 generalized spinor 当前禁用求值。`cached` 表示当前来源和网格参数已有科学 Grid3D；VDB 是可重建的显示缓存。更改计算区域、来源修订或派生版本后，旧结果不会冒充当前缓存。

## 密度和 ESP

- `Electron Density from Occupations` 根据明确的轨道占据数合成总电子密度。
- 已有 one-RDM 可直接计算 total 或 spin density；界面同时显示其 SCF/post-SCF 层级和实体标识。
- ESP 使用 total RDM 和同一 Structure 的显式 `nuclear_charge` 数据集。应选择源文件给出的有效核电荷；原子序数不替代 ECP 下的核电荷。
- Molden 缺少原始 total RDM 时，`ESP from Occupations` 要求显式选择来源的密度层级，再从轨道占据数派生矩阵。只有知道源计算属于 SCF 或 post-SCF 时才选择相应项；整数占据本身不能证明计算层级。派生矩阵与 ESP 一起成功才进入项目，并分别记录来源。

ESP 核位置具有奇点。网格含核位置或落入核排除半径时会给出诊断，调整起点/步长后重算；不能把核电势静默置零。密度面与 ESP 场需要匹配结构、单位和完整网格变换，当前不做隐式重采样。

## 属性映射、切片与剖面

在 Grid3D 控件中选择表面网格的 Dataset Index；属性面另选属性 Grid 及其 Property Dataset Index。
两侧必须属于同一结构并共享完整网格变换。关闭 Symmetric 后可分别设置 Color Min/Max；
跨零范围的中性色始终对应零。属性面旁的色标按钮使用属性场的 dataset、单位和同一范围。

`Fit Slice / Profile to Grid` 从完整仿射网格选择中心平面和对角剖面，再按需调整：

| 参数 | 单位/含义 |
| --- | --- |
| Slice Origin | 绑定 Grid 的科学坐标，bohr 或 angstrom |
| Slice U / V | 平面两条完整边的向量，可旋转或倾斜，不是单个 pixel 步长 |
| Slice Counts | 两个方向的点数，包含端点 |
| Profile Start / End | 科学坐标中的两端点 |
| Profile Samples | 包含两端点的采样数 |
| Profile Radius | 显示线条半径，angstrom |
| Colorbar Width / Height | 显示色标尺寸，angstrom |

创建 Slice、Profile 或 Colorbar 后，选中其主对象可加载已保存参数、显式重建或导出 CSV。
修改控件影响下一次创建；已有 View 按自己的 preset 设置保存。科学采样共用三线性插值；
越界切片留透明孔，剖面断线，CSV 的无效值留空并写入 `valid_mask=0`。非有限坐标、退化平面
和零长剖面会被拒绝。显示 View 最多包含 1,000,000 个采样点，提交前显示点数和采样数组估计。

移动、旋转或缩放 View 不改变其科学参数，也不改变 CSV 数值。CSV 的首行 JSON 元数据记录
来源 UUID/revision、dataset、原始 affine、单位和采样参数；使用普通 CSV 工具读取时跳过首行。
独立色标使用同一色图，并显示范围、单位及范围内的零点；调整表面范围后，以相同范围重新创建色标。
切片和色标的颜色使用 emission，不随灯光强度变化；表面保留三维光照。出图仍受 Blender 的 Color Management 设置影响。

## 顺序导出轨道图片

在 `Orbital Images · Current Spin and Grid` 中输入编号，例如 `5,6` 或 `3-6`，选择尚不存在的输出目录，再设置相位阈值、颜色和透明度。输出父目录必须已经存在。

先将场景相机对准分子的科学坐标位置（显示单位 angstrom）。导出使用固定相机、当前自旋通道和计算网格；每张临时创建当前轨道及其结构，已有视图暂时隐藏，完成后恢复。已移位排版的总览视图不改变导出时的科学坐标位置。

| 设置或产物 | 含义 |
| --- | --- |
| Orbitals (1-based) | 按填写顺序处理，去掉重复编号；每次计算一个未缓存轨道 |
| Phase Isovalue / Phase Colors / Opacity | 所选轨道统一使用的 signed-surface 参数 |
| `images/` | 当前通道各轨道的 PNG |
| `display.json` | 相机、渲染设置、网格绑定、轨道能量/占据、阈值和相位颜色 |
| `manifest.json`、`report.md` | 科学来源、派生记录、图片与显示参数的哈希 |

成功计算的科学网格逐项进入项目；全部图片和报告成功后才发布输出目录。取消、渲染失败或源网格改变时清理暂存图片。`Cancel Image Export` 或 `Esc` 在阶段之间取消；当前单张 Blender 渲染结束后才继续处理取消。批量导出暂时关闭 compositor 和 sequencer，避免场景的 File Output 节点写到其它位置，结束后恢复原设置。

## 失败、取消和旧视图

运行任务时可使用取消入口或 `Esc`。数值 worker 写入 session 内的独立项目副本；主线程核对输入修订和完整输出后一次提交。失败、取消或输入在计算期间变化时不发布半成品。

旧 `property_on_surface` v1 视图会标记需要重建。点击 `Rebuild View` 后，density 网格负责生成几何，property 网格只参与采样与着色。新资源成功创建后才替换原视图；重建失败保留原对象和诊断。

保存项目时继续使用[既有 `.blend + .cbq` 流程](project-sidecar.md)。科学数组来自 sidecar；显示对象、节点和 VDB 的存在不代表源数组已经保存。
