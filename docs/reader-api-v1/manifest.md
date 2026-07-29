# Reader plugin manifest v1

manifest 使用 UTF-8 TOML。全部字段都是必填项；未知字段、重复 `reader_id`、
不兼容 API 范围或非法 token 均 fail closed。

```toml
schema_version = "1"
plugin_id = "org.example.reader"
plugin_version = "1.0.0"
chemblender_api = ">=1.0,<2.0"
execution_mode = "extension"
license = ["SPDX:MIT"]

[[readers]]
reader_id = "example-format"
reader_version = "1"
extensions = [".example"]
capabilities = ["structure"]
```

## 顶层字段

| 字段 | 契约 |
| --- | --- |
| `schema_version` | 精确为 `"1"` |
| `plugin_id` | 小写稳定 token：`[a-z][a-z0-9_.-]*` |
| `plugin_version` | 数字点分版本 |
| `chemblender_api` | 半开区间 `>=MAJOR.MINOR,<MAJOR.MINOR` |
| `execution_mode` | `built_in`、`extension` 或 `worker` |
| `license` | 非空、去重并排序的许可证字符串 |
| `readers` | 至少一个 reader table |

## Reader 字段

| 字段 | 契约 |
| --- | --- |
| `reader_id` | 插件内唯一的小写稳定 token |
| `reader_version` | 数字点分版本 |
| `extensions` | 非空 suffix 列表；解析时小写、补前导点、去重并排序 |
| `capabilities` | 非空 `lower_snake_case` token 列表；去重并排序 |

Python 中使用 `ReaderPluginManifest.from_toml()` 解析 manifest，并让
`PublicReaderDescriptor` 的 plugin、reader、execution mode、extensions 与
supported capabilities 精确匹配对应 manifest entry。
