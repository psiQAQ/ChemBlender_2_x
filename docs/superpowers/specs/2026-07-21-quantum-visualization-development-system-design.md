# ChemBlender 量子化学可视化持续开发体系设计

## 目标

把 2026 年 7 月 21 日的项目调研转成可执行、可追踪的开发体系。文档按物理量与架构责任组织，不按文件后缀堆功能；每次只激活一个主题，完成验收后再推进下一个主题。

本轮只建立文档、决策和参考仓库占位，不创建 `chemblender_core`，不安装依赖，也不拉取外部仓库。

## 已确认边界

- `origin/main` 继续作为维护发布线，`upstream/main` 作为上游参考。
- 2.2.0 及后续版本使用 `ChemBlender/` 作为 Blender Extension 根目录；仓库根目录仍是开发工作区。
- Blender 端保留结构建模、Geometry Nodes、材质、动画和交互职责。
- 长期目标包含独立于 `bpy` 的量子化学语义核心，但是否拆成独立 Python 包，要等首个架构任务验证后决定。
- 不把大型数组、轨道系数或体数据直接写入 `.blend` 作为权威数据源。
- 新依赖、Blender wheel、外部 worker 和数据存储格式都需要单独决策，不能由路线图默认引入。

## 组织原则

开发主题围绕可组合的物理语义展开：结构、计算记录、属性、网格、轨道、振动、激发态、周期电子结构、拓扑和 provenance。文件格式只负责把来源数据转换成这些语义对象。

计划文档描述稳定范围、优先级、依赖关系和验收标准；`.agents/active/` 只记录当前任务。完成一个主题后，将结果移入 `.agents/completed/`，再从路线图选择下一项。长期路线图不记录临时 commit、CI run 或本机状态。

## 文档结构

```text
docs/quantum-visualization/
├── README.md
├── roadmap.md
├── architecture/
│   └── data-boundary.md
├── plans/
│   ├── semantic-core.md
│   ├── readers-and-formats.md
│   ├── wavefunction-and-grids.md
│   ├── blender-visualization.md
│   ├── periodic-electronic-structure.md
│   ├── storage-and-workers.md
│   └── workflows-and-connectors.md
└── references.md

submodules/
└── README.md

.agents/active/
└── quantum-visualization-foundation.md
```

各文件职责如下：

| 文件 | 职责 |
| --- | --- |
| `README.md` | 面向开发者的入口，说明阅读顺序和当前阶段 |
| `roadmap.md` | Phase 0–4、阶段门、主题依赖与推进规则 |
| `architecture/data-boundary.md` | 记录语义模型、`Grid3D`、单位、reader contract、Blender/边车边界五项待决策内容 |
| `plans/*.md` | 每个主题的 P0/P1/P2、交付物、非目标、验收标准和参考仓库触发条件 |
| `references.md` | 候选项目、参考用途、许可证核查状态和计划中的使用位置 |
| `submodules/README.md` | 外部仓库候选清单与按需添加流程；在真正需要代码审阅前保持空占位 |
| `.agents/active/*.md` | 当前唯一执行主题、已确认事实、下一步和验证状态 |

不创建空目录。Git 不能跟踪空目录，因此 `submodules/README.md` 同时承担占位和规则说明。

## 主题划分

### 1. 语义核心

定义 `Structure`、`CalculationRecord`、`PropertyDataset`、`Grid3D`、`ParserReport` 和 `Provenance` 的最小契约。优先解决数组维度、单位、缺失信息和来源记录，不先覆盖调研中列出的全部对象。

### 2. Reader 与格式能力

建立 reader/capability registry、内容 sniffing、ParserReport 和格式能力矩阵。cclib、IOData、ASE、Gemmi、spglib 与 QCSchema 都通过 adapter 接入，不把第三方容器直接暴露给 Blender。

现有 MOL2 声明与读取实现不一致，作为该主题的首个回归案例处理，不在文档阶段顺带修改。

### 3. 波函数、网格与表面

覆盖 Cube、多数据集与非正交 step vectors、MO/密度/自旋密度/ESP、表面采样和等值面。IOData 与 Molecular Blender 提供解析和求值参考；GBasis/Grid 或 ORBKIT 的主后端选择留到基准测试后。

### 4. Blender 可视化映射

把原子标量、原子矢量、轨迹、振动、光谱、网格和表面映射到 named attributes、Geometry Nodes、Volume、Mesh、Curve、Material 和动画。Blender datablock 是视图与缓存，不是项目数据模型。

### 5. 周期电子结构

覆盖晶体标准化、CHGCAR/ELFCAR/LOCPOT、band/DOS、费米面和 phonopy 复数模态。Gemmi/spglib 的 CIF 与对称性替换属于前置任务；pymatgen、PyProcar、sumo 和 phonopy 在需要实现该主题时再引入参考代码。

### 6. 存储与 worker

确定 `.cbq` 项目、数组边车、hash 失效、OpenVDB 缓存、worker 协议和长轨迹缓存。Zarr、HDF5 和 OpenVDB 都是候选项，不在没有数据规模基准时同时实现。

### 7. 工作流与 connector

把 quantum-chem-skills 的功能分类转成 recipe schema，并为 Multiwfn、critic2、QCArchive、AiiDA 和 NOMAD 设计外部 adapter。该主题不把第三方服务栈嵌入 Blender。

## 优先级定义

每份主题计划使用同一套优先级：

| 优先级 | 含义 | 进入条件 |
| --- | --- | --- |
| P0 | 当前阶段闭环所必需；缺失时后续主题不能可靠实施 | 已有复现输入、明确输出契约和可运行验证 |
| P1 | 扩大已完成闭环的覆盖面 | P0 验收通过，且存在真实使用场景或 fixture |
| P2 | 专业、高成本或可选能力 | P1 不能满足已确认需求，并有维护人与依赖方案 |

优先级属于主题内部，不等于 Phase。某个 Phase 只选择各主题中当时必要的条目。

## 阶段与阶段门

### Phase 0：数据边界

先完成五项正式决策：量子化学语义模型、`Grid3D` 数据约定、单位约定、reader capability contract、Blender 与边车的职责边界。随后实现最小纯 Python 核心，并以 MOL2 能力不一致和两种结构格式归一化作为早期验证。

阶段门：普通 CPython 可以运行 core tests；没有 `bpy` import；未支持字段显式报告；数值都有单位或明确标记为 dimensionless。

### Phase 1：分子量子化学闭环

接入 cclib、IOData 和 Cube，覆盖优化轨迹、能量、原子属性、振动、激发态光谱、轨道与常用标量场。QCSchema/CJSON 只实现闭环需要的交换子集。

阶段门：至少一个 Gaussian 或 ORCA 输出及配套波函数/网格 fixture 能从解析走到 Blender 视图，并保留 provenance。

### Phase 2：周期量子化学

接入 ASE/pymatgen、周期体数据、band/DOS、费米面和 phonopy。先完成 Gemmi/spglib 路径，再扩展材料电子结构。

阶段门：结构、倒空间数据和可视化共享稳定 ID；复数 q-point 模态按相位公式生成动画。

### Phase 3：大型数据与交互

根据 Phase 1/2 的实测规模选择数组存储、OpenVDB、worker、lazy loading、缓存和长轨迹方案。

阶段门：缓存可按 source/parser/derivation/render hash 失效；`.blend` 不包含权威大型数组；崩溃或重开后可以恢复项目引用。

### Phase 4：工作流与自动化

实现 recipe、外部分析 adapter、数据库 connector、报告与场景模板。

阶段门：recipe 明确输入语义、单位、外部程序、输出、验证和引用，失败不会留下被误认为有效的派生数据。

## 参考仓库策略

`submodules/` 初始只有说明文件，不创建 `.gitmodules`。当某项已批准计划需要逐行审阅、运行测试或保留固定 commit 证据时，才添加对应 submodule。

添加前必须记录：

- 上游 URL、用途和对应主题；
- 许可证以及可复制代码的边界；
- 固定 commit；
- 是否只用于阅读、测试对照或实际复用；
- 更新与移除方式。

仅需 API 文档或架构思想时，不添加 submodule。首次候选是 `xyzrender`、`quantum-chem-skills`、Molecular Blender、Beautiful Atoms 和 Molecular Nodes；cclib、IOData 等正式依赖仍通过依赖决策管理，不能因为存在 submodule 就成为运行时依赖。

## 首个执行主题

首个 active task 是“量子化学数据边界与契约”。它只产出五项 ADR、最小接口规格、fixture 选择规则和实现计划，不立即创建完整模型目录。

该任务完成后，再决定是否创建 `ChemBlender/chemblender_core/`，或将纯 Python 核心放在扩展根目录之外。这个位置选择必须同时满足 Blender 打包、普通 CPython 测试和未来独立 worker 三个入口。

## 文档更新规则

- `docs/quantum-visualization/` 保存稳定路线、计划和架构说明。
- `.agents/active/` 只在目标、事实、下一步或验证结果发生实质变化时更新。
- 架构结论写入新的编号 decision，不用路线图替代 ADR。
- 依赖、打包或 release gate 变化同步更新 `.agents/reference/dependencies-and-release.md`。
- 完成主题后归档 active 文档，并在路线图中只更新阶段状态和下一主题。

## 验证

第一轮文档体系通过以下检查：

- `docs/README.md`、`.agents/README.md` 和新增入口之间的相对链接全部存在；
- 每份主题计划都有范围、非目标、P0/P1/P2、依赖、交付物、验收标准和参考仓库触发条件；
- `submodules/` 只有占位说明，没有 `.gitmodules` 或外部工作树；
- active 文档只指定一个当前主题；
- 文档不把候选依赖写成已批准依赖；
- `git diff --check` 通过，新增 Markdown 为 UTF-8 无 BOM。

## 非目标

- 本轮不修复 MOL2，不迁移 CIF parser，不创建 reader registry。
- 不一次性定义调研中全部模型字段。
- 不同时实现 Zarr 和 HDF5，也不预选轨道求值后端。
- 不添加 Git submodule、Python 包、Blender wheel 或网络服务。
- 不修改 remotes，不 push，不发布版本。
