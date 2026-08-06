# 格式与支持范围

这页回答两个不同问题：文件格式本身可能装什么数据，以及 ChemBlender 2.4.0 实际读取、显示、处理和导出什么。不要把“格式规范允许”当成“插件已支持”。

事实源是现有的[格式指南](../formats.md)、生成的 [format-capabilities.json](../format-capabilities.json)和 [dependencies.json](../dependencies.json)。生成清单对 import 使用 `supported` / `partial` capability，对 exporter 使用 F0–F5 maturity；它没有单独生成一个 import F 数字，本页不会补造。

## 成熟度怎么读

| 级别 | 含义 |
| --- | --- |
| F0 | 能识别来源并解释 reader/dependency/export 不可用原因 |
| F1 | 保留 Structure identity、coordinates 和适用的 cell |
| F2 | 再保留 topology、charge、occupancy 或 hierarchy 等语义 |
| F3 | 再保留 frames、properties 或 Grid3D 结果 |
| F4 | 完成 Quick Import、Project Browser、View、保存/重开和 diagnostics 工作流 |
| F5 | 在明确 loss policy 下完成 export 与 semantic round-trip |

F5 不是“字节无损”。只要目标格式不能表示某项来源语义，Project Browser 仍会显示 loss preview 并要求确认。

## 基础格式一览

| 格式 | 文件可能提供的数据 | ChemBlender 2.4.0 导入范围 | View 与处理 | 导出 / 成熟度 | 依赖 | 已知边界或损失 | 样例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| XYZ | 元素、笛卡尔坐标、comment；重复 block 可表示 frames | Structure、trajectory | Structure View、frame playback；可另行提议 topology | Project Browser XYZ，F4；只写一个 Structure 的 coordinates | built-in | 不保存 topology、cell/PBC、typed property；多帧应选 extXYZ | [water.xyz](../../../examples/user-workflows/inputs/xyz/water.xyz) |
| extXYZ | XYZ frames、`Properties` schema、per-atom/per-frame values、`Lattice`、PBC、metadata | Structure、trajectory、typed properties、validity masks、cell/PBC | Structure/trajectory View，属性可按支持范围映射；revision 仍受来源约束 | Project Browser extXYZ，F5 | built-in | 不受支持的 metadata 或无法表示的缺失值按 preview 归一化/省略 | [carbon-trajectory.extxyz](../../../examples/user-workflows/inputs/extxyz/carbon-trajectory.extxyz) |
| MOL V2000/V3000 | atoms、bonds、2D/3D coordinates、formal charge、isotope、stereo 和 CT record | Structure、Topology、AtomicIdentity、MolecularRecord；RDKit sanitize 结果单独记录 | Structure View；可做 derived scientific edit 或切换 topology | Project Browser MOL，F5 | RDKit；Windows Release 随附 | 目标版本限制、sanitize/representability、未知 CT 字段和不支持的 record 内容会进入 preview | [V2000](../../../examples/user-workflows/inputs/mol/water-v2000.mol)、[V3000](../../../examples/user-workflows/inputs/mol/water-v3000.mol) |
| SDF | 多个 MOL record、每条 record property、2D/3D conformer；也可能有坏记录 | 多 Structure、Topology、MolecularRecord；record property 为 partial support，坏记录按 validation mode 隔离 | Structure/record/conformer 检阅，可保留独立 records 或经确认归组 | Project Browser SDF，F5 | RDKit；Windows Release 随附 | malformed record、ordered property 和 conformer 归组必须看 Diagnostics；目标不表示的 property 会预览 | [mixed-properties.sdf](../../../examples/user-workflows/inputs/sdf/mixed-properties.sdf) |
| SMILES | molecular graph、charge、isotope、atom/bond stereo；通常没有 3D coordinates | AtomicIdentity、Topology、MolecularRecord，并确定性派生 3D Structure | Structure View；派生坐标不是源文件测量值 | Project Browser SMILES，F5 | RDKit；Windows Release 随附 | 导出省略 coordinates、conformer、title、properties，并可能 canonicalize atom order；非 isomeric 模式还会省略 stereo/isotope | [ethanol.smi](../../../examples/user-workflows/inputs/smiles/ethanol.smi) |
| CIF | cell、fractional sites、occupancy、symmetry、ADP、多个 data block 和额外 tags | Structure、crystal/site metadata、CIFEnvelope | 周期 Structure View；查看 declared/derived/comparison symmetry，可创建 standardized View | Project Browser CIF，F5；`Preserve` 或 `Normalized` | Gemmi；Windows Release 随附 | normalized 输出可能改变 block/tags/排版；occupancy、ADP 或 symmetry 的 replace/add/omit 会逐项预览 | [nacl.cif](../../../examples/user-workflows/inputs/cif/nacl.cif) |
| POSCAR / CONTCAR | lattice、species/count、Direct/Cartesian coordinates、Selective Dynamics、ion/lattice velocity | periodic Structure、crystal、Selective Dynamics 和受支持 velocity property | 周期 Structure View；约束可视化，scientific edit 生成 derived Structure | Project Browser POSCAR/CONTCAR，F5 | built-in | POSCAR 不表示一般 occupancy、ADP、声明 symmetry；scale、coordinate、constraint 和 velocity policy 必须核对 | [si.POSCAR](../../../examples/user-workflows/inputs/poscar/si.POSCAR)、[velocities.CONTCAR](../../../examples/user-workflows/inputs/poscar/velocities.CONTCAR) |
| MOL2 | 多 molecule、atom type、bond type/order、partial charge、substructure 与未知 sections | 多 Structure、Topology、atomic property、Tripos metadata、substructure | Structure View；可按 substructure color/select，切换或派生 topology | Project Browser normalized MOL2，F5 | built-in | 未知 sections、省略字段和不完整 Tripos semantics 需要确认；normalized export 不复刻原排版 | [substructure.mol2](../../../examples/user-workflows/inputs/mol2/substructure.mol2) |
| PDB | atom identity、chain/residue、MODEL、altloc/occupancy、B-factor、CONECT、CRYST1 及大量 record | Structure、BiologicalHierarchy；原子身份一致时形成 multi-model trajectory；atomic properties；crystal/topology 为 partial | Biological default View、层级选择、兼容 MODEL playback | Project Browser PDB，F5 | built-in | unsupported records、alternate-location 决策、partial topology/crystal 和 normalized columns 会预览；MODEL 原子身份不一致时拆为独立 Structure | [model-trajectory.pdb](../../../examples/user-workflows/inputs/pdb/model-trajectory.pdb)、[multimodel.pdb](../../../examples/user-workflows/inputs/pdb/multimodel.pdb) |
| PQR | PDB 风格 identity/hierarchy、coordinates、partial charge、radius；通常没有标准 bond record | Structure、AtomicIdentity、BiologicalHierarchy、charge/radius AtomicProperty；不推断 topology | Biological View 和层级选择；charge/radius 保留为属性 | Project Browser PQR，F5 | built-in | 导出要求每个 atom 有可表示 charge/radius；其他 PDB record、topology 和 annotation 不在 PQR 表达范围 | [with-chain.pqr](../../../examples/user-workflows/inputs/pqr/with-chain.pqr) |
| Cube | atom coordinates、grid origin/axes、voxel values、可选多个 dataset；unit/semantic 常依赖上下文 | Structure、Grid3D、受支持 atomic property、多 dataset values | Structure、Volume、Signed Surface、property surface；Ambiguous 时先 Resolve Grid Semantics | Project Browser Cube，F5；一次导出一个明确 dataset | built-in | semantic round-trip，不承诺源字节；多 dataset 必须选 index，数值格式和不表示的 metadata 会变化 | [two-datasets.cube](../../../examples/user-workflows/inputs/cube/two-datasets.cube) |
| CJSON | 轻量 JSON envelope，可含 structure、bonds、properties、trajectory、vibration、spectrum、excited state、grid/orbital | Structure、Topology、AtomicIdentity/Property；部分 result types 为 partial；完整 CJSONEnvelope 保留 | 对已导入 Structure/Grid/property 使用现有 View；没有每种 envelope 的专用面板 | core controlled-envelope exporter 为 F5；Project Browser 没有通用 CJSON writer | built-in | UI 不提供通用写出；partial result 字段不能因 envelope 保留而宣称全部已规范化为科学实体 | [water-results.cjson](../../../examples/user-workflows/inputs/cjson/water-results.cjson) |
| QCSchema | Molecule、AtomicResult、model、driver、properties、return_result、provenance 和 native/raw fields | Structure；CalculationRecord、energy/gradient 为 partial；完整 source JSON 保留为 QCSchemaEnvelope | Structure View；受支持 gradient 可用于现有结果展示，其他 raw 字段只在 envelope 中 | core source-envelope exporter 为 F5；Project Browser 没有通用 QCSchema writer | built-in | UI 不编辑或重建任意 QCSchema result；导入到实体的仅是明确支持字段，原 JSON envelope 仍是其余字段来源 | [atomic-result.json](../../../examples/user-workflows/inputs/qcschema/atomic-result.json) |

## Legacy `.blend` 不是交换格式

ChemBlender 2.1/2.2 `.blend` 保存的是旧对象与属性，不走 reader maturity 矩阵。当前支持范围是 `Legacy Migration` 的显式 detect、preview、diagnostics、migration、backup 和 save/reopen；没有 F0–F5 exporter，也没有自动 unmigrate。练习文件是 [chemblender-2.1-molecule.blend](../../../examples/user-workflows/inputs/legacy/chemblender-2.1-molecule.blend)。流程见[项目保存与迁移](05-project-lifecycle.md)。

## 可选 runtime 不属于基础格式成功条件

cclib、IOData、ASE 和 pymatgen adapter 可以在单独 runtime 可用时增加计算输出、wavefunction、periodic structure 或 VASP grid/electronic data。选择 reader 时才检查真实 availability。这里没有为它们放入基础教程样例，也不声称当前机器已安装；缺失时应显示具体 dependency reason，而不是静默 fallback。

## 选择格式的实用规则

- 只交换一个几何结构且接受无 topology/cell 时用 XYZ；有 frames、cell/PBC 或 typed properties 时用 extXYZ。
- 分子 graph、stereo、records 或 properties 优先用 MOL/SDF；只交换 graph 表达式时才用 SMILES。
- 周期结构在 CIF 与 POSCAR 之间选择时，先看是否需要 symmetry/occupancy/ADP，还是 VASP 的 scale、Selective Dynamics/velocity。
- 生物 hierarchy 用 PDB；以 charge/radius 为核心时用 PQR。不要期待 PQR 自带 topology。
- Grid3D 用 Cube，并在多 dataset 文件中明确选择 index。
- CJSON/QCSchema 用于保留对应 envelope；当前普通 UI 导出请选择已列入 Project Browser 的目标格式。

返回[工作流总览](README.md)，或直接进入[导入](01-import.md)和[导出](04-export.md)。
