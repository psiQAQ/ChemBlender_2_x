# External record connector v1

`chemblender_external_record_request/1` 是 Blender、local worker 与可选数据库 SDK 之间的只读记录请求。它只保存 provider locator 和凭据引用，不保存凭据值。

## Provider descriptors

| Provider | Locator fields | Envelope | 默认凭据引用 |
| --- | --- | --- | --- |
| `qcarchive` | `server_url`, `record_id` | QCSchema | `env:CHEMBLENDER_QCARCHIVE_TOKEN` |
| `aiida` | `profile`, `node_uuid` | QCSchema/CJSON | 无 |
| `nomad` | `base_url`, `entry_id` | QCSchema/CJSON | `env:CHEMBLENDER_NOMAD_TOKEN` |

URL locator 禁止 userinfo、query 和 fragment。locator 字段不允许 token、password、secret 或 credential；`authentication_ref` 只能是 `env:VARIABLE_NAME`。写入 provenance 的 source 统一为不含 endpoint 与凭据的 URI，例如 `qcarchive://record/42`。

## Worker operation

`external_record.fetch@1` 支持：

- `offline_fixture`：只读取 `.cbq` 内相对 POSIX path，复制到内容寻址 cache，再调用现有 QCSchema/CJSON adapter。
- `provider`：预留可选 SDK；当前在凭据缺失时返回 `authentication_missing`，未安装后端时返回 `dependency_missing`。

稳定错误还包括 `invalid_connector_request`、`external_record_missing` 与 `invalid_external_record`。connector failure 不归类为 parser failure，也不会修改已打开的本地项目。

## 持久化边界

Worker result 只返回 provider、connector version、envelope type、transport、redacted source URI、相对 artifact path 和 cache key。offline fixture 的本机路径、environment value 和 endpoint 不进入 project provenance。
