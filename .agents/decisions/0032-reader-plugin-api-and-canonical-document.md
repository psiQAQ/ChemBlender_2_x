# 0032：Reader Plugin API 使用 Python 与 canonical document 双边界

## Status

Proposed for 2.3.0; user direction approved.

## Context

内置ReaderDescriptor缺少plugin来源、API版本、执行模式和依赖可用状态。第三方生态不能依赖私有core路径，worker也不能返回Python对象。

## Decision

定义Built-in、Extension Reader和Worker Reader。Built-in/Extension返回PublicImportBatch；Worker返回版本化canonical JSON和任务目录内的NPY artifacts。两者可确定性往返，并在QCProject提交前重新校验。Blender Extension间通过`bpy.app.driver_namespace`中的版本化API handle发现实际安装模块，不能硬编码repository namespace。

Reader API在alpha使用0.x，beta.1冻结v1 RC，beta.2只兼容扩展，2.3.0发布v1 stable。

## Consequences

- 第三方reader不能直接创建Blender对象或修改项目registry。
- 缺失插件不妨碍打开已保存sidecar。
- 需要conformance kit和仓库外示例插件。

## Rejected Alternatives

- 任意模块运行时直接注册内部ReaderDescriptor。
- 所有插件使用pickle或任意RPC。
- 2.3.0 alpha立即冻结稳定v1。

## Verification Contract

Python batch与canonical document逐字段round-trip；路径逃逸、pickle、未知type和插件异常被隔离；示例extension reader可安装、禁用和缺失恢复。
