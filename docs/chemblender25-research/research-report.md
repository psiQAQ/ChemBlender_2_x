# ChemBlender 2.5 用户教程与真实案例交付调研

## 结论与审查范围

ChemBlender 2.5 最需要补齐的不是更多功能说明，而是一套**以真实科研任务为主线、绑定具体发布制品、由真实 GUI 操作和科学数据检查共同证明的教程交付体系**。建议新增独立的“2.5 教程与案例验收”里程碑：复用现有输入语料与来源记录，重新执行当前架构下的用户路径；不要把旧脚本改几个版本号、旧图换标题，或把一次安装烟测当作教程完成。

本报告固定检查 `release/2.5.0` 在调研时的 HEAD：`478bbd498277a0ce9a32fc9b262f36ec8410d2d9`，时间范围截至 2026-09-10。证据来自该提交的用户文档、公开接口清单、生产注册/路由/View 实现、案例索引、图像 manifest、离线文档生成器及 GitHub Release/Actions 查询；外部对照仅采用官方或项目一手文档。不是对整个仓库的完整代码安全审计，也没有在用户机器上重跑 Blender、外部计算或 GUI 教程。[S01][S02][S21][S28]

**本交付物中的所有新案例均为设计状态 `not_run`。** 已有 2.5 资格数字均明确归于仓库记录，不能当作本次独立执行成绩。附带案例目录、执行任务书和证据检查器是供本地 agent 落地使用的材料，不是已经完成的新截图、新视频或新 `.blend` 工程。

## 一、当前项目已经具备什么

2.5 将科学计算和 Blender 显示明确分离。Extension 负责 CBQ 导入/导出、纯 Mesh 编辑及 Apply、View、动画、Cycles 和项目恢复；外部 `chemblender-prepare 0.1.0` 负责读取原始科学文件、派生、校验、交换、诊断及 Worker 执行。Standard prepare 的 NumPy、RDKit、Gemmi 位于独立 Python 3.12 环境，而不是 Blender 的科学依赖安装目录。[S01][S05][S06]

权威数据是 `.cbq/` 内的科学实体、来源、revision 与数组；`.blend` 保存 Blender 场景、呈现状态和项目链接。修改外观不改变科学事实；Mesh Apply 应新增 derived Structure，不覆盖 imported Structure。这不仅是架构细节，也是新用户教程必须教会的第一层概念。[S04][S15]

| 公开面 | 当前清单数量 | 对教程设计的含义 |
|---|---:|---|
| CLI commands | 10 | 要覆盖能力诊断、转换、派生、校验、导出、升级、Worker 等入口 |
| GUI commands | 9 | prepare GUI 需要自己的真实操作图，不只拍 Blender |
| Worker operations | 21 | 注册存在、环境可用、真实成功必须分别判定 |
| 内置 readers | 22 | 应有 reader→案例映射，不必写 22 篇重复导入教程 |
| 导出格式 | 13 | 每个目标格式要记录适用实体、保留信息及损失确认 |

以上数量来自当前生成的公开清单，不是当前机器的可用数量，更不是端到端成功数量。[S02]

仓库已经有中英文用户/prepare 指南、2.5 SOP、离线 HTML 和一张声明由隔离安装实例采集的 Blender 截图；2.4 用户流程明确归档。已有科学案例还保存了波函数、轨迹、原子性质、谱学、周期结构输入，以及一些历史渲染和工作台工程。因此不能将当前状态描述为“没有文档、没有实图、没有真实案例”。准确的缺口是：**新版本的场景化教学和逐步操作证据尚未形成完整交付链。**[S03][S06][S12][S13]

## 二、优先修复的交付缺口

### 1. 截图没有绑定到最终资格 ZIP

当前 `docs/user/assets/2.5.0/manifest.json` 记录的截图构建，与最终交付记录中的构建哈希不同。[S06][S07]

| 记录 | Extension ZIP SHA-256 |
|---|---|
| 当前 2.5 截图 manifest | `1eb77f65fab61b89645554f38015014979bd12a91f393104fea3c6b175e870dc` |
| 最终本地交付资格记录 | `8e92b3439e92be8f90e3e63fd25e935a2592148d464d010ee1ca3a87e85ea6eb` |

这**不能证明截图伪造，也不能证明功能错误**；它证明目前缺少“最终制品→运行实例→截图”的一致性闭环。最稳妥的处理是冻结新教程使用的制品，重新安装、执行和采集。如果确实只发生不影响界面的构建变更，也必须给出可审计的差异与例外说明，不能默认为同一制品。

### 2. 根 AGENTS 存在旧依赖规则

根规则仍写着：`RDKit remains a pinned offline manifest wheel`；当前交付文档则把 2.5 定义为 `a wheel-free Blender Viewer`。根规则还要求验证 Blender 内的 RDKit import，而新交付记录恰恰验证了 Blender 不能 import RDKit/Gemmi/prepare。[S09][S06]

建议先同步当前有效规则和历史决策链接，再开展本地 agent 教程工作。不应让 agent 为了遵守过期条目，把科学依赖重新塞回 Extension。这里是**规则口径过时**，不等于应推翻当前架构。

### 3. 现有 SOP 是总流程，不是可照做的完整课程

当前 SOP 覆盖安装、Test Processor、生成 CBQ、导入/Apply、外部 operation、View、保存/移动/重建/恢复，但步骤普遍是高层动作。它没有对每一个真实输入给出全部当前界面路径、确切参数、每步预期现象、失败提示、下载制品及独立复做证据。[S03]

例如“创建 Surface”不够。教程需要明确：选的是哪个科学实体、语义是什么、单位是什么、等值面阈值怎么选、正负两相是否对称、第二个属性场是否与表面网格匹配、成功后界面出现什么，以及渲染是否使用该 View。不能要求读者自己阅读源代码补齐这些信息。

### 4. 离线 HTML 的字节一致性不等于可用性

当前生成器的 `_inline()` 将 Markdown 链接转换为文字与括号 URL，而不是正文可点击链接；表格逐行生成 `<pre>`；截图通过固定列表统一插入正文前方。manifest 中 `remote_resources` 与 `missing_resources` 为固定写入的数值，`--check` 主要比较生成字节是否与仓库一致。[S08]

这些实现足以支持“生成物与源码同步”的检查，却不足以支持“所有教程链接可用、步骤图片就近显示、表格可读、下载目标存在”的用户验收。建议在现有生成器上最小增量修复：支持内部跳转、正文插图和语义表格；额外执行实际资源遍历与浏览检查。没有必要为此重写一个通用文档平台。

### 5. 可选能力必须比 README 描述更精确

`runtime.py` 对 `external_record.fetch` 直接返回 `available=False` 与 `no live provider transport configured`。这不是“用户再填写一个 provider 配置就一定能用”的证据。它应进入不可用边界说明，而非正常在线数据获取教程。专用 PubChem 转换路径与通用 provider operation 也不能相互代证。[S10]

第三方 Reader 的公开集成说明明确：当前 CLI 默认只有 22 个内置 reader，**不会自动加载**文档中显式注册的第三方实例。历史 SimpleCoords Blender Extension 已明确不应安装到当前 Viewer。因此“安装一个 Reader 扩展就会自动出现在 2.5 导入界面”的教程是不成立的。[S11][S27]

QCSchema compute 的能力探测检查 `current` 环境中的 QCEngine/PySCF 等发行包；不能从包元数据存在直接推断某个程序、方法、基组的计算成功，更不能凭空增加一个配置文档未支持的路由键。[S10][S16]

### 6. 发布资格与公开发布仍要分开

仓库记录已完成本地 2.5 资格；本次查询的最新公开 Release 仍是 2026-08-03 发布的 v2.4.0，精确调研 HEAD 的 Actions 查询返回零条运行。这里仅说明本次查询结果和该 HEAD 的证据边界，不否定其他提交的 CI，也不代表已经重测本地资格。[S06][S19][S20]

| 仓库记录的本地资格项 | 记录值/状态 | 本次独立执行 |
|---|---|---|
| 单元测试 | 2,531 passed；36 skipped；0 failures/errors | 未执行 |
| 资格 Blender | 5.1.1 | 未启动 |
| 原生安装、冷启动、reload、View/Cycles、生命周期 | Passed | 未执行 |
| Extension ZIP | 2,830,577 bytes；109 members；无 wheels | 未下载复核二进制 |
| 远端 2.5 发布/PyPI | Not Run by approved boundary | 未发布 |

表中全部历史执行状态来自仓库资格记录，不是本报告生成的新成绩。[S06]

## 三、产品能力应该怎样呈现给用户

建议每个教程明确两条路线，而不是要求所有读者先搭满科学环境。

**结果查看路线：** 下载已校验 CBQ 和配套 `.blend`，在真实 Viewer 中导入、改样式、播放、渲染、保存。发布这些预计算结果前，必须确认其中所需科学实体确实已持久化，并真实测试移除 source/processor 后仍能重建对应 View。不能泛化为“所有外部结果都天然完全离线”。[S01][S03][S04]

**原始数据重算路线：** 用户按明确的输入、版本、后端、参数重新 convert/derive，再把结果交给同一个 Viewer。需要专用后端时，将安装与权限说明放在独立准备章节，不在教程中隐式安装，也不把内部 Python helper 当作稳定 API。[S16][S17][S18]

| 能力层 | 可教学的内容 | 必须保留的条件 |
|---|---|---|
| Viewer 本地 | 结构显示、纯 Mesh 编辑/Apply、各类已存数据 View、动画、Cycles、项目交接 | 科学实体/数组确实存在；View 类型与实体匹配 |
| Standard prepare | 原生分子/晶体/网格/交换格式、RDKit 分子操作、校验与导出 | 独立 Standard 环境完整；输入和语义满足 operation 要求 |
| wavefunction | MO、电子/自旋密度、RDM 网格、ESP | 对应波函数/密度矩阵信息存在；路由安装同版本 prepare |
| scientific | cclib 光谱/振动、ASE/pymatgen 周期数据、phonopy | 源文件及伴随文件、版本、数据集关联真实成立 |
| critic2 / Fermi | QTAIM/NCI、Fermi surface | 后端真实运行；输入数据和许可可用 |
| 特殊扩展 | Reader API、QCSchema compute、provider 边界 | 不等同于默认 CLI 即插即用；分别做集成和失败验收 |

该表依据当前代码路由、公开清单和 View 匹配实现；它不是新增功能承诺。[S02][S10][S15][S16][S18]

## 四、建议的真实案例集

建议采用 **21 个教学/操作案例，加 1 个在线 provider 边界验收单**。这是按用户成果划分的内容单元，不是要求同时发布 22 篇长文。首批 P0 是 8 个案例；已有后端和数据的 P1 再分批推进。任何对外宣传的高级案例，都必须先完成其正向实操，不因“在 P1/P2”而免验收。

| ID | 用户最终得到什么 | 输入与关键后端 | 关键界限 |
|---|---|---|---|
| T00 | 能安装、Test Processor，并识别正常 optional warning | 最终 ZIP/wheel；Standard | 记录真实版本，不能假设 PyPI 已发布 |
| T01 | 阿司匹林第一张科研配图及可交接工程 | 现有 AIN MOL；Standard | 外观调整不改变科学坐标 |
| T02 | SMILES 三维构象、力场优化和 derived Mesh 编辑 | RDKit | 力场能量不是 DFT；原结构不可覆盖 |
| T03 | 可解释的 SDF 记录与构象分组 | 有稳定 atom mapping 的数据 | 不能把多分子集合自动叫构象系综 |
| T04 | CIF 占位/晶胞与已有 diamond 超胞图 | COD CIF、64-site POSCAR | 显示已有超胞不等于存在任意超胞生成器 |
| T05 | 多模型蛋白结构与 PQR 电荷图 | 1D3Z、APBS PQR、5SUN MOL2 | NMR 模型不是 MD 时间序列；电荷不是密度 |
| T06 | rMD17 坐标动画与逐帧力 | 32 帧×21 原子 extXYZ | 无 Δt 时只标 source frame |
| T07 | Cube 体渲染、等值面、切片、剖面与差分 | 64³ H₂ 网格；VASP 变体可选 | 明确解析教学数据、单位和仿射网格 |
| T08 | 正负相位可解释的 HOMO/LUMO 图 | IOData/GBasis | 轨道振幅正负不是电荷正负 |
| T09 | 电子/自旋密度、RDM 与可比差分 | water、CH₃、N MP2 语料 | 信息不足即阻塞，不以另一种密度偷换 |
| T10 | 密度表面上着色的 ESP | 同结构、同网格双场 | 几何与颜色来自两个不同物理量 |
| T11 | IR/Raman 峰与振动动画联动 | cclib；Gaussian/ORCA 分开 | Raman activity 不冒充实验强度 |
| T12 | UV–Vis/ECD 跃迁谱图 | 真实 TD 输出 | ECD gauge、符号、单位保留 |
| T13 | Si 能带与 DOS 图 | 独立 bands/DOS 计算 | 两份 E_F/来源分开；不得强改身份强制链接 |
| T14 | NaCl q 点声子动画 | phonopy、FORCE_SETS 等 | 周期相位演示不是有限温度动力学 |
| T15 | QTAIM 图和 NCI 曲面 | critic2 真实输出 | 缺失路径不虚构；不凭图推定键能 |
| T16 | 合法 Fermi surface 与可重开的场景 | pyprocar、均匀 k 采样 | 先解决许可；不发布 POTCAR/pickle |
| T17 | 13 格式的损失说明、导出与重导入 | 已有格式语料 | 按可表达字段验收，不要求文件逐字相同 |
| T18 | 保存、移动、缓存重建、取消、Relink 和迁移指南 | 各代表工程的副本 | 只能破坏测试副本；科学数组不是可删缓存 |
| T19 | 第三方 Reader 外部集成示例 | Reader API 1.0-rc1 | 默认 CLI 不自动加载；旧 Blender 扩展不可用 |
| T20 | 已有 QCSchema 结果与真实重算的区别 | QCSchema；授权计算后端 | metadata 可用不等于计算成功 |
| B01 | 用户理解 provider 为何 unavailable | 当前 runtime | 负向边界通过不计正向取数成功 |

前述输入存在性、代表规模和历史数据边界主要来自现有两套案例索引及输入说明；拟补样的构象、VASP grid 或可公开 Fermi 数据在详细目录中均明确为“需要核对/补齐”，不宣称已存在。[S12][S13][S14] 场景匹配与可用 View 依据生产代码，不由外部软件功能倒推。[S15]

`case-catalog.json` 给出了每个案例的输入、目标、operation、reader、View、科学检查、真实截图检查点和禁止越界事项；`case-catalog.md` 是便于人工阅读的版本。它还将当前 **21 operation、22 reader、13 export、10 CLI、9 GUI** 映射到至少一个设计案例。此处“覆盖”仅指设计条目都有去处，**不是 100% 运行通过**。

### 首批应该选择什么

P0 选择 T00、T01、T02、T04、T06、T07、T17、T18。这样既覆盖“安装—第一张图”，又覆盖分子、晶体、轨迹、体数据和项目交接；不需要一开始就被 Fermi 数据许可或全部专业后端绑住。T03/T05 和已具备真实环境的高级量子案例紧随其后。

不建议把首个教程写成一次启用全部后端、导入所有格式的超级演示。它不利于新用户定位失败原因，也很难在下一版本稳定维护。每个教程只有一个主成果；全部选项移到 reference 或 how-to。

### 三个最能体现 Blender 与科学数据结合价值的展示项目

建议在分步基础课之外，优先做三个完整展示项目。它们应组合已验收的子案例，不新增未公开的科学能力，也不宣传成现有“一键生成全部图”的功能。

**分子量子工作台：** 使用同一份信息完整的 water 计算，依次生成轨道正负相位、电子密度、密度面上的 ESP，以及一张切片或剖面；保持结构、方法、网格和 provenance 的对应。形成同视角的组图和可切换 View 的工程，展示 T08/T09/T10 的协作。CH₃ 自旋和 N MP2 密度另作独立案例，不混入水分子的单一计算叙事。[S14][S15]

**分子动态配图：** 使用 rMD17 阿司匹林真实源帧，结合坐标播放、逐帧力箭头、定格渲染和视频。利用 Blender 做相机、光照和版式，不额外虚构能量曲线专用 GUI 或物理采样时间。这比只有一段“原子在动”的视频更能证明实体关联和动画持久化价值。[S12][S13][S15]

**周期振动展示：** 使用 NaCl 有限位移数据，完成 q 点模式选择、周期副本相位演示和可重开的动画工程。Si 能带/DOS 属于另一套材料计算，另页展示；不要为制造一张综合图而将不相干的材料或计算伪装成同一结果。[S14][S15]

## 五、从成熟项目借鉴什么，而不是照搬什么

| 对照 | 一手文档中的有效做法 | ChemBlender 的具体改法 |
|---|---|---|
| Diátaxis | 教程围绕可达成成果、小步操作和可见反馈 | 教学课、任务指南、参数参考、原理说明分开；一步一个可观察结果 |
| Avogadro 轨道教程 | 先说明所需量子结果，再对应界面和结果图 | MO 教程先检查源文件是否真的含轨道，再教选轨道、网格和相位 |
| ChimeraX | 按真实科学任务组织案例，并把执行入口与说明关联 | 以“完成什么图/动画”做目录；公开 CLI 命令对应 GUI 截图和结果 |
| ORCA 6.1 Tutorials | 入门、性质、光谱与流程分层，并链接更详尽手册 | 第一张图保持最短成功路径，复杂计算与数据解释拆成独立章节 |

这四项只借鉴教程结构和维护方式，不构成 ChemBlender 已实现 ChimeraX 的所有结构分析能力、Avogadro 的所有轨道功能或 ORCA 6.1 完整兼容性的证据。[S22][S23][S24][S25]

## 六、怎样保证“真实操作”，而不仅是“真实截图”

### 两条执行轨道必须分开

**语义重放轨道**通过公开 CLI、Worker 和已注册 Blender Operator/RNA 运行，验证科学实体、状态、导出、冷重开及错误回滚。这条轨道可以是后台执行，适合回归和确定性参数检查。

**真实 GUI 轨道**在可见的 prepare/Blender 窗口中，通过正常鼠标、键盘、菜单和面板完成公开教程步骤，并逐步留证。没有面板的专业操作如实写成 CLI 或 prepare 专家入口，不为了“全 GUI”虚构按钮。

Blender 官方区分全窗口 `bpy.ops.screen.screenshot` 与单 editor 的 `screenshot_area`。截图能证明捕获了某个窗口状态，却不能单独证明这个状态来自正常按钮点击。用 Python 构建完整场景后截一张界面图，属于 API-assisted 场景证据，不等价于普通用户 GUI 路径通过。[S26] 历史用户案例本身也明确指出：公开 Operator 自动走查不能取代 UI 手工验收。[S12]

因此，manifest 中至少区分 `os_gui`、`human_gui`、`blender_operator`、`cli`、`worker`。一篇主张 GUI 可照做的课程，其核心 GUI 步骤不能全部由 `blender_operator` 代替。

### 每个检查点需要什么

建议每步记录：“操作前截图→真实输入事件/动作说明→当前实体和参数→操作后截图→可观测断言”。截图保留无标注原件，箭头、框选、编号放在单独副本，并链接回原图哈希。事件记录要含步骤 ID、运行 ID、时间、前后台窗口/进程身份、执行类型和前后图，关键连续交互另保存短录屏。

证据关联建议为：

```text
教程步骤 ID
  → 本次运行 ID 与环境记录
  → 已安装 Extension / prepare 制品 SHA-256
  → 输入来源、许可及 SHA-256
  → GUI 输入事件或公开命令
  → 科学实体 UUID / revision / 数组检查
  → 原始截图、标注副本、渲染和冷重开记录
```

哈希提供一致性和防误换能力，不是独立真实性证明。输入日志也可能自报错误；因此还需要第二个干净 profile 的文档盲走、独立审阅以及对图中科学内容的检查。不能把“manifest 字段都填了”升级为“教程已认证”。

### 截图与渲染的建议规格

| 证据类型 | 建议规格 | 验收目标 |
|---|---|---|
| 原始 GUI 截图 | 固定窗口分辨率与缩放；建议 1920×1080 起，优先保证面板文字可读 | 看到当前实体、参数和成功/错误状态，不能只拍漂亮视口 |
| 标注教程图 | 由原图生成裁剪/箭头副本，保留原图映射 | 读者能找到按钮；不得改写字段数值或错误信息 |
| 最终科研图 | 可沿用既有 2400×1800、Cycles 256 samples 作为一档测试配置，实际记录硬件和用时 | 结构、颜色、单位、等值面和标签科学正确；不是以样本数代替质量 |
| 动画 | 原始帧序列＋可播放视频；注明动画帧率与物理时间的关系 | 切换帧/模式正确，不仅第一帧好看 |
| 故障证据 | 错误前后状态及恢复后结果 | 报错可理解，原项目不受污染 |

上述截图规格是建议，不是已测性能承诺。2400×1800、256 samples 是现有历史分子案例记录过的配置；新机器、新案例是否合适必须实测。[S13]

## 七、科学正确性怎样验收

每个案例先固定“应当比较什么”，再执行，避免运行后根据结果临时放宽口径。输入文件哈希、元素和实体身份通常要求精确一致；浮点网格、导出再导入和重新计算则采用明确的数值容差与参考来源，不能只比较图片。

分子结构比较原子映射、坐标单位、键阶、显式氢、立体信息及可表达字段；View 展示变换与 Mesh Apply 的科学变更分别检查。周期结构比较晶格矩阵、坐标约定、占位、周期映射，不能仅看晶胞轮廓。[S04][S12]

网格比较原点、三轴、shape、单位、语义、数据集选择和切片抽样；`property_on_surface` 要求真正兼容的仿射网格。密度的积分误差需要同时考虑网格范围和分辨率，不能给所有体系机械套用一个固定阈值。RDM、开壳层自旋、ESP 的来源和层级必须写在图注和元数据里。[S14][S15]

轨迹比较真实源帧及同帧属性；rMD17 当前案例未声明物理时间间隔，动画帧率不补出缺失的科学时间。光谱保留频率/能量、强度类型、展宽参数、自旋或 gauge；Raman activity 与实验谱强度、rotatory strength 与 molar ECD 不可混称。[S13][S14]

Band/DOS 必须记录各自 Calculation 和能量参考。当前例子来自独立计算，若现有身份约束不允许 linked View，应使用独立 View 并列展示并说明来源，不能靠内部修改 UUID 绕过校验。[S14][S15]

**跨机器图像不要求逐像素完全相同。** 建议优先检查物理参数和几何/图例，再对相同渲染设置建立经过校准的图像质量阈值。科学数组的守恒检查与 Blender 渲染随机性是两个不同问题。文件保存中的时间戳、归一化格式或 UUID 变化，也不应被误当作科学数值错误。

## 八、用户内容包还应该包含什么

建议用户入口按“结果/任务”组织，而不是让用户在 `.agents`、historical qualification 和 API 文档之间找教程。每张案例卡给出缩略结果图、当前验证版本、输入来源、所需后端、产物下载及真实测得的耗时范围；尚未实测的时间保持空白。

每课应包含：一个具体成果、必要前置条件、固定输入、逐步操作与预期现象、最终图/动画、可下载 `.blend + .cbq`、真实记录的参数与性能、失败恢复、科学解释限制、来源与许可。教学正文不放大段内部 JSON；专家 JSON 放在可复制附件和参数参考页。界面语言及确切标签必须与当前实际 UI 一致，不把文档中文译名冒充按钮原文。

除此之外，成熟发布还应补齐一个“我有什么文件/我想画什么→应该走哪条路线”的决策入口、版本兼容矩阵、2.4→2.5 迁移对照、数据损失表、卸载/恢复说明、隐私友好的故障报告模板和可下载的轻量案例包。故障报告仅采集相关版本、报错和必要日志，不收集全部环境变量、宿主配置或凭据。

对大体积结果，建议源码仓库保留必要 manifest、脚本、缩略图和可审计来源；大 `.blend`、完整 `.cbq`、原始录屏和帧序列采用独立案例发布资产，发布前检查分发许可与相对路径。不要将案例视频和原始全部计算结果打包进入 Extension ZIP，也不要无条件把所有二进制放入 Git 历史。[S12][S13][S14]

## 九、本地 agent 的实施流程和停止条件

本次提供的 `local-agent-task.md` 可以直接作为本地 agent 的任务书。它要求先读当前规则、保护用户修改、确认 baseline，再进入以下交付门槛，而不是直接从文档生成一套“看起来已完成”的结果。

| 阶段 | 产物 | 进入下一阶段的条件 |
|---|---|---|
| M0 冻结范围 | 当前 HEAD/dirty state、制品来源和哈希、真实环境能力、许可清单 | 消除规则冲突；不允许环境注入掩盖依赖缺失 |
| M1 建立最小闭环 | T00+T01 的真实操作、原始图、渲染、工程及冷重开 | 普通用户路径能完成；另一路公开接口重放也通过 |
| M2 核心覆盖 | 完成 8 个 P0 案例与格式矩阵 | 必测检查无 skipped；损失/失败结果如实记录 |
| M3 扩展展示 | 按已有环境逐个推进 P1/P2 | 真实后端、许可与合法输入都通过；缺失案例明确阻塞 |
| M4 教程验收 | 双语页面、离线包、资源检查、第二 profile 文档盲走 | 关键 GUI 路径不能依赖隐藏脚本修正或内部源码知识 |
| M5 发布候选交接 | 单一最终制品关联的案例包、校验清单、未解决项 | 只报告本地候选；push/tag/Release/PyPI 另需明确授权 |

阶段是成果门槛，不是对未来执行耗时的保证。应把首次运行、重跑、渲染耗时、峰值内存和硬件写入真实运行记录，再形成面向用户的时间预算。

建议同时显示四个覆盖指标：设计映射完成率、正向运行通过率、真实 GUI 通过率、可分发交付完成率。mandatory 与 optional 分母分开；预期 unavailable 的边界通过不能提高正向计算通过率；核心案例缺图、没有冷重开或仍用旧版本截图就不能关闭。

遇到界面/参数缺陷时，应记录失败步骤，做最小相关修复和回归，然后重跑受影响步骤。不能通过直接调用内部 helper 绕过 bug，再把正常菜单路径写成成功。GUI 会话采用单一操作者和锁；并行 agent 可以分析文件、核查许可、审阅结果，但不能同时操作同一 Blender 窗口。

## 十、建议的仓库落点

保持现有维护结构，避免同时出现几套互不相认的教程站和验收系统。

```text
# 新增或按现有约定整合；这些是建议落点，不表示仓库已经存在。
docs/user/zh-CN/tutorials/2.5.0/
docs/user/en/tutorials/2.5.0/
examples/tutorials/2.5.0/
  catalog.json
  T01-aspirin/
    case.json
    README.md
    sources.json
    replay/                 # 公开 CLI / Worker / Operator 重放
    expected/               # 科学与界面断言
    evidence/               # 本次 GUI、数据及生命周期证据
    project/                # 发布包中相邻的 .blend + .cbq
.agents/active/2.5.0-tutorial-qualification.md
```

旧 `examples/user-workflows/inputs` 和 `examples/scientific-visualization/inputs` 可按许可引用或明确复制快照；不修改既有输入字节，不以旧输出满足新 GUI 通过项。复用现有公开清单、文档生成器和生命周期校验逻辑；自动生成映射与版本栏，手工/真实运行采集教学叙事与截图。兼容性变更时，使受影响 case 状态自动回到需要复验，而不是默认沿用上一版 green 状态。

## 交付物的使用边界

附带 `validate_evidence.py` 是独立的、标准库实现的证据一致性检查器草案：检查版本/哈希绑定、文件引用、必需步骤、GUI 证据类型和冷重开记录。它不连接 Blender，不会执行科学计算或 UI 点击，也不能从文件哈希证明截图真伪。它只应作为真实执行之后的一道机械门槛；现有仓库已具备的检查能力应优先复用，再选择性整合该草案。

`T01.case-spec.json` 是首课验收规格；`run-manifest.template.json` 保持 `not_run`，故发布检查必须失败。完整工程、真截图、后端日志和实测数值要由本地 agent 真实采集后填入。不得将此模板或检查器的合成单元测试当作 ChemBlender GUI 已通过。

本报告的关键建议是：**以可照做、可复核的案例闭环检验产品，而不是以文档篇数或漂亮渲染数量宣布教程成熟。**

## 来源

完整来源清单见同目录 `sources.json`。下列引用均保留具体路径和固定提交或实际查询端点；仓库资格记录始终按“记录声称”使用。

<a id="source-S01"></a>

**S01 · README：2.5 产品与组件边界**  
来源：[https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/README.md](https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/README.md)  
访问日期：2026-09-10。固定提交源码或文档；仓库记录不等于本次独立实测。

<a id="source-S02"></a>

**S02 · 公开接口生成清单**  
来源：[https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/docs/prepare/public-surface.json](https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/docs/prepare/public-surface.json)  
访问日期：2026-09-10。固定提交源码或文档；仓库记录不等于本次独立实测。

<a id="source-S03"></a>

**S03 · Blender 完整联动 SOP**  
来源：[https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/docs/user/zh-CN/blender-workflow.md](https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/docs/user/zh-CN/blender-workflow.md)  
访问日期：2026-09-10。固定提交源码或文档；仓库记录不等于本次独立实测。

<a id="source-S04"></a>

**S04 · 能力与项目生命周期**  
来源：[https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/docs/user/zh-CN/capabilities-and-projects.md](https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/docs/user/zh-CN/capabilities-and-projects.md)  
访问日期：2026-09-10。固定提交源码或文档；仓库记录不等于本次独立实测。

<a id="source-S05"></a>

**S05 · 发布状态与已知限制**  
来源：[https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/docs/user/zh-CN/release-status.md](https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/docs/user/zh-CN/release-status.md)  
访问日期：2026-09-10。固定提交源码或文档；仓库记录不等于本次独立实测。

<a id="source-S06"></a>

**S06 · 2.5.0 本地交付资格记录**  
来源：[https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/.agents/completed/2.5.0-public-delivery.md](https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/.agents/completed/2.5.0-public-delivery.md)  
访问日期：2026-09-10。固定提交源码或文档；仓库记录不等于本次独立实测。

<a id="source-S07"></a>

**S07 · 2.5 截图来源 manifest**  
来源：[https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/docs/user/assets/2.5.0/manifest.json](https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/docs/user/assets/2.5.0/manifest.json)  
访问日期：2026-09-10。固定提交源码或文档；仓库记录不等于本次独立实测。

<a id="source-S08"></a>

**S08 · 公开清单及离线 HTML 生成器**  
来源：[https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/ChemBlender/scripts/generate_public_delivery_docs.py](https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/ChemBlender/scripts/generate_public_delivery_docs.py)  
访问日期：2026-09-10。固定提交源码或文档；仓库记录不等于本次独立实测。

<a id="source-S09"></a>

**S09 · 根 AGENTS 规则**  
来源：[https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/AGENTS.md](https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/AGENTS.md)  
访问日期：2026-09-10。固定提交源码或文档；仓库记录不等于本次独立实测。

<a id="source-S10"></a>

**S10 · 实时能力探测与路由实现**  
来源：[https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/chemblender_prepare/runtime.py](https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/chemblender_prepare/runtime.py)  
访问日期：2026-09-10。重点核查前 260 行，含 provider 固定 unavailable 与路由判定；非全文件执行审计。

<a id="source-S11"></a>

**S11 · Reader API 与外部 Python 集成**  
来源：[https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/docs/reader-api-v1/README.md](https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/docs/reader-api-v1/README.md)  
访问日期：2026-09-10。固定提交源码或文档；仓库记录不等于本次独立实测。

<a id="source-S12"></a>

**S12 · 历史用户案例语料清单**  
来源：[https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/examples/user-workflows/README.md](https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/examples/user-workflows/README.md)  
访问日期：2026-09-10。固定提交源码或文档；仓库记录不等于本次独立实测。

<a id="source-S13"></a>

**S13 · 科学可视化案例及历史验证索引**  
来源：[https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/examples/scientific-visualization/README.md](https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/examples/scientific-visualization/README.md)  
访问日期：2026-09-10。固定提交源码或文档；仓库记录不等于本次独立实测。

<a id="source-S14"></a>

**S14 · 真实科学输入及许可边界**  
来源：[https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/examples/scientific-visualization/inputs/README.md](https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/examples/scientific-visualization/inputs/README.md)  
访问日期：2026-09-10。固定提交源码或文档；仓库记录不等于本次独立实测。

<a id="source-S15"></a>

**S15 · 科学 View 的实体匹配与绑定实现**  
来源：[https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/ChemBlender/ui/scientific_view.py](https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/ChemBlender/ui/scientific_view.py)  
访问日期：2026-09-10。重点核查前 240 行的生产实现，非本次 Blender 执行结果。

<a id="source-S16"></a>

**S16 · 可选后端配置**  
来源：[https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/docs/prepare/zh-CN/advanced-routes.md](https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/docs/prepare/zh-CN/advanced-routes.md)  
访问日期：2026-09-10。固定提交源码或文档；仓库记录不等于本次独立实测。

<a id="source-S17"></a>

**S17 · prepare CLI 与 GUI**  
来源：[https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/docs/prepare/zh-CN/cli-and-gui.md](https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/docs/prepare/zh-CN/cli-and-gui.md)  
访问日期：2026-09-10。固定提交源码或文档；仓库记录不等于本次独立实测。

<a id="source-S18"></a>

**S18 · Worker Protocol 与 Reader API**  
来源：[https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/docs/prepare/zh-CN/protocol-and-reader-api.md](https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/docs/prepare/zh-CN/protocol-and-reader-api.md)  
访问日期：2026-09-10。固定提交源码或文档；仓库记录不等于本次独立实测。

<a id="source-S19"></a>

**S19 · GitHub 最新公开 Release 查询**  
来源：[https://api.github.com/repos/psiQAQ/ChemBlender_2_x/releases?per_page=1](https://api.github.com/repos/psiQAQ/ChemBlender_2_x/releases?per_page=1)  
访问日期：2026-09-10。本次返回 v2.4.0，发布时间 2026-08-03T02:02:01Z；运行时查询结果会随发布变化。

<a id="source-S20"></a>

**S20 · 精确 HEAD 的 Actions 查询**  
来源：[https://api.github.com/repos/psiQAQ/ChemBlender_2_x/actions/runs?head_sha=478bbd498277a0ce9a32fc9b262f36ec8410d2d9&per_page=5](https://api.github.com/repos/psiQAQ/ChemBlender_2_x/actions/runs?head_sha=478bbd498277a0ce9a32fc9b262f36ec8410d2d9&per_page=5)  
访问日期：2026-09-10。本次 total_count=0；不据此否定其他提交的 CI。

<a id="source-S21"></a>

**S21 · release/2.5.0 最新提交查询**  
来源：[https://api.github.com/repos/psiQAQ/ChemBlender_2_x/commits?sha=release%2F2.5.0&per_page=3](https://api.github.com/repos/psiQAQ/ChemBlender_2_x/commits?sha=release%2F2.5.0&per_page=3)  
访问日期：2026-09-10。本次 HEAD 为 478bbd498277a0ce9a32fc9b262f36ec8410d2d9。

<a id="source-S22"></a>

**S22 · Diátaxis — Tutorials**  
来源：[https://www.diataxis.fr/tutorials/](https://www.diataxis.fr/tutorials/)  
访问日期：2026-09-10。教程的教学目标、具体步骤、早期可见结果与实际观察。

<a id="source-S23"></a>

**S23 · Avogadro — Viewing Molecular Orbitals**  
来源：[https://avogadro.cc/docs/tutorials/viewing-molecular-orbitals.html](https://avogadro.cc/docs/tutorials/viewing-molecular-orbitals.html)  
访问日期：2026-09-10。参考其输入前提—界面步骤—结果图结构；不据此推定 ChemBlender 支持相同功能。

<a id="source-S24"></a>

**S24 · UCSF ChimeraX Tutorials**  
来源：[https://www.cgl.ucsf.edu/chimerax/tutorials.html](https://www.cgl.ucsf.edu/chimerax/tutorials.html)  
访问日期：2026-09-10。参考按任务组织、可执行命令与案例画廊；仅借鉴文档设计。

<a id="source-S25"></a>

**S25 · ORCA 6.1 Tutorials**  
来源：[https://www.faccts.de/docs/orca/6.1/tutorials/](https://www.faccts.de/docs/orca/6.1/tutorials/)  
访问日期：2026-09-10。参考入门/性质/光谱/流程分层；不是 ChemBlender 对 ORCA 6.1 的兼容承诺。

<a id="source-S26"></a>

**S26 · Blender Screen Operators**  
来源：[https://docs.blender.org/api/main/bpy.ops.screen.html](https://docs.blender.org/api/main/bpy.ops.screen.html)  
访问日期：2026-09-10。官方区分全窗口 screenshot 与 editor screenshot_area；main 文档不是 5.1 兼容验收。

<a id="source-S27"></a>

**S27 · 历史 Reader 扩展示例**  
来源：[https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/examples/reader-extension/README.md](https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/examples/reader-extension/README.md)  
访问日期：2026-09-10。固定提交源码或文档；仓库记录不等于本次独立实测。

<a id="source-S28"></a>

**S28 · 生产注册入口**  
来源：[https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/ChemBlender/runtime/registration.py](https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/ChemBlender/runtime/registration.py)  
访问日期：2026-09-10。固定提交源码或文档；仓库记录不等于本次独立实测。

<a id="source-S29"></a>

**S29 · 外部 operation 事务执行实现**  
来源：[https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/ChemBlender/ui/processor_operations.py](https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/ChemBlender/ui/processor_operations.py)  
访问日期：2026-09-10。重点核查前 230 行，含固定操作族、源文件哈希和伴随文件规则。

<a id="source-S30"></a>

**S30 · 2.5 对外交付任务及阶段记录**  
来源：[https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/.planning/2026-09-10-2.5.0-public-delivery/task_plan.md](https://github.com/psiQAQ/ChemBlender_2_x/blob/478bbd498277a0ce9a32fc9b262f36ec8410d2d9/.planning/2026-09-10-2.5.0-public-delivery/task_plan.md)  
访问日期：2026-09-10。固定提交源码或文档；仓库记录不等于本次独立实测。

