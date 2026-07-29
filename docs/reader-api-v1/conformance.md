# Reader API v1 Conformance

Conformance kit 在独立 Python 子进程中加载 Reader Extension 的
`reader.py`，运行受限 fixture，并输出 UTF-8、无 BOM、单个 LF 结尾的
canonical JSON。它不安装依赖、不扫描 `sys.path`，也不修改项目或 sidecar。

## 运行

```text
python -m ChemBlender.reader_api.conformance_cli --plugin-path examples/reader-extension --fixtures examples/reader-extension/fixtures --output conformance-result.json
```

`--plugin-path` 必须是包含普通 `reader.py` 的目录；该模块必须提供
`create_plugin(api)`。`--fixtures` 必须是普通目录，kit 仅选择 reader 声明
extension 的普通文件，并拒绝 link 逃逸。插件代码只在子进程中导入。

| Exit code | 含义 |
| --- | --- |
| `0` | 所有 required case 通过；optional case 可以显式 skip |
| `1` | 至少一个 required case 失败；JSON 结果仍会写入 |
| `2` | CLI、路径、插件加载或结果传输失败 |

## Result document

顶层记录 `schema_version`、exact `reader_api_version`、plugin ID/version、
environment、ordered `cases`、`summary` 和 aggregate `passed`。每个 case
记录稳定 ID、reader ID/version、required 标志、`pass`/`fail`/`skip`、
duration seconds、fixture basename/SHA-256、ordered checks、diagnostics 和
optional `skip_reason`。

required case 不允许 skip；optional skip 必须提供非空原因。检查固定覆盖：

1. manifest/runtime descriptor 一致性；
2. 64 KiB bounded sniff 与 deterministic sniff；
3. availability、parse output、source identity 和 graph references；
4. units、quality/diagnostics 和 declared capabilities；
5. canonical round-trip、content-addressed artifact path/hash 安全；
6. per-stage monotonic progress、cancellation 和 exception isolation。

旧 `ReaderConformanceResult` 的 `0.1` schema、12 项 check 顺序和公开 Python
signature 保持不变；v1 suite document 由 CLI 使用。
