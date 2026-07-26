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
匹配的 `StagedImportSession`。缺少 selected reader 的 row 只接受
`chemblender.preflight` 生成的 v0/Reader API 0.1 failure provenance，不把
`selected_reader_id=None` 当作任意 reader 的通配符。
`render_diagnostics_markdown()` 只接受 document，不访问 staging state。

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

Renderer 在输出前深层验证 schema。`schema_version` 必须是 exact integer；
全部 ID 必须是 canonical UUID text；severity、quality status、summary row 字段和
五个非负 integer count 键必须精确；row/diagnostic ID 必须唯一，summary 必须与
diagnostics 的 source/entity 关联和计数一致。所有畸形 document 统一抛出
`ValueError`。

Markdown 从同一 document 渲染，并把全部 diagnostic 内容视为纯文本。先用
stdlib HTML escaping 处理 raw HTML，再转义原有 backslash 和
backtick、emphasis、link/image、tilde、pipe 等 Markdown 语法字符；CR/LF
替换为空格。此顺序使已有 `\|`、连续 backslash 和嵌套 JSON 都不会改变表格列，
且重排原始 diagnostic 输入不会改变 canonical JSON 或 Markdown bytes。
