# Worker Reader Operation v0.1

## Operation

Worker Reader 使用固定 operation：

```text
reader.parse@0.1
```

请求沿用 Worker Protocol v1。`inputs` 必须为空，`parameters` 必须且只能包含：

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `reader_id` | string | 固定 worker registry 中的 reader ID |
| `source_artifact` | string | 请求任务目录内的安全 POSIX 相对路径 |
| `source_sha256` | string | 来源文件的小写 SHA-256 |
| `validation_mode` | string | `strict`、`balanced` 或 `maximum` |
| `canonical_parameters` | object | 稳定 token 到 string 的映射 |

请求不得携带 module、callable、shell、argv 或其他字段。Worker 不接受动态 import、任意命令或 pickle。

## Worker publication

Worker 只从 `builtin_reader_plugin_registry()` 选择 reader。来源路径不得为绝对路径，不得含 `..`、反斜杠或 `:`，任一 segment 不得以点或空格结尾，也不得经过 symlink/junction；读取前复验来源 SHA-256。

成功结果写入当前任务目录：

```text
reader-bundle/import-batch.json
reader-bundle/artifacts/<content-sha256>.npy
```

发布 `SUCCESS` 前必须重开 bundle，并通过 `internal_batch_from_public()` 的临时 `QCProject.commit()` 图校验。该 operation 不打开、不修改或替换权威 `.cbq`。

## Result metadata

成功 `WorkerResult.metadata` 必须且只能包含：

| 字段 | 值 |
| --- | --- |
| `operation` | `reader.parse@0.1` |
| `schema_version` | `0.1` |
| `document_path` | `reader-bundle/import-batch.json` |
| `document_sha256` | canonical document SHA-256 |
| `artifact_sha256` | NPY 相对路径到 SHA-256 的映射 |

`WorkerResult.artifacts` 必须精确覆盖 document 和 `artifact_sha256` 的键。
不得有重复路径。`reader-bundle` 递归 inventory 只能包含 document、`artifacts/` 目录和声明的 content-addressed NPY，不允许额外文件、目录或 link/junction。

Worker 原子创建此前不存在的 `reader-bundle` 并持有该目录。写出后若取消、重开失败、图校验失败、hash 失败或 runner 拒绝输出，必须只清理本次创建的 exact `task_directory/reader-bundle`；预先存在的同名路径不得删除。清理后同一任务目录可安全重试。

## Main-process acceptance

`parse_with_worker(request, result, task_directory)` 仅接受匹配 request ID 的 `SUCCESS` 结果。主进程重新检查：

- request operation、参数白名单和来源 SHA-256；
- exact result metadata 与 artifacts 集合；
- 所有路径仍位于原任务目录内且不经过 link；
- document 与每个 NPY 的 SHA-256；
- canonical bundle 可安全重开；
- public batch 可转换并通过完整项目图校验。

`ERROR` / `CANCELLED` 转换为 `WorkerReaderExecutionError`；篡改、过期或不兼容输出转换为 `WorkerReaderIntegrityError`。
