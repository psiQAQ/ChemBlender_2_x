# 量子化学可视化开发

ChemBlender 将继续作为 Blender 原生可视化前端；量子化学解析、语义归一化和大型数组管理放在不依赖 `bpy` 的数据边界之后。开发按物理量与数据责任组织，不按文件后缀逐项增加按钮。

## 当前阶段

Phase 0 已完成，当前进入 Phase 1 分子量子化学闭环。Cube/OpenVDB 与 cclib Gaussian/ORCA 已完成，当前建立 basis/orbital 语义并实现 IOData FCHK/Molden adapter；第三方 parser 保留在独立 core 环境。

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
19. [已完成的分子量化读取闭环](../../.agents/completed/molecular-quantum-chemistry-ingestion.md)
20. [当前任务](../../.agents/active/wavefunction-derived-fields.md)

路线图和主题计划保存稳定范围、依赖顺序与验收标准；`.agents/active/` 只记录正在执行的一个任务及其下一步。临时 commit、测试运行和本机状态不写入路线图。

## 开发主题

- [语义核心](plans/semantic-core.md)
- [Reader 与格式能力](plans/readers-and-formats.md)
- [波函数、网格与表面](plans/wavefunction-and-grids.md)
- [Blender 可视化映射](plans/blender-visualization.md)
- [周期电子结构](plans/periodic-electronic-structure.md)
- [存储、缓存与 worker](plans/storage-and-workers.md)
- [工作流、recipe 与 connector](plans/workflows-and-connectors.md)

候选项目、用途和按需拉取条件见[参考项目目录](references.md)。根目录 `submodules/` 只保存已进入实现并固定 commit 的参考源码；当前包含 cclib v1.8.1 与 IOData v1.0.1。
