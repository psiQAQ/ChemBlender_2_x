# ChemBlender 2.5 案例目录与覆盖表

**这是设计映射，不是运行报告。全部案例初始状态均为 `not_run`。**

| ID | 场景 | 优先级 | 执行路线 |
|---|---|---|---|
| T00 | 安装、处理器诊断与离线查看 | P0 | Viewer；Standard prepare |
| T01 | 阿司匹林：从真实结构到第一张科研配图 | P0 | Standard；已有 CBQ 的查看路线不需要重计算后端 |
| T02 | SMILES → 三维构象 → 力场优化 → Mesh Apply | P0 | Standard / RDKit |
| T03 | SDF 多记录与显式构象分组 | P1 | Standard / RDKit |
| T04 | 晶体、占位与超胞：从 CIF 到周期结构图 | P0 | Standard / Gemmi；ASE 变体为 scientific 可选路线 |
| T05 | 蛋白与 PQR：层级、多个模型和原子电荷 | P1 | Standard |
| T06 | rMD17 阿司匹林轨迹与逐帧力 | P0 | Standard extXYZ |
| T07 | Cube 体数据、等值面、切片与差分 | P0 | Standard；VASP grid 变体为 scientific |
| T08 | 真实波函数的 HOMO/LUMO 与轨道相位 | P1 | wavefunction：qc-iodata / qc-gbasis；Viewer 可读预计算 CBQ |
| T09 | 电子密度、自旋密度与 1-RDM 差分 | P1 | wavefunction；预计算 CBQ 可离线看图 |
| T10 | ESP 映射到电子密度表面 | P1 | wavefunction；预计算同网格 CBQ 可直接显示 |
| T11 | IR/Raman 光谱与分子振动联动 | P1 | scientific / cclib |
| T12 | UV–Vis/ECD：跃迁与带符号谱线 | P1 | scientific / cclib |
| T13 | Si 能带与 DOS：并排展示但不混淆计算 | P1 | scientific / pymatgen |
| T14 | NaCl 声子：q 点相位与周期位移 | P1 | scientific / phonopy |
| T15 | QTAIM 与 NCI：从真实外部分析到图像 | P1 | critic2 独立 executable；场数据可另由 wavefunction 提供 |
| T16 | Fermi surface：合法均匀 k 网格与网格曲面 | P2 | fermi / pyprocar；另有数据授权前提 |
| T17 | 13 种格式的损失感知导出与交换 | P0 | Standard；某些源 reader 为 optional |
| T18 | 完整工程交接、冷重开、迁移与故障恢复 | P0 | Viewer；验证时主动隔离 processor/source（只操作副本） |
| T19 | 第三方 Reader 的正确扩展边界 | P2 | prepare 外部 Python Reader API 1.0-rc1；开发者教程 |
| T20 | QCSchema 交换与真实计算后端 | P2 | 交换部分 Standard；compute 要求实际可用 QCEngine/PySCF 等后端并经授权 |
| B01 | 在线 provider 的不可用边界验收 | P2 | 当前产品边界；不是正向在线教学案例 |

## T00 · 安装、处理器诊断与离线查看

**用户成果：**分别走通“已有结果直接查看”和“原始文件经 prepare 转换”；准确诊断缺失后端。

**输入：**经确认的 2.5 Extension ZIP、prepare wheel；T01 完成后发布的已验证 CBQ

**路线：**Viewer；Standard prepare

**公开 operation：**project.verify

**reader：**按案例说明，不增加内置 reader 计数

**View：**以当前公开 UI / 配套案例为准

**科学检查：**实际 ZIP/wheel SHA-256 与发布候选一致；Extension 版本、实际 Blender 版本、Worker Protocol 1 留证；干净 profile 中不依赖 checkout 或 Blender 科学包；Standard 必需项与 optional warnings 分开。

**真实界面留证：**Install from Disk 安装及启用；prepare GUI capabilities/doctor；Blender Test Processor 结果；取消或错误路径及恢复。

**禁止越界：**不把 optional unavailable 记为 Standard 失败；尚未公开发布的 wheel 不能写成已能从 PyPI 安装；不未经授权修改已有用户环境。

**依据：**S01, S05, S06, S16（详见 sources.json）。

## T01 · 阿司匹林：从真实结构到第一张科研配图

**用户成果：**导入真实分子结构，设置样式、相机和图注，Cycles 渲染并冷重开工程。

**输入：**沿用 examples/user-workflows/inputs/mol/ain-aspirin-v2000.md 对应原始数据及 manifest

**路线：**Standard；已有 CBQ 的查看路线不需要重计算后端

**公开 operation：**reader.parse

**reader：**mol, mol-v2000

**View：**structure_publication

**科学检查：**原子、元素、显式氢、键与输入对照；相机/对象展示变换不改变科学坐标；输出包含 .blend 与相邻 .cbq。

**真实界面留证：**prepare inspect/convert 输入和输出；CBQ Preview/Import；Project Browser 与 Structure View 设置；Render Result；冷重开后的实体与视图。

**禁止越界：**不要把调整球棍外观称为几何优化；精确输入文件名、原子数从现有 manifest 实查，不凭分子名称推定。

**依据：**S12, S15, S17（详见 sources.json）。

## T02 · SMILES → 三维构象 → 力场优化 → Mesh Apply

**用户成果：**认识 2D 图、3D 构象、力场能量和 Blender 编辑的不同职责。

**输入：**现有 ethanol SMILES；可增补一个授权的芳香分子输入，保留原文和立体化学

**路线：**Standard / RDKit

**公开 operation：**molecule.smiles_to_3d, molecule.kekulize, molecule.optimize, molecule.energy

**reader：**smiles

**View：**structure_publication

**科学检查：**固定随机种子（仅当实际公开参数支持）和力场名；记录是否收敛及不支持参数；Apply 新增 derived Structure，原坐标和旧 View 不覆盖；比较同一力场、同一分子定义下的优化结果。

**真实界面留证：**2D 导入诊断；三维/优化 operation 参数与完成状态；Mesh 编辑前后及 Apply；旧实体和 derived 实体并存。

**禁止越界：**MMFF/UFF 不是 HF/DFT；无真实收敛判定不得写“已优化到基态”；局部 Mesh 编辑不自动重算量子性质。

**依据：**S01, S04, S17, S29（详见 sources.json）。

## T03 · SDF 多记录与显式构象分组

**用户成果：**区分多分子记录与同一分子的构象集合，并理解分组确认。

**输入：**CCD SDF showcase；另选具有稳定 atom mapping 的同分子构象数据；不同分子负例单独保存

**路线：**Standard / RDKit

**公开 operation：**reader.parse, molecule.group_conformers

**reader：**sdf

**View：**structure_publication

**科学检查：**记录总数与恢复诊断一致；构象映射完整，元素、键和身份匹配；不把截断映射和不同分子当作合法构象组。

**真实界面留证：**inspect 记录表；构象候选复核窗口；显式接受参数；有效与拒绝分组的结果。

**禁止越界：**已有 showcase 不保证每条记录互为构象；能量缺失不能虚构排序或 Boltzmann 分布。

**依据：**S12, S17, S02（详见 sources.json）。

## T04 · 晶体、占位与超胞：从 CIF 到周期结构图

**用户成果：**展示晶胞、周期结构及已有超胞，解释 occupancy/disorder。

**输入：**COD 4503272 共晶 CIF；COD 9012293 diamond 2×2×2 POSCAR 的现有数据

**路线：**Standard / Gemmi；ASE 变体为 scientific 可选路线

**公开 operation：**reader.parse

**reader：**cif, poscar, ase-structure

**View：**structure_publication

**科学检查：**晶格矩阵、分数/笛卡尔坐标、单位与输入一致；64-site 数据与原胞/常规胞明确区分；占位和 disorder 不静默删掉；ASE reader 另记真实依赖与格式。

**真实界面留证：**CIF 多块和晶胞预览；实体选取与周期展示；两个尺度结构及图注；POSCAR 输入约定。

**禁止越界：**已存在超胞的显示不等于插件提供任意超胞生成按钮；有序展示不等于解决无序结构；不能承诺未验收的表面/缺陷生成流程。

**依据：**S12, S15, S10（详见 sources.json）。

## T05 · 蛋白与 PQR：层级、多个模型和原子电荷

**用户成果：**查看结构层级和 NMR 模型；展示已有电荷/半径，不混淆电子密度。

**输入：**1D3Z ubiquitin NMR PDB；APBS protein/RNA PQR；OpenBabel 5SUN MOL2

**路线：**Standard

**公开 operation：**reader.parse

**reader：**pdb, pqr, mol2

**View：**structure_publication, atomic_scalar

**科学检查：**1D3Z 的 10 MODEL 与层级保留；MOL2 代表输入 6185 原子按源复验；PQR charge/radius 单位和缺失项保留；不同模型不被当作时间序列。

**真实界面留证：**导入摘要与模型/层级入口；选择相关实体；原子标量配色和图例；代表性大结构渲染。

**禁止越界：**不凭 PDB 支持宣称 docking/接触分析/蛋白动力学已实现；原子点电荷不等于三维 ESP 场；Cartoon 等表示仅在当前公开 UI 实查通过后收录。

**依据：**S12, S15（详见 sources.json）。

## T06 · rMD17 阿司匹林轨迹与逐帧力

**用户成果：**用时间线播放真实坐标，联动原子力箭头与能量记录。

**输入：**现有 aspirin-rmd17-32 数据：32 帧 × 21 原子

**路线：**Standard extXYZ

**公开 operation：**reader.parse

**reader：**extxyz, xyz

**View：**trajectory, trajectory_force, atomic_vector

**科学检查：**32 帧及每帧原子映射一致；抽检首、中、末帧坐标和力向量；整段播放后来源数组哈希不变；区分动画帧率与物理采样间隔。

**真实界面留证：**FrameSet 与 force dataset 绑定；首/中/末帧界面；播放过程短录屏；力箭头比例与单位。

**禁止越界：**未提供物理 Δt，横轴用 source frame 而不是 ps；箭头缩放是显示参数；不能从任意展示片段推导动力学统计结论。

**依据：**S12, S13, S15（详见 sources.json）。

## T07 · Cube 体数据、等值面、切片与差分

**用户成果：**从显式场语义开始，生成 Volume/Surface/切片/剖面/色标并比较兼容网格。

**输入：**现有 64³ H₂ LCAO-1s density Cube；有符号网格测试输入；CHGCAR/LOCPOT 变体需另核对合法真实来源

**路线：**Standard；VASP grid 变体为 scientific

**公开 operation：**reader.parse, grid.resolve_semantics, grid.difference

**reader：**cube, pymatgen-vasp-grid

**View：**grid_volume, signed_isosurface, grid_slice, grid_profile, grid_colorbar

**科学检查：**64³ 网格对应 262144 采样点；检查原点、三轴步长、轴顺序、单位与 dataset index；同网格差分及不兼容网格拒绝分开；切片/剖面数值与原网格独立抽样对照。

**真实界面留证：**语义/单位确认；Grid View 参数；切片平面与剖面路径；差分合法/非法输入；Cycles 输出。

**禁止越界：**H₂ LCAO 输入标为解析/教学数据，不冒充高等级 ab initio 结果；一般有符号标量场不等于分子轨道；电子密度和轨道振幅单位不同。

**依据：**S12, S15, S17, S02（详见 sources.json）。

## T08 · 真实波函数的 HOMO/LUMO 与轨道相位

**用户成果：**从已有量子化学结果读取轨道并在外部求值网格，展示正负相位。

**输入：**IOData 固定 water FCHK/Molden 语料；实际文件和方法按 input-manifest 核对

**路线：**wavefunction：qc-iodata / qc-gbasis；Viewer 可读预计算 CBQ

**公开 operation：**reader.parse, wavefunction.mo_grid

**reader：**iodata_wavefunction

**View：**signed_isosurface, grid_volume

**科学检查：**轨道索引、占据、自旋、基组和来源方法有记录；正负两相采用同一 |isovalue|；网格预算、单位与轴方向明确；不能仅凭文件存在推断某个未占据轨道可用。

**真实界面留证：**轨道列表和选择；外部求值参数/进度；两相等值面参数；带轨道标签的最终图。

**禁止越界：**轨道振幅的正负不是正负电荷；表面是选定等值面，不是电子运动轨迹；不跨独立计算直接比较未对齐轨道相位。

**依据：**S14, S15, S16, S29（详见 sources.json）。

## T09 · 电子密度、自旋密度与 1-RDM 差分

**用户成果：**比较轨道构建密度和密度矩阵结果，展示开壳层自旋分布。

**输入：**IOData water/CH₃ FCHK 与 nitrogen MP2 FCHK；只使用确实包含所需信息的原文件

**路线：**wavefunction；预计算 CBQ 可离线看图

**公开 operation：**wavefunction.electron_density_grid, wavefunction.density_matrix_grid, grid.difference

**reader：**iodata_wavefunction

**View：**grid_volume, signed_isosurface, grid_slice, grid_profile

**科学检查：**电子密度/自旋密度角色及 RDM 层级写明；数值积分随网格范围/分辨率作收敛检查；差分要求坐标、网格、电子数和参考约定可比；参考值和容差从真实数据及独立计算确定。

**真实界面留证：**密度来源/自旋选择；两种结果数据集；差分参数与色标；积分及误差表。

**禁止越界：**不能随意把两个不同计算的差叫相关修正；网格截断会影响积分；未解析到相关 RDM 则标记阻塞，不用占据轨道密度顶替。

**依据：**S14, S15, S02（详见 sources.json）。

## T10 · ESP 映射到电子密度表面

**用户成果：**把表面定义和表面着色分开：密度决定几何，ESP 决定颜色。

**输入：**具有所需电子信息的 water FCHK/Molden；与密度同结构、同仿射网格的 ESP

**路线：**wavefunction；预计算同网格 CBQ 可直接显示

**公开 operation：**wavefunction.esp_grid, wavefunction.esp_from_orbitals_grid

**reader：**iodata_wavefunction

**View：**property_on_surface, grid_colorbar, grid_slice

**科学检查：**表面网格和属性网格共享仿射变换；单位、isovalue、颜色范围和零点明确；核附近奇异值处理不得暗中影响图例；两条 ESP 路线仅在各自输入满足时正向验收。

**真实界面留证：**主表面/第二属性网格绑定；色标及单位；错误配对被拒绝；同一视角的密度与 ESP 图。

**禁止越界：**ESP 不是电子密度；原子电荷着色不等价于波函数 ESP；不能用亮度或颜色深浅替代物理单位。

**依据：**S14, S15, S29（详见 sources.json）。

## T11 · IR/Raman 光谱与分子振动联动

**用户成果：**从峰选择到振动模式动画，解释谱线与可视化振幅。

**输入：**现有 Gaussian 16 与 ORCA 5 dvb IR/Raman 输出，分别作为独立 Calculation

**路线：**scientific / cclib

**公开 operation：**reader.parse

**reader：**cclib_output

**View：**vibration_mode, vibration_spectrum_linked, spectrum_plot

**科学检查：**频率、模式索引、位移和单位与源输出对照；记录展宽函数及参数；虚频和缺失强度不静默处理；Gaussian/ORCA 两个文件不合并成一次计算。

**真实界面留证：**光谱和选中峰；链接模式与振幅设置；一个周期中的代表相位；播放录屏和结果图。

**禁止越界：**Raman activity 不直接叫实验强度；动画振幅通常为显示放大；未注明缩放的计算谱不冒充实验拟合。

**依据：**S14, S15（详见 sources.json）。

## T12 · UV–Vis/ECD：跃迁与带符号谱线

**用户成果：**展示跃迁强度和有符号 ECD，保留每份计算的来源和单位。

**输入：**Gaussian 16 / ORCA 5 TD；Gaussian 09 含非零 signed rotatory strengths 的独立语料

**路线：**scientific / cclib

**公开 operation：**reader.parse

**reader：**cclib_output

**View：**electronic_spectrum_linked, spectrum_plot

**科学检查：**激发能、oscillator/rotatory strength 与源输出对应；ECD 使用记录中的 length gauge 和原始单位；禁阻跃迁及零强度保留；能量与波长转换说明采用的谱密度约定。

**真实界面留证：**激发态列表；谱线/跃迁联动；正负 ECD 色标和单位；不同源文件的项目身份。

**禁止越界：**不把 rotatory strength 直接称实验 molar ECD；不擅自宣称电子/空穴或 NTO 场已提供；计算结果不等于实验谱。

**依据：**S14, S15（详见 sources.json）。

## T13 · Si 能带与 DOS：并排展示但不混淆计算

**用户成果：**明确结构绑定、能量参考、自旋与投影通道。

**输入：**现有 Si bands：160 个高对称路径点与 KPOINTS；独立 DOS：4×4×4 网格、10 不可约点

**路线：**scientific / pymatgen

**公开 operation：**reader.parse

**reader：**pymatgen-vasprun-electronic

**View：**band_structure, density_of_states, band_dos_linked

**科学检查：**每个 Calculation 独立记录 E_F 和方法；能带路径不冒充均匀 k 网格；linked preset 的 Structure 身份约束真实满足；不重写原始身份来强行链接不同计算。

**真实界面留证：**伴随 KPOINTS 输入；能带坐标/高对称标签；DOS/投影通道；独立来源图注或合法 linked View。

**禁止越界：**已有 bands/DOS 来源不是同一次自洽计算；若无法合法建立共享结构，使用两个独立 View 并排，不绕过校验。

**依据：**S14, S15, S29（详见 sources.json）。

## T14 · NaCl 声子：q 点相位与周期位移

**用户成果：**从真实有限位移数据生成模式并在 Blender 中展示周期相位。

**输入：**现有 NaCl FORCE_SETS、位移 YAML、BORN、原胞和 VASP XML

**路线：**scientific / phonopy

**公开 operation：**reader.parse, periodic.phonon

**reader：**phonopy-file

**View：**phonon_mode

**科学检查：**FORCE_SETS 伴随文件必须在真实路径中使用；q 点坐标约定、频率、复特征向量和归一化保留；原胞/超胞/显示副本映射一致；BORN 非解析修正配置单独记录。

**真实界面留证：**phonopy 文件及伴随文件选择；q 点与模式设置；相邻晶胞不同相位；时间线播放。

**禁止越界：**模式示意不是有限温度 MD；不以已有适配器或旧图片代替当前文件工作流正向验收。

**依据：**S14, S15, S29（详见 sources.json）。

## T15 · QTAIM 与 NCI：从真实外部分析到图像

**用户成果：**展示已有临界点/路径与 NCI 场，解释数值计算和显示层界限。

**输入：**现有 water WFX 与合法真实密度；绑定同一结构的 critic2 输出

**路线：**critic2 独立 executable；场数据可另由 wavefunction 提供

**公开 operation：**topology.qtaim, grid.nci_fields

**reader：**按案例说明，不增加内置 reader 计数

**View：**topology_graph, nci_surface

**科学检查：**外部命令、版本、输入/输出哈希与返回码留存；临界点/路径确实在输出中存在；RDG 与 sign(lambda2)rho 配对约定校验；失败或取消不发布部分科学结果。

**真实界面留证：**critic2 能力状态；operation 参数/进度；临界点/路径与 NCI 参数；带量纲或无量纲标注的最终图。

**禁止越界：**不虚构缺失路径；QTAIM/NCI 结果不是直接键能或相互作用强弱定量结论；ELF/LOL 历史外部成果不意味着存在同名公开 operation。

**依据：**S13, S14, S15, S02（详见 sources.json）。

## T16 · Fermi surface：合法均匀 k 网格与网格曲面

**用户成果：**读取合法周期电子数据，生成 FermiSurfaceMesh 和可复用渲染。

**输入：**现有 Fermi 原档涉及 POTCAR/pickle 与分发许可问题；公开教程应替换为明确允许分发的数据或只发布取数说明

**路线：**fermi / pyprocar；另有数据授权前提

**公开 operation：**periodic.fermi_surface

**reader：**按案例说明，不增加内置 reader 计数

**View：**fermi_surface

**科学检查：**INCAR/KPOINTS/POSCAR/OUTCAR/PROCAR 及可选 IBZKPT 哈希；k 采样确适合 Fermi 重建；能量参考和选带/自旋明确；生成网格形状和坐标轴与原数据一致。

**真实界面留证：**后端和源文件清单；选带/能量设置；外部任务结果；布里渊区内曲面图。

**禁止越界：**未解决许可前不得放入公开样例 ZIP；不提取/执行 pickle 或泄露 POTCAR；一维能带路径不能替代 Fermi 三维采样。

**依据：**S14, S15, S29（详见 sources.json）。

## T17 · 13 种格式的损失感知导出与交换

**用户成果：**理解“格式能写出”与“所有科学信息能保留”的区别。

**输入：**已有 XYZ/extXYZ/MOL/V3000/SDF/SMILES/CIF/POSCAR/MOL2/PDB/PQR/Cube/CJSON/QCSchema 真实输入与小型合同变体

**路线：**Standard；某些源 reader 为 optional

**公开 operation：**molecule.export, reader.parse

**reader：**xyz, extxyz, mol, mol-v2000, sdf, smiles, cif, poscar, mol2, pdb, pqr, cube, cjson, qcschema, gaussian-input, orca-input

**View：**以当前公开 UI / 配套案例为准

**科学检查：**13 个公开目标格式各一份适用实体与预览报告；存在损失时必须明确确认；重导入比较可表达字段，而不是文本字节完全相同；Gaussian/ORCA 输入 reader 仅证明实际解析出的信息。

**真实界面留证：**导出对象选择与 preview；损失清单/确认；一次成功导出和重导入；格式能力矩阵。

**禁止越界：**.inp/.com 输入读取不是运行相应量子化学程序；不得给每种格式编造通用完整 round-trip 保真承诺；unsupported 组合应正确拒绝而非作成功计数。

**依据：**S02, S12, S17（详见 sources.json）。

## T18 · 完整工程交接、冷重开、迁移与故障恢复

**用户成果：**把可视化当作可交接项目：保存、移动、重建与恢复都有证据。

**输入：**T01/T06/T07 和选定高级案例的配对工程；另有历史 legacy 工程副本

**路线：**Viewer；验证时主动隔离 processor/source（只操作副本）

**公开 operation：**project.verify

**reader：**按案例说明，不增加内置 reader 计数

**View：**以当前公开 UI / 配套案例为准

**科学检查：**独立进程冷重开 .blend + .cbq；整体移动后科学实体 UUID/revision/数组哈希保持；删除副本的派生缓存后在无 processor/source 时重建视图；取消/错路径/失效 revision/损坏副本不污染原项目；legacy 显式迁移只生成新输出。

**真实界面留证：**Save/Save As 与文件对；重开和移动后的 Project Browser；Relink 失败及恢复；任务取消状态；缓存重建结果。

**禁止越界：**不得重命名/删除用户原始环境或科学输入来做破坏性测试；不要用 .blend 二进制字节恒等代替科学数组守恒；只隔离显示缓存，不删除 CBQ 权威科学数组。

**依据：**S03, S04, S06, S18（详见 sources.json）。

## T19 · 第三方 Reader 的正确扩展边界

**用户成果：**展示第三方解析器如何返回合法数据并交付 CBQ，而不是注入 Blender。

**输入：**复用 SimpleCoords reader.py 与来源许可证；不要安装历史 Blender reader Extension

**路线：**prepare 外部 Python Reader API 1.0-rc1；开发者教程

**公开 operation：**不新增计算 operation

**reader：**按案例说明，不增加内置 reader 计数

**View：**以当前公开 UI / 配套案例为准

**科学检查：**显式注册/discovery/unregister 与 conformance；拒绝无效单位/原子数量输入；生成经校验 CBQ 后再由 Viewer 导入；确认实际公开入口，记录稳定 API 与内部 pipeline 的分界。

**真实界面留证：**合法 CBQ 的 Viewer 导入结果；Reader 关闭后已有项目仍可打开。

**禁止越界：**默认 CLI 不自动加载第三方实例；注册示例不是完整安装式插件分发流程；不得把 core.* 包装成已承诺的稳定 SDK；需要新桥接功能时单列提案。

**依据：**S11, S18, S27（详见 sources.json）。

## T20 · QCSchema 交换与真实计算后端

**用户成果：**区分导入已有 AtomicResult 与重新进行真实计算。

**输入：**现有 MolSSI water gradient HF QCSchema；新增计算输入需固定方法、基组、电荷与自旋

**路线：**交换部分 Standard；compute 要求实际可用 QCEngine/PySCF 等后端并经授权

**公开 operation：**qcschema.compute

**reader：**qcschema

**View：**structure_publication, atomic_vector

**科学检查：**实际 compute backend、方法/基组和程序版本留存；SCF/梯度成功结果与输入身份对应；现有原始结果导入与新计算分别归档；gradient 与 force 的符号及单位不能混淆。

**真实界面留证：**CLI/GUI compute 路由可用性；计算成功或明确 unavailable；导入的结果实体与向量表示。

**禁止越界：**runtime 探测到 distribution 不等于实际计算通过；qcschema.compute 当前走 current 环境；不凭空新增 qcschema route 键；不得把 fixture/fake transport 当真实计算。

**依据：**S10, S12, S18（详见 sources.json）。

## B01 · 在线 provider 的不可用边界验收

**用户成果：**准确解释在线连接器状态，阻止把注册项当可用取数功能。

**输入：**当前 runtime capabilities 及明确的未配置状态；PubChem 专用 convert 路线另测

**路线：**当前产品边界；不是正向在线教学案例

**公开 operation：**external_record.fetch

**reader：**按案例说明，不增加内置 reader 计数

**View：**以当前公开 UI / 配套案例为准

**科学检查：**当前源码明确 available=False，reason=no live provider transport configured；诊断信息与 UI/文档保持一致；不通过 mock 成功伪装真实在线结果。

**真实界面留证：**capabilities/doctor 中的明确 unavailable。

**禁止越界：**PubChem 专用下载路线不等于通用 external_record.fetch 已打通；要支持真实 provider 需独立产品改动与安全/授权审查；BOUNDARY 通过不能计作正向 compute/fetch 通过。

**依据：**S10, S02（详见 sources.json）。

## 公开 operation 覆盖

| Operation | 版本 | 设计案例 |
|---|---|---|
| `external_record.fetch` | 1 | B01 |
| `grid.difference` | 1 | T07, T09 |
| `grid.nci_fields` | 1 | T15 |
| `grid.resolve_semantics` | 1 | T07 |
| `molecule.energy` | 1 | T02 |
| `molecule.export` | 1 | T17 |
| `molecule.group_conformers` | 1 | T03 |
| `molecule.kekulize` | 1 | T02 |
| `molecule.optimize` | 1 | T02 |
| `molecule.smiles_to_3d` | 1 | T02 |
| `periodic.fermi_surface` | 1 | T16 |
| `periodic.phonon` | 1 | T14 |
| `project.verify` | 1 | T00, T18 |
| `qcschema.compute` | 1 | T20 |
| `reader.parse` | 0.1 | T01, T03, T04, T05, T06, T07, T08, T11, T12, T13, T14, T17 |
| `topology.qtaim` | 1 | T15 |
| `wavefunction.density_matrix_grid` | 1 | T09 |
| `wavefunction.electron_density_grid` | 1 | T09 |
| `wavefunction.esp_from_orbitals_grid` | 1 | T10 |
| `wavefunction.esp_grid` | 1 | T10 |
| `wavefunction.mo_grid` | 1 | T08 |

## 内置 reader 覆盖

| Reader | 设计案例 |
|---|---|
| `ase-structure` | T04 |
| `cclib_output` | T11, T12 |
| `cif` | T04, T17 |
| `cjson` | T17 |
| `cube` | T07, T17 |
| `extxyz` | T06, T17 |
| `gaussian-input` | T17 |
| `iodata_wavefunction` | T08, T09, T10 |
| `mol` | T01, T17 |
| `mol-v2000` | T01, T17 |
| `mol2` | T05, T17 |
| `orca-input` | T17 |
| `pdb` | T05, T17 |
| `phonopy-file` | T14 |
| `poscar` | T04, T17 |
| `pqr` | T05, T17 |
| `pymatgen-vasp-grid` | T07 |
| `pymatgen-vasprun-electronic` | T13 |
| `qcschema` | T17, T20 |
| `sdf` | T03, T17 |
| `smiles` | T02, T17 |
| `xyz` | T06, T17 |
