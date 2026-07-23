# ChemBlender `main` 深度审计与 2.3.0 可执行改进报告

## 1. 审计范围与证据边界

本报告审阅 `psiQAQ/ChemBlender_2_x` 的 `main` 分支快照：

```text
commit: 1cf492f40d5fa8799fa964b8dfc914ab5ecbec4c
commit message: docs: add code architecture guide
date reviewed: 2026-07-23
```

主要证据来自以下仓库文件和固定提交内容：

- `AGENTS.md`
- `.agents/README.md`
- `.agents/reference/code-architecture-guide.md`
- `.agents/reference/dependencies-and-release.md`
- `.agents/completed/quantum-visualization-roadmap-audit.md`
- `docs/quantum-visualization/roadmap.md`
- `ChemBlender/core/model.py`
- `ChemBlender/core/readers.py`
- `ChemBlender/core/reader_catalog.py`
- `ChemBlender/core/sidecar.py`
- `ChemBlender/read.py`
- `ChemBlender/output.py`
- `ChemBlender/panel.py`
- `ChemBlender/auto_load.py`
- `.github/workflows/extension-package.yml`
- `.github/workflows/extension-release.yml`
- `tests/blender_smoke.py`
- 相关 reader、adapter 和测试文件

执行前必须 live-verify；本审计不声称已在本环境重新运行仓库测试或 Blender 构建。

## 2. 总体判断

### 2.1 结论

当前仓库的架构基础显著强于 2.2.0 对外产品描述。纯 Python 语义核心、reader registry、`.cbq`、worker、安全边界、量子数据模型和 Blender adapter 已经覆盖较广。其最突出的优势是：已经形成“数据先于视图、可选依赖隔离、引用原子校验、缓存有身份”的正确方向。

但路线图把 Phase 0–4 全部标记为“完成”会掩盖产品成熟度差异。许多功能达到的是 Contract 或 Synthetic Integration，而不是基础安装下的 Real-file Integration、Product UX 或 Release-qualified。下一步不应继续横向增加更多高级后端，而应把已有基础收敛为真实格式、统一 UI、来源/质量管理和可恢复项目闭环。

### 2.2 维度评分

| 维度 | 当前评价 | 2.3.0 目标 | 优先级 |
| --- | ---: | ---: | --- |
| 仓库治理与决策记录 | 8.5/10 | 9/10 | P1 |
| Extension 发布工程 | 7.5/10 | 9/10 | P0 |
| 纯 Python 语义核心 | 8/10 | 9/10 | P0 |
| 模块边界与可维护性 | 5.5/10 | 8.5/10 | P0 |
| 基础格式原生覆盖 | 4/10 | 9/10 | P0 |
| 量子后端契约广度 | 8/10 | 保持 | P2 |
| 普通用户 UI 闭环 | 2.5/10 | 8.5/10 | P0 |
| 科学质量与诊断 UX | 5/10 | 9/10 | P0 |
| 真实文件测试覆盖 | 5.5/10 | 8.5/10 | P0 |
| 性能与规模门禁 | 5/10 | 8/10 | P1 |
| 第三方 reader 生态 | 3/10 | 8/10 | P1 |
| 旧项目升级路径 | 3/10 | 8/10 | P1 |

## 3. 原计划完成度重新分类

### 3.1 Phase 0：数据边界

**判断：Contract 和主要核心实现基本完成。**

已确认：

- `ChemBlender/core/` 可由普通 CPython 导入，不要求 `bpy`。
- `ArrayData`、`Structure`、`PropertyDataset`、`Grid3D`、轨道、密度矩阵、周期与拓扑模型存在。
- `QCProject.commit()` 在修改 registry 前校验引用，并能拒绝悬空关系。
- `ReaderRegistry` 支持扩展名、bounded sniffing、优先级和歧义拒绝。
- `ParserReport` 对缺失、未支持、歧义和无效字段有基础表示。
- `.cbq` 使用 canonical JSON、content-addressed NPY、`allow_pickle=False`、路径约束与 hash 复验。

未完成或需升级：

- `model.py` 已成为 2500 行以上单体模块。
- `core/__init__.py` 作为 400 行以上全量 re-export，同时导入几乎全部 adapter 模块。
- 没有 `SourceRecord`、`SourceRevision`、解析身份和重复导入历史。
- `ParserIssue` 只有 `kind/path/message`，不足以表达恢复动作、科学后果、原值和规范化值。
- sidecar type registry依赖扫描单一 `model` 模块；模型拆分后需要显式、安全、版本化 registry。
- Scene link 代码保存 project UUID、schema 和 locator，但架构文档所称的 manifest hash 当前没有实际字段。

### 3.2 Phase 1：分子量子化学闭环

**判断：可选后端的适配器和部分 Blender 映射完成，基础用户闭环未完成。**

已确认：

- cclib adapter 覆盖结构、轨迹、SCF 能量、原子电荷/自旋、振动和激发态。
- IOData adapter 覆盖 FCHK/Molden 的基组、轨道、密度矩阵和有效核电荷。
- GBasis 网格求值、振动/光谱和表面 adapter 存在。
- 固定 cclib/IOData fixture 的 integration tests 在相应环境可运行。

缺口：

- cclib、IOData、GBasis 不在官方 ZIP，用户必须配置外部环境。
- Quick Import 和 Project Browser 没有把这些数据暴露为产品工作流。
- `CalculationRecord` 在 cclib adapter 中没有填充 `CalculationMetadata`；方法、基组、程序和版本主要埋在 provenance 参数中。
- `create_structure_view()` 仅建立顶点和原子序数，不建立拓扑边或默认球棍节点。
- 光谱当前是裸 Curve，没有坐标轴、单位标签、峰选择 UI 和质量状态。
- 真实 integration tests 在常规 package CI 中可能因未 checkout submodule、未安装依赖而跳过。

### 3.3 Phase 2：周期量子化学

**判断：数据模型和合成视图较完整，基础安装不能直接使用主要 reader。**

已确认：

- Gemmi/spglib、ASE/pymatgen、band/DOS、phonopy、Fermi surface adapter 存在。
- Blender smoke 覆盖周期结构、电子图、复数声子和 Fermi surface 的合成数据映射。

缺口：

- Gemmi、ASE、pymatgen、phonopy、PyProcar 都不在基础 ZIP。
- CIF 基础导入仍可能落入旧手写 parser；新 Gemmi reader 未形成安装即用 UI。
- POSCAR 基础读取依赖旧 `read.py` 或外部 ASE，不符合新的统一 reader contract。
- `ReaderRegistry` 使用 `Path.suffix`，需要专门支持无扩展名的 `POSCAR`、`CONTCAR` 内容 sniffing。
- 文件声明的空间群与 spglib 派生结果必须并存，目前产品 UI 尚未表达差异。

### 3.4 Phase 3：大型数据与交互

**判断：存储、缓存和 worker contract 完成；会话项目、用户恢复和规模门禁未完成。**

已确认：

- NPY sidecar、lazy mmap、trajectory LRU、Grid LOD、OpenVDB cache identity 和 worker JSON contract 存在。

缺口：

- 没有“未保存会话项目→保存 `.blend` 时固化 `.cbq`”的正式状态机。
- 没有保存/另存/重新链接/验证/恢复/清缓存 UI。
- `save_project()` 以 manifest 最后发布保证项目级一致性，但不是整个目录的 generation staging；需要为会话固化和迁移定义 generation/temporary-root 策略。
- 没有 SourceRevision 级别的缓存复用和文件移动重链接。
- 性能目标未成为 CI 可比较基线。

### 3.5 Phase 4：工作流与自动化

**判断：协议和中立模型较多，真实外部程序/服务接入与 UI 尚未成为承诺。**

已有 recipe、外部进程、critic2 topology、QCSchema/CJSON、QCEngine、报告、scene preset 和 connector contract。仓库自身审计也明确指出真实 Multiwfn/critic2 二进制、在线 connector、linked brushing 和远程 worker 为条件未来工作。该判断应继续保留，2.3.0 不应把这些升级为基础发布门。

## 4. 仓库结构评价

### 优点

1. `ChemBlender/` 是明确的 Extension root，仓库根目录用于 CI、测试、文档和 Agent 知识。
2. `.agents/decisions` 采用追加式 ADR，能够追踪架构演化。
3. `.agents/completed` 与 active/queued 分离，避免历史状态污染当前任务。
4. `.agents/reference/code-architecture-guide.md` 通过测试跟踪源码文件，减少文档漂移。
5. 外部参考项目固定 gitlink，运行时不进入 ZIP。

### 改进方向

1. 将 `core/model.py` 按责任拆分，保留 `ChemBlender.core` 兼容门面。
2. 将 readers、exporters、storage、import pipeline 与 public reader API 分目录。
3. `auto_load` 只注册显式 Blender 模块，不递归导入 `core`。
4. 新增 `ui/` 和 `views/` 分层；现有 `panel.py` 保留兼容外观，不继续膨胀。
5. `legacy/` 明确隔离旧 `read.py/scaffold.py` 兼容桥和迁移逻辑。
6. 子模块 integration fixtures 与基础仓库 tests 分开，避免日常 checkout 必须初始化全部大型上游。

## 5. CI/CD 审计

### 已有强项

- GitHub-owned actions 固定到完整 SHA。
- 日常 package workflow 只读权限。
- Blender 和 RDKit 下载后验证 SHA-256。
- 使用临时 `BLENDER_USER_RESOURCES` 做隔离安装。
- ZIP 内容、RDKit 操作、`.blend` 节点库、注册/注销和重复生命周期都有 smoke test。
- Release workflow 不重建制品，而是选择 exact-tag 成功 artifact 并复验 digest。

### 阻断问题

#### 5.1 版本和 artifact 名称硬编码

`extension-package.yml` 硬编码：

```text
chemblender-2.2.0.zip
chemblender-2.2.0.sha256
chemblender-2.2.0-windows-x64
```

而 release workflow 动态期待 `chemblender-$version-windows-x64`。下一版本会出现不一致。必须由 manifest 单一派生 version、package、checksum 和 artifact name。

#### 5.2 预发布版本不被当前工具接受

- release workflow tag regex 只接受 `vX.Y.Z`。
- `extract_release_notes.py` 只接受 `X.Y.Z`。
- 本地 validator 只识别三段数字，其他版本会警告。
- release workflow 当前发布后设置 `latest`，没有 pre-release 分支。

实施前必须用 Blender 5.1.2 原生 validator 对 `2.3.0-alpha.1` 做真实探针。若不接受，必须在任何 tag 或 changelog 变更前确定经验证的数字映射。

#### 5.3 真实 optional integration 测试可能静默跳过

cclib/IOData tests 使用 `skipUnless`。package workflow 未递归 checkout 全部 submodule，也未安装相应依赖，因此“全量 unittest 通过”不能证明真实 Gaussian/ORCA/FCHK/Molden integration 在 CI 中执行。需要独立 `qc-core-integration` job，输出执行与 skip 数量，并在该 job 中禁止目标测试 skip。

#### 5.4 只有一个大型 Windows job

当前 package job同时执行 unit、下载 Blender、build、install 和 artifact，反馈慢且无法明确区分失败层。应拆为：

```text
native-core
optional-qc-core
blender-extension
release-contract
```

最终 artifact 仍只能由完整 Blender job产生。

#### 5.5 缺少制品体积和 wheel 许可证门禁

2.3.0 新增 Gemmi 后必须：

- 固定 wheel 文件名、URL、SHA-256、许可证。
- 记录压缩和解压体积。
- 与 2.2.0 artifact 比较。
- 生成 wheel inventory 和许可证清单。
- 未解释的显著增长阻断。

## 6. Extension 代码结构与注册

### 6.1 `auto_load` 风险

`auto_load.py` 递归 import Extension 下的大部分模块，再扫描 Blender class。随着 `core` 和 UI 增长，这会：

- 增加启用耗时；
- 让无 UI 的模型和 adapter 在启用时导入；
- 增大顶层副作用与可选依赖误加载风险；
- 使第三方 reader 异常可能影响本体注册；
- 让 reload/unregister 更难验证。

方向：引入显式 `REGISTER_MODULES` 或每个 UI package 的 `register()` 汇总；`core/`、`reader_api/` 和纯 parser 不参与扫描。

### 6.2 `core/__init__.py` 过宽

当前公共门面一次性 re-export 几乎全部模型、reader、adapter、recipe、storage 和 worker 类型。它提供便利，但也造成：

- import surface 过大；
- 公共和私有 API 边界不清；
- 模块拆分困难；
- 第三方插件可能依赖内部 adapter；
- 文档和兼容承诺难以管理。

方向：保留现有导入兼容，但新增明确的 `reader_api`；对 `core` 公共符号建立显式 version/compatibility table，内部 adapter 不再自动承诺稳定。

## 7. Reader 与格式实现审计

### 7.1 原生 XYZ

优点：单/多帧、UTF-8、有限值、元素校验和 provenance 边界清晰。

缺口：

- 额外列全部丢弃，只报告 unsupported。
- 不解析 extXYZ `Properties`、`Lattice`、`pbc`、frame energy/stress/time。
- D/T 映射为 H 后只留下 warning，没有独立同位素字段。
- 多帧只允许相同元素顺序，没有 atom mapping 或 frame-level cell。

执行方向：实现通用 extXYZ schema、typed unknown properties、frame/atom-frame/cell-frame datasets 和 round-trip exporter。

### 7.2 MOL V2000

当前 core reader只读原子坐标，显式丢弃 bonds 和 property records。这不应在用户能力矩阵中标为成熟 MOL 支持。

执行方向：基础路径改用已打包 RDKit，保留原始 block、显式拓扑、形式电荷、同位素、芳香性、立体化学和 sanitize 状态；V2000/V3000 共享模型。

### 7.3 SDF

旧 `read.py` 对 `.sdf` 调用 `MolFromMolFile`，只处理单个分子，无法保存多 record 和 SD properties。新 reader catalog 没有 SDF reader。

执行方向：使用 `SDMolSupplier`，record 级恢复、稳定 record key、SD property 原始字符串与类型化列、智能 conformer 分组、record 顺序 round-trip。

### 7.4 MOL2

旧类型检测可能返回 `mol2`，但 `read_MOL()` 没有对应分支，后续 `mol` 可能未赋值。统一 reader catalog 也没有 MOL2。这是实际功能声明与实现不一致。

执行方向：2.3.0 Wave 3 原生轻量 MOL2 reader，支持 molecule/atom/bond/substructure/charge type；导出为 P1。

### 7.5 PDB/PQR

旧路径只调用 RDKit PDB reader，缺乏 record-level chain/residue/altloc/MODEL/PQR 语义。新 core 无 PDB/PQR reader。

执行方向：原生 fixed-column PDB 与 whitespace PQR reader；MODEL、CONECT、CRYST1；保留 chain/residue/altloc/occupancy/B-factor/charge/radius；不进入 ribbon 范围。

### 7.6 CIF

旧手写 parser通过 strip 和逐行判断解析有限字段，难以可靠处理 CIF quoting、loops、save frames、方言和不确定度。新 Gemmi adapter 是正确方向，但目前可选依赖不在 ZIP。

执行方向：Gemmi 成为基础 wheel，CIF Quick Import 无 spglib 也必须完整；原始 envelope 保留，导出受控替换；文件声明与 spglib 派生结果并存。

### 7.7 POSCAR/CONTCAR

当前基础路径仍依赖旧 parser或可选 ASE。需要原生 reader保留缩放、负体积 scale、元素/计数、Direct/Cartesian、Selective Dynamics、速度块和注释。无扩展名文件必须通过 basename/content sniff。

### 7.8 Cube

当前 core reader在多 dataset、非正交 step vectors、数据量和歧义处理方面较强，是 Wave 1 可直接产品化的基础。

仍需：

- Import Preview 中选择 dataset；
- 用户确认 semantic role 和 unit；
- 语义 preset、默认 isovalue、正负面与 property-on-surface UI；
- 保留核电荷与 dataset ID，而不是只报告 unsupported；
- 大文件进度、取消和 lazy staging。

### 7.9 CJSON

已有 adapter 和 raw envelope，适合 Wave 3 作为轻量交换。需完成 public Reader API conformance、项目级字段映射和明确的部分支持报告。

## 8. 数据模型缺口

2.3.0 的基础格式需要新增或扩展：

- `SourceRecord`、`SourceRevision`；
- `ImportDiagnostic`；
- `ImportRequest`、`ImportPreview`、`ProjectTransaction`；
- `ConformerSet`；
- `FrameProperty`、`AtomFrameProperty`、`CellFrameProperty`；
- 结构原子身份：名称、同位素、形式电荷、序号、标签；
- 生物层级：chain、residue、insertion code、altloc；
- 记录属性表：SDF SD properties；
- typed categorical/string encoding；
- `TopologyRecord` 或带 provenance 的拓扑实体；
- topology source、status、inference parameters 和 confidence；
- `CalculationGroup` 和 source grouping suggestion；
- view registry，明确哪些 Blender object绑定哪些实体/revision。

当前 sidecar拒绝 object array，因此字符串和混合属性不能简单存 NumPy object dtype；必须使用字符串表 + integer codes 或明确的字符串序列类型。

## 9. Blender View 与 UI 审计

### 9.1 当前 UI 缺失

现有 N 面板仍主要是 Build Molecules、Molecular Tools、Crystal Tools 和 Output Tools。新量子功能大多只有函数入口，没有：

- Quick Import；
- Import Preview；
- Project status；
- By Source / By Data 浏览；
- Source revision 和冲突处理；
- ParserReport；
- Dataset/record/dataset-index 选择；
- sidecar 保存、重链接、验证和恢复；
- worker/optional dependency 诊断；
- 质量状态 badge；
- legacy migration wizard。

### 9.2 统一结构视图缺口

`create_structure_view()` 只创建点，不写文件拓扑边，也不自动接入现有球棍 Geometry Nodes。这导致新 QCProject 结构不能自然继承 ChemBlender 的成熟显示和编辑能力。

方向：`StructureViewBuilder` 同时消费 Structure + selected Topology + ViewSettings，创建兼容旧 scaffold属性和新 UUID/revision 的单一对象契约。

### 9.3 Workspace 实现建议

- N 面板保留 Quick Import、项目状态和当前选择。
- 独立 ChemBlender Workspace 使用 bundled workspace asset 或经测试的 on-demand layout。
- Project Browser 使用 `UIList` 的扁平树投影，支持 By Source/By Data、搜索、状态和展开。
- 右侧属性面板显示 entity metadata、quality、view parameters。
- 底部报告区域显示 diagnostic 详情或数值预览。
- Workspace 缺失或用户修改布局时，N 面板仍可完成全部核心操作。

## 10. 具体代码缺陷与近期修复

| 编号 | 问题 | 风险 | 建议波次 |
| --- | --- | --- | --- |
| B-001 | `mol_block_v3000()` 的 bond ID 从 0 开始 | 生成非规范或不可读 V3000 | Wave 1，立即回归测试 |
| B-002 | 旧 `read_MOL()` 对 MOL2 无分支，`mol` 可能未赋值 | 用户导入崩溃 | Wave 3；Wave 0 先改为明确不支持错误 |
| B-003 | `read_MOL()` 不检查 RDKit parser 返回 `None` | 后续 `GetAtoms()` 崩溃 | Wave 1 |
| B-004 | 旧 SDF 只读第一记录 | 数据静默丢失 | Wave 1 |
| B-005 | core MOL reader丢弃键和 property | capability 误导 | Wave 1 |
| B-006 | `create_structure_view()` 不使用拓扑 | 新旧显示体系割裂 | Wave 1 |
| B-007 | CI artifact/ZIP 名硬编码 2.2.0 | 2.3.0 构建/发布失配 | Wave 0 |
| B-008 | release/version scripts 不支持 prerelease | 发布列车无法执行 | Wave 0 探针后修复 |
| B-009 | optional real-file tests 可静默 skip | CI 绿但真实解析未测 | Wave 4，先在 Wave 1 建 job |
| B-010 | `auto_load` 递归 import core | 启动、隔离和插件风险 | Wave 0 |
| B-011 | project link未保存 manifest hash | 文档与实现不一致 | Wave 0 |
| B-012 | cclib CalculationMetadata 未填充 | UI 无法规范展示方法/基组 | 可选后端维护计划 |
| B-013 | manifest tagline仍只描述 molecular/crystal tools | 发行描述过时 | Wave 4 |
| B-014 | changelog Unreleased 未记录大量 main 功能 | 发布审计不完整 | Wave 4，先补历史分类 |
| B-015 | sidecar模型 registry依赖单体 module扫描 | 模型拆分会破坏反序列化 | Wave 0 |
| B-016 | `ParserIssue` 信息不足 | 质量 UX 无法实现 | Wave 0 |
| B-017 | reader descriptor没有 execution mode/availability/API version | 插件和缺依赖 UX 不稳定 | Wave 0 |
| B-018 | network/file permission描述未覆盖项目 sidecar | manifest 权限与真实行为偏差 | Wave 4 |

## 11. 安全与完整性

已有 sidecar避免 pickle、约束路径和 hash，是强项。后续必须保持：

- Worker Reader 只返回 canonical JSON 和受限相对 artifact。
- Extension Reader不得直接修改 QCProject 或 Blender scene。
- 拖放与批量导入先预检，确认后原子提交。
- 外部程序仍使用固定 operation 和 `shell=False`。
- 原始 envelope/输入文件字节不能被未审查模板执行。
- 不将文件内容拼接为 Python 表达式或命令。
- 导出路径、sidecar locator 和 plugin artifact都做目录逃逸检查。

## 12. 性能判断

现有 lazy trajectory、Grid LOD 和 OpenVDB可复用，但需要把性能转成发布指标：

- enable ≤2 s；
- 首次反馈 ≤0.5 s；
- 普通 XYZ/MOL/CIF view ≤3 s；
- 128³ Cube view ≤10 s；
- cached frame ≤100 ms；
- browser filter ≤200 ms；
- >1 s 任务必须有进度、取消且不长期阻塞 UI。

注意：50k 原子级别的全量键推断不能使用 O(N²)；旧 `add_BONDS` 已使用空间格子，但需要 PBC、金属、配位上限和 provenance。SDF 10k/100k records 需要索引、渐进预览和 lazy property table，不能一次为所有记录创建 Blender object。

## 13. 参考项目的继续使用方向

| 项目 | 2.3.0 参考方向 | 不应直接复制的部分 |
| --- | --- | --- |
| RDKit | MOL/SDF/SMILES、拓扑、stereo、writer | 不暴露 RDKit Mol 作为项目权威模型 |
| Gemmi | CIF parser、raw block/loop、小分子晶体 | 不让 Gemmi对象进入 Blender adapter |
| xyzrender | reader sniff、格式测试、Cube/显示参数 | 2D renderer不是 Blender后端 |
| Molecular Blender | Molden/Cube/轨道和自适应等值面 | 不增加基础 worker范围 |
| Beautiful Atoms | ASE/Blender桥、体数据着色、PBC | 不用隐藏 Mesh 保存权威体数据 |
| Molecular Nodes | session、轨迹、选择和 workspace经验 | 不扩大到完整结构生物学产品 |
| cclib | 输出 parser 和 capability matrix | 不把可选依赖变成基础格式门 |
| Avogadro/CJSON | 轻量项目交换和 UI工作流 | 大数组仍留 sidecar |

## 14. 推荐执行顺序

```text
Wave 0  平台骨架
  → 模型模块化、SourceRevision、session project、Import Preview、Reader API、显式注册、最小 UI

Wave 1  小分子与场
  → extXYZ、RDKit MOL/SDF/SMILES、拓扑、统一 StructureView、Cube UX

Wave 2  晶体
  → Gemmi wheel/CIF、原生 POSCAR/CONTCAR、晶体视图、受控导出、spglib可选

Wave 3  其余格式与生态
  → MOL2、PDB/PQR、CJSON、示例第三方 reader、conformance kit

Wave 4  迁移与发布
  → legacy migration、旧 UI桥、CI/CD、性能、文档、预发布/正式发布
```

任何 Wave 都必须完成真实 fixture→reader→project→UI→Blender view→save/reopen→export（适用时）的纵向闭环，不能只提交模型或按钮。
