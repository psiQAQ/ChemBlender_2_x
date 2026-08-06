# ChemBlender 用户流程样例

这里保存与 `docs/user/workflows/` 配套的小型、可复现样例。

- `inputs/` 是不可变输入。文档操作不得覆盖这些文件。
- `outputs/` 由 Blender 5.1 实测流程生成；只有通过冷启动重开、hash 和大小检查的代表性结果才会纳入仓库。
- `scripts/` 保存通过 ChemBlender 公开 Operator 复现 UI 流程的脚本。
- `manifest.json` 记录每个输入的来源、运行时依赖、预期数据、实测字节数和 SHA-256。

从 `tests/fixtures/` 复制的文件是独立快照，不会在运行时引用测试目录。`ethanol.smi` 是本地生成的最小 SMILES。当前全部输入远小于 50 MiB；新文件应尽量保持在 50 MiB 以内，任何文件都不得超过 100 MiB。

## 样例选择

| 格式族 | 样例 | 主要用途 |
| --- | --- | --- |
| XYZ / extXYZ | `water.xyz`、`carbon-trajectory.extxyz` | 单结构、多帧、cell/PBC |
| MOL / SDF / SMILES | 两版 water MOL、混合属性 SDF、ethanol SMILES | RDKit 分子记录、属性与 3D 派生 |
| CIF / POSCAR | NaCl、Si、含速度 CONTCAR | 晶体、周期边界与导出损失检查 |
| MOL2 / PDB / PQR | substructure、multi-model、with-chain | 拓扑、层级、charge/radius |
| Cube | two-datasets | Structure、Grid3D 与多 dataset 选择 |
| CJSON / QCSchema | water results、AtomicResult | 计算结果 envelope 与可支持属性 |
| Legacy | ChemBlender 2.1 molecule | 显式迁移、诊断与另存 |

操作入口见 [`docs/user/workflows/README.md`](../../docs/user/workflows/README.md)。
