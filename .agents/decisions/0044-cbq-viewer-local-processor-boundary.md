# 0044：共享 CBQ、保留本地编辑与统一外部处理

日期：2026-09-08。状态：用户批准，实施中；不表示验收完成。

## 决策

以cbq_core维护唯一模型、CBQ1.1/单位/事务/采样及Worker v1协议；chemblender_prepare负责原始文件、第三方科学依赖和重计算，提供独立CLI/薄Tk GUI以及统一本地worker入口。Blender保留纯Mesh编辑和高频可视化，用全局processor_executable发起异步任务，路径不进入项目文件。

RDKit wheel延后删除，不能以裁剪源码替代其二进制依赖。先完成已有迁移的干净逻辑提交，再接入统一处理程序；等价/性能/取消/数据一致性/生命周期门槛全部通过才移除正式wheel与相关import。失败保留原功能及wheel并延期，不发布降级版本。仅保留wheel而丢失按钮也不构成功能保留。

## 原因与代价

高频显示与纯编辑应在本地即时响应；RDKit等按钮式重计算可通过文件协议隔离。独立工具增加一次配置及外部环境维护，统一可执行路径把内部Python/Fermi/critic2细节留在工具端。复用既有模型、worker协议、缓存与事务，避免维护第二套科学模型或服务框架。

## 约束及证据

轻量参数节流预览；昂贵操作仅Apply/Recompute。主线程冻结编辑输入，结果按request/hash/revision/provenance校验后追加新实体；失败、取消或过期结果不修改项目。能力文档独立版本化，记录实际后端版本。

100ms进入modal、1秒显示运行、两秒确认取消、百原子以内冷启动额外开销不超过两秒必须实测。当前无wheel候选smoke只证明基础Viewer生命周期，不替代这些门槛。

完整[方案与验收矩阵](../../docs/quantum-visualization/architecture/local-processor.md)为实施依据；[当前任务](../active/physical-quantity-visualization-sop.md)记录进度。新架构尚未发布，旧编号决策保留历史依据。
