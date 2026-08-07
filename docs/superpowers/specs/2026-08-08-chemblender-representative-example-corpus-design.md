# ChemBlender 可追溯代表性案例库设计

- 日期：2026-08-08
- 状态：已按用户“所有选择采用推荐项并持续行动”的约定批准
- 分支：`codex/representative-example-corpus`

## 目标

现有 `examples/user-workflows/inputs/` 文件首先是解析器和 UI 工作流合同。
它们很小并不等于坐标精度不足：一个小分子的元素、键和双精度坐标本来就只需数
KB。真正不足的是演示规模，例如两帧轨迹、`2 × 2 × 2` Cube 网格和两个残基的
层级无法证明播放、等值面、生物结构选择和较复杂的格式语义。

本任务建立两层案例库：保留现有快速合同样本，再为每个基础格式增加来源明确、
规模适中、能展示该格式主要价值的 representative 样本。案例必须可离线使用、可由
用户在 UI 中重走、可被自动测试，并且不能把格式规范允许的字段误写成插件已支持。

## 不采用的方案

1. **直接替换合同样本**：真实感更强，但会扩大基础测试、破坏现有字节合同，且让
   malformed/边界条件难以稳定复现。
2. **完整数据仓库作为 submodule**：上游历史清楚，但下载、离线使用和版本维护成本
   远高于本任务实际需要。只有无法取得可再分发单文件时才重新评估。

采用的方案是在现有格式目录中并列保存 `contract` 与 `representative` 文件，由
manifest 明确角色，不移动原路径。

## 目录与元数据

数据仍按 `inputs/<family>/` 排列。每个数据文件旁必须有同名 Markdown，例如：

```text
inputs/pdb/1d3z-ubiquitin-nmr.pdb
inputs/pdb/1d3z-ubiquitin-nmr.md
```

`manifest.json` 升级为 schema 2。每条记录至少包含：

| 字段 | 内容 |
| --- | --- |
| `role` | `contract` 或 `representative` |
| `source_platform` / `source_id` | 数据平台和稳定标识符 |
| `source_url` / `retrieved_at` | 原始下载地址和检索日期 |
| `license` / `license_url` | 可再分发依据；不明确则不得提交 |
| `derivation` | 原样下载、截取、转换或计算步骤及工具版本 |
| `source_sha256` | 下载原件哈希；原样提交时与文件哈希相同 |
| `sha256` / `bytes` | 仓库内 exact bytes 合同 |
| `metrics` | 原子、键、record、frame、site、grid 等格式相关指标 |
| `specifications` | 格式规范标题、版本和 URL |
| `documentation` | 相邻 Markdown 路径 |

原始下载进入忽略目录 `.agents/cache/representative-examples/`。仓库只提交选定原件、
确定性派生文件、相邻说明和可复现脚本；不提交临时完整数据集。

## 来源矩阵

候选必须经过许可证、内容和插件实测后才转为最终样本。

| 格式 | 推荐实例或派生源 | 主要证明内容 | 规范与来源 |
| --- | --- | --- | --- |
| XYZ | 从 wwPDB Chemical Component Dictionary 的 `TA1` ideal coordinates 确定性导出的 paclitaxel | 113 个原子与三维坐标；说明文本小不等于低精度 | [RCSB PDB TA1](https://www.rcsb.org/ligand/TA1)、[PDB archive CC0](https://www.rcsb.org/pages/policies) |
| extXYZ | rMD17 aspirin 的固定 32 帧子集 | 真实 DFT 轨迹、energy、force、`Properties` | [rMD17, CC0](https://figshare.com/articles/dataset/Revised_MD17_dataset_rMD17_/12672038)、[libAtoms extxyz](https://github.com/libAtoms/extxyz) |
| MOL V2000 | wwPDB CCD `AIN` aspirin ideal SDF record | 21 个原子、21 个键、3D ideal coordinates | [RCSB PDB AIN](https://www.rcsb.org/ligand/AIN)、BIOVIA CTfile 规范 |
| MOL V3000 | wwPDB CCD `TA1` 经固定 RDKit 版本写出 | 113 个原子、119 个键、V3000 CTAB 与立体化学 | [RCSB PDB TA1](https://www.rcsb.org/ligand/TA1)、BIOVIA CTfile 规范 |
| SDF | wwPDB CCD `AIN`、`CFF`、`TA1` ideal SDF 的确定性组合 | 3 records、record property、规模差异 | [RCSB ligand downloads](https://www.rcsb.org/downloads/ligands) |
| SMILES | 由上述三个 CC0 CCD records 确定性写出的 isomeric SMILES | graph、芳香性、charge、stereo；明确无坐标 | [Daylight SMILES](https://www.daylight.com/dayhtml/doc/theory/) |
| CIF | COD 中含真实 cell、symmetry、occupancy/disorder 的条目 | 实验晶体数据、site 和 CIF envelope | [COD, CC0](https://www.crystallography.net/cod/new.html)、[IUCr CIF](https://www.iucr.org/resources/cif) |
| POSCAR | COD 晶体经插件 loss preview 后规范化导出 | lattice、species、Direct coordinates 与跨格式损失 | [VASP POSCAR](https://vasp.at/wiki/POSCAR) |
| CONTCAR | COD diamond 的确定性 `2 × 2 × 2` supercell，并按 VASP 规范加入零初速度 | 64 sites、Direct coordinates 与 ion velocity；明确不是 DFT relaxation 输出 | [VASP POSCAR](https://vasp.at/wiki/POSCAR)、[CONTCAR](https://vasp.at/wiki/CONTCAR) |
| MOL2 | Open Babel 官方仓库固定 commit 的 `5sun_protein.mol2` | 6185 atoms、6248 bonds、390 substructures 与扩展 section | [Open Babel source](https://github.com/openbabel/openbabel)、Tripos MOL2 公开规范链接及本插件支持子集 |
| PDB | RCSB PDB `1D3Z` ubiquitin NMR ensemble | 多 MODEL、chain/residue、B-factor、真实生物层级 | [RCSB 1D3Z](https://www.rcsb.org/structure/1D3Z)、[wwPDB 3.30](https://www.wwpdb.org/documentation/file-format) |
| PQR | APBS 官方仓库的蛋白或蛋白-RNA示例 | 真实 hierarchy、每原子 charge/radius | [APBS PQR](https://apbs.readthedocs.io/en/latest/formats/pqr.html) |
| Cube | 按 hydrogenic 1s LCAO 公式生成 H2 `64³` 电子密度 | 可复算的 Grid3D、体素分辨率和等值面；明确不是 ab initio 结果 | [h5cube Cube 说明](https://h5cube-spec.readthedocs.io/en/latest/cubeformat.html)；公式与参数随文件记录 |
| CJSON | Avogadro 官方 BSD-3-Clause 仓库固定 commit 的 phthalocyanine ligand | structure、bonds 和 CJSON envelope | [Avogadro CJSON](https://avogadro.cc/docs/getting-started/saving-files.html) |
| QCSchema | MolSSI 官方 AtomicResult 示例，或已存在 PySCF 计算的合法 v2 文档 | Molecule、model、driver、energy/gradient、provenance | [MolSSI QCSchema](https://molssi.org/software/qcschema-2/)、[AtomicResult v2](https://molssi.github.io/QCElemental/dev/api/qcelemental.models.v2.AtomicResult.html) |
| legacy `.blend` | 现有 2.1 hash-locked fixture | 迁移边界，不伪装成交换格式 | Blender 文件兼容说明和仓库生成记录 |

同一 wwPDB CCD 或 COD 原件可派生多个格式，以便用户比较语义保留与损失；每个派生文件
仍须单独记录命令、工具版本、输入哈希和输出哈希。

## 相邻文档合同

每份同名 Markdown 使用相同结构，但内容按文件实际字段填写：

1. 这个文件是什么、为什么选择它；
2. 来源平台、稳定 ID、原作者/数据集、许可证和检索日期；
3. 原子/键/帧/网格等规模，及其是否构成“分辨率”；
4. 文件字段逐项说明，并给出该实例中的实际值或范围；
5. 格式规范允许范围与 ChemBlender 2.4.0 实际支持范围；
6. UI 导入、展示、导出路径，成功判据和已知损失；
7. 可复制的 Blender MCP Agent 提示词，只使用公开 UI/Operator 边界；
8. SHA-256、bytes、解析结果、Blender 验证状态和参考链接。

合同样本也获得相邻文档，但不会被包装成真实科研数据；它们明确标记为 repository
fixture 或 synthetic，并解释其刻意缩小的测试目的。

## 获取与失败策略

- 只接受 HTTPS 官方平台、官方项目仓库或有稳定 DOI 的公开数据。
- 下载必须先保存原始 bytes、计算 SHA-256、确认许可证，再做转换。
- HTTP 失败、内容漂移、许可证不明确或规范与样本不匹配时，候选失败关闭；改用下一
  个权威来源，不能用无出处文件填位。
- 不添加运行时依赖。只使用标准库、仓库现有代码、Blender bundled NumPy，以及
  manifest 已有的 RDKit/Gemmi。当前机器的本地 PySCF 因缺少 SciPy 无法导入，不能把
  未运行的计算写成证据，也不能未经授权安装依赖；Cube 因而使用可审计的解析模型。
- GitHub 仓库只按固定 commit 读取必要文件。没有必要时不添加 submodule。
- 单文件目标低于 50 MiB，硬上限 100 MiB；整套新增输入优先控制在约 15 MiB 内。

## 验证设计

### 静态合同

- manifest 路径有序且唯一，数据、文档、bytes、SHA-256 双向一致；
- 每条记录都有来源、许可证、规范和角色；
- representative 指标达到格式相关门槛，而不是统一用文件大小判断：轨迹至少 20 帧，
  Cube 每轴至少 48，PDB 至少 5 个兼容 MODEL 或一个有真实 hierarchy 的结构，SDF
  至少 3 records；
- 所有本地 Markdown 链接可解析，远程引用只使用 HTTPS；
- 文档不得声称插件未实现的 capability。

### 解析与语义

先用对应 built-in/RDKit/Gemmi reader 断言实体数量、结构身份、坐标、frame、property、
cell、hierarchy、charge/radius 和 Grid3D dimensions。转换文件要比较源/目标可表示语义，
而不是只断言“不抛异常”。

### Blender 5.1

在新临时 profile 安装当前精确 ZIP，通过 `bpy.ops.chemblender.*` 和公开 Scene RNA 执行：

1. 小分子多格式导入与 normalized export；
2. extXYZ trajectory playback；
3. PDB/PQR biological hierarchy；
4. CIF/POSCAR periodic View；
5. Cube Volume/Signed Surface；
6. 保存 `.blend` 与配套 `.cbq`，冷启动重开并核对实体、View、外部路径和文件大小。

选定结果保存到 `examples/user-workflows/outputs/representative/`，每个 `.blend` 和 sidecar
继续遵守小于 50 MiB、绝不超过 100 MiB 的限制。自动流程不能替代发布前人工插件使用
体验检阅。

## 完成条件

所有基础格式均有清楚说明的合同样本和代表性样本，或文档明确证明该格式的有效实例
天然很小且无需人为膨胀；所有代表性文件都有合法来源、规范、相邻文档和确定性哈希；
自动测试及 Blender UI 等价流程完成，保存结果冷启动重开通过，发现的产品缺陷修复并
复测，最终仅本地提交并合并回 `main`。
