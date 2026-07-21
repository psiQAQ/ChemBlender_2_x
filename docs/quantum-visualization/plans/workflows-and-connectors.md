# 工作流、recipe 与 connector 开发计划

## 范围

把可复现的量子化学分析描述为 recipe，并通过外部 adapter 连接分析程序、计算引擎和数据库。

## 非目标

- quantum-chem-skills 不作为 parser 或数值核心复制进项目。
- Blender UI 不绑定 Multiwfn 交互菜单编号。
- 不把 QCArchive、AiiDA 或 NOMAD 服务栈嵌入 Extension。

## 优先级

| 优先级 | 内容 | 验证重点 |
| --- | --- | --- |
| P0 | recipe schema：输入语义、单位、参数、派生步骤、输出、视图、验证与引用 | 输入缺失或单位不兼容时拒绝执行；同一 recipe 可重放 |
| P1 | quantum-chem-skills 配方映射；Multiwfn/critic2 外部进程 adapter；QCEngine/PySCF 可选执行入口 | 命令、版本、stdout/stderr、返回码和输出文件进入 provenance |
| P2 | QCArchive、AiiDA、NOMAD connector；自动图组、场景模板和分析报告 | 本地缓存、鉴权与失败恢复有独立边界 |

## 依赖关系

依赖稳定的语义输入、单位、provenance、边车和 worker 协议。每个 adapter 只负责准备输入、执行与解析输出；生成的属性仍通过 reader 和 normalized model 进入 Blender。

## 交付物

- versioned recipe schema 与 validation rules。
- 几何优化、频率、TDDFT 和波函数分析的首批 recipe。
- 外部程序 adapter contract 和安全的非交互执行方式。
- recipe 运行记录、引用信息和失败产物隔离规则。
- connector 的缓存、分页、身份和 provenance 映射。

## 验收标准

- recipe 明确声明支持的来源程序、单位和输入 capability。
- 外部命令失败、超时或输出不完整时不生成有效 dataset。
- Multiwfn/critic2 版本与执行输入可追踪，不依赖 UI 菜单序号。
- 相同输入、参数和程序版本产生相同 derivation identity。
- connector 断网或凭据缺失不影响本地项目打开与浏览。

## 参考仓库触发条件

- 定义首批 recipe 时审阅 quantum-chem-skills 的功能分类和工作流，不直接复制占位脚本。
- QTAIM/NCI adapter 实施时审阅 critic2；hole-electron、键级和表面分析实施时审阅 Multiwfn。
- 只有用户确认数据库导入需求后才固定 QCArchive、AiiDA 或 NOMAD 参考版本。
