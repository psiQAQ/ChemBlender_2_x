# 波函数、网格与表面开发计划

## 范围

从波函数或体数据得到可验证的 `Grid3D`、标量场和表面，覆盖 MO、电子密度、自旋密度、ESP 与 NCI 的数据和显示边界。

## 非目标

- Cube 只是一种容器，不作为物理语义或 UI 功能名称。
- 不用 face normal 推断轨道正负相位。
- 没有数值和性能基准前不预选 ORBKIT、GBasis/Grid 或 GPU 后端。

## 优先级

| 优先级 | 内容 | 验证重点 |
| --- | --- | --- |
| P0 | 多 dataset Cube、非正交 step vectors、`GridSemantic`、`SurfaceStyle`、正负相位、field-on-surface | 网格坐标、单位与 dataset 不丢失；ESP on density 与 ESP 等值面不混淆 |
| P1 | IOData basis/MO adapter；比较 IOData+GBasis/Grid 与 ORBKIT；适应性 MO 网格和 mesh fallback | 解析 convention、开放壳层、数值误差、峰值内存和时间 |
| P2 | CuGBasis、导数/Hessian 场、GPU 加速与高级拓扑量 | P1 后端已成为瓶颈且目标平台明确 |

## 依赖关系

依赖 `Grid3D`、单位、轨道数据和 provenance 契约。Blender Volume、Mesh 和 Material 只消费派生结果，不能反向定义网格存储。

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
- 后端基准启动时才固定 ORBKIT 或 GBasis/Grid commit；GPU 需求得到证据后再审阅 CuGBasis。

