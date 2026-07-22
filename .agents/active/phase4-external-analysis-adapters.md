# Phase 4 External Analysis Adapters

## Goal

在 local worker 边界上建立安全、非交互、可审计的外部分析 adapter contract，并以 critic2 与 Multiwfn 的代表性 recipe 验证命令、输入、输出和失败隔离。

## Success Criteria

- adapter 声明 program ID、版本探测、支持的 recipe、所需 artifacts 和预期 outputs。
- 执行使用参数列表而非 shell 字符串，限制工作目录，记录 executable/version/argv/return code/stdout/stderr hash。
- timeout、取消、非零退出、缺少或畸形输出均不发布有效 dataset。
- 至少有一个 fake executable integration test 覆盖成功、失败、timeout 和输出不完整。
- critic2 与 Multiwfn 使用稳定输入模板/输出 parser 边界，不让 Blender UI 依赖交互菜单编号。

## Constraints

- 不在 Extension 内安装或启动外部程序；执行只发生在独立 worker 环境。
- 不假设用户已安装 Multiwfn 或 critic2，缺失程序必须是可诊断状态。
- 不使用 `shell=True`，不接受任意用户 shell 片段。
- 没有真实、稳定 fixture 的分析功能只登记 capability，不伪造 parser。

## Next Action

审阅 local worker 原子提交规则和 critic2 官方 CLI，先以 fake executable 写 external-run contract 的失败测试，再实现最小 runner 与 adapter descriptor。

## References

- [Recipe contract v1](../../docs/quantum-visualization/specs/recipe-contract-v1.md)
- [本地 worker protocol](../../docs/quantum-visualization/specs/local-worker-protocol-v1.md)
- [工作流、recipe 与 connector 计划](../../docs/quantum-visualization/plans/workflows-and-connectors.md)
