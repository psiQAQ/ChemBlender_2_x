# 量子化学可视化开发

ChemBlender 将继续作为 Blender 原生可视化前端；量子化学解析、语义归一化和大型数组管理放在不依赖 `bpy` 的数据边界之后。开发按物理量与数据责任组织，不按文件后缀逐项增加按钮。

## 当前阶段

当前处于 Phase 0：先确定数据边界，再开始功能实现。本阶段不安装 cclib、IOData、Gemmi、spglib 等候选依赖，也不创建完整的 core 目录。

## 阅读顺序

1. [持续开发路线图](roadmap.md)
2. [Phase 0 数据边界议程](architecture/data-boundary.md)
3. [文档体系设计规格](../superpowers/specs/2026-07-21-quantum-visualization-development-system-design.md)
4. [语义核心实现计划](../superpowers/plans/2026-07-21-quantum-semantic-core.md)
5. [当前任务](../../.agents/active/quantum-visualization-foundation.md)

路线图和主题计划保存稳定范围、依赖顺序与验收标准；`.agents/active/` 只记录正在执行的一个任务及其下一步。临时 commit、测试运行和本机状态不写入路线图。

## 开发主题

- [语义核心](plans/semantic-core.md)
- [Reader 与格式能力](plans/readers-and-formats.md)
- [波函数、网格与表面](plans/wavefunction-and-grids.md)
- [Blender 可视化映射](plans/blender-visualization.md)
- [周期电子结构](plans/periodic-electronic-structure.md)
- [存储、缓存与 worker](plans/storage-and-workers.md)
- [工作流、recipe 与 connector](plans/workflows-and-connectors.md)

候选项目、用途和按需拉取条件见[参考项目目录](references.md)。根目录 `submodules/` 当前只有说明文件，不包含外部仓库。
