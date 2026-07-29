# Reader API v1 Worker API

Worker 路径用于受控的外部 Python parser。它复用 Reader API v1 公开模型，但进程
边界使用 `reader.parse@0.1` operation 和 canonical bundle，不传递 Python object、
pickle、callable、shell 或任意 import 名称。

## Request

`WorkerRequest.parameters` 精确包含：

| 字段 | 契约 |
| --- | --- |
| `reader_id` | worker registry 中的稳定 reader ID |
| `source_artifact` | task directory 内安全的 POSIX 相对路径 |
| `source_sha256` | 小写 SHA-256 |
| `validation_mode` | `strict`、`balanced` 或 `maximum` |
| `canonical_parameters` | 稳定 token 到 string 的 mapping |

读取 source 前复验 SHA-256。路径不得为 absolute、包含 `..`、反斜杠、drive、
symlink 或 junction。

## Success bundle

```text
reader-bundle/import-batch.json
reader-bundle/artifacts/<content-sha256>.npy
```

`import-batch.json` 是 UTF-8、无 BOM 的 canonical JSON。数组使用
content-addressed NPY，`allow_pickle=False`；主进程复验 inventory、document、
artifact SHA-256、dtype、shape、content hash 与 source revision identity。

## cancellation 与错误

worker 在 hash、parse、artifact write 和 publication 边界检查 cancellation。
取消或失败只清理本次拥有的 `reader-bundle`；预先存在的路径不得删除。非 success
状态转为 `WorkerReaderExecutionError`，篡改或不兼容结果转为
`WorkerReaderIntegrityError`。主进程校验通过后仍须完成 public-to-internal 图
验证；worker 不打开或修改 `.cbq`。
