# `.cbq` sidecar v0.2 架构

## 目标与边界

v0.2 是当前唯一写入格式。它在 v0.1 的 content-addressed `.npy` 数组与 manifest
最后发布机制上增加 source registry、generation metadata 和 manifest 自校验。
本阶段不增加 diagnostic/view registry，也不实现 Task 4 的整目录 generation
staging、backup 或恢复服务。

## Manifest

`manifest.json` 顶层字段必须精确为：

| 字段 | 约束 | 含义 |
| --- | --- | --- |
| `format` | `chemblender.cbq` | 格式识别符 |
| `manifest_version` | `0.2` | 存储协议版本 |
| `generation_id` | canonical UUID string | 本次 manifest 写入身份 |
| `created_at_utc` | ISO 8601 UTC，`Z` 后缀 | 本次写入时间 |
| `manifest_sha256` | lowercase SHA-256 hex | manifest 内容校验值 |
| `project_id` | canonical UUID string | 项目身份 |
| `project_schema_version` | `0.2` | `QCProject` schema |
| `project` | tagged `QCProject` object | normalized project graph |

多余或缺失顶层字段、无效 UUID/UTC timestamp、header/payload 不一致及 hash
不匹配均为完整性错误。未知 manifest version 为兼容性错误。

## Canonical hash

hash 使用两次序列化，明确排除 `manifest_sha256` 本身：

```python
payload = {
    key: value
    for key, value in manifest.items()
    if key != "manifest_sha256"
}
encoded = json.dumps(
    payload,
    ensure_ascii=False,
    allow_nan=False,
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")
manifest["manifest_sha256"] = hashlib.sha256(encoded).hexdigest()
document = json.dumps(
    manifest,
    ensure_ascii=False,
    allow_nan=False,
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8") + b"\n"
```

reader 从解析后的 JSON 按同一规则重算 hash，因此 JSON 空白或 key 输入顺序不进入
身份；NaN、Infinity 和未知对象不能进入 canonical document。

## Project schema 与 source registry

`QCProject` schema `0.2` 增加：

```text
sources: dict[UUID, SourceRecord]
source_revisions: dict[UUID, SourceRevision]
```

`ImportBatch` 对应增加两个 tuple group。`QCProject.commit()` 在任何 registry
mutation 前构造最终 ID 集并一次验证：

- 所有 project registry 共用一个 UUID namespace；
- 每个 `SourceRevision.source_id` 必须存在于最终 `sources`；
- 每个 `created_entity_ids` 条目必须存在于最终 combined ID set；
- 当前没有 ID-bearing diagnostic registry，因此非空 `diagnostic_ids` 一律作为
  dangling reference 拒绝；
- 直接以非空 registry 初始化 `QCProject` 时执行同样的 source relation 校验。

任一检查失败时，source 与既有科学实体 registry 均不变化。

## v0.1 读取迁移

v0.1 顶层和旧 `QCProject` payload 先按 legacy contract 校验，再复制到内存中：

1. manifest/project schema 改为 `0.2`；
2. 注入编码后的空 `sources` 与 `source_revisions`；
3. 进入现有严格 dataclass decoder；
4. 保留 project UUID、实体、数组 descriptor 与 lazy mmap 行为。

迁移结果不写回 fixture，也不补造 v0.2 generation/hash 字段。传给
`save_project()` 的 schema `0.1` caller 会被编码为 v0.2，但 caller 对象本身不变。

## Generation scope

本阶段的 `generation_id` 只标识一次有效 manifest 写入。数组仍按内容寻址并先于
manifest 原子发布；完整目录的临时 generation、复验、backup rename 与回滚由后续
sidecar publication task 实现。
