# 波函数、网格与表面开发计划

## 范围

从波函数或体数据得到可验证的 `Grid3D`、标量场和表面，覆盖 MO、电子密度、自旋密度、ESP 与 NCI 的数据和显示边界。

## 非目标

- Cube 只是一种容器，不作为物理语义或 UI 功能名称。
- 不用 face normal 推断轨道正负相位。
- 不把数值后端打入 Blender Extension；worker、缓存和 UI 必须保持解耦。

## 优先级

| 优先级 | 内容 | 验证重点 |
| --- | --- | --- |
| P0 | 多 dataset Cube、非正交 step vectors、`GridSemantic`、`SurfaceStyle`、正负相位、field-on-surface | 网格坐标、单位与 dataset 不丢失；ESP on density 与 ESP 等值面不混淆 |
| P1 | 已完成 IOData basis/MO/1-RDM 与 GBasis MO/density/spin-density/ESP 规则网格；继续导数、field-on-surface、适应性 MO 网格和 mesh fallback | 解析 convention、开放壳层、电子数/轨道 norm、数值误差、峰值内存和时间 |
| P2 | CuGBasis、导数/Hessian 场、GPU 加速与高级拓扑量 | P1 后端已成为瓶颈且目标平台明确 |

## 依赖关系

依赖 `Grid3D`、单位、轨道数据和 provenance 契约。Blender Volume、Mesh 和 Material 只消费派生结果，不能反向定义网格存储。

### GBasis 0.1.0 的边界

PyPI 安装名固定为 `qc-gbasis==0.1.0`，Python import 名仍为 `gbasis`；撤回的旧 `gbasis` distribution 不得安装。GBasis 不是 SCF/DFT solver、完整文件 parser 或 Blender renderer，而是把 normalized Gaussian basis、MO coefficients 和 one-RDM 求值到任意空间点的外部 worker 数值内核。

| 输入 | GBasis 输出 | ChemBlender 消费方式 |
| --- | --- | --- |
| `BasisSet + OrbitalSet + points` | AO/MO values | `Grid3D`、正负相位等值面、按需 HOMO/LUMO/SOMO |
| `BasisSet + DensityMatrix + points` | electron/spin density | density volume、surface 与切片 |
| density matrix、核坐标/电荷、points | ESP | density surface 顶点着色，或独立 grid 分析 |
| density derivatives | gradient、Hessian、Laplacian、kinetic-energy density | 后续 RDG、拓扑与局部分析 |
| Gaussian integrals | overlap、kinetic、nuclear attraction、ERI 等 | P2 轨道匹配/跟踪，不进入当前可视化 MVP |

当前规则 affine grid 已直接用 NumPy 生成采样点，因而不为已有能力增加 `qc-grid`。局部包围盒、分辨率 presets、chunking、缓存和自适应采样属于 worker/storage 后续任务；只有真实性能基准证明需要时才扩展。

## 交付物

- Cube 与波函数字段映射。
- MO/density/spin density/ESP/NCI 的 semantic role 表。
- 网格求值后端基准 fixture。
- 正负相位表面和 field-on-surface 的中间数据契约。
- OpenVDB 与 marching-cubes fallback 的一致性检查。

## 验收标准

- 非正交网格按三个 step vectors 正确定位。
- 一个输入可保存多个 dataset，不静默保留第一项。
- unrestricted 轨道保留 alpha/beta；generalized 轨道不强行压成两通道。
- 密度面顶点采样 ESP 的结果与直接网格插值基准一致。
- 数值后端不 import `bpy`，相同输入可在普通 CPython 复现。

## 参考仓库触发条件

- Molden 轨道选择和适应性网格进入实现时审阅 Molecular Blender。
- 体数据表面着色进入实现时审阅 Beautiful Atoms。
- GBasis 规则网格后端已固定 v0.1.0；原子中心积分或自适应采样出现明确验收需求时再固定 Grid。
- ORBKIT 当前不拉取；只有 GBasis 缺失的独有能力和可维护构建链同时得到证据时才重新比较。
- GPU 需求得到性能瓶颈证据后再审阅 CuGBasis。
