# Import diagnostics report v1

`chemblender_import_report` v1 是 Import Preview 的只读、确定性诊断导出。
报告只读取 preview 指定的 live staging batches，不读取或修改 `QCProject`。
preview/session 身份、source-to-batch 关联、revision 或 diagnostic 引用不一致时，
生成报告必须失败。

## API

```python
summary = import_summary(preview, staged_session)
document = diagnostics_document(preview, staged_session)
markdown = render_diagnostics_markdown(document)
```

`import_summary()` 和 `diagnostics_document()` 接受不可变 `ImportPreview` 及其
匹配的 `StagedImportSession`。`render_diagnostics_markdown()` 只接受 document，
不访问 staging state。

## Document

顶层字段固定为：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `schema_name` | string | 固定为 `chemblender_import_report` |
| `schema_version` | integer | 固定为 `1` |
| `session_id` | UUID string | staging session 身份 |
| `staged_batch_ids` | UUID string list | preview 明确引用的 batch |
| `summary` | object | diagnostic status 计数 |
| `diagnostics` | object list | 完整诊断字段与关联的 `source_id` |

每个 diagnostic row 保留 `ImportDiagnostic` 的全部字段：
`id`、`severity`、`quality_status`、`source_revision_id`、`record_key`、
`entity_id`、`field_path`、`code`、`message`、`original_value`、
`normalized_value`、`recovery_action`、`scientific_consequence` 和
`suggested_action`；另含关联的 source record UUID `source_id`。
`DiagnosticValue` 恢复为普通 JSON scalar、list 或 object。

## Summary semantics

`summary` 固定包含 `overall`、`by_source` 和 `by_entity`。计数键按
`Complete`、`Partial`、`Ambiguous`、`Incomplete`、`Invalid` 顺序生成。
`by_source` 使用 source record UUID；`by_entity` 只包含非空 entity UUID。
没有 entity 的诊断仍计入 overall 和 source。Invalid diagnostic 引用的 entity
即使没有可提交的 staged entity，也必须出现在 entity 计数中。

这些数字统计 diagnostic status occurrence，不是对 source 或 entity 的单一、
聚合科学质量判定。

## Determinism and encoding

Diagnostic rows 按以下键排序：

1. severity：`error`、`warning`、`info`；
2. source record UUID；
3. `record_key`；
4. `field_path`；
5. `code`；
6. diagnostic UUID。

Source/entity summary rows 按 UUID 排序。Canonical JSON 编码为 UTF-8，并使用：

```python
json.dumps(
    document,
    ensure_ascii=False,
    allow_nan=False,
    sort_keys=True,
    separators=(",", ":"),
)
```

Markdown 从同一 document 渲染。表格单元中的 `|` 转义为 `\|`，CR/LF 替换为
空格，因此重排原始 diagnostic 输入不会改变 canonical JSON 或 Markdown bytes。
