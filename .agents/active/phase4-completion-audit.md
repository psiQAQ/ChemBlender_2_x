# Phase 4 Completion Audit

## Goal

对照量子化学可视化路线图、主题计划、ADR、代码、测试与 submodule 清单执行完成度审计，关闭可在本地无新增授权完成的缺口，并只把真正需要用户选择或外部账号的事项列为明确边界。

## Success Criteria

- Phase 0–4 每项交付物和退出条件映射到当前代码、文档与测试证据。
- 格式 capability matrix、依赖分层、submodule 状态和 Extension ZIP 边界一致。
- 无 stale active/queued 链接、未跟踪源文件或文档自相矛盾。
- 可本地完成的缺口直接修复并验证；在线 provider、真实第三方二进制等需授权事项形成最小决策清单。
- 最终全量 CPython、extension validate/build、ZIP audit、Blender isolated smoke 与 `git diff --check` 通过。

## Constraints

- 不安装新依赖、不访问外部账号、不执行网络写入、不 push。
- 不把建议项伪装成已实现功能。
- 不为审计引入新的抽象层。

## Next Action

从 roadmap 当前顺序、各主题 P0/P1/P2、`.agents` 状态和 submodule manifest 生成证据矩阵，定位未闭环项。
