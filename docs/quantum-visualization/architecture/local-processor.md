# ChemBlender CBQ Viewer 与本地处理模块实施方案

状态：2026-09-09 共享核心、CBQ 1.1、外部分发包、统一 CLI、Blender 单路径异步控制器、既有 scientific reader／Fermi／wavefunction、RDKit 分子 operation 以及 QTAIM／NCI／phonon 专业分析均已接入。专业分析已通过真实后端、CLI、源码态 Blender View、保存重开和移走源文件验证；正式 ZIP、全量回归及随后性能／取消移除门槛仍须完成，不能由接口存在代替验收。

## 目录

- [目标与保留边界](#目标与保留边界)
- [交互与计算边界](#交互与计算边界)
- [单一本地程序配置](#单一本地程序配置)
- [CLI、能力文档与环境路由](#cli能力文档与环境路由)
- [共享模型与 Worker 协议](#共享模型与-worker-协议)
- [一次计算与结果缓存](#一次计算与结果缓存)
- [CBQ 兼容与生命周期](#cbq-兼容与生命周期)
- [实施顺序与提交门槛](#实施顺序与提交门槛)
- [验收矩阵与移除 wheel 条件](#验收矩阵与移除-wheel-条件)
- [交付、SOP 与错误恢复](#交付sop-与错误恢复)

## 目标与保留边界

Blender 负责分子编辑和高频可视化交互；`chemblender-prepare` 负责原始格式解析、RDKit、波函数、Fermi、QTAIM、Phonopy 等第三方依赖或重计算。科学交换边界仍为 CBQ，解析算法不搬回 Blender。

保留两种启动位置、同一条计算链：用户可在独立 CLI／轻量 Tkinter GUI 中准备 CBQ，也可在 Blender 面板发起外部异步任务。两者使用相同 operation、共享模型和结果校验。Blender 不再要求用户分别配置 Python、仓库、Fermi 环境或 critic2 路径。

RDKit 的按钮式科学操作需迁移而非删除：SMILES 建模、芳香键／Kekulé、加氢、MMFF／UFF、势能及分子格式导出。相机、材质、轨迹和滑块更新保持本地。实施前以现有调用点及实际操作建立基线。

不截取或复制 RDKit 源码，不维护 RDKit 私有子集。正式扩展暂时保留已锁定的 RDKit wheel；只有外部调用通过功能、性能、取消、数据一致性和生命周期验收后才删除。候选无 wheel 包可以用于隔离验证，其通过不能代替功能等价验收。任一门槛失败均继续保留 wheel、修复或延期，不发布功能降级版本。

## 交互与计算边界

| 功能区域 | Blender 内即时交互 | Blender 内显式 Apply | 外部异步处理 |
| --- | --- | --- | --- |
| 分子结构 | 原子／键编辑、选择、测距测角、半径、材质、球棍比例 | 将编辑后的 Mesh 属性冻结为 CBQ Structure／Topology | SMILES 3D、AddHs、Kekulé、MMFF／UFF、势能、MOL／SDF／SMILES 导出 |
| 标量场／体数据 | 色值范围、colormap、透明度、正负颜色、体密度比例 | 等值面重建、全分辨率切片／剖面、同 affine 密度差 | MO、电子密度、ESP、NCI 科学场 |
| 轨迹／振动／声子 | 帧、速度、相位、振幅、模式、已有 q-point、超胞重复、矢量尺度 | 保存显示设置和完整动画缓存 | Phonopy 解析、力常数相关计算、群速度、新增 q-point 数据 |
| 光谱／能带／DOS | 能量零点、范围、线宽、峰、PDOS、spin 镜像 | IR／Raman／UV-Vis／ECD 展宽及派生数据入库 | cclib、pymatgen 原始输出解析 |
| Fermi 面 | 颜色／矢量属性、stride、箭头比例、已有 band 选择 | 已有网格的 Blender 几何更新 | VASP 数据抽取及 Fermi mesh 生成 |
| QTAIM | 临界点／路径显隐、半径、颜色属性及范围 | 已有拓扑数据的 View 更新 | critic2 执行、临界点与实际梯度路径生成 |

轻量参数采用节流实时预览；切片可使用受限预览采样，Apply 才生成完整结果。等值面、派生数据、外部科学计算不由参数拖动自动触发。线宽预览与显式入库分开：预览不改写权威数组。

同 affine 密度差还必须满足 shape、dataset、单位、结构绑定一致；保留原数据并以新实体记录来源。Mesh 编辑在 Apply 前只是显示层草稿；冻结时检查 atom mapping、元素、键端点、键级、科学坐标、单位及结构 revision，不能把对象平移／缩放无声解释为科学坐标变化。

## 单一本地程序配置

全局 Add-on Preferences 仅增加 `processor_executable`：本地 `chemblender-prepare.exe` 的绝对路径。`Test Processor` 异步执行 capability 检查，显示工具版本、RDKit 版本、可用 operation 及缺失原因。该路径和能力缓存不写入 `.blend`、CBQ、View 或场景 preset。

使用时在 `Edit > Preferences > Add-ons > ChemBlender` 选择该可执行文件并点击 `Test Processor`。检查立即进入 modal；`Esc` 请求取消。处理程序缺失或能力不足只影响相应外部操作，不影响 CBQ 浏览、Mesh 编辑、已有 View 或本地相位／帧预览。

Project Browser 的 `Local Processor · Scientific Input` 提供 IOData wavefunction、cclib output、VASP band/DOS、Phonopy 和 Fermi 输入；Orbital Results 提供 MO、电子密度、density-matrix density、matrix ESP 与 orbital-derived ESP。按钮先进入公共 modal，首个 timer 才冻结输入并启动处理器；成功结果追加新 UUID 并自动选择，自动 View 不适用或创建失败时仍保留已验证结果。reader 与 Fermi 的持久 provenance 指向原始文件及 hash，不引用随后删除的任务目录。

分子 Structure View 的 Mesh Edit 面板提供 Generate 3D、Kekulize、Optimize、Energy 和 MOL／SDF／SMILES Export。Mesh 草稿必须先 Apply；纯坐标或键编辑保留逐原子身份，增删原子或修改元素时清除身份并阻止把旧映射用于外部重算。优化和结构派生追加新 Structure／Topology 并自动选择，势能追加 `kilocalorie_per_mole` 标量 `PropertyDataset`，导出仅原子复制经 hash 验证的任务 artifact，不修改项目实体。

程序未配置、文件不存在或缺少 capability 时，CBQ 浏览、本地编辑、展示、动画、渲染、保存、重开保持可用；仅禁用对应计算按钮并解释缺失能力。正式过渡版本中的内置 RDKit 路径保持原有功能，直至外部等价门槛通过后切换。

Blender 不执行 pip／uv，不修改 Blender Python，不复制环境路径到项目。首版仅本地可执行文件与文件协议，无 HTTP、常驻服务、认证或远程上传。

## CLI、能力文档与环境路由

统一增加以下入口，并保留已规划的 `formats`、`inspect`、`convert`、`derive`、`validate`、`upgrade`、`export`：

```text
chemblender-prepare capabilities --json
chemblender-prepare worker REQUEST RESULT --cancel-file CANCEL
chemblender-prepare doctor
```

`capabilities` 使用单独版本化的 JSON 文档，至少包含文档版本、处理程序版本、Worker 协议版本、operation／version 列表、能力可用性、实际后端版本及缺失原因。未安装／无法启动的后端不得报告可用；不以静态注册表代替实际检查。能力检查不安装依赖或启动科学任务。

`doctor` 只诊断可执行文件、依赖、环境路由、任务目录权限和 critic2 可运行性，提供面向用户的修复说明，不自动安装。工具自身管理已批准的科学环境、Fermi 环境及 critic2 路径，保留 GBasis 与 NumPy 版本隔离；Blender 不再存储 `worker_python`、`worker_repository`、`fermi_python`。

路由配置使用版本化的 `chemblender-prepare.json`，放在CLI可执行文件旁，或由外部工具环境变量`CHEMBLENDER_PREPARE_CONFIG`指向。文件只接受三个绝对Python路径`wavefunction`、`scientific`、`fermi`和一个可选critic2绝对路径；不写入`.blend`或CBQ。统一`worker`读取请求后按固定operation/reader白名单选择环境，再直接调用同一runner；请求不能指定Python、模块或callable。未配置的专用路由明确报告不可用并拒绝对应任务，不能回退处理程序自身环境；实际缺失依赖也必须在capability和doctor中报告为不可用。

独立包继续采用当前仓库的 `pyproject.toml`、`uv.lock`、`.venv`，构建 wheel／sdist并进行安装测试，为后续 PyPI 发布准备；本次不发布。轻量 Tkinter GUI 通过 CLI 子进程工作，不包含第二份算法。

## 共享模型与 Worker 协议

双方共用的协议和 CBQ 模型放入唯一源码 `cbq_core`，仅依赖标准库与 NumPy。外部包直接使用；Blender 构建时 vendoring 同份源码并核对逐文件 hash。保留 Worker Protocol v1、任务目录、`request.json`、`result.json`、`progress.json` 和 cancel marker；现有字段承载新的 operation，不另建通信框架或升级协议版本。

保留现有 operation，补齐并分别验证：

| Operation | 版本 | 结果或用途 |
| --- | --- | --- |
| `reader.parse` | `0.1` | 原始计算／结构文件到已有科学实体 |
| `wavefunction.*` | `1` | 既有 MO、密度、自旋密度、ESP 网格 |
| `periodic.fermi_surface` | `1` | 中立 Fermi mesh 及属性 |
| `molecule.smiles_to_3d` | `1` | 带 atom mapping 的结构与拓扑 |
| `molecule.kekulize` | `1` | Kekulé 键级及来源 |
| `molecule.optimize` | `1` | MMFF／UFF 优化结构及结果 |
| `molecule.energy` | `1` | 带单位的标量势能 |
| `molecule.export` | `1` | 验证过的 MOL／SDF／SMILES 导出文件 |
| `topology.qtaim` | `1` | 临界点与实际梯度路径 |
| `periodic.phonon` | `1` | 声子及所请求 q-point 数据 |
| `grid.nci_fields` | `1` | NCI 所需关联科学场 |

不新增科学结果模型。复用 `Structure`、`TopologyRecord`、`PropertyDataset`、`CalculationRecord`、`ProvenanceRecord` 和已有网格／声子／拓扑实体。分子势能必须进入带单位的标量 `PropertyDataset`，不能只显示在临时 UI 字符串中。未实现操作不放入“可用”能力清单。

三项专业操作均冻结实际来源文件及SHA-256。QTAIM发布5类可验证临界点语义和真实梯度路径的`TopologyGraph`；NCI发布同一Structure绑定、相同affine的RDG与`sign(lambda2)rho`网格对；phonon发布Structure和请求q-point的复数`PhononModeSet`，可选BORN/NAC及group velocity。Windows上的配置若指向WSL critic2 ELF，处理程序使用固定`wsl.exe --exec`参数运行且不经过shell。历史专业provenance不会被后续operation重写。

## 一次计算与结果缓存

1. Blender 主线程验证对象及参数，把所需 Structure、Topology、数组和用户编辑后的 Mesh 属性冻结到私有临时 CBQ。冻结本身须计入启动体验，不能在进入 modal 前阻塞大对象。
2. 请求包含输入 UUID／revision、operation／version、规范化参数及 hash。
3. 用无 shell 的 `subprocess` 启动统一程序。modal operator 轮询进度，旧 View 保持可见。
4. 外部程序验证输入与 capability，执行计算，在私有任务目录原子发布完整结果。
5. Blender 验证 request ID、协议版本、输出清单、路径边界、hash、provenance 和输入 revision。外部任务期间用户继续编辑导致 revision 变化时拒绝过期提交。
6. 成功结果以新 UUID 追加到当前 CBQ，自动选中新结果并重建相应 View；旧结构、旧 View 和原始科学数组保留。新 View 创建失败保留原显示并记录诊断。
7. 失败、取消、超时或输出不可信均不改动当前项目。取消先写 marker；超过两秒未响应才终止本任务进程，按实际进程标识和启动路径核验，不按名称终止其他程序。路由出的子进程也必须纳入任务生命周期，防止后台重计算遗留。

缓存键包括输入 UUID／revision、operation／version、规范化参数、处理程序版本和实际后端版本。命中前仍校验完整性、来源和输入一致性；命中时不启动 RDKit 或其他重计算。缓存失效和失败不能发布“有效”的半成品。成本控制复用现有任务和缓存机制，不引入常驻服务。

## CBQ 兼容与生命周期

继续使用 CBQ 1.1 的 `manifest.json + arrays/*.npy`；保留单位、完整 affine、结构绑定、能量参考、来源 hash、软件版本和处理参数。周期对称性由外部生成数值旋转／平移，Viewer 用 NumPy 展开和旋转 ADP。

普通历史包在完整性校验后读取；缺数值对称操作的旧晶体包保持可读取部分，提示外部 `upgrade` 到新目录，保留原包。升级前验证历史 hash，科学内容变化才更新 revision 和来源；旧 View 显式重链接／重建。历史 `.blend` 使用归档旧版本或专用 Blender 迁移脚本，不承诺普通 Python 解析任意 `.blend`。

CBQ 整包预览、事务加入当前项目：同 UUID／同内容复用，同 UUID／不同内容拒绝；可疑重复来源由用户明确决定。导入数组固化到项目自有存储。包内来源路径仅用于记录，不执行包内脚本，不自动读取来源文件或访问网络。

## 实施顺序与提交门槛

| 顺序 | 工作 | 退出条件 |
| --- | --- | --- |
| 0 | 完成当前 `feat/cbq-only-viewer` 的核心／准备工具迁移及测试迁移 | 独立 Python、共享模型、CBQ 1.1、当前 CLI 和基础 Viewer 验证通过；架构指南同步；形成可审查的干净逻辑提交。当前大规模未提交移动期间不插入新异步框架 |
| 1 | 稳定共享 CBQ／Worker v1，统一 CLI，补 capabilities／doctor | 单一可执行入口可复现实有请求，能力及实际版本准确，未知／缺失能力诊断明确 |
| 2 | Blender 单一路径设置、公共异步任务控制器、节流预览 | 配置不进入项目；缺处理程序时本地编辑／展示可用；状态、取消、失败不冻结 UI |
| 3 | 迁移 wavefunction、Fermi、scientific reader 调用 | 原 Worker 由统一入口驱动，数值和来源一致，无新增场景环境路径 |
| 4 | 迁移 RDKit 操作，保留纯 Mesh 编辑、静态元素数据及显示 | 编辑冻结、atom mapping、键级、势能入库、导出往返、旧结果回退通过 |
| 5 | 接入 QTAIM、phonon、NCI | 真实输入／外部输出／解析／场景／来源五层验证；已有数据展示保持本地 |
| 6 | RDKit 功能等价和交互性能专项 | 下表所有移除前门槛通过；任何失败继续保留 wheel，不发布降级版本 |
| 7 | 移除正式扩展中的科学 wheel、RDKit import 及相关安装入口 | 私有 profile 证明无可选科学依赖；完整打包、重开、渲染回归通过 |
| 8 | 更新架构／依赖决策／SOP／恢复说明，完成发行物验证 | 逐量真实图像、窗口截图、可跟随操作、可安装的 Viewer 与外部 Python 包；本次不发布 Release／PyPI |

当前未提交原型对旧模块和 wheels 的删除必须逐项对照本方案：拆分算法可以继续；纯 Mesh 编辑和 RDKit 功能不得因瘦身丢失。无 wheel 候选验证单独标记，正式构建保留已有依赖直到门槛关闭。保留 wheel 本身也不等于保留按钮，须验证旧功能入口或完整外部替代。

## 验收矩阵与移除 wheel 条件

| 范围 | 必须留下的证据 |
| --- | --- |
| RDKit 功能等价 | 苯芳香／Kekulé、手性、带电、多片段 SMILES、AddHs、ETKDG、MMFF／UFF、势能、MOL／SDF／SMILES 往返；与迁移前实际结果按既有容差比较 |
| 编辑闭环 | Blender 修改坐标／键级→冻结→外部优化→新结果；atom mapping、键级、单位、provenance 正确，旧版本可回退 |
| 实时交互 | 颜色、透明度、矢量尺度、帧和相位更新不启动外部进程；节流预览及 Apply 区分可测，拖动无 UI 阻塞 |
| 性能 | 按钮在 100 ms 内进入 modal；1 秒内显示运行状态；取消在两秒内确认；标准百原子以内分子冷启动额外开销不超过两秒。记录硬件、输入、版本、计时起止和重复结果，不以热缓存或纯 CLI 耗时替代 UI 体验 |
| 故障与信任边界 | 缺程序／能力、崩溃、过期 revision、路径穿越、symlink、hash 错误、恶意结果、取消、超时均不改变当前项目；不能读取任务目录以外结果或执行结果内脚本 |
| CBQ 生命周期 | 处理程序及外部环境不存在、原始文件与输入 CBQ 移走后，保存、Save As、移动目录、独立冷启动重开、缓存删除后重建、Cycles 渲染仍可用 |
| 科学可视化 | grid、轨迹、振动、声子、光谱、band／DOS、Fermi、QTAIM 的即时参数、Apply、缓存、重开逐项测试，并记录模型／适配器／真实文件／UI渲染／保存重开五层状态 |
| 正式无 wheel 扩展 | Blender 5.1.1／Python 3.13.9 私有 profile 安装；register／unregister／reload、native validate／build、ZIP 审计、完整 smoke；ZIP 不含 RDKit、Gemmi 或其他科学 wheel，`find_spec("rdkit") is None` |

性能门槛中“取消确认”指 UI 进入已取消状态且取消后不会提交结果；若后端两秒内不能配合停止，达到两秒后才执行本任务的终止流程并记录终止延迟，不能把立即强杀当作正常取消通过。上述冲突必须由实测修复，不能放宽移除条件。

L6 删除前专项已 **Passed**：历史 `78c2d8d` 调用面与外部 RDKit operation 对照覆盖芳香／Kekulé、手性、带电、多片段拒绝、AddHs、ETKDG、MMFF／UFF、势能及 MOL／SDF／SMILES；Blender 编辑冻结、过期 revision、路径穿越、symlink、hash 篡改、取消和生命周期门槛均通过。阿司匹林冷进程额外开销 0.01761 秒；真实 Blender NCI 128³ 任务进入 modal 0.0000078 秒、显示 running 0.01089 秒、取消确认 0.33582 秒，均低于门槛。正式无 wheel 扩展仍须在 L7 独立验收，不能由 L6 结果替代。

L7 正式无 wheel 扩展已 **Passed**：manifest、依赖清单、staging 与 CI 已一致移除 RDKit、Gemmi 和其他科学 wheel，正式候选 ZIP 为 2,830,321 bytes、109 members、SHA-256 `4dabb6dc463a740846eca72b239e875689bfdd07e390b06e34d82f63cfcbabb5`。Blender 5.1.1 私有 profile 完成安装、冷启动、重复 reload、CBQ 导入导出、纯 Mesh 编辑／Apply、结构／表面／体积 View、保存重开、源移走和三个 `.blend` 资产检查；独立冷启动中 `find_spec("rdkit")` 与 `find_spec("gemmi")` 均为 `None`，Bundled NumPy 可用。全量回归 2525 项通过（37 skips）。最终精确发行物预算与截图 SOP 留给 L8。

## 交付、SOP 与错误恢复

SOP 提供带正文标题链接的目录及真实窗口截图，覆盖：独立工具准备／验证 CBQ→Blender 导入→面板展示→Cycles 合适背景和材质出图→保存重开；另含一次性处理程序配置、面板计算、编辑后 Apply／Recompute、取消与错误恢复、旧包升级。

每种物理量分别记录适合的网格／体积云／等值面／曲线／箭头等手段、Research／Teaching 材质参数、输入来源、软件和方法、显示参数、数值检查、图像及重开证据。命令和 screenshots 必须来自实际完成的路径，未完成界面不以示意图替代。

缺依赖时提示在外部安装／配置；失败或取消后旧项目继续可用；过期结果要求用户重新计算；损坏 CBQ 保留原包并报告检查失败；旧晶体缺数值操作提示外部升级。继续同步架构导览、依赖政策、规划三文件和现有[科学可视化 SOP](../scientific-visualization/README.md)。

## MOL/SDF 导入前检查

在外部 GUI 选择 `inspect`、选择 MOL/SDF 文件并运行，或在项目环境执行：

```powershell
.venv/Scripts/python.exe -m chemblender_prepare inspect tests/fixtures/sdf/records.sdf --json
```

`metadata.molecular` 显示记录数、V2000/V3000 版本、原始属性数量、类型化属性列、诊断和构象候选依据。`requires_review` 表示存在须人工复核的原子映射；候选不代表已经生成 ConformerSet。检查默认保持 `keep_independent`，不会修改源文件或发布 CBQ。原始文件检查中的候选仅供了解内容；需要接受分组时，先 convert 为 CBQ，再 inspect 该 CBQ，以固定实体和 revision。

记录、候选、单组依据及单记录 atom mapping 的显示上限均为 100，并通过对应的 `*_truncated` 字段注明截断；截断摘要不能用于批准分组。该上限约束结果显示量，不代表解析或构象分析的计算预算。分析在 GUI 启动的 CLI 子进程中进行，沿用取消文件；输入哈希发生变化时拒绝检查结果。

构象分组使用现有 `derive` 入口，operation 为 `molecule.group_conformers`。在 GUI 输入准备好的 CBQ，在“派生输入 UUID”中填写候选 evidence 的全部 record_id；“派生参数 JSON”填写 `suggestion_id`、`snapshot` 和布尔 `review_confirmed`，输出填写新的 CBQ 目录。前两项取自 **CBQ inspect** 返回的候选，存在歧义时必须复核原子映射后才设 `review_confirmed: true`。普通 `convert` 不自动创建构象集。

该 operation 复用 Worker Protocol v1 和已有构象算法，结果追加 ConformerSet、对应属性列和 provenance；输入包及原结构/记录保留。缺失输入记录、过期快照、未知参数、非布尔复核值或超出显示上限的映射均拒绝。原始文件无需继续存在。GUI 检查 CBQ 完成后，点击“复核构象候选”，选择候选并阅读完整映射依据；有歧义时勾选复核确认，再点击“填入派生任务”。窗口会填入来源、记录 UUID 和快照参数，清空旧输出位置；选择新输出后点击执行。切换候选会清除复核确认，填入参数不会自动启动计算。被截断的映射不能接受。通用 derive 参数入口仍可使用。


SDF 记录恢复：inspect 会保留并显示损坏记录诊断；convert 仅在错误明确属于未导入的独立记录、且仍有有效记录时允许继续。有效记录保持原 source_record_index，不重新编号。全部记录失败、错误关联到已保留记录或其他完整性错误时，不发布 CBQ；修正源文件后重新转换。


历史 SMILES 片段：在 GUI 选择 convert → 输入类型 smiles，使用“历史 SMILES 片段”下拉框填入既有目录文本，也可直接编辑。选择本身不启动计算；选择新输出并执行后复用 inline SMILES 转换生成 CBQ。该目录包含未完整指定立体化学的糖类和封端片段，须按用途核对文本，不代表唯一立体异构体或完整聚合物。当前转换提供二维坐标；三维生成和优化仍按后续外部操作验收。


## PubChem 外部准备

在外部 GUI 选择 convert → 输入类型 pubchem，填写 CID 或名称及新的 CBQ 输出目录，再点击执行。也可执行：

```powershell
.venv/Scripts/python.exe -m chemblender_prepare convert --pubchem 962 --output water.cbq --json
```

此操作执行时联网下载 SDF，经现有暂存、解析和来源哈希验证后发布 CBQ；来源 URL 与下载内容哈希保存在 provenance 中。文件、SMILES 和 PubChem 三种输入互斥。网络失败、取消或暂存内容被修改时不发布结果，下载暂存随任务清理。

实际 CID 962 下载及 CBQ 完整性重开已验证：一个 O/H/H 结构、两条显式键、angstrom 坐标，并保留 mol.coordinates_2d 诊断。该接口取得的平面坐标不代表三维优化结构；未据此关闭三维生成、GUI 在线点击或两秒取消验收。


普通文件 convert 不接受 --entity；该参数目前仅用于 critic2 绑定已有 Structure，其他 reader 的数据绑定来自解析结果。传入不受支持的绑定参数会报错且不发布结果，不能把 --project 追加数据理解为自动绑定其中某个结构。


共享协议源码现位于 cbq_core/worker_protocol.py；外部 worker/protocol.py 仅重导出同一实现。扩展 staging 将协议与其余共享核心一并复制并记录 SHA-256，协议版本仍为 v1。此模块不依赖科学后端或 Blender。
