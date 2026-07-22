# 量子化学可视化开发

ChemBlender 将继续作为 Blender 原生可视化前端；量子化学解析、语义归一化和大型数组管理放在不依赖 `bpy` 的数据边界之后。开发按物理量与数据责任组织，不按文件后缀逐项增加按钮。

## 当前阶段

Phase 0、Phase 1 分子闭环与 Phase 2 周期量子化学均已完成。`.cbq` v0.1、local worker v1 与 lazy trajectory manager 已验收；当前实施 Phase 3 Grid3D LOD 与 Volume cache identity。第三方 parser 和数值后端继续保留在独立 core/worker 环境。

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
34. [已完成：Phase 1 Blender adapters 收口](../../.agents/completed/phase1-blender-adapters.md)
35. [Phase 1 Blender adapters 收口设计](../superpowers/specs/2026-07-22-phase1-blender-adapters-design.md)
36. [Phase 1 Blender adapters 收口实现计划](../superpowers/plans/2026-07-22-phase1-blender-adapters.md)
37. [Phase 1 Blender dataset contract](../../.agents/decisions/0009-phase1-blender-dataset-contract.md)
38. [Gemmi/spglib 晶体基础设施设计](../superpowers/specs/2026-07-22-crystal-foundation-design.md)
39. [Gemmi/spglib 晶体基础设施实现计划](../superpowers/plans/2026-07-22-crystal-foundation.md)
40. [已完成：Gemmi/spglib 晶体基础设施](../../.agents/completed/crystal-foundation.md)
41. [Gemmi/spglib 晶体边界决策](../../.agents/decisions/0010-crystal-parsing-and-symmetry-boundary.md)
42. [已完成：Phase 2 周期结构与标量场](../../.agents/completed/periodic-structure-and-fields.md)
43. [`.cbq` v0.1 格式](specs/cbq-sidecar-v0.1.md)
44. [`.cbq` 与 cache identity 决策](../../.agents/decisions/0015-cbq-npy-sidecar-and-cache-identity.md)
45. [已完成：sidecar 与 cache foundation](../../.agents/completed/sidecar-and-cache-foundation.md)
46. [本地 worker protocol v1](specs/local-worker-protocol-v1.md)
47. [`.npy` Windows benchmark](benchmarks/2026-07-22-npy-sidecar-windows.md)
48. [worker v1 与 `.npy` 决策](../../.agents/decisions/0016-local-worker-v1-and-npy-retention.md)
49. [已完成：sidecar benchmark 与 local worker](../../.agents/completed/sidecar-benchmark-and-local-worker.md)
50. [Lazy trajectory frame manager 规格](specs/lazy-trajectory-frame-manager.md)
51. [Lazy trajectory 决策](../../.agents/decisions/0017-lazy-trajectory-frame-manager.md)
52. [已完成：lazy trajectory frame manager](../../.agents/completed/lazy-trajectory-frame-manager.md)
53. [当前任务：Phase 3 Grid3D LOD cache](../../.agents/active/phase3-grid-lod-cache.md)

路线图和主题计划保存稳定范围、依赖顺序与验收标准；`.agents/active/` 只记录正在执行的一个任务及其下一步。临时 commit、测试运行和本机状态不写入路线图。

## 开发主题

- [语义核心](plans/semantic-core.md)
- [Reader 与格式能力](plans/readers-and-formats.md)
- [波函数、网格与表面](plans/wavefunction-and-grids.md)
- [Blender 可视化映射](plans/blender-visualization.md)
- [周期电子结构](plans/periodic-electronic-structure.md)
- [存储、缓存与 worker](plans/storage-and-workers.md)
- [工作流、recipe 与 connector](plans/workflows-and-connectors.md)

候选项目、用途和按需拉取条件见[参考项目目录](references.md)。根目录 `submodules/` 只保存已进入实现并固定 commit 的参考源码；当前还包含 ASE 3.29.0 与 pymatgen-core 2026.7.16，二者和已有量化后端一样不进入 Extension ZIP。
