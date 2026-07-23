# `.cbq` sidecar v0.2 架构

## 目标与边界

v0.2 是当前唯一写入格式。它在 v0.1 的 content-addressed `.npy` 数组与 manifest
最后发布机制上增加 source registry、generation metadata 和 manifest 自校验。
本阶段不增加 diagnostic/view registry。会话固化服务在目标同目录暂存并复验完整
generation，再通过 backup rename 发布；失败时恢复旧目录并保留可明确报告的候选
generation。

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

## Generation publication

`generation_id` 标识一次有效 manifest 写入。`solidify_session()` 在目标同目录
独占创建 `.<name>.cbq.<uuid>.tmp/`，用现有 writer 写完 content-addressed arrays
和 manifest；writer 对每个新文件执行 flush 与 `fsync`，然后关闭全部 writer。
服务以 `verify_arrays=True` 重开暂存目录，验证 project UUID、schema、manifest
hash 与数组后才进入发布步骤。publication metadata 来自同一次 manifest 解析、
严格验证和模型 decode，不再二次读取未验证文档。Windows 不提供此处可移植的目录
`fsync`，因此不把目录 `fsync` 记为已执行。

目标不存在时，暂存目录通过同卷 rename 成为目标；目标已存在时，先把旧目录
rename 为本次唯一 `.<name>.cbq.<uuid>.backup/`，再发布候选目录。发布后再次完整
复验，并要求 project、schema、manifest hash 与 generation ID 精确匹配已复验的
暂存 generation。最终 rename 或复验失败时，服务在紧邻 rollback rename 前用不受
final wrapper 影响的 reader 再次证明目标仍是该 generation；只有证明成功才把候选
退回原临时路径并恢复旧 backup。无法证明归属、候选撤离失败或 backup 恢复失败时，
不删除任何现存目录，并抛出 `PublicationRecoveryError`，同时保留原发布错误、回滚
错误、candidate/destination/backup 路径和不可变 recovery report。

只有最终复验成功后才更新 session 的 `sidecar_path`，服务不清除 dirty reasons。
backup 清理失败不使已复验的 publication 失败；该 backup 保留并由 orphan report
明确列出。

`inspect_publication_orphans()` 只按当前目标名和 canonical UUID 严格识别同目录的
`.tmp` 与 `.backup` 目录，按 ordinal 名称排序返回不可变报告。它不删除或重命名
任何路径；名称近似、其他目标和其他后缀均视为含糊内容并保留。
