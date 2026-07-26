# 2.3.0 格式成熟度矩阵

## 成熟度定义

| 等级 | 含义 |
| --- | --- |
| F0 Detect | 可靠识别，能说明 reader、依赖和失败原因 |
| F1 Structure | 原子、坐标、晶胞和基本身份 |
| F2 Chemistry | 键、键级、形式电荷、同位素、占位或层级语义 |
| F3 Results | 轨迹、属性、网格、光谱或计算结果 |
| F4 Workflow | Quick Import、Project Browser、默认视图、保存恢复和质量报告 |
| F5 Round-trip | 在明确损失边界内导出并通过往返验证 |

## 2.3.0 承诺

| 格式 | 当前快照估计 | 2.3.0 目标 | 基础依赖 | 主要验证 |
| --- | --- | --- | --- | --- |
| XYZ | F1/F3 partial | F5 | 原生 | 单帧、多帧、D/T、错误恢复、导出 |
| extXYZ | F0/F1 partial via ASE | F5 | 原生 | Properties S/I/R/L、Lattice、pbc、frame/atom properties |
| MOL V2000 | F1，core丢拓扑 | F5 | RDKit | charge/isotope/stereo/aromaticity、writer |
| MOL V3000 | exporter存在但 bond ID bug | F5 | RDKit | V3000 reader/writer、large counts、collections降级报告 |
| SDF | 旧路径只读一条 | F5 | RDKit | multi-record、record recovery、SD fields、order round-trip |
| SMILES | 旧路径可生成结构 | F4/F5文本 | RDKit | canonical/isomeric、3D parameters、source text |
| MOL2 | 未统一支持 | F4，export P1 | 原生 | atom/bond/substructure/charge type |
| PDB | 旧 RDKit浅支持 | F4，export P1 | 原生 | ATOM/HETATM/MODEL/CONECT/CRYST1/altloc |
| PQR | 未支持 | F4，export P1 | 原生 | charge/radius、optional chain、identity |
| CIF | Gemmi adapter可选，旧 parser基础 | F4/F5 controlled | Gemmi bundled | loops/occupancy/Uij/raw envelope/controlled export |
| POSCAR/CONTCAR | 旧 parser/ASE optional | F5 | 原生 | scale、Direct/Cartesian、Selective Dynamics、basename sniff |
| Cube | F2/F3强，缺 UI | F4 | 原生 + Blender OpenVDB | multi dataset、oblique grid、semantic confirmation、VDB/surface |
| CJSON | adapter存在 | F5 lightweight | 原生 | structure/topology/trajectory/property envelope round-trip |

## “支持”显示规则

用户 UI 和文档不得只显示布尔 `Supported`。每个 reader必须列出：

- execution mode；
- dependency availability；
- capability maturity；
- tested fixture families；
- import recovery mode；
- exporter and loss policy；
- known limits；
- reader/plugin/API version。

## 格式优先级

```text
Wave 1: XYZ/extXYZ, MOL/SDF/SMILES, Cube
Wave 2: CIF, POSCAR/CONTCAR
Wave 3: MOL2, PDB/PQR, CJSON
```
