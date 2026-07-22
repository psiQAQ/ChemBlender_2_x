# 0019：Versioned recipe contract

## Status

Accepted for Phase 4 workflow planning.

## Context

现有 spectrum、wavefunction 和 worker operation 已能执行单项派生，但缺少统一声明来描述语义输入、
参数、输出、默认视图、验证和引用。直接复制 workflow 脚本或绑定外部程序菜单编号无法形成稳定接口。

## Decision

- `RecipeDefinition` 是纯数据、版本化、严格可序列化的分析声明，不包含 callable。
- 输入按 entity kind 绑定 `QCProject` 中的 UUID/revision，并可约束 semantic role、domain、dims、unit 和必需字段。
- partial dataset 在规划阶段拒绝；显式 ambiguous dataset 仅在其被 recipe 使用的字段满足约束时允许。
- 参数不做隐式类型转换；未知、缺失、越界或 choice 不匹配在执行前失败。
- `RecipePlan` 按 recipe 输入顺序和归一化参数产生 derivation key。
- planner 不执行外部程序，也不发布输出；worker 成功并原子提交后才产生有效 dataset。
- 首批内置 recipe 覆盖 IR、TDDFT UV-Vis 与 GBasis molecular-orbital grid。

## Consequences

- Blender UI、CLI 和 worker 可共享同一 recipe 定义，而不共享运行时依赖。
- 外部 adapter 后续只需实现 preparation/execution/parsing，不重新定义科学输入输出。
- DAG、重试、远程调度和程序 discovery 不属于 v1。

## Verification Contract

1. schema invariants、严格 JSON round-trip 与未知字段拒绝有纯 CPython tests。
2. 缺输入、未知参数、类型错误、partial dataset 和单位不兼容在规划时失败。
3. entity revision 或参数变化使 derivation identity 变化。
4. 内置 recipe 均包含 view、validation 和 citation。
