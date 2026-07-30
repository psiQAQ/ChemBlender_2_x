# Reader API v1 Diagnostics

Reader 不使用日志代替科学诊断。解析结果通过以下公开对象报告：

| 对象 | 用途 |
| --- | --- |
| `ParserReport` | reader identity、created entity IDs、capabilities 与 issues |
| `ParserIssue` | 稳定 issue kind、path 与简短 message |
| `ImportDiagnostic` | code、severity、原始/规范值、恢复动作、科学后果与建议 |
| `DiagnosticValue` | 可安全 canonical 化的 typed value |

`SourceRevision.diagnostic_ids` 与 `ParserReport.created_entity_ids` 必须精确引用
同一 `PublicImportBatch` 中的对象。恢复模式必须显式降低 `QualityStatus`；不得用
warning 隐藏丢失或推断。

## exception isolation

- sniff 抛出的普通 `Exception` 只使该 reader 失配，并生成安全的
  `reader.sniff` issue；其他 reader 继续选择。
- parse 抛出的普通 `Exception` 转为 `reader.parse` invalid batch；异常 message、
  路径和 traceback 不越过插件边界。
- `MemoryError`、`KeyboardInterrupt` 与 `SystemExit` 不包装为普通 reader 诊断。
- unavailable dependency 产生 `reader.availability` unsupported issue。
- host progress/cancel callback 失败由宿主隔离，不冒充 parser 科学错误。

当 plugin is missing 时，已提交的 `.cbq`、科学实体和已有 view 仍可 reopen；
只有依赖该插件的 reparse 不可用。插件自身启用、禁用或失败不得阻止 ChemBlender
注册、项目重开或其他 reader 工作。
