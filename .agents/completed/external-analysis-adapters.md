# External Analysis Adapter Process Boundary

## Result

- 新增 critic2/Multiwfn descriptor、显式 invocation builder 和安全 subprocess runner。
- 记录 version、argv、return code、elapsed time、stdout/stderr artifact 与 SHA-256。
- timeout、cancel、launch failure、nonzero exit、missing/stale output 均不能返回 success。
- 固定 critic2 官方源码 `4b5dec9`；Multiwfn 不存在可固定的官方 GitHub 源码，因此只登记 adapter contract。

## Evidence

- targeted external program tests：7 passed。
- full suite：236 tests passed，27 optional-dependency skips。
- Blender 5.1.2 native validate/build 与隔离 Extension lifecycle smoke passed；worker 未进入 ZIP。

## Decision

`.agents/decisions/0020-external-analysis-process-boundary.md`

## Known Limitations

- 本阶段不解析 critic2/Multiwfn 科学输出，也不要求本机安装二者。
- Multiwfn version probe、许可证和命令模板须对目标安装包做实机复核。
