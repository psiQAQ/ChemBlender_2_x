# ChemBlender 用户工作流与人工体验发布门设计

## 目标

为 ChemBlender 建立一套面向普通使用者、可实际执行、可由 Blender MCP
辅助、可在发布前重复检阅的工作流中心。文档必须从用户目标出发说明导入、
检查、处理、展示、导出、保存恢复和旧项目迁移，而不是从内部模块或路线图
出发罗列能力。

交付还必须包含可入库的全格式最小样例、少量可直接打开的代表性结果、
UI 等价 Agent 提示词、自动化 Blender 走查代码、人工结果模板和版本化发布
证据。自动走查发现的插件缺陷在本目标内修复并复测；所有工作只在本地分支和
worktree 中提交，全部通过后合并回本地 `main`，不 push、不 tag、不发布版本。

## 非目标

- 不把只有 core、worker、adapter 或 contract 的研发能力宣传成可点击产品功能。
- 不为完成教程新增第三方依赖、在线安装流程或新的格式支持。
- 不通过私有模块、直接写 `.cbq`、改缓存或伪造 Blender 自定义属性来绕过 UI。
- 不在本目标内发布新版本、修改 remote、创建 PR 或上传 Release。
- 不把材质、灯光、相机和一般场景美化归入 ChemBlender 产品能力。

## 目录结构

```text
docs/user/workflows/
├─ README.md
├─ 01-import.md
├─ 02-process.md
├─ 03-visualize.md
├─ 04-export.md
├─ 05-project-lifecycle.md
├─ 06-agent-and-mcp.md
├─ 07-agent-beyond-plugin.md
├─ formats.md
└─ reviews/
   ├─ README.md
   └─ template.md

examples/user-workflows/
├─ README.md
├─ manifest.json
├─ inputs/
│  ├─ xyz/
│  ├─ extxyz/
│  ├─ mol/
│  ├─ sdf/
│  ├─ smiles/
│  ├─ cif/
│  ├─ poscar/
│  ├─ mol2/
│  ├─ pdb/
│  ├─ pqr/
│  ├─ cube/
│  ├─ cjson/
│  ├─ qcschema/
│  └─ legacy/
├─ outputs/
└─ scripts/
   └─ run_ui_workflows.py
```

根 `README.md` 和 `docs/README.md` 指向
`docs/user/workflows/README.md`。现有 `docs/user/*.md` 继续作为细节事实源；
新工作流中心不搬迁这些文件，只做用户路线编排和必要交叉链接。现有
`docs/user/2.4.0-experience-review.md` 保留为 2.4.0 历史检阅入口，并指向新的
长期发布门。

## 文档职责与写作模板

### 总览

`README.md` 说明 2.1.0 传统对象工作流与当前 Project 工作流的可见差异，提供
以下推荐路线：

```text
准备环境 → 导入 → Import Preview → 处理 → 展示 → 导出
                         ↓
                 保存 / 重开 / 恢复 / 迁移
```

总览只列出基础安装可完成、可选依赖可完成和仅 Agent/开发接口可完成三种边界，
不得把三者混写。

### 流程文档

每个可操作步骤使用同一小节结构：

1. 用户要完成什么；
2. 使用哪个示例；
3. Blender UI 路径；
4. 操作前检查；
5. 操作步骤；
6. 屏幕上应看到什么；
7. 如何验证结果；
8. 常见失败与安全退出；
9. UI 等价 Agent 提示词。

步骤必须使用界面上的真实英文 label 和用户可见状态，并解释必要术语。不能要求
用户阅读 Python 类名、UUID 或内部 schema 才能完成普通操作。

### 格式说明

`formats.md` 覆盖 ChemBlender 2.4 基础格式族：XYZ、extXYZ、MOL V2000/V3000、
SDF、SMILES、CIF、POSCAR/CONTCAR、MOL2、PDB、PQR、Cube、CJSON 和
QCSchema。每种格式说明：

- 格式本身可能提供的结构、拓扑、轨迹、属性、晶胞、对称性、层级或 Grid3D
  数据；
- ChemBlender 当前实际导入的数据；
- 默认或可选 View；
- Project Browser 中可执行的处理与导出；
- F0–F5 import/export 成熟度；
- RDKit、Gemmi 或可选 runtime 边界；
- 规范化导出会省略或改变的内容；
- 对应样例和工作流文档。

现有 `docs/user/formats.md`、`docs/user/format-capabilities.json` 和
`docs/user/dependencies.json` 仍是能力事实源。新增格式页必须覆盖其中的基础格式，
并由测试防止格式、成熟度或依赖描述漂移。

## 样例数据集

### 输入样例

首选复制并冻结已由仓库测试验证的 fixtures；复制后的用户样例拥有独立 SHA-256，
不通过相对链接依赖 `tests/`。初始样例选择如下：

| 格式族 | 用户样例 | 来源基线 | 主要用途 |
| --- | --- | --- | --- |
| XYZ | `inputs/xyz/water.xyz` | `tests/fixtures/xyz/water.xyz` | 单结构 Quick Import |
| extXYZ | `inputs/extxyz/carbon-trajectory.extxyz` | `tests/fixtures/extxyz/multiframe-cell.extxyz` | 多帧、cell/PBC |
| MOL | `inputs/mol/water-v2000.mol` | `tests/fixtures/mol/water-v2000.mol` | RDKit 结构与拓扑 |
| SDF | `inputs/sdf/mixed-properties.sdf` | `tests/fixtures/sdf/mixed-properties.sdf` | 多记录和属性 |
| SMILES | `inputs/smiles/ethanol.smi` | 本地生成的 `CCO` 文本 | 文本/文件导入和 3D 派生 |
| CIF | `inputs/cif/nacl.cif` | `tests/fixtures/cif/nacl.cif` | 晶胞、位点和对称性 |
| POSCAR | `inputs/poscar/si.POSCAR` | `tests/fixtures/poscar/si.POSCAR` | Direct 坐标和晶体结构 |
| MOL2 | `inputs/mol2/substructure.mol2` | `tests/fixtures/mol2/substructure.mol2` | bond、charge、substructure |
| PDB | `inputs/pdb/multimodel.pdb` | `tests/fixtures/pdb/multimodel.pdb` | 生物层级和 MODEL frames |
| PQR | `inputs/pqr/with-chain.pqr` | `tests/fixtures/pqr/with-chain.pqr` | chain、charge 和 radius |
| Cube | `inputs/cube/two-datasets.cube` | `tests/fixtures/cube/two-datasets.cube` | Structure、Grid3D 和多 dataset |
| CJSON | `inputs/cjson/water-results.cjson` | `tests/fixtures/cjson/water-results.cjson` | 轻量结果 envelope |
| QCSchema | `inputs/qcschema/atomic-result.json` | `tests/fixtures/qcschema/atomic_result_v2.json` | Molecule、AtomicResult 和 raw envelope |
| Legacy | `inputs/legacy/chemblender-2.1-molecule.blend` | hash-locked 2.1 fixture | 显式迁移流程 |

如果上述来源缺少教程需要的合法语义，先本地生成最小文件并加入 parser 测试；只有
本地无法安全生成时才考虑明确许可的在线来源。任何需要未下载仓库、额外 runtime
或网络素材的剩余案例统一留到目标末尾，一次性向用户报告并申请批准。

### 样例清单

`manifest.json` 按 Unicode code point 排序记录：

- 相对路径；
- 格式族；
- 来源或生成方法；
- 许可/仓库内 provenance；
- SHA-256；
- 文件字节数；
- 预期 reader/runtime；
- 预期主要实体、质量状态和 View；
- 对应文档流程。

`examples/user-workflows/README.md` 将同一信息转换为用户可读表格，但
`manifest.json` 是测试使用的样例清单。

### 文件大小和已保存结果

- 所有单文件绝对不得超过 100 MB。
- 目标是每个文件不超过 50 MB；超过 50 MB 的文件必须在 manifest 中记录不可
  替代原因，否则测试失败。
- 样例分辨率、帧数和 Grid 尺寸只保留演示当前工作流所需的最低规模。
- `outputs/` 只提交能够证明独特 save/reopen 行为、可直接观看且不与输入重复的
  代表结果。
- 候选 `.blend`/`.cbq` 包括分子、晶体、Grid3D 和 legacy migration 四类；只有
  在真实保存、冷重开、项目链接、关键 View、外部引用和大小检查均通过后才纳入。
- 自动走查产生但没有独立教学价值的临时导出进入隔离临时目录，不提交。
- 提交任何 `.blend` 前必须用 Blender 5.1.0+ 重开并检查关键 scene/object/project
  状态；不能只检查文件存在或大小。

## Agent 与 Blender MCP 契约

### 插件能力内

每个提示词包含以下硬边界：

1. 先通过 Blender MCP 一次查询 Blender version、executable、bundled Python、
   runtime system、extension repositories、活动文件和 ChemBlender enabled key；
2. 要求 Blender 5.1.0+，并确认 `bl_ext.user_default.chemblender`；
3. 使用当前可用的 Blender MCP code-execution tool；
4. 仅调用已注册的 `bpy.ops.chemblender.*` Operator 和公开 Scene RNA 属性；
5. 在调用前检查 Operator RNA 参数，不猜测参数名；
6. 不 import ChemBlender 私有模块，不直接修改 `.cbq`、缓存、内部 Python state
   或自定义属性；
7. 不绕过 Import Preview、质量/冲突决定、loss preview、显式确认或事务边界；
8. 调用后读取与人工 UI 相同的可见状态、报告、对象或输出文件并验证；
9. 任一前置条件不满足时停止并说明，不用私有 API 伪造成功。

提示词使用 Agent 中立措辞，可直接交给 Codex、Claude Code 或其他能连接同一
Blender MCP 的 Agent。不同 Agent 的 MCP tool 名可能不同，文档不硬编码未经当前
会话确认的工具名。

### 插件能力外

`07-agent-beyond-plugin.md` 独立展示以下通用 Blender 案例：

- 为 ChemBlender 已创建的对象调整材质；
- 设置世界背景、灯光和相机；
- 组织 collection 和视图可见性；
- 设置 Cycles/Eevee 渲染参数并保存副本；
- 不改变科学实体的前提下制作展示场景。

这些案例允许使用一般 `bpy`，但必须标注“Agent/Blender 能力，不是 ChemBlender
产品能力”。不得把 Object transform、材质或显示变化描述为科学数据编辑。

## 自动化工作流走查

`examples/user-workflows/scripts/run_ui_workflows.py` 是 Blender 内运行的
UI 等价走查入口。它只通过公开 Operator 和公开 RNA 驱动以下流程：

1. Quick Import 单文件、多文件、SMILES 和取消；
2. Import Preview 检查并确认；
3. Project Browser source/data 投影、搜索、质量过滤和选择；
4. 科学编辑、拓扑 proposal/accept/reject/switch；
5. CIF/POSCAR 晶体属性、symmetry 和 selective dynamics；
6. PDB/PQR biological hierarchy、选择和 MODEL playback；
7. Cube dataset 选择、语义确认、Volume、Signed Surface 和 property map；
8. 支持格式的 Project Browser export、loss preview、取消和原子发布；
9. `.blend`/`.cbq` 保存、冷重开、Verify/Relink 和 cache reconstruction；
10. 2.1 legacy preview、显式确认、迁移、保存和冷重开。

Runner 为每条流程输出结构化 JSON 结果，包含案例 ID、输入、Operator、结果、可见
状态、输出路径、耗时和失败信息。它不替代人工检阅，只减少用户第一次走文档时
遇到明显参数、注册、路径或事务错误的概率。

纯 Python 测试验证 runner 没有私有 import、直接 sidecar 写入或被禁止的状态突变；
Blender runtime smoke 验证真实 Operator 和输出。无法通过 Operator 自动完成的
文件选择或确认界面必须由对应 Operator 的公开执行参数驱动，并在人工文档中保留
真实 UI 步骤；不能改用内部函数绕过。

## Blender MCP、安装与崩溃恢复

首次 Blender 操作严格按以下顺序：

1. 运行 `blender-mcp --help`；
2. 检查 Agent runtime system；
3. 通过 MCP 一次读取 Blender version、executable、bundled Python、runtime
   system、extension repositories、活动文件和 dirty state；
4. 确认仓库与 Blender 同为 Windows runtime，路径可由 Blender 读取；
5. 用 MCP 返回的 Blender/Python 路径 validate/build；
6. 通过 Blender Extensions 安装 ZIP 到 `user_default`；
7. 验证 enabled key、公开 Panel/Operator/Scene properties、RDKit/Gemmi import；
8. 运行两次 register/unregister/reload lifecycle；
9. 再运行工作流走查。

若 MCP 断开或 Blender 崩溃：

1. 通过精确 executable path 和 command line 检查 Blender 5.1 进程；
2. 若没有匹配进程，直接启动 MCP 上一次确认的 Blender 5.1 executable，使用
   `-WindowStyle Hidden` 仅限不需人工交互的恢复进程；需要用户观察的 GUI 走查
   保持可见；
3. 条件轮询 MCP listener，不使用长时间固定 sleep；
4. 重新执行完整 runtime query，确认不是 stale path/version；
5. 检查上一个案例是否留下 staging、半成品输出或 dirty project；
6. 从该案例的干净前置状态重跑，不从未知中间状态继续。

监听端口存在、manifest 可解析、Operator 返回 `FINISHED` 或输出文件存在都不足以
单独证明成功；必须验证真实项目、View、sidecar、导出语义或冷重开状态。

## 缺陷修复循环

自动或人工流程失败时：

1. 保存最小输入、准确 Operator/UI 步骤、Blender/runtime 信息、错误和残留路径；
2. 区分文档错误、案例错误、环境缺失和插件缺陷；
3. 插件缺陷使用最小可复现测试进入 RED；
4. 追踪所有调用者，在共享根因位置做最小修复；
5. 运行 GREEN 测试、相邻测试、真实 Blender 案例和文档对应步骤；
6. 单独提交该缺陷修复；
7. 在版本检阅结果中链接修复 commit，并从失败步骤开始重跑，必要时重跑完整流程。

不在一个提交中混入多个无关缺陷或顺手重构。若某缺陷需要新依赖、扩展产品范围
或外部写入，停止并请求用户授权。

## 人工插件使用体验检阅发布门

`reviews/template.md` 是版本无关模板，至少记录：

- 版本、commit、ZIP SHA-256、Blender/MCP/runtime/profile；
- 每条工作流的输入、UI 步骤、Agent 提示词结果、耗时和证据；
- UI 与 Agent 是否得到相同项目/输出语义；
- Blocker、Major、Minor、Suggestion finding；
- 缺陷 commit、复测结果和剩余限制；
- 所有样例和保存结果的大小、hash 和冷重开状态；
- 最终 `Passed`、`Failed` 或 `Blocked` 结论。

每个候选/正式版本复制为 `reviews/<version>.md` 并受 Git 跟踪。任一必需流程未
执行、失败、使用私有绕过或缺少真实输出验证时，发布门为 `Failed/Blocked`；自动
测试通过不能替代人工结果。发布文档和依赖规则把该检阅列为 tag/Release 前的
明确 gate，但本目标不创建版本结果或发布版本。

## Git 与阶段边界

- 从 `main` 创建本地 `codex/user-workflow-experience-gate` 隔离 worktree。
- 设计、计划、文档/样例、自动走查、每个缺陷修复和最终证据各自形成可审查的本地
  commit。
- 不 push、不创建 PR、不 tag、不发布、不修改 remote。
- 所有必需流程通过、工作树干净且本地提交历史可审查后，普通合并回本地 `main`；
  不 rebase、不 force、不改写已发布 tag。
- 合并前确认 `main` 未漂移或存在未提交用户修改；若漂移导致冲突，停止并报告，
  不隐式覆盖。

## 验证与完成标准

### 静态和纯 Python

- 新增标准库测试检查文档清单、链接、根 README/docs index 入口、格式覆盖、
  manifest schema、Unicode ordinal 排序、SHA-256、来源、许可和大小门。
- 每个基础格式至少有一个存在且 hash 匹配的样例。
- 能由 built-in reader 解析的样例运行真实 parser；RDKit/Gemmi 样例在安装态
  Blender 中强制验证，不以 skip 代替。
- Agent 提示词均包含 MCP preflight、公开 Operator、成功判据和禁止绕过边界。
- 自动走查脚本不存在 ChemBlender 私有模块 import、直接 `.cbq` 写入或 private
  custom-property mutation。
- 运行现有文档、生成物、repository contract、compile 和 `git diff --check`。

### Blender 5.1 安装态

- MCP runtime query、Extension validate/build、ZIP audit 和干净安装通过。
- enabled key、RDKit/Gemmi、Panel/Operator/Scene property 和两轮 lifecycle 通过。
- 全格式导入、适用处理/View、适用导出、保存/冷重开、恢复和 legacy migration
  通过。
- 提交的 `.blend`/`.cbq` 代表结果可冷重开、无缺失 library/image、关键科学实体
  和 View 与 manifest 一致。
- 每个流程的 JSON 自动结果为 `Passed`，或被明确分类为需要用户批准的外部前置
  条件并集中留到最后。

### 最终状态

- 文档和案例完整，可由用户按顺序执行。
- 已发现插件缺陷均有复现、修复、测试和对应流程复测证据。
- 没有超过 100 MB 的文件；超过 50 MB 的例外均有必要性记录。
- 人工检阅模板和发布门规则已被仓库文档引用。
- 隔离分支全部本地提交，验证通过，合并回本地 `main`，最终工作树干净。
- 没有执行任何远端写入或版本发布。
