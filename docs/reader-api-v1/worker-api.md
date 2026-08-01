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
content-addressed NPY，`allow_pickle=False`。主进程独立校验：

- `WorkerResult.request_id == WorkerRequest.request_id`，以及唯一
  `SourceRevision.id` 等于 request 指定的 revision UUID；
- worker/protocol/operation/schema version、安全路径和 exact inventory；
- source、document 和 artifact SHA-256，以及 canonical NPY 的 dtype、
  shape 和 content hash；
- public-to-internal 转换后的完整 bundle graph 与引用。

`reader_plugin_id`、`reader_id`、reader version、canonical parameters 与
`parse_identity` 由固定受信 worker 的 `stage_import_batch()` 构造；当前 host
不独立重算这些字段与 source bytes 的全部关系。这是当前的明示信任
边界；完整 identity 复验属于后续 runtime hardening，不是本文档任务已
实现的保证。

## cancellation 与错误

worker 在 hash、parse、artifact write 和 publication 边界检查 cancellation。
取消或失败只清理本次拥有的 `reader-bundle`；预先存在的路径不得删除。非 success
状态转为 `WorkerReaderExecutionError`，篡改或不兼容结果转为
`WorkerReaderIntegrityError`。主进程校验通过后仍须完成 public-to-internal 图
验证；worker 不打开或修改 `.cbq`。

## Host process lifecycle

[`WorkerHandle`](../../ChemBlender/worker_client.py) 由 host 持有 process、request、
result、cancel 和 stdout/stderr 路径：

- `poll()` 在 result 存在时读取严格 `WorkerResult`；进程退出但没有 result 时抛出
  `WorkerProcessError("worker exited with code ...")` 并保留日志路径。
- `WorkerHandle.wait(timeout=...)` 只把 `subprocess.TimeoutExpired` 转为稳定
  timeout error；它不会把超时伪装成 parser diagnostic，也不会自动发布结果。
- cooperative cancel 使用 `request_cancel()` 创建 task-owned cancel marker；worker
  在后续边界返回 cancelled。
- caller 决定超时后的策略。需要停止进程时显式调用 `terminate()`，再按 task
  ownership 清理；不得按进程名终止其他 Python/Blender process。

worker module 固定为受信部署配置，reader request 不能选择任意 module、callable、
argv 或 shell。`reader.parse@0.1` 的 worker crash、cancel 或 timeout 不修改项目；
只有主进程完成 bundle integrity 和 batch graph 验证后，结果才可进入 import
transaction。
