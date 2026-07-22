# 量子化学可视化路线图

## 推进规则

- 同一时间只激活一个开发主题。
- 每个主题先完成 P0 验收，再根据真实输入和使用场景选择 P1。
- 候选项目只提供架构或实现参考；依赖与 submodule 需要单独批准。
- 阶段退出条件未满足时，不用新格式按钮绕过数据契约。

## Phase 0：数据边界

状态：已完成（2026-07-22）。

进入条件：2.2.0 Extension 发布边界稳定，现有解析、数据和 Blender 构建路径已经盘点。

交付结果：完成量子化学语义模型、`Grid3D`、单位、reader capability contract、Blender/边车职责五项 ADR；定义最小纯 Python 契约；以 MOL2 声明不一致和跨格式结构归一化作为首批回归案例。

退出条件：普通 CPython 可以运行 core tests；core 不 import `bpy`；未支持字段显式报告；数值有单位或标为 dimensionless。

## Phase 1：分子量子化学闭环

状态：已完成（2026-07-22）。

进入条件：Phase 0 的对象、单位、parser report 和缓存身份已经稳定。

交付结果：通过 cclib、IOData 和 Cube reader 支持优化轨迹、能量与收敛、原子属性、振动、IR/UV-Vis、分子轨道、密度、自旋密度和 ESP 表面。

退出条件：至少一组 Gaussian 或 ORCA 输出及配套波函数/网格 fixture 能从解析进入 Blender 视图，并保留来源与派生关系。

## Phase 2：周期量子化学

状态：已完成（2026-07-22）。周期结构、VASP scalar fields、band/DOS/projection、phonopy complex modes 与 Fermi-surface/PyProcar 中立边界均已交付。

进入条件：Gemmi/spglib 已覆盖 CIF 语法、空间群与标准化边界，周期结构 ID 可以跨数据集复用。

交付结果：接入 ASE/pymatgen、CHGCAR/ELFCAR/LOCPOT、band/DOS、费米面和 phonopy；结构、能带、DOS 与倒空间对象可以联动。

退出条件：复数 q-point 模态按相位公式生成动画；周期体数据保留完整晶格和网格轴；投影数据共享稳定 atom/orbital/dataset ID。

## Phase 3：大型数据与交互

状态：已完成（2026-07-22）。`.cbq` v0.1、local worker v1、lazy trajectory manager、Grid3D LOD 与 Volume cache identity 均已验收。

进入条件：Phase 1/2 已提供网格、轨迹和轨道数组的规模基准。

交付结果：确定边车格式、source/parser/derivation/render hash、OpenVDB、worker、lazy loading、多分辨率表面与长轨迹缓存。

退出条件：`.blend` 不保存权威大型数组；缓存能可靠失效；重开项目可恢复 dataset 引用；worker 失败不会损坏源数据。

## Phase 4：工作流与自动化

状态：进行中；versioned recipe 与 external analysis process contract 已完成，当前进入 `TopologyGraph` 与 critic2 parser。

进入条件：语义输入、派生数据和 provenance 已足以描述可重复分析。

交付结果：定义 recipe，接入 Multiwfn/critic2 外部分析，并按需连接 QCArchive、AiiDA、NOMAD；生成场景模板、图组、引用和报告。

退出条件：每个 recipe 都声明输入、单位、外部程序、输出、验证与引用；失败结果不会被标记为有效派生数据。

## 当前顺序

1. 已完成：Cube 多 dataset、非正交 `Grid3D` 与 OpenVDB 可重建视图。
2. 已完成：Gaussian/ORCA cclib adapter。
3. 已完成：FCHK/Molden IOData basis/orbital adapter。
4. 已完成：GBasis MO/electron-density 规则网格与 Blender Volume。
5. 已完成：DensityMatrix、RDM electron/spin density 与 ESP。
6. 已完成：振动语义、IR/Raman 光谱和 Blender 模态动画。
7. 已完成：激发态语义、UV-Vis/ECD 光谱与 transition/NTO 引用。
8. 已完成：Phase 1 原子标量/矢量、优化轨迹和 linked selection 的 Blender adapters 收口。
9. 已完成：Gemmi CIF envelope 与 spglib 对称性/标准化基础设施。
10. 已完成：ASE/pymatgen-core 周期结构、CHGCAR/PARCHG/ELFCAR/LOCPOT 与 Blender volume identity。
11. 已完成：band structure、DOS/PDOS、projection 与 Blender linked selection。
12. 已完成：phonopy q-point、复数 eigenvector 与周期超胞动画。
13. 已完成：Fermi-surface 中立 mesh schema 与 PyProcar worker adapter。
14. 已完成：`.cbq` sidecar manifest、lazy array reference、Blender scene link 与分层 cache hash。
15. 已完成：代表性数组存储 benchmark、worker request/result/error/cancel/version 协议。
16. 已完成：lazy trajectory frame manager、有界 frame cache、插值与区间均值。
17. 已完成：Grid3D 多分辨率派生、lazy stride access 与 Blender Volume cache identity。
18. 已完成：versioned recipe schema、语义输入绑定、validation 与 citation contract。
19. 已完成：critic2/Multiwfn external adapter、非交互执行与失败产物隔离。
20. 当前：中立 `TopologyGraph`、critic2 critical points/bond paths parser 与 Blender point/curve 映射。

Phase 3 已依据 benchmark 保留 `.npy`，建立不阻塞 Blender 的本地 worker，并完成长轨迹与大型网格缓存闭环；Phase 4 从可验证 recipe contract 开始。
