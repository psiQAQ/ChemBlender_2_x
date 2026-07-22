# 量子化学可视化开发

ChemBlender 将继续作为 Blender 原生可视化前端；量子化学解析、语义归一化和大型数组管理放在不依赖 `bpy` 的数据边界之后。开发按物理量与数据责任组织，不按文件后缀逐项增加按钮。

## 当前阶段

Phase 0 已完成，当前进入 Phase 1 分子量子化学闭环。Cube/OpenVDB、cclib、IOData、GBasis MO/density、RDM/spin-density/ESP、振动与激发态光谱已完成；当前收口原子属性、矢量、优化轨迹和 linked selection 的 Blender adapters。第三方 parser 和数值后端保留在独立 core/worker 环境。

## 阅读顺序

1. [持续开发路线图](roadmap.md)
2. [Phase 0 数据边界议程](architecture/data-boundary.md)
3. [文档体系设计规格](../superpowers/specs/2026-07-21-quantum-visualization-development-system-design.md)
4. [语义核心实现计划](../superpowers/plans/2026-07-21-quantum-semantic-core.md)
5. [Reader registry 实现计划](../superpowers/plans/2026-07-21-reader-registry.md)
6. [XYZ reader 实现计划](../superpowers/plans/2026-07-22-xyz-reader.md)
7. [多帧 XYZ 与 FrameSet 设计](../superpowers/specs/2026-07-22-multiframe-xyz-design.md)
8. [多帧 XYZ 实现计划](../superpowers/plans/2026-07-22-multiframe-xyz.md)
9. [MOL V2000 reader 设计](../superpowers/specs/2026-07-22-mol-v2000-reader-design.md)
10. [MOL V2000 reader 实现计划](../superpowers/plans/2026-07-22-mol-v2000-reader.md)
11. [Cube reader 设计](../superpowers/specs/2026-07-22-cube-reader-design.md)
12. [Cube reader 实现计划](../superpowers/plans/2026-07-22-cube-reader.md)
13. [OpenVDB Volume adapter 设计](../superpowers/specs/2026-07-22-grid-volume-adapter-design.md)
14. [OpenVDB Volume adapter 实现计划](../superpowers/plans/2026-07-22-grid-volume-adapter.md)
15. [cclib adapter 设计](../superpowers/specs/2026-07-22-cclib-adapter-design.md)
16. [cclib adapter 实现计划](../superpowers/plans/2026-07-22-cclib-adapter.md)
17. [IOData 波函数语义设计](../superpowers/specs/2026-07-22-iodata-wavefunction-design.md)
18. [IOData 波函数实现计划](../superpowers/plans/2026-07-22-iodata-wavefunction.md)
19. [波函数派生 Grid3D 设计](../superpowers/specs/2026-07-22-wavefunction-grid-design.md)
20. [波函数派生 Grid3D 实现计划](../superpowers/plans/2026-07-22-wavefunction-grid.md)
21. [GBasis worker 后端决策](../../.agents/decisions/0007-wavefunction-grid-backend.md)
22. [已完成的分子量化读取闭环](../../.agents/completed/molecular-quantum-chemistry-ingestion.md)
23. [已完成的波函数派生场](../../.agents/completed/wavefunction-derived-fields.md)
24. [DensityMatrix、spin density 与 ESP 设计](../superpowers/specs/2026-07-22-wavefunction-observables-design.md)
25. [DensityMatrix、spin density 与 ESP 实现计划](../superpowers/plans/2026-07-22-wavefunction-observables.md)
26. [已完成：RDM、spin density 与 ESP](../../.agents/completed/wavefunction-observables.md)
27. [已完成：振动、IR/Raman 与 Blender 模态](../../.agents/completed/vibrations-and-spectra.md)
28. [振动、IR/Raman 与 Blender 模态设计](../superpowers/specs/2026-07-22-vibrations-and-spectra-design.md)
29. [振动、IR/Raman 与 Blender 模态实现计划](../superpowers/plans/2026-07-22-vibrations-and-spectra.md)
30. [已完成：激发态、UV-Vis/ECD 与 transition reference](../../.agents/completed/excited-states-and-spectra.md)
31. [激发态与电子光谱决策](../../.agents/decisions/0008-excited-state-and-spectrum-contract.md)
32. [激发态、UV-Vis/ECD 与 transition reference 设计](../superpowers/specs/2026-07-22-excited-states-and-spectra-design.md)
33. [激发态、UV-Vis/ECD 与 transition reference 实现计划](../superpowers/plans/2026-07-22-excited-states-and-spectra.md)
34. [当前任务：Phase 1 Blender adapters 收口](../../.agents/active/phase1-blender-adapters.md)

路线图和主题计划保存稳定范围、依赖顺序与验收标准；`.agents/active/` 只记录正在执行的一个任务及其下一步。临时 commit、测试运行和本机状态不写入路线图。

## 开发主题

- [语义核心](plans/semantic-core.md)
- [Reader 与格式能力](plans/readers-and-formats.md)
- [波函数、网格与表面](plans/wavefunction-and-grids.md)
- [Blender 可视化映射](plans/blender-visualization.md)
- [周期电子结构](plans/periodic-electronic-structure.md)
- [存储、缓存与 worker](plans/storage-and-workers.md)
- [工作流、recipe 与 connector](plans/workflows-and-connectors.md)

候选项目、用途和按需拉取条件见[参考项目目录](references.md)。根目录 `submodules/` 只保存已进入实现并固定 commit 的参考源码；当前包含 cclib v1.8.1、IOData v1.0.1 与 GBasis v0.1.0。
