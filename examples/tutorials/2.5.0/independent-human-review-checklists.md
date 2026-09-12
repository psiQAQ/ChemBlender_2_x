# ChemBlender 2.5 独立人工复做清单

本文件只供独立复做者填写。Agent 不得勾选、填写签名或把已有 Agent/MCP 证据改写为人工结果。每个案例使用新的干净 Blender profile；按双语教程盲走，记录操作、结果、缺陷、修复和复测。章节或依赖缺失时保持未勾选并写明 Blocked。

每个案例的证据目录至少包含：`reviewer-record.md`、原生 GUI 截图、命令与退出码、科学检查、最终渲染或 N/A 理由、移动/冷重开/恢复记录，以及被测 Extension/Prepare 哈希。

## T00 — 安装、诊断与处理器故障恢复

- [ ] 在第二干净 profile 核对当前候选安装、启用键和处理器路径。
- [ ] 依次复做 Test Processor、doctor、capabilities、取消和错误路径恢复。
- [ ] 保存原生 GUI 截图、命令、退出码及候选哈希。
- [ ] 按中英离线教程盲走并记录每一步预期/实际结果。
- [ ] 记录缺陷、修复与独立复测；未修复项标 Blocked。
- [ ] Reviewer／日期／签名：________________

## T01 — MOL 阿司匹林首课

- [ ] 从 `T01.case-spec.json` 固定输入、许可和哈希开始。
- [ ] 直接 GUI 复做 Prepare 转换、Preview/Import/View、显式键显示与 Cycles 渲染。
- [ ] 核对 21 原子、21 输入键、坐标容差及最终 PNG。
- [ ] 保存、整体移动 `.blend`+`.cbq`、冷重开并在 processor 不可用时重建。
- [ ] 按中英离线教程盲走，记录缺陷、修复与复测。
- [ ] Reviewer／日期／签名：________________

## T02 — SMILES、构象、能量与 Apply

- [ ] 从 `T02.case-spec.json` 固定输入、许可和哈希开始。
- [ ] 直接 GUI 复做 SMILES→3D、MMFF94、构象分组、View 与显式 Apply。
- [ ] 独立核对构象数、能量、原子映射和编辑前后科学身份。
- [ ] 保存渲染、移动工程、冷重开、缓存重建和失败恢复。
- [ ] 按中英离线教程盲走，记录缺陷、修复与复测。
- [ ] Reviewer／日期／签名：________________

## T03 — SDF 构象记录

- [ ] 从 `T03.case-spec.json` 固定输入、许可和哈希开始。
- [ ] 直接 GUI 复做 SMILES 三维化、力场优化、SDF 记录和构象分组。
- [ ] 独立核对构象身份、能量单位、映射和分组结果。
- [ ] 完成 View、渲染、工程移动、冷重开、重建与恢复。
- [ ] 双语章节缺失时标 Blocked；记录缺陷、修复与复测。
- [ ] Reviewer／日期／签名：________________

## T04 — CIF/POSCAR/ASE 晶胞

- [ ] 从 `T04.case-spec.json` 固定两份输入、许可和哈希开始。
- [ ] 直接 GUI 复做 CIF、POSCAR、ASE 路线并保存可读侧栏截图。
- [ ] 独立核对位点、占位、晶胞、超胞和来源边界。
- [ ] 完成两套渲染、工程移动、冷重开、重建与恢复。
- [ ] 按中英离线教程盲走，记录缺陷、修复与复测。
- [ ] Reviewer／日期／签名：________________

## T05 — PDB/PQR/MOL2 层级

- [ ] 从 `T05.case-spec.json` 固定输入、许可和哈希开始。
- [ ] 直接 GUI 复做 PDB 多模型、PQR 电荷/半径及 MOL2 层级。
- [ ] 独立核对 model、residue、segment、charge、radius 和 bond type。
- [ ] 完成 View、渲染、工程移动、冷重开、重建与恢复。
- [ ] 双语章节缺失时标 Blocked；记录缺陷、修复与复测。
- [ ] Reviewer／日期／签名：________________

## T06 — 轨迹与同帧力

- [ ] 从 `T06.case-spec.json` 固定输入、许可和哈希开始。
- [ ] 直接 GUI 复做 Prepare、两个 View、帧 0/15/31 标量、播放与暂停。
- [ ] 独立核对 energy/source index、同帧力、单位及 32 帧顺序。
- [ ] 完成静态/动画渲染、配对工程、移动、冷重开、重建与恢复。
- [ ] 按中英离线教程盲走，记录缺陷、修复与复测。
- [ ] Reviewer／日期／签名：________________

## T07 — 密度网格、切片与表面

- [ ] 从 `T07.case-spec.json` 与 VASP 变体规格固定输入、许可和哈希开始。
- [ ] 直接 GUI 复做 density/difference/sampling/VASP View 与缺源/缺处理器恢复。
- [ ] 独立核对 affine grid、积分、差分、等值面符号和 VASP 适用范围。
- [ ] 完成所有 volume/surface render、移动、冷重开和 VDB 重建。
- [ ] 按中英离线教程盲走，记录缺陷、修复与复测。
- [ ] Reviewer／日期／签名：________________

## T08 — FCHK/Molden 轨道

- [ ] 从 `T08.case-spec.json` 固定真实输入、许可和哈希开始。
- [ ] 在批准的 wavefunction 环境直接 GUI 生成正负相位轨道。
- [ ] 独立核对轨道索引、占据、相位、单位和网格。
- [ ] 完成 View、渲染、工程移动、冷重开、重建与恢复。
- [ ] 环境或双语章节缺失时标 Blocked；记录修复与复测。
- [ ] Reviewer／日期／签名：________________

## T09 — 电子/自旋/RDM 密度

- [ ] 从 `T09.case-spec.json` 固定真实输入、许可和哈希开始。
- [ ] 在批准环境直接 GUI 生成电子、自旋和 RDM 网格。
- [ ] 独立核对来源、密度层级、单位、积分和网格。
- [ ] 完成 View、渲染、工程移动、冷重开、重建与恢复。
- [ ] 环境或双语章节缺失时标 Blocked；记录修复与复测。
- [ ] Reviewer／日期／签名：________________

## T10 — 密度表面 ESP 着色

- [ ] 从 `T10.case-spec.json` 固定同结构同网格输入与哈希开始。
- [ ] 在批准环境直接 GUI 生成密度表面和 ESP 着色。
- [ ] 独立核对结构绑定、affine grid、ESP 单位和颜色范围。
- [ ] 完成 View、渲染、工程移动、冷重开、重建与恢复。
- [ ] 环境或双语章节缺失时标 Blocked；记录修复与复测。
- [ ] Reviewer／日期／签名：________________

## T11 — 振动与 IR/Raman

- [ ] 从 `T11.case-spec.json` 固定 Gaussian/ORCA 输入、许可和哈希开始。
- [ ] 在批准环境直接 GUI 生成频率、强度和模式动画。
- [ ] 独立核对 normal mode、IR/Raman 单位、虚频和原子映射。
- [ ] 完成图表/View、动画渲染、移动、冷重开、重建与恢复。
- [ ] 环境或双语章节缺失时标 Blocked；记录修复与复测。
- [ ] Reviewer／日期／签名：________________

## T12 — TD、UV–Vis 与 ECD

- [ ] 从 `T12.case-spec.json` 固定 TD 输入、许可和哈希开始。
- [ ] 在批准环境直接 GUI 生成激发态、UV–Vis/ECD 图。
- [ ] 独立核对能量、波长、oscillator/rotatory strength、gauge 边界。
- [ ] 完成图表渲染、工程移动、冷重开、重建与恢复。
- [ ] 环境或双语章节缺失时标 Blocked；记录修复与复测。
- [ ] Reviewer／日期／签名：________________

## T13 — 能带与 DOS

- [ ] 从 `T13.case-spec.json` 固定输入、许可和哈希开始。
- [ ] 在批准 scientific 环境直接 GUI 生成 band/DOS/projection。
- [ ] 独立核对 k 路径、投影、能量单位和参考零点。
- [ ] 完成图表/View 渲染、移动、冷重开、重建与恢复。
- [ ] 环境或双语章节缺失时标 Blocked；记录修复与复测。
- [ ] Reviewer／日期／签名：________________

## T14 — q 点声子

- [ ] 从 `T14.case-spec.json` 固定 NaCl 输入、许可和哈希开始。
- [ ] 在批准 scientific 环境直接 GUI 生成 q 点模式和周期相位动画。
- [ ] 独立核对 q vector、eigenvector、频率、相位和超胞映射。
- [ ] 完成动画渲染、工程移动、冷重开、重建与恢复。
- [ ] 环境或双语章节缺失时标 Blocked；记录修复与复测。
- [ ] Reviewer／日期／签名：________________

## T15 — critic2 QTAIM/NCI

- [ ] 从 `T15.case-spec.json` 固定 WFX 输入、许可和 critic2 身份。
- [ ] 在批准环境直接 GUI 复做 QTAIM 与配对 NCI 网格。
- [ ] 独立核对 CP/path、RDG、sign(lambda2)rho；不得虚构键能。
- [ ] 完成 View、渲染、工程移动、冷重开、重建与恢复。
- [ ] 双语章节/部署资格缺失时标 Blocked；记录修复与复测。
- [ ] Reviewer／日期／签名：________________

## T16 — Fermi surface

- [ ] 从 `T16.case-spec.json` 核对许可与可再分发输入，不使用未批准 POTCAR/pickle。
- [ ] 在批准且当前的 Fermi 环境直接 GUI 生成 surface。
- [ ] 独立核对 k mesh、band、energy reference、spin 和周期边界。
- [ ] 完成 View、渲染、工程移动、冷重开、重建与恢复。
- [ ] 许可/环境/双语章节缺失时标 Blocked；记录修复与复测。
- [ ] Reviewer／日期／签名：________________

## T17 — 13 格式科学导出

- [ ] 从 `T17.case-spec.json` 与 MOL2 正向规格固定输入、许可和哈希。
- [ ] 直接 GUI 复做 13 格式 preview/确认/export/reimport 和拒绝案例。
- [ ] 独立核对 loss gate、科学字段、单位、层级与 envelope 边界。
- [ ] 核对相对路径 review package；render/`.blend` 以 Prepare-only N/A 记录。
- [ ] 按中英离线教程盲走，记录缺陷、修复与复测。
- [ ] Reviewer／日期／签名：________________

## T18 — 保存、迁移、relink 与离线恢复

- [ ] 从 `T18.case-spec.json` 固定候选、工程对和恢复故障矩阵。
- [ ] 第二干净 profile 直接 GUI 复做 Save As/Cancel、legacy migration 和 relink。
- [ ] 独立核对实体/revision/数组、缺失/错误/损坏/过期拒绝。
- [ ] 移除副本源并使用不存在 processor 路径，重建后冷重开。
- [ ] 按中英离线教程盲走，记录缺陷、修复与复测。
- [ ] Reviewer／日期／签名：________________

## T19 — 外部 Reader API

- [ ] 从 `T19.case-spec.json` 固定 reader、fixture、许可和哈希。
- [ ] 外部 Python 复做 conformance、显式注册/discovery/parse/unregister。
- [ ] 独立核对 CBQ、错误输入拒绝及内置 reader 数不变。
- [ ] 完成 Viewer GUI、渲染、工程移动、冷重开、重建与恢复。
- [ ] 双语章节缺失时标 Blocked；记录缺陷、修复与复测。
- [ ] Reviewer／日期／签名：________________

## T20 — QCSchema 真实 compute

- [ ] 从 `T20.case-spec.json` 固定 AtomicInput、现有 AtomicResult、许可和哈希。
- [ ] 在批准 QCEngine/PySCF 环境直接运行真实 compute；交换成功不能代替计算。
- [ ] 独立核对 method/basis/driver、energy/gradient/force 符号和单位。
- [ ] 完成 GUI/View、渲染、工程移动、冷重开、重建与恢复。
- [ ] 依赖或双语章节缺失时标 Blocked；记录修复与复测。
- [ ] Reviewer／日期／签名：________________

## B01 — 外部 provider 边界

- [ ] 从 `B01.case-spec.json` 固定无凭据请求、provider 与候选身份。
- [ ] 直接 GUI 复做 capabilities、缺依赖、缺认证、取消和错误恢复。
- [ ] 只有真实远端成功才勾正向 fetch；离线 fixture/PubChem 不得替代。
- [ ] 核对输出/无输出、网络行为、凭据脱敏和 review package。
- [ ] 双语章节或 live transport 缺失时标 Blocked；记录修复与复测。
- [ ] Reviewer／日期／签名：________________
