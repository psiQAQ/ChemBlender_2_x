# 2.3.0 四级开发优先级

## Priority 1：官方 ZIP 安装后直接可用

边界：项目自身代码、Blender 自带库、已批准基础 wheels。用户不配置外部 Python 或程序。

| 能力 | 2.3.0 工作 |
| --- | --- |
| 分子结构 | XYZ/extXYZ、MOL/SDF/SMILES、MOL2、PDB/PQR |
| 晶体结构 | Gemmi CIF、原生 POSCAR/CONTCAR |
| 场数据 | Cube multi-dataset、VDB、signed/property surfaces |
| 交换 | CJSON |
| 平台 | Session Project、SourceRevision、Import Preview、Project Browser、Reader API |
| 视图 | 统一 StructureView、拓扑、轨迹、晶体、网格、属性 |

准入：必须有真实 fixture、UI闭环、sidecar保存恢复、质量报告和适用导出。

## Priority 2：小型低成本集成

边界：单wheel压缩目标≤10 MB、解压≤30 MB，全部新增wheel压缩目标≤20 MB；有固定版本/URL/SHA/license和故障隔离。

2.3.0 已批准：Gemmi。其他组件需要单独 ADR 和真实用户场景，不能只因体积小加入。

## Priority 3：外部 Python worker

边界：与 Blender Python 3.13/NumPy ABI或依赖栈不兼容，或不适合放入基础包。

- cclib
- IOData
- GBasis
- ASE
- pymatgen
- phonopy

2.3.0 保持现有接口和integration CI，不作为基础格式门。后续 UI 可以显示可用状态和配置入口，但不得让缺失 worker破坏基础项目。

## Priority 4：大型独立工具和服务

- PyProcar/VTK/PyVista
- Multiwfn
- critic2
- QCArchive
- AiiDA
- NOMAD
- GPU/CuGBasis
- 远程 worker/provenance federation

采用文件交换、固定 operation或只读 connector。只有真实程序、公开稳定 fixture、许可证、部署和维护方案齐全后才能升级优先级。

## 决策规则

新需求进入路线图前回答：

1. 是否能只读取已有数据而不计算？
2. 是否能使用 Priority 1已有组件实现？
3. 新依赖是否给基础用户带来明确且可测价值？
4. 是否有真实文件、许可证和长期维护人？
5. 是否能失败隔离和降级？
6. 是否会削弱跨格式统一语义？

任一关键问题无答案时，保持可选或延后。
