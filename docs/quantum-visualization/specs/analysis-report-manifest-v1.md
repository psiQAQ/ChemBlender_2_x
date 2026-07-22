# Analysis report manifest v1

`chemblender_analysis_report/1` 是可审计的本地报告摘要，不是大型数组或渲染结果的
替代存储。相同 project revision、选择、recipe plan 和 artifact 内容产生相同 JSON 与
Markdown；manifest 不写当前时间或机器路径。

## 内容

| 字段 | 内容 | 规则 |
| --- | --- | --- |
| `project` | project UUID 与 schema version | 不复制 `.cbq` manifest |
| `calculations` | 状态、结构/dataset/provenance IDs、方法和程序摘要 | 选择 calculation 时自动纳入其 datasets |
| `datasets` | semantic role、domain、dims、shape、unit 与状态 | 不复制数组值 |
| `provenance` | 所选实体 provenance 及 parent closure | 参数必须为有限 JSON |
| `recipe` | recipe/version、plan binding、parameters、derivation key、citations | plan binding 必须仍匹配 project revision |
| `artifacts` | role、相对 POSIX path、media type、size、SHA-256 | 文件必须存在且位于显式 root 内 |
| `warnings` | failed/incomplete/ambiguous 状态 | 非 `complete` 报告明确声明不能作为有效结论 |

`write_analysis_report_bundle` 只生成 `manifest.json` 与 `report.md`，目标已存在时拒绝
覆盖。它先写同级临时目录并原子替换，不联网、不执行程序、不读取凭据。

## 非目标

- v1 不嵌入图像、Cube、轨道矩阵或数值数组。
- v1 不生成 PDF/DOCX，不引入模板引擎。
- v1 不自动解释数值或生成科研结论。
