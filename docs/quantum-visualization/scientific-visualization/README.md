# 科学量可视化操作手册

> **归档资格证据。** 本页冻结在 2026-09-09，不再作为 ChemBlender 2.5 日常教程，也不会替换为新 UI 截图。当前教程见[中文 2.5 SOP](../../user/zh-CN/blender-workflow.md)或 [English 2.5 SOP](../../user/en/blender-workflow.md)。

**最终验收稿 · 2026-09-09。** 本手册按 CBQ Viewer 与单一本地处理程序说明真实文件准备、科学量选择、表示和出图，包含 11 张实际 Blender 窗口截图。水、CH₃ 和 N 原子的 22 张 Research / Teaching 图片、PQR/rMD17 的 6 张静图、128 帧 PNG、4 段 MP4 与 5 个可重开工作台均已保留。统一处理程序还以真实 FCHK、VASP、WFX 和 phonopy 输入完成 wavefunction、Fermi、QTAIM、NCI 与 phonon 操作；各量的五层证据边界见[最终验收矩阵](#verification)。

可离线打开同目录 [index.html](index.html)。网页及图片需连同仓库相对目录一起保存；不用 CDN，不需要网络脚本。

<!-- TOC START -->
- [1. 准备与输入来源](#prepare)
- [2. 面板与共同操作](#workflow)
- [3. 轨道、总密度、自旋与差分密度](#wavefunction)
- [4. ESP、切片、剖面与色标](#esp)
- [5. ELF、LOL、RDG 与 NCI](#local-fields)
- [6. 原子标量、向量与结构](#atomic)
- [7. 分子振动、IR、Raman、UV-Vis 与 ECD](#spectra)
- [8. 轨迹与逐帧力](#trajectory)
- [9. Band、DOS 与 PDOS](#bands)
- [10. 晶格声子](#phonon)
- [11. Fermi surface](#fermi)
- [12. QTAIM 临界点与梯度路径](#qtaim)
- [13. Cycles 正式出图与动画](#render)
- [14. 保存、重开和缓存重建](#lifecycle)
- [15. 最终验收与检查清单](#verification)
- [16. 离线网页的构建与维护](#offline)
<!-- TOC END -->

<a id="prepare"></a>
## 1. 准备与输入来源

使用 Blender 5.1.0 或更新版本，通过 Extensions 安装 ChemBlender。最终无 wheel 快照在 Blender 5.1.1 / Python 3.13.9 私有 profile 中完成启停、reload、22 个 Reader、纯 Mesh 编辑、CBQ 导入导出、View 与保存重开验证；Blender 冷启动中 `rdkit` 和 `gemmi` 均不可导入。实际窗口截图来自同一 UI 的先前实操快照，截图包身份与最终包身份分别记录，不能相互冒充。

打开 3D Viewport，按 `N` 展开侧栏，进入 **ChemBlender → Project Browser**。在 Add-on Preferences 只配置一个 `processor_executable` 绝对路径并点击 **Test Processor**；Blender 不再分别配置 Worker Python、Repository、Fermi 或 critic2。外部程序负责第三方依赖和重计算，Blender 只持有 CBQ、显示对象与项目关联。

| 环境 | 用途 | 最终状态 |
| --- | --- | --- |
| Blender 5.1.1 自带 NumPy | CBQ Viewer、纯 Mesh 编辑、View、渲染和保存 | 私有 profile 通过；正式 ZIP 无科学 wheel |
| `chemblender-prepare` | 22 Reader、RDKit、wavefunction、Fermi、QTAIM、NCI、phonon | capabilities/Worker v1/doctor 与真实操作通过 |
| 外部处理程序配置文件 | 固定 wavefunction/scientific/fermi Python 与 critic2 路由 | 仅存在外部环境；路径不写入 `.blend` 或 CBQ |

处理程序环境版本、哈希锁和安装影响见[独立环境提案](../../../examples/scientific-visualization/dependencies/PROPOSAL.md)。此手册不触发安装；运行时能力以 **Test Processor** 或 `chemblender-prepare capabilities --json` 的真实结果为准。

以下路径均相对于 `examples/scientific-visualization/`。输入的固定 commit、原始 URL、字节数、SHA-256 和许可以[输入 manifest](../../../examples/scientific-visualization/input-manifest.json)为准，[输入说明](../../../examples/scientific-visualization/inputs/README.md)说明每份文件的边界。

| 真实输入 | 科学用途 | 身份与方法边界 |
| --- | --- | --- |
| [water_sto3g_hf_g03.fchk](../../../examples/scientific-visualization/inputs/wavefunction/water_sto3g_hf_g03.fchk) | H₂O MO、总密度、ESP | 头部明确 RHF/STO-3G；`g03` 文件名不证明原程序的精确版本 |
| [ch3_hf_sto3g.fchk](../../../examples/scientific-visualization/inputs/wavefunction/ch3_hf_sto3g.fchk) | CH₃ 自由基 α/β MO、自旋密度 | UHF/STO-3G；两通道分别选择 |
| [nitrogen-mp2.fchk](../../../examples/scientific-visualization/inputs/wavefunction/nitrogen-mp2.fchk) | N 原子 SCF / post-SCF RDM 差分 | UMP2-FC / 6-31G，multiplicity 2；不是 N₂，也不据此称为基态 |
| [h2o.molden.input](../../../examples/scientific-visualization/inputs/wavefunction/h2o.molden.input) | Molden MO、occupation 派生密度 | 标题声明 ORCA 转换器，未给出可直接确认的 SCF / post-SCF 层级 |
| `inputs/cclib/Gaussian/basicGaussian16/` 与 `ORCA/basicORCA5.0/` | dvb IR、Raman activity、TD 激发 | 各文件是独立计算，禁止拼接为同一 Calculation |
| [Gaussian09 dvb_td.out](../../../examples/scientific-visualization/inputs/cclib/Gaussian/basicGaussian09/dvb_td.out) | 有非零旋光强度的 ECD | length gauge；保留原始 `10⁻⁴⁰ erg·esu·cm/Gauss` 单位 |
| `inputs/silicon/bands/`、`inputs/silicon/dos/` | Si Band 与 DOS / PDOS | 路径计算与均匀网格计算独立，E_F 分别记录 |
| `inputs/phonopy/NaCl/` | NaCl 有限位移声子 | YAML、FORCE_SETS、BORN 与原始 VASP 力数据配套 |
| [water_sto3g_hf.wfx](../../../examples/scientific-visualization/inputs/wavefunction/water_sto3g_hf.wfx) | critic2 派生输入 | critic2 1.3.15 已据此生成并验收 ELF / LOL / NCI / QTAIM；原文件本身仍只是波函数输入 |

另两个分子项目复用既有语料：[APBS 蛋白–RNA PQR](../../../examples/user-workflows/inputs/pqr/apbs-protein-rna-nb.pqr)与 [rMD17 aspirin extXYZ](../../../examples/user-workflows/inputs/extxyz/aspirin-rmd17-32.extxyz)，来源见[用户流程 manifest](../../../examples/user-workflows/manifest.json)。前者保存原子电荷和半径；后者是有明确来源与单位转换的 32 帧子集。

在仓库根目录做只读输入核验：

```powershell
& .agents/cache/gbasis-py312/Scripts/python.exe -B examples/scientific-visualization/prepare_inputs.py --verify
```

**检查点：** 输入哈希匹配；处理程序 capability 与所需后端一致；没有把文件名、占据数或显示效果作为计算方法证据。

<a id="workflow"></a>
## 2. 面板与共同操作

1. **准备或计算科学数据。** 原始文件先用外部 `chemblender-prepare convert` 生成 CBQ；也可在 Project Browser 的 **Local Processor · Scientific Input** 选择 Reader/Input 后点击 **Run Local Processor**。QTAIM、NCI、phonon 使用同一区域的专业操作。任务异步运行，`Esc` 可取消；成功结果以新 UUID 追加并自动选中。
2. **选择科学实体。** 在 Project Browser 选择 Structure、Grid3D、Spectrum 等数据行。选中场景里的 Mesh 只代表选中了显示对象；计算与表示绑定仍以项目中的数据 UUID 和 revision 为准。
3. **建立表示。** 展开 **Scientific Representation**，选择 `Representation`，点 **Preset Defaults**，检查数据索引、单位和阈值，再点 **Create View**。需要第二份数据时显式选择 **Linked Dataset**。
4. **修改已有表示。** 在场景里选中 View 根对象，点 **Load Selected View**，修改面板参数，再点 **Update Style / Parameters**。**Rebuild Selected View** 按该 View 已保存的参数重建；它不等于重新计算波函数。

| 通用控制 | 作用 | 应核对的结果 |
| --- | --- | --- |
| Template：Research / Teaching | 研究与教学显示模板 | 改变材质、图形可读性及正式导出背景，不改变科学数组 |
| Light Quantitative Colors | 是否让光照影响定量颜色 | 定量读色时保持关闭，色标与表面使用一致色域 |
| Material Opacity | 表示的透明度 | 透明叠加会影响屏幕颜色，不能从混色反推数值 |
| Isovalue / Surface Isovalue | 选择等值面 | 单位来自数据；阈值变化不是电子数或性质变化 |
| Dataset Index、Mode / State Index | 选择数组通道或状态 | 这些索引从 0 开始；Wavefunction 的 Orbital Number 从 1 开始 |
| Color Minimum / Maximum、Symmetric Color Range | 定量映射范围 | 非对称范围也必须把颜色零点放到真实 0；截色不截数据 |

结构球和 CP 球用于表达形状。切片、色标、原子标量、曲线与文本采用不依赖场景灯光的显示方式；属性表面、NCI、Fermi 属性和 CP 属性可以启用光照，此时颜色只宜辅助观察形状。真正的体积表示使用 Volume shader；光学密度系数仅控制可见程度。

**检查点：** 记录源实体、数据集索引、阈值和单位。移动、旋转 View 后，Browser 中的科学数据及原始坐标不应改变。

下面是私有 Blender 5.1.1 中真实水 HOMO 5 的操作界面，已建立 View 并加载其参数：等值面阈值为 `0.06 bohr⁻³ᐟ²`，正负相位分别着色。下方 Project 显示 Connected / clean。界面截图用于定位按钮；正式 Cycles 图见各量的图集。点击截图可查看原尺寸，安装包哈希、项目身份和参数保存在[截图 manifest](screenshots/manifest.json)。

[![真实 HOMO5 的 Scientific Representation 参数与项目连接状态](screenshots/01-water-homo-scientific-view.png)](screenshots/01-water-homo-scientific-view.png)

<a id="wavefunction"></a>
## 3. 轨道、总密度、自旋与差分密度

用统一处理程序导入 FCHK / Molden，并在 Project Browser 选择 OrbitalSet。核对 `Orbital / Energy (hartree) / Occupation / Spin / Grid cache`；HOMO、LUMO、SOMO 按当前通道占据信息标记，未知字段保持 unknown。MO、密度和 ESP 的 Apply/Recompute 走同一异步控制器。

1. 设置 **Origin (bohr)**、**Step (bohr)**、**Grid Counts**、**Padding (bohr)**，点击 **Fit Grid to Molecule** 可初始化边界。网格末点为 `origin + step × (count − 1)`。
2. 检查点数与内存估算。先用较粗网格检视，再按需要缩小步长和扩大边界做独立数值比较；本例没有提供积分收敛证明。
3. 选择 Channel 和 **Orbital Number**，点 **Evaluate Selected MO**。结束后使用新 Grid3D，或点 **Use Cached MO Grid** 复用匹配源与网格的已有结果。取消通过 **Cancel Calculation**，成功前不会发布半个数组。

下图在真实水轨道表中选择 restricted HOMO 5，能量列保持 hartree；Grid cache 表示当前源和网格已有匹配结果，并不意味着整张轨道表都已计算。网格步长为 0.25 bohr，点数为 56×49×60，共 164640 点。此次 GUI 示例采用原点 `(-5.9075,-5.9275,-6.7025)` bohr 的偏移网格，水密度与 ESP 使用同一网格；[实际操作记录](screenshots/operations.json)保存参数和避开核奇点的原因。

[![波函数轨道表、HOMO 选择、网格参数与计算入口](screenshots/07-water-wavefunction.png)](screenshots/07-water-wavefunction.png)

| 科学量 | 计算与含义 | 表示和本例起点 |
| --- | --- | --- |
| 实数 MO ψ | 带正负相位的振幅，单位 `bohr⁻³ᐟ²`；不是密度 | **Signed scalar isosurface**，同时看 ±阈值。水 HOMO 5 可从 0.06、LUMO 6 从 0.05 开始；这些是显示选择 |
| α / β MO | 开壳层两套轨道；相同序号不保证能量或空间形状相同 | CH₃ 分别选择 α、β HOMO；比较时固定相同阈值、视角和比例 |
| 总电子密度 ρ | `e/bohr³`，可由 occupation 或明确 total RDM 得到 | **Electron Density from Occupations** 或 `Total Density · level`；用正等值面、**Grid volume**、切片 |
| 自旋密度 ρ_α − ρ_β | `e/bohr³`，正负是通道差 | 选择 Spin RDM 对应 `Spin Density · level`；CH₃ 的 ±0.008 可作为观察起点 |
| 差分密度 ρ_left − ρ_right | `e/bohr³` 或一致的密度单位，正负表示所定义差值 | 在左总密度上选 Right Density，点 **Derive Left − Right Density**；N 示例为 MP2 − SCF，±0.0007 仅是显示阈值 |

MO 的整体正负相位可随轨道约定翻转，不能将红蓝区域直接解释为电子的正负电荷。总密度与自旋密度不同；总密度不是单个轨道的振幅。

RDM 密度保留 `SCF` / `POST_SCF` 和 `total` / `spin` 标记。整数 occupation 不足以推断方法层级；NTO 权重也不能当作占据数。当前真实 complex / spinor 波函数会被拒绝，不能先丢虚部再绘制。

**总密度界面检查：** 下图使用真实水密度，阈值 `0.08 e/bohr³`；坐标与数值单位分别显示。密度无负区时，不会因为选择了 signed isosurface 就生成第二个科学相位。

[![真实水总密度等值面与单位参数](screenshots/02-water-density-surface.png)](screenshots/02-water-density-surface.png)

**体积界面检查：** 选择 Grid volume，水总密度使用非 signed 通道；Volume Density Scale 为 5，仅控制光学显示。下图 Image Editor 中显示的是公开导出入口实际生成的 Cycles 预览，尺寸 960×720、64 samples；正式对照图采用更高分辨率与采样数。源数值单位仍为 e/bohr³。

[![总密度 Volume 参数与实际 Cycles 预览](screenshots/03-water-density-cloud.png)](screenshots/03-water-density-cloud.png)

差分要求相同 Structure、网格形状、原点、步矢和单位。界面不会自动对齐、插值或重采样。原本属于不同几何的数据，即使看上去相似，也不能为获得一张图而强行绑定。

**检查点：** 分别记录 α / β、轨道序号和 occupation；差分报告写出左减右的方向及两个 RDM 层级。改变颜色或 Volume Density Scale 后，数组 revision 和来源保持不变。

<a id="esp"></a>
## 4. ESP、切片、剖面与色标

ESP 单位为 `hartree/elementary_charge`。这里的符号按正试探电荷约定：核项为正，电子项为负。它既不是部分电荷，也不是电子密度。核附近有奇点，应选避开核位置的采样点。

1. 在 Wavefunction 选择明确的 **Effective Nuclear Charges** 来源和 total RDM，然后点 `ESP · level`。有 ECP 时使用源文件的有效核电荷，不以原子序数代替。
2. Molden 若缺少原始 total RDM，界面显示 **ESP will derive a total density matrix from occupations**。只有确知原计算层级时才设置 **Density Level** 为 SCF 或 POST_SCF，再用 **ESP from Occupations**；不知道层级就保持 UNSET。本例 Molden 标题本身不足以作这个判断。
3. 选总密度 Grid，Representation 选 **Property mapped on surface**；Linked Dataset 选同网格 ESP。水例可以用密度等值面 `0.002 e/bohr³`、ESP 色域 `−0.06 … +0.06 hartree/e`。不要把密度阈值和 ESP 色域写成同一单位。

下图的 **Surface isovalue** 明确是 `electron_per_cubic_bohr`，**Color values** 是 `hartree_per_elementary_charge`。Teaching 模板中关闭 Light Quantitative Colors，保持 ESP 的定量配色。

[![ESP 映射在密度面上，面阈值与颜色值分别标单位](screenshots/04-water-esp-surface.png)](screenshots/04-water-esp-surface.png)

| 表示 | 面板操作 | 科学坐标与范围 |
| --- | --- | --- |
| Scientific plane slice | 指定 Plane Origin、Full Plane Span U / V 和 Plane Samples，Create View；也可从 Grid 控制中 Create Slice | U / V 是整幅跨度，点数包含端点；可在斜网格上采样 |
| Scientific line profile | 指定 Profile Start / End、Profile Samples，Create View；也可 Create Profile | 距离轴保持 Grid 的 coordinate_unit；不是场景对象坐标 |
| Scientific colorbar | 固定 dataset、色域、colormap，再 Create View 或 Create Grid Colorbar | Width / Height 是显示 Å；不改变科学单位 |
| Export Samples CSV | 选已建立的切片 / 剖面 View，再从 Grid View 控制导出 | 按保存的科学采样参数重新取值；不应用对象显示变换 |

水例的平面可以取 `origin=(-4,0.35,-4)`、`U=(9,0,0)`、`V=(0,0,10)`、`129×129`，均用 bohr；剖面可取 `(-4,0.7,0.6)` 到 `(5,0.7,0.6)`、257 点。这些偏移用于避开原子核，不是经过误差优化的标准参数。

**切片参数检查：** 129×129 是平面样点数；U / V 的长度为完整跨度，ESP 色域为 ±0.1 hartree/e。

[![ESP 平面切片的原点、完整跨度、样点和色域](screenshots/05-water-esp-slice.png)](screenshots/05-water-esp-slice.png)

**剖面参数检查：** 源端点均以 bohr 给出，257 个采样点；Profile Radius 使用显示 Å。下方曲线的距离范围为 0–9 bohr，纵轴保持 ESP 科学单位。

[![ESP 剖面的端点、采样数及科学距离与值](screenshots/06-water-esp-profile.png)](screenshots/06-water-esp-profile.png)

剖面图的横轴为 bohr，纵轴为 `hartree_per_elementary_charge`，不能给整幅图赋一个长度单位。正式图清单已仅更正这两条记录的坐标 metadata，并在 `metadata_corrections` 中保存原文件哈希和依据；此次更正没有重渲图片或改动科学值。

越界采样保留 invalid / NaN：切片透明，剖面在无效段断开，不以 0 填补或跨越空段连线。颜色范围超出部分会截色，但 CSV 仍保留原值。定量色图应关闭 Light Quantitative Colors；Research / Teaching 可以换背景与线宽，保持同一数值映射。

**检查点：** 导出一次 CSV，移动或旋转根对象后再次导出，科学坐标和值应一致；色标显示正确单位和真实零点；ESP 与密度的源 RDM、网格和核电荷可追溯。

水 ESP 等密度面、切片和剖面的同参数 Research / Teaching 对照见[正式图索引](#molecular-gallery)。

<a id="local-fields"></a>
## 5. ELF、LOL、RDG 与 NCI

水 HF/STO-3G WFX 已由固定 critic2 1.3.15 实际生成 40×40×40 ELF、LOL、RDG 与 `sign(λ₂)ρ` 网格。ELF / LOL 经统一 CLI 转为语义明确的无量纲 CBQ，在无 wheel 安装扩展中通过 Preview / Import、`Grid Volume`、Research / Teaching Cycles 渲染；移走原 CUBE 和输入 CBQ 后，两个独立 Blender 5.1.1 冷进程均完成数组校验、View 重建和 Save As。NCI 配对网格另通过统一 operation、安装态 View 和保存重开。

1. 用外部 `convert` 或 **Run Local Processor** 导入 Cube，检查坐标单位、原子和 affine 网格。对于语义不明的 Grid，准备阶段必须明确 ELF、LOL、reduced_density_gradient 或 sign_lambda2_rho 及数值单位。文件扩展名不能证明物理量。
2. ELF / LOL 选择切片或等值面，色域设 `0 … 1`，用顺序色图。它们是无量纲局域性指标，不能解释为电子个数或某条化学键的概率；定义及使用的波函数 / 密度模型影响结果。
3. RDG 是非负无量纲场。NCI 选择 **NCI: RDG surface colored by sign(lambda2) rho**；Linked Dataset 必须为配套 signed-density 网格，检查两个 Dataset Index。`surface_isovalue=0.5` 和色域 `−0.05 … +0.05` 是当前默认起点，色域单位取自 signed-density 数据。

NCI 的几何来自 RDG，颜色来自 `sign(λ₂)ρ`；λ₂ 是密度 Hessian 的中间特征值。默认蓝 / 绿 / 红分别表示负值 / 零附近 / 正值，可用于观察常见的吸引、弱相互作用及排斥特征，但颜色本身不量化相互作用能。

系统要求相同非空 Structure、完整 affine、兼容单位和有限实数；ELF / LOL 超出 `[0,1]`、负 RDG 应先查源数据。独立文件没有共同 Calculation / provenance 时，只有确认来自同一密度分析后才勾选 **Confirm Same Density Analysis**。这个声明不能修复来源不符或网格错位。

**没有自动高密度 cutoff。** Color Minimum / Maximum 只映射颜色。若科研分析需要密度筛选，应先用有来源记录的外部计算明确生成所需网格，不能把截色说成筛选。

**检查点：** 每个网格保留实际输入哈希、critic2 版本和命令；NCI 记录两份源网格和配对依据；Research / Teaching 两图使用同一 RDG 阈值及 signed-density 色域。

<a id="atomic"></a>
## 6. 原子标量、向量与结构

1. 先导入并选择 Structure，使用 **Publication structure** 建立基础图。表示中的 Å 是显示单位；原始 bohr 坐标仍在项目里。
2. 选择逐原子标量数据，使用 **Atomic scalar**。例如 APBS PQR 的 partial charge 单位为 `elementary_charge`，radius 为 Å；PQR 不包含量子电子密度或 ESP 网格。
3. 选择逐原子三分量数据，使用 **Atomic vectors**，调整 **Vector Display Scale**。只有数据明确为能量梯度时才使用 **Display Force = −Gradient**；已是 force 的数据不能再取负。

| 原子量 | 数值解释 | 建议表示与核对 |
| --- | --- | --- |
| 部分电荷 | 正负是具体电荷划分 / 参数化方案的结果 | 发散色图与真实 0；报告 Mulliken、其他人口分析或 PQR 力场来源，不跨方案直接比较 |
| 原子自旋 population | 原子分区后的自旋指标，不同于连续自旋密度 | Atomic scalar；说明 α−β 与分区方法；只有实际 reader 提供该字段才可用 |
| 原子半径 | 几何或模型参数，通常非负 | 顺序色图；PQR 中 0 半径可能合法，不自动替换 |
| 力 / 能量梯度 | 向量单位取自源数据，例如 eV/Å 或 hartree/bohr | 箭头方向和符号核对；Display Scale 不改单位和值 |

APBS 示例含 998 个原子，其元素和 segment 恢复存在明确诊断，见[原始 PQR 说明](../../../examples/user-workflows/inputs/pqr/apbs-protein-rna-nb.md)。教学图可增强箭头和球体对比；研究图保留比例、单位和定量色标，不能用反光高亮代替数值颜色。

下图展示 Atomic scalar 的公开参数：Research、Coolwarm、对称色域 ±1.2 e，Light Quantitative Colors 关闭。Load Selected View 后核对这些值，再更新已有 View。

[![PQR 原子电荷的模板、色域、色图及更新入口](screenshots/08-pqr-atomic-charge.png)](screenshots/08-pqr-atomic-charge.png)

以下 PQR 图使用同一 `−1.2 … +1.2 e` 色域、coolwarm 映射和固定视角，均为 Cycles、2400×1800、256 samples。源头部声明 PDB2PQR 1.1.2 / amber；不把这个力场电荷当作量子计算所得电荷。参数、原始文件和数组哈希见[原子与轨迹总 manifest](../../../examples/scientific-visualization/output/atom-trajectory/manifest.json)，数值来源见[PQR 科学报告](../../../examples/scientific-visualization/output/atom-trajectory/pqr-charge/report.md)。

可打开 [PQR 工作台](../../../examples/scientific-visualization/output/atom-trajectory/scenes/pqr.blend)并保留相邻 `pqr.cbq`，分别选择两个模板 View，再用 Load Selected View 查看保存的色域与科学绑定。

| 真实量与参数 | Research | Teaching |
| --- | --- | --- |
| APBS PQR partial charge；998 原子，色域 ±1.2 e | [![PQR partial charge Research](../../../examples/scientific-visualization/output/atom-trajectory/pqr-charge/images/001-atomic_scalar-research-0001.png)](../../../examples/scientific-visualization/output/atom-trajectory/pqr-charge/images/001-atomic_scalar-research-0001.png) | [![PQR partial charge Teaching](../../../examples/scientific-visualization/output/atom-trajectory/pqr-charge/images/001-atomic_scalar-teaching-0001.png)](../../../examples/scientific-visualization/output/atom-trajectory/pqr-charge/images/001-atomic_scalar-teaching-0001.png) |

**检查点：** 属性行数与 Structure 原子数一致；缺字段时不要用零补齐；箭头长度只作显示比例，方法信息写入图注。

<a id="spectra"></a>
## 7. 分子振动、IR、Raman、UV-Vis 与 ECD

固定 Gaussian/ORCA 输入已通过 22-Reader 能力矩阵、真实 reader 与模型/表示回归。输入选 [Gaussian16 IR](../../../examples/scientific-visualization/inputs/cclib/Gaussian/basicGaussian16/dvb_ir.out)、[Raman](../../../examples/scientific-visualization/inputs/cclib/Gaussian/basicGaussian16/dvb_raman.out)、[TD](../../../examples/scientific-visualization/inputs/cclib/Gaussian/basicGaussian16/dvb_td.out)，或 [ORCA5 对应目录](../../../examples/scientific-visualization/inputs/cclib/ORCA/basicORCA5.0)。每份文件独立导入。

1. 在 **Local Processor · Scientific Input** 选择 Gaussian / ORCA Reader 和文件，点 **Run Local Processor**。选择 VibrationalModeSet 或 ExcitedStateSet，核对频率 / 激发能、位移和实际强度字段。
2. 振动选择 **Vibrational mode**，设置从 0 开始的 Mode / State Index、Displacement Amplitude、Arrow Scale、Phase。点 Create View，再用 **Apply Phase / Play / Pause**。Frames Per Cycle 仅控制教学播放节奏，不代表真实振动周期。
3. 选择 **Spectrum Profile**：Stick 保留离散线；Gaussian / Lorentzian 使用 Axis Start / End、Axis Samples 和 FWHM。点击 **Derive IR / Derive Raman Activity / Derive UV-Vis / Derive ECD**，再选择 Spectrum 表示。
4. 要观察谱峰与模式 / 态的对应关系，先生成 Stick spectrum，再选 **Vibration and spectrum linked view** 或 **Electronic state and spectrum linked view**，显式选 Linked Dataset；展宽后的曲线没有一对一单峰选择契约。

| 量 | 当前科学轴与强度 | 解释限制 |
| --- | --- | --- |
| 分子振动 | 频率 cm⁻¹；位移单位以源数组为准 | 虚频保留有符号值；Include Imaginary Modes 是选择策略，不是把虚频修正为稳定振动 |
| IR | 波数 cm⁻¹；原始强度通常 km/mol，按数据单位显示 | 展宽和频率缩放都应声明；本流程不自动应用经验缩放因子 |
| Raman activity | 波数 cm⁻¹；原始 activity 通常 Å⁴/amu | activity 不等于给定激光波长、温度下的实验 Raman intensity |
| UV-Vis | 当前轴为 cm⁻¹，离散 oscillator strength 无量纲 | 当前面板不是直接输入 nm；禁阻态可能强度为 0；展宽曲线单位由归一化线形和轴单位共同决定 |
| ECD | 当前轴 cm⁻¹；rotatory strength 保留 signed 源单位 | 正负不能取绝对值；Gaussian09 例是 length gauge 的 10⁻⁴⁰ cgs，不能称为已转换的实验 Δε |

方法、基组、几何、频率尺度、FWHM 与线形都会影响曲线。两模板的原生 Curve / 文字保持清楚的轴、刻度和零线；Research 固定数值范围便于比较，Teaching 可强调当前模式，但不增加来源没有的振动或激发。

绘图区将所选数值范围映射到 `8×5` 显示框，使 cm⁻¹ 与较小强度的谱线保持可读；刻度仍显示原始数值和单位。图框比例、对象坐标和科学数组分开保存，不能从 Curve 的场景高度直接读出 oscillator strength。

**检查点：** Derive 按钮只有实际强度存在时可用；核对峰位和至少一个源强度；ECD 单位未知时不能声称完整定量结果；模式动画核对位移方向而不是只看“动了”。

<a id="trajectory"></a>
## 8. 轨迹与逐帧力

真实输入为 [rMD17 aspirin 的 32 帧 extXYZ](../../../examples/user-workflows/inputs/extxyz/aspirin-rmd17-32.extxyz)。[来源说明](../../../examples/user-workflows/inputs/extxyz/aspirin-rmd17-32.md)记录从 NPZ array rows `0,100,…,3100` 取子集及 kcal/mol → eV 换算。`source_index` 是原序列索引，不保证单调；没有显式时间单位时不得换算为 fs。

1. 外部 `convert` 后在 CBQ Preview 检查 32 frames 和 atomic_force 等摘要，确认后核对每帧 21 原子、坐标 Å、力 eV/Å、能量 eV。
2. 在 Browser 选 FrameSet，Representation 选 **Trajectory frame**；需要力时选 **Trajectory with forces** 并显式绑定匹配的 force 数据。设置 **Source Frame Index (0-based)**，点 Create View。
3. 使用 **Apply Frame** 检视当前索引，再用 **Play / Pause**。Timeline Frames Per Source Frame 只控制播放映射。检查第 0、15、31 帧；用 **Update Style / Parameters** 保存静态帧选择，不能把一次预览当作持久 View 参数已更新。

逐帧坐标和力按同一个 FrameSet 对齐。缺力值的原子箭头应隐藏，不能沿用上一帧。显示材质不应随换帧重置。Research 图标注来源帧及真实单位，Teaching 可放大箭头，但不能把稀疏子集播放解释为真实时间连续演化。

4. 选中 trajectory 或 trajectory_force 的 View 根对象，在 **Cycles · Scientific Images** 选择 **PNG Sequence + MP4**。轨迹导出遍历 FrameSet 的全部源帧，使用固定相机；它不使用振动的 Frames Per Cycle。当前静态导出则使用 View 保存的 Source Frame Index。
5. 完成后核对 `display.json` 中各帧的 source index，以及有明确来源时的 time / time unit。FPS 只决定视频播放速度，不补造物理时间。实际导出回归已覆盖两模板、固定相机、取消与资源恢复；本例已完成两种表示、两套模板的全部 32 帧序列。

下图在公开面板选择 Source Frame Index 31；Timeline Start Frame 为 1、每源帧占 1 个 Timeline 帧，因此下方时间线位于 32。Linked Dataset 绑定 atomic_force，Vector Display Scale 为 0.5；Apply Frame 与 Play / Pause 位于同一控制区。视口环境仅帮助辨认原子，不改变坐标与力。

[![rMD17 的 32 帧摘要、逐帧力绑定和播放控制](screenshots/09-rmd17-force-trajectory.png)](screenshots/09-rmd17-force-trajectory.png)

以下静图使用源帧索引 0、固定视角与 `framing_margin=1.5`，均为 Cycles、2400×1800、256 samples；力箭头的显示系数为 0.5，科学单位仍为 eV/Å。两种表示分别保留[轨迹报告](../../../examples/scientific-visualization/output/atom-trajectory/aspirin-trajectory/report.md)和[逐帧力报告](../../../examples/scientific-visualization/output/atom-trajectory/aspirin-force/report.md)。

| 真实量与参数 | Research | Teaching |
| --- | --- | --- |
| rMD17 aspirin 结构；21 原子，源帧 0 | [![rMD17 aspirin trajectory Research](../../../examples/scientific-visualization/output/atom-trajectory/aspirin-trajectory/images/001-trajectory-research-0001.png)](../../../examples/scientific-visualization/output/atom-trajectory/aspirin-trajectory/images/001-trajectory-research-0001.png) | [![rMD17 aspirin trajectory Teaching](../../../examples/scientific-visualization/output/atom-trajectory/aspirin-trajectory/images/001-trajectory-teaching-0001.png)](../../../examples/scientific-visualization/output/atom-trajectory/aspirin-trajectory/images/001-trajectory-teaching-0001.png) |
| rMD17 aspirin force；源帧 0，显示系数 0.5 | [![rMD17 aspirin force Research](../../../examples/scientific-visualization/output/atom-trajectory/aspirin-force/images/001-trajectory_force-research-0001.png)](../../../examples/scientific-visualization/output/atom-trajectory/aspirin-force/images/001-trajectory_force-research-0001.png) | [![rMD17 aspirin force Teaching](../../../examples/scientific-visualization/output/atom-trajectory/aspirin-force/images/001-trajectory_force-teaching-0001.png)](../../../examples/scientific-visualization/output/atom-trajectory/aspirin-force/images/001-trajectory_force-teaching-0001.png) |

四段动画均为 **32 帧、1280×720、24 fps**，逐帧 PNG 使用 Cycles 64 samples；视频解码后的帧数、尺寸和帧率已核验。图注明确标注 **Source sequence; physical time unavailable**。下列目录包含完整 PNG、MP4、`display.json` 与报告；[总 manifest](../../../examples/scientific-visualization/output/atom-trajectory/manifest.json)记录 134 张 PNG、4 段 MP4，以及实际相机、View 变换、输入与输出哈希。

可打开 [rMD17 工作台](../../../examples/scientific-visualization/output/atom-trajectory/scenes/rmd17.blend)并保留相邻 `rmd17.cbq`。其中四个 View 分别为两套模板的 trajectory / trajectory_force，均保存源帧 0；逐一 Load 后可切换帧或重建。

| 表示 | Research 视频 | Teaching 视频 | PNG 与来源报告 |
| --- | --- | --- | --- |
| Trajectory frame | [32 帧 MP4](../../../examples/scientific-visualization/output/atom-trajectory/aspirin-trajectory-animation/001-trajectory-research.mp4) | [32 帧 MP4](../../../examples/scientific-visualization/output/atom-trajectory/aspirin-trajectory-animation/001-trajectory-teaching.mp4) | [完整目录](../../../examples/scientific-visualization/output/atom-trajectory/aspirin-trajectory-animation) |
| Trajectory with forces | [32 帧 MP4](../../../examples/scientific-visualization/output/atom-trajectory/aspirin-force-animation/001-trajectory_force-research.mp4) | [32 帧 MP4](../../../examples/scientific-visualization/output/atom-trajectory/aspirin-force-animation/001-trajectory_force-teaching.mp4) | [完整目录](../../../examples/scientific-visualization/output/atom-trajectory/aspirin-force-animation) |

**检查点：** 三个抽查帧的坐标、力、原始索引一致；无显式时间时只显示帧 / step；本子集不作为独立训练集或收敛统计证据。

<a id="bands"></a>
## 9. Band、DOS 与 PDOS

Si Band 与 DOS 的固定真实 VASP 输入已通过 reader/模型/原生 Curve 回归。Band 输入为 [bands/vasprun.xml.gz](../../../examples/scientific-visualization/inputs/silicon/bands/vasprun.xml.gz)和 [KPOINTS](../../../examples/scientific-visualization/inputs/silicon/bands/KPOINTS)；DOS 输入为 [dos/vasprun.xml.gz](../../../examples/scientific-visualization/inputs/silicon/dos/vasprun.xml.gz)。来源分别声明 VASP 5.2.11 与 5.2.12，不合并成同一来源。

1. 在 **Local Processor · Scientific Input** 选择 VASP Bands / DOS Reader。Band 同时选择配套 KPOINTS，核对高对称点标签、分支和 160 个路径点。
2. 单独导入 DOS XML，Calculation 选 **Uniform DOS Mesh**；不要复用 Band KPOINTS。此例为 4×4×4 Monkhorst-Pack 网格、10 个不可约点。
3. Browser 选 BandStructure → **Band structure**，打开 Show Axes，Energy Reference 选 **E − E_F** 或 Absolute。均匀网格没有真实路径分支，不能绘为一条 band path。
4. Browser 选 DensityOfStates → **DOS / PDOS**。原子 / 轨道选择均为空时显示 total DOS；填写 PDOS Atom Indices、PDOS Orbital Labels 和 Spin Indices 后得到所选投影之和。原子、自旋索引从 0 开始，轨道名必须与源标签相同。

能量轴为 eV；E − E_F 的 0 线使用该数据自己的 E_F。Band 横轴是其 reciprocal path distance；DOS 横轴为态密度，纵轴为能量，态密度单位取自数据，通常为 states/eV。**Mirror Beta DOS** 仅把 β 通道画在负侧，原始 DOS 不是负态密度。

投影依赖上游投影方案；某组 PDOS 不一定严格加和到 total DOS，不做强制归一化。Research / Teaching 曲线均保留轴、分支、能量参考和自旋含义。**Band structure and DOS linked view** 需要项目中明确兼容的绑定；本例两个独立导入若没有匹配的 Structure 身份，应分别出图，不伪造关联。

Band / DOS 均使用 `8×5` 显示框和原科学值刻度。合法的 linked view 按各自能量参考转换后，取两者完整能量范围的并集并对齐纵轴，不裁掉能带或 DOS 的数据。

**检查点：** 记录两个源文件各自 E_F；抽查一个高对称点能量和一个 PDOS 选择；确认 β 镜像只改变图形，不改变保存数组。

<a id="phonon"></a>
## 10. 晶格声子

真实 NaCl phonopy 4.4.0 operation 已通过 CLI 和正式 ZIP 安装态 Blender 验收。输入使用 [phonopy_disp.yaml](../../../examples/scientific-visualization/inputs/phonopy/NaCl/phonopy_disp.yaml)、[FORCE_SETS](../../../examples/scientific-visualization/inputs/phonopy/NaCl/FORCE_SETS)，需要非解析修正时显式提供 [BORN](../../../examples/scientific-visualization/inputs/phonopy/NaCl/BORN)。原始 VASP 力输出和原胞见[完整目录](../../../examples/scientific-visualization/inputs/phonopy/NaCl)。

1. 在专业操作中选择 phonon，设置 YAML、FORCE_SETS、可选 BORN 与 Fractional q-points，例如 `0,0,0; 0.25,0,0`，点击 **Run Local Processor**。
2. 只有确知方向时开启 **Explicit NAC Direction** 并填写方向；Group Velocities 仅在实际计算并有单位时保留，不根据位移箭头推断。
3. Browser 选 PhononModeSet → **Phonon mode**，设置 q-point Index、Mode / State Index、Supercell Repetitions、Displacement Amplitude 和 Phase，Create View 后 Apply Phase / Play。

模式保留复数特征向量；显示取指定相位与晶胞平移下的实位移。不能把复数部分直接删除，也不能把 q 点误作真实空间坐标。当前频率单位按 PhononModeSet 显示（phonopy 通常 THz）；负频率 / 虚模保留原解释。NAC、超胞、力常数与计算设置都可能改变频率及 LO–TO 行为。

**检查点：** 对比 Γ 与非零 q 点的邻胞相位；两模板使用同一 q、模式和超胞。动画的 FPS 是展示速度，不是 THz 到秒的自动换算。

<a id="fermi"></a>
## 11. Fermi surface

固定 SrVO₃ VASP 五文件已通过统一 launcher 的真实 Fermi surface 提取。来源与六个文本哈希见[manifest 的 fermi_cache](../../../examples/scientific-visualization/input-manifest.json)：立方晶格 3.84652 Å、Γ 21³ 网格、286 不可约点、20 bands、VASP 6.4.3、ISPIN=1、E_F=5.6990 eV；INCAR 为含 V 的 U=5 eV、J=0 的 DFT+U 设置。

原包和选取文本只在 `.agents/cache/scientific-visualization/fermi/`。该包存在许可与再分发边界，仓库不分发 POTCAR / pickle，导入器不读取或执行它们；取得信息与哈希足以复核来源。

1. 在 **Local Processor · Scientific Input** 选择 Fermi operation、输入目录和 spin index。目录必须包含匹配的 INCAR、KPOINTS、POSCAR、OUTCAR、PROCAR，可选 IBZKPT。
2. 点 **Run Local Processor**。处理程序检查真正的三维均匀网格、Structure / 能带身份和对称展开；高对称路径被拒绝。首期 interpolation factor 固定 1。
3. Browser 选 FermiSurfaceMesh → **Fermi surface**。Color Property 留空时按真实 band index 分类着色；图例中的 band number 用于标识，不是能量色标。

曲面满足 `E_n(k)=E_F`，坐标是包含 `2π` 约定的 reciprocal Cartesian `Å⁻¹`。E_F 不能在已减去参考能的数据上再次减一次。当前 importer 不生成未经核验的速度、有效质量或自旋纹理；只有已经导入且明确单位的外部 scalar / vector 属性才能填入 Color Property / Vector Property 显示。

**检查点：** band 分类与原 band index 对应；记录 reciprocal unit、E_F、spin 与网格；Research / Teaching 同一曲面的配色分类不变。真实提取和图像验收尚未完成，不以 mock 球面替代。

<a id="qtaim"></a>
## 12. QTAIM 临界点与梯度路径

真实 water WFX 已由 critic2 1.3.15 生成 5 个临界点与 4 条有序梯度分支，并通过统一 `topology.qtaim@1`、正式 ZIP 安装态 View、保存重开和源文件移走验收。

1. 在专业操作中选择 QTAIM，并选择 WFX；处理程序内部固定生成和解析 CPREPORT JSON 与 FLUXPRINT TEXT。
2. Analyzed Field 默认未设置。只有 critic2 确实分析原子单位电子密度时，选择 **Electron Density (atomic units)**。rho 为 bohr⁻³，Laplacian / Hessian 为 bohr⁻⁵；坐标按文件单位换算，不能按画面大小猜。
3. 点 **Run Local Processor**。结果核对源原子种类、坐标、分子居中矢量或周期晶胞、文件哈希及绑定 Structure；错误或取消不提交部分图。
4. Browser 选择有路径的 TopologyGraph → **QTAIM critical points and paths**。Color Property 选 `kind`、`field_value` 或 `laplacian`；调整 Critical Point Radius、Gradient Path Radius，Create View。

CP 使用球形 glyph；路径是 FLUXPRINT 实际按序样点构成的管状 Curve。仅有 CP 间连接关系时不会画成采样 bond path。可先导入 CP-only，再补同源路径，原 CP graph 与派生 graph 都保留。默认端点容差为 0.02 bohr；记录实际端点误差，不能把样点强行吸附到 CP。

周期路径保留 cell CP 身份、Crys2Car 与路径端点 lattice translation，不把跨胞路径折回成错误短线。QTAIM 拓扑依赖分析场和方法；CP 类型、ρ 和 ∇²ρ 的颜色不同，图注必须标明当前量，不能以几何连线自动宣称化学键性质。

**检查点：** CP 数目 / 类型可对照 JSON；至少一条路径的首尾与 TEXT 样点顺序一致；重新打开 .cbq 后保留每条路径的 CP 身份、单位和周期平移。

<a id="render"></a>
## 13. Cycles 正式出图与动画

1. 在场景中选中要导出的科学 View 根对象。选中原始数据行或任意普通 Mesh 不足以指定导出；纯 Structure 图目前不能单独满足 Scientific Images 的科学数据报告要求。
2. 展开 **Cycles · Scientific Images**，指定尚不存在的 **New Output Folder**。选择 Research + Teaching 可对相同科学 View 输出两套样式。
3. 设置 Width / Height、Cycles Samples；当前默认 `2400×1800`、256 samples。先做低分辨率预览确认构图，再正式导出。
4. 必要时启用 **Custom Camera Direction**。Direction from Center 决定观察方向，Framing Margin 调整留白。**Volume Focus Threshold** 只用于相机取景，单位与源 field 一致；0 表示按全网格取景，不截断或修改体积值。
5. 点 **Render Selected Scientific Views**。完成后检查 `images/`、`display.json`、`manifest.json`、`report.md`；来源、表示参数和实际输出应一致。取消在图像 / 帧之间响应，未完整成功时不发布最终目录。

下图记录公开入口成功导出两套模板的预览：960×720、64 samples，方向 `(1.2,−1.6,1.1)`、Framing Margin 1.4、Volume Focus Threshold 0.03 e/bohr³。Image Editor 显示其中一张结果。确认取景后，可恢复 2400×1800、256 samples 做正式输出。

[![Cycles 公开导出参数与成功生成的图像预览](screenshots/10-cycles-public-export.png)](screenshots/10-cycles-public-export.png)

| 类型 | Research / Teaching 对照 | 必须保留的信息 |
| --- | --- | --- |
| 等值面与体积 | Research 浅中性背景；Teaching 深中性背景，适度加强几何辨识 | 正负定义、等值面阈值、体积光学比例；负场拆成非负正 / 负通道，不使用负 extinction |
| 定量面、切片、原子标量 | 保持同一色域；研究读色关闭光照。切片 / 色标 / 原子标量始终使用 Emission | 真实 0、范围、单位和是否截色；有光照的教学属性面只作形状辅助，透明度会影响读色 |
| Band / DOS / spectra | 原生 Curve / 字体，背景改变后仍清晰 | 轴、刻度、单位、E_F 或零线，自旋镜像 / signed 强度 |
| 振动与声子 | 可增强教学位移幅度，但同一对照图固定相位与模式 | mode、q、amplitude、phase 与播放映射，不把动画幅度当热位移 |
| QTAIM / Fermi | 几何和类别可识别，属性颜色与分类色分开说明 | CP 类型 / band 身份或实际属性单位 |

**PNG Sequence + MP4** 支持 vibration_mode、vibration_spectrum_linked、phonon_mode、trajectory 和 trajectory_force。振动 / 声子按 Frames Per Cycle 输出一个相位周期；轨迹按实际 FrameSet 帧数输出。H.264 要求宽高均为偶数。检查首、中、末帧及 MP4 能播放，并区分 FPS 和真实物理时间。

Wavefunction 另有 **Export Orbital Images**，按明确的 1-based Orbital Numbers 列表逐轨道出图，复用匹配网格或计算缺失网格；比较轨道时固定相同阈值、相机和网格。

**检查点：** 色标不被强光冲白、曲线轴和文字不互相遮挡；报告中的阈值与实际图一致；科学来源、实际图像 QA 和项目生命周期分别记录。

<a id="molecular-gallery"></a>
### 已生成的分子正式图

以下图片由真实 FCHK 数值生成，均为 Cycles、2400×1800、256 samples、OptiX。点击图片可看原尺寸。每行两图共享科学输入与阈值，显示模板不同；完整相机、光源、色域、源 hash 和数组检查在[渲染 manifest](../../../examples/scientific-visualization/output/molecular/images/render-manifest.json)，各量的[科学报告目录](../../../examples/scientific-visualization/output/molecular/images/reports)保留 provenance 闭包。切片和色标保持不受光照影响的数值颜色；剖面的科学距离轴保留 bohr，ESP 值保留 hartree/e。

分子报告中的 `artifact.path` 相对于 `output/molecular/images/`，不是其下 `reports/<case>/` 目录。PQR / 轨迹报告中的同名字段相对于各自 case 输出目录；打开原始文件时应使用对应根目录。

| 量与参数 | Research | Teaching |
| --- | --- | --- |
| H₂O HOMO 5，±0.06 bohr⁻³ᐟ² | [![H2O HOMO Research](../../../examples/scientific-visualization/output/molecular/images/water-homo-research.png)](../../../examples/scientific-visualization/output/molecular/images/water-homo-research.png) | [![H2O HOMO Teaching](../../../examples/scientific-visualization/output/molecular/images/water-homo-teaching.png)](../../../examples/scientific-visualization/output/molecular/images/water-homo-teaching.png) |
| H₂O LUMO 6，±0.05 bohr⁻³ᐟ² | [![H2O LUMO Research](../../../examples/scientific-visualization/output/molecular/images/water-lumo-research.png)](../../../examples/scientific-visualization/output/molecular/images/water-lumo-research.png) | [![H2O LUMO Teaching](../../../examples/scientific-visualization/output/molecular/images/water-lumo-teaching.png)](../../../examples/scientific-visualization/output/molecular/images/water-lumo-teaching.png) |
| CH₃ α HOMO，±0.055 bohr⁻³ᐟ² | [![CH3 alpha HOMO Research](../../../examples/scientific-visualization/output/molecular/images/ch3-alpha-homo-research.png)](../../../examples/scientific-visualization/output/molecular/images/ch3-alpha-homo-research.png) | [![CH3 alpha HOMO Teaching](../../../examples/scientific-visualization/output/molecular/images/ch3-alpha-homo-teaching.png)](../../../examples/scientific-visualization/output/molecular/images/ch3-alpha-homo-teaching.png) |
| CH₃ β HOMO，±0.055 bohr⁻³ᐟ² | [![CH3 beta HOMO Research](../../../examples/scientific-visualization/output/molecular/images/ch3-beta-homo-research.png)](../../../examples/scientific-visualization/output/molecular/images/ch3-beta-homo-research.png) | [![CH3 beta HOMO Teaching](../../../examples/scientific-visualization/output/molecular/images/ch3-beta-homo-teaching.png)](../../../examples/scientific-visualization/output/molecular/images/ch3-beta-homo-teaching.png) |
| H₂O 总密度面，0.08 e/bohr³ | [![Water density isosurface Research](../../../examples/scientific-visualization/output/molecular/images/water-density-iso-research.png)](../../../examples/scientific-visualization/output/molecular/images/water-density-iso-research.png) | [![Water density isosurface Teaching](../../../examples/scientific-visualization/output/molecular/images/water-density-iso-teaching.png)](../../../examples/scientific-visualization/output/molecular/images/water-density-iso-teaching.png) |
| H₂O density cloud，Density Scale 5 | [![Water density volume Research](../../../examples/scientific-visualization/output/molecular/images/water-density-cloud-research.png)](../../../examples/scientific-visualization/output/molecular/images/water-density-cloud-research.png) | [![Water density volume Teaching](../../../examples/scientific-visualization/output/molecular/images/water-density-cloud-teaching.png)](../../../examples/scientific-visualization/output/molecular/images/water-density-cloud-teaching.png) |
| CH₃ α−β 自旋密度，±0.008 e/bohr³ | [![CH3 spin density Research](../../../examples/scientific-visualization/output/molecular/images/ch3-spin-research.png)](../../../examples/scientific-visualization/output/molecular/images/ch3-spin-research.png) | [![CH3 spin density Teaching](../../../examples/scientific-visualization/output/molecular/images/ch3-spin-teaching.png)](../../../examples/scientific-visualization/output/molecular/images/ch3-spin-teaching.png) |
| N 原子 MP2−SCF 密度，±0.0007 e/bohr³ | [![Nitrogen MP2 minus SCF Research](../../../examples/scientific-visualization/output/molecular/images/nitrogen-mp2-minus-scf-research.png)](../../../examples/scientific-visualization/output/molecular/images/nitrogen-mp2-minus-scf-research.png) | [![Nitrogen MP2 minus SCF Teaching](../../../examples/scientific-visualization/output/molecular/images/nitrogen-mp2-minus-scf-teaching.png)](../../../examples/scientific-visualization/output/molecular/images/nitrogen-mp2-minus-scf-teaching.png) |
| H₂O ρ=0.002 e/bohr³ 上的 ESP，±0.06 hartree/e | [![Water ESP surface Research](../../../examples/scientific-visualization/output/molecular/images/water-esp-surface-research.png)](../../../examples/scientific-visualization/output/molecular/images/water-esp-surface-research.png) | [![Water ESP surface Teaching](../../../examples/scientific-visualization/output/molecular/images/water-esp-surface-teaching.png)](../../../examples/scientific-visualization/output/molecular/images/water-esp-surface-teaching.png) |
| H₂O ESP 切片，±0.1 hartree/e | [![Water ESP slice Research](../../../examples/scientific-visualization/output/molecular/images/water-esp-slice-research.png)](../../../examples/scientific-visualization/output/molecular/images/water-esp-slice-research.png) | [![Water ESP slice Teaching](../../../examples/scientific-visualization/output/molecular/images/water-esp-slice-teaching.png)](../../../examples/scientific-visualization/output/molecular/images/water-esp-slice-teaching.png) |
| H₂O ESP 剖面，距离 bohr / 值 hartree/e | [![Water ESP profile Research](../../../examples/scientific-visualization/output/molecular/images/water-esp-profile-research.png)](../../../examples/scientific-visualization/output/molecular/images/water-esp-profile-research.png) | [![Water ESP profile Teaching](../../../examples/scientific-visualization/output/molecular/images/water-esp-profile-teaching.png)](../../../examples/scientific-visualization/output/molecular/images/water-esp-profile-teaching.png) |

默认 Framing Margin 为 1.4，切片为 1.45；density cloud 的 Volume Focus Threshold 为 0.03 e/bohr³，只用于相机取景。不同量使用的观察方向见 manifest，不能把取景参数解释成科学截断。

<a id="lifecycle"></a>
## 14. 保存、重开和缓存重建

可直接打开 [water.blend](../../../examples/scientific-visualization/output/molecular/scenes/water.blend)、[ch3.blend](../../../examples/scientific-visualization/output/molecular/scenes/ch3.blend)和 [nitrogen.blend](../../../examples/scientific-visualization/output/molecular/scenes/nitrogen.blend)，并保留各自相邻 `.cbq`。三场景分别包含 14、6、2 个科学量 View；[场景 manifest](../../../examples/scientific-visualization/output/molecular/scenes/scene-manifest.json)记录表示参数与源数组 hash。含配套结构在内共 40 个 View，已在独立副本完成 Save As、整体移动、移除渲染缓存后公开面板重建与冷启动重开，61 个科学数组文件哈希保持一致。结果见[生命周期核验报告](../../../examples/scientific-visualization/output/molecular/scenes/lifecycle-verification.json)，可按[原生测试脚本](../../../tests/blender_molecular_scene_lifecycle.py)复核；正式场景文件未被测试改动。

另有 [PQR / rMD17 场景清单](../../../examples/scientific-visualization/output/atom-trajectory/scenes/scene-manifest.json)，对应两个工作台、6 个 View。已正常保存并在另一 Blender 进程重开，逐个公开 Load / Rebuild；四个轨迹 View 均检查全部 32 帧坐标及适用的力，再回到保存帧。缓存副本还通过 Save As、整体移动与另一进程冷启动重开：View 身份、显示参数、变换和 14 个科学数组文件哈希保持一致，正式场景与原有 153 个渲染产物未改动。结果见[原子与轨迹生命周期报告](../../../examples/scientific-visualization/output/atom-trajectory/scenes/lifecycle-verification.json)。

使用[保存与重开脚本](../../../examples/scientific-visualization/save_atom_trajectory.py)复核时，按示例入口配置私有 Blender 环境及已有库；传 `--lifecycle-cache .agents/cache/your-new-lifecycle` 只对新缓存副本执行 Save As / 移动。随后在另一 Blender 进程保留同一参数并加 `--verify`，核对冷启动并写出紧凑报告；不要将正式场景目录当作生命周期缓存目录。

1. 用 Blender 正常保存 `.blend`，同时检查相邻 `.cbq` 项目目录存在。`.blend` 保存显示和关联，`.cbq` 中的科学 manifest 与 `arrays/*.npy` 是权威数据。
2. 关闭该测试 Blender，在新的进程中打开 `.blend`。确认 Project Browser 能找到同一数据、View 参数可 Load、科学单位和源 revision 一致。
3. 做一次 **Save As** 到新的测试目录，检查新 `.blend` 与相邻 `.cbq` 配套。只移动 `.blend` 会造成关联缺失；应整体移动后再次冷启动检验。
4. 要验证缓存恢复，先复制一套测试项目并退出使用它的 Blender。仅移走副本中的 `.cbq/cache/render/`；保留科学 manifest 和 arrays。重开后使用 **Rebuild Selected View**，检查重建结果及参数。
5. 对重建前后的科学 `.npy` 做 SHA-256 比较；对切片 / 剖面按已保存参数重新导出 CSV。相机、光源、View transform、材质或渲染缓存变化不应改科学数组。

下面是实际操作项目保存、关闭并重开后的界面，Project 显示 Connected / clean。[操作记录](screenshots/operations.json)核验了同一项目 UUID、13 个数据实体的 revision 与 10 个 View；这份 GUI 演示项目与上方五份交付工作台分别记录，不能互相替代生命周期证据。

[![实际 GUI 项目保存重开后 Connected 和 clean 状态](screenshots/11-save-reopen-connected.png)](screenshots/11-save-reopen-connected.png)

如果源 revision 已改变，先在 Browser 处理失效 / 过期 View。不要用旧缓存绕过科学身份检查，也不要把仅能显示旧 Mesh 当作项目成功重开。资源丢失时按界面关联恢复提示选择正确 `.cbq`，不猜另一个同名文件。

**检查点：** 原地重开、Save As 后重开、缓存恢复分别记录；每次确认科学数组 hash、数据单位、采样 CSV 及两个模板显示。最终覆盖范围与不能合并解释的分层证据见下一节。

<a id="verification"></a>
## 15. 最终验收与检查清单

确切隔离安装包、完整测试与产物哈希见[验证报告](VERIFICATION.md)，22 Reader 的逐格式能力见[格式能力矩阵](../../user/formats.md)。下表把模型、适配器、真实文件、UI/渲染、保存重开五层分开记录；同一行各层通过不表示每张历史图片都由最终无 wheel ZIP 重新截图。

| 物理量组 | 模型 | 适配器 / operation | 真实文件 | UI / 渲染 | 保存重开 |
| --- | --- | --- | --- | --- | --- |
| MO、总/自旋/差分密度、ESP | Passed | unified wavefunction operations | water/CH₃/N FCHK | 22 Cycles 图、7 张操作截图 | 3 工作台、40 Views、61 arrays Passed |
| 原子电荷、轨迹、逐帧力 | Passed | native CBQ Viewer | PQR 998、rMD17 32 frames | 6 静图、128 PNG、4 MP4、2 截图 | 2 工作台、6 Views、14 arrays Passed |
| NCI：RDG + `sign(λ₂)ρ` | Passed | `grid.nci_fields@1` | water WFX / critic2 1.3.15 | 正式 ZIP 安装态 NCI View Passed | CBQ/WFX 移走后重开 Passed |
| QTAIM：CP、ρ、Laplacian、路径 | Passed | `topology.qtaim@1` | water WFX / critic2 1.3.15 | 正式 ZIP 安装态 Topology View Passed | 源与处理程序移走后重开 Passed |
| Phonon | Passed | `periodic.phonon@1` | NaCl YAML/FORCE_SETS/BORN，phonopy 4.4.0 | 正式 ZIP 安装态 phase View Passed | 源与处理程序移走后重开 Passed |
| Fermi surface | Passed | unified Fermi operation + native mesh | SrVO₃ VASP five-file set | 真实网格提取；原生 Fermi View 回归 Passed | CBQ/array identity 与任务目录移走 Passed |
| Vibration、IR/Raman、UV-Vis/ECD | Passed | cclib reader + native mode/Curve | 固定 Gaussian/ORCA 输出 | 模式/光谱/linked View 回归 Passed | CBQ/scene lifecycle contracts Passed |
| Band、DOS、PDOS | Passed | VASP reader + native Curve | 固定 Si VASP band/DOS | 能量参考、β镜像、PDOS选择回归 Passed | CBQ/scene lifecycle contracts Passed |
| ELF / LOL | Passed（范围/单位） | critic2 Cube → unified CLI → native grid templates | water HF/STO-3G WFX；critic2 1.3.15；40×40×40 | 安装态 Grid Volume；Research/Teaching 各两轮 Cycles Passed | 原 CUBE/输入 CBQ 移走；独立冷重开、Rebuild、Save As Passed |

每个量按五层独立取证：**模型 → 适配器/operation → 真实输入与来源 → 实际 UI/渲染 → 保存重开/缓存恢复**。动态图另检查 PNG 序列与 MP4。ELF/LOL 使用独立真实网格和生命周期证据，不以 NCI、源码能力或文件名代替。

本手册的 11 张 GUI 图均来自私有 Blender 实际操作，[截图清单](screenshots/manifest.json)记录图片哈希、确切安装包、项目身份与 View 参数，[操作记录](screenshots/operations.json)保留实际导入、计算、播放、导出与重开结果，[截图复核步骤](screenshots/REPLAY.md)给出从原始输入重现的顺序。界面截图、正式科学图和重开核验各自提供证据；后续补齐其余量的真实闭环时，应更新对应章节与验证表并重新构建网页。

<a id="offline"></a>
## 16. 离线网页的构建与维护

源文件是本 README，生成入口为 [build_html.mjs](build_html.mjs)。脚本使用已经安装的 Node.js 与 marked，不下载依赖。若本机可直接解析 `marked`：

```powershell
node docs/quantum-visualization/scientific-visualization/build_html.mjs
```

marked 位于外部已有依赖目录时，显式传入其本地 ESM 入口，不修改项目依赖：

```powershell
node docs/quantum-visualization/scientific-visualization/build_html.mjs --marked 'C:/path/to/installed/marked/lib/marked.esm.js'
```

构建会检查重复 / 缺失的章节锚点、本地链接和图片是否存在，拒绝空链接和远程脚本资源。所有样式内嵌在 `index.html`；输入文件、Markdown 附页和图片通过相对路径引用。修改截图或输入路径后，应重新运行构建并在浏览器检查宽屏 / 窄屏表格、目录、代码和本地图片。
