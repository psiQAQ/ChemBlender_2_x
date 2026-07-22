# External analysis adapter implementation plan

## Goal

建立显式 descriptor 与安全 worker subprocess runner，为 critic2/Multiwfn 后续 parser 提供可审计边界。

## Plan

1. 固定 critic2 官方源码并核对 CLI、许可证和测试调用。
2. 以 fake executable 测试成功、非零退出、timeout、cancel、缺输出和路径逃逸。
3. 实现 descriptor、invocation、version probe、日志 hash 与结构化 run record。
4. 提供 critic2 argv 和 Multiwfn stdin-script invocation builder，不暴露任意 shell。
5. 更新 ADR、参考目录和阶段状态；执行全量 tests 与 Blender package smoke。

## Verify

- `python -m unittest tests.test_external_program`
- `python -m unittest discover -s tests`
- Blender Extension validate/build 与隔离 package smoke
- `git diff --check`
