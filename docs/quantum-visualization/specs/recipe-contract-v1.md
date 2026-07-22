# Recipe contract v1

## 目的

Recipe 描述一个可重复分析需要什么以及将产生什么，不负责在 Blender 进程内执行计算。
`RecipeDefinition` 是可版本化声明，`RecipePlan` 是它与一个 `QCProject` 中具体实体的绑定结果。

## 定义

每个 recipe 必须声明：

- 稳定 `recipe_id`、`version`、标题和支持的来源程序；
- 命名输入及其 entity kind，可选 semantic role、domain、dims、unit 与必需字段约束；
- 类型化参数、默认值、数值边界或字符串 choices；
- 输出 semantic role、domain、dims 与 unit；
- 默认 view、validation rule 和 citation。

v1 entity kind 为 `structure`、`dataset`、`basis_set`、`orbital_set`、
`density_matrix`。空约束表示该字段不适用于对应 entity kind，而不是 wildcard 字符串。

## 规划

`plan_recipe` 只执行预检：

1. 输入名与参数名必须精确匹配定义；
2. entity 必须存在、类型正确且 revision 与项目当前记录一致；
3. partial dataset 被拒绝；complete 或显式 ambiguous dataset 必须满足 role/domain/dims/unit 和必需字段；
4. 参数不做隐式类型转换；
5. 按 recipe 输入顺序和归一化参数计算 derivation key。

计划成功不代表计算成功。外部 worker 仍须返回成功结果并原子提交输出后，dataset 才能进入项目。

## 内置首批 recipe

- `vibrational_ir_spectrum`：振动模态到 IR stick/broadened spectrum；
- `tddft_uvvis`：激发态到 UV-Vis stick/broadened spectrum；
- `wavefunction_molecular_orbital_grid`：structure、basis 与 orbital set 到 scalar `Grid3D`。

这些 recipe 固定输入/输出语义和默认视图；具体数值实现继续复用现有 core/worker operation。

## 非目标

- v1 不提供 DAG、重试、远程调度或外部程序 discovery。
- v1 不把 Multiwfn 菜单编号作为稳定 API。
- recipe codec 不序列化 Python callable。
