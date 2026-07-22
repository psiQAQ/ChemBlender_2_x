# 0020：External analysis process boundary

## Status

Accepted for Phase 4 local analysis adapters.

## Context

critic2、Multiwfn 等独立程序需要文件、stdin 和长时间运行。若 Blender 或通用 request 可直接提交
shell 字符串，将引入命令注入、UI 阻塞、旧输出误发布和不可追踪版本等问题。

## Decision

- 外部程序只在 `worker/` 内由显式注册 adapter 构造 invocation；request 不携带 executable 或 argv。
- runner 始终使用参数列表、固定 job root 与 `shell=False`。
- stdin、input 和 expected output 都是 job root 内的相对 artifact；已有 output 被拒绝。
- stdout/stderr 写独立日志并记录 SHA-256；run record 包含 program/adapter version、argv、return code、elapsed time 和 error code。
- timeout/cancel 会终止进程；非零退出、缺程序、缺输出均不是 success。
- critic2 v1 使用官方测试采用的 `-q -t -l input output` argv。
- Multiwfn v1 只声明 stdin-script invocation；实际版本、许可和 parser 必须随安装包/fixture 另行验证。

## Consequences

- Blender UI 不接触 Multiwfn 菜单编号，也不能执行任意 shell。
- 失败产物可留在隔离 job directory 诊断，但不会构造或发布有效 dataset。
- 科学 output parser 与 `TopologyGraph` 留在后续独立阶段。

## Verification Contract

1. fake executable 覆盖 success、nonzero、missing program、timeout、cancel 和 missing output。
2. path escape、missing input 和 stale output 在启动前拒绝。
3. stdin script、version probe 和 run metadata 不使用 shell。
4. worker 目录不进入 Blender Extension ZIP。
