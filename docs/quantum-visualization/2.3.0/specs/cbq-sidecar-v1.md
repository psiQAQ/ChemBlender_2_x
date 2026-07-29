# `.cbq` sidecar v1

`.cbq` v1 是 ChemBlender 2.3.0 的权威项目持久化格式。当前
`manifest_version` 与 `project_schema_version` 均为 `"1.0"`；保存操作只写
v1，读取继续支持 v0.1 与 v0.2 的内存迁移。

## 目录与权威性

```text
project.cbq/
├── manifest.json
├── arrays/<content-sha256>.npy
└── cache/render/...
```

- `manifest.json` 与 `arrays/` 是权威科学数据。
- `cache/render/` 是可删除、可重建的派生 View cache，不进入 manifest 的
  权威 array registry。
- `.blend` 只保存经验证的 project UUID、schema、sidecar locator 和 manifest
  hash link。

## v1 manifest

顶层字段固定为：

| 字段 | 契约 |
| --- | --- |
| `format` | `"chemblender.cbq"` |
| `manifest_version` | `"1.0"` |
| `generation_id` | canonical UUID |
| `created_at_utc` | UTC `Z` timestamp |
| `manifest_sha256` | 去除本字段后 canonical JSON 的 SHA-256 |
| `project_id` | 与 payload 一致的 canonical UUID |
| `project_schema_version` | `"1.0"` |
| `project` | tagged `QCProject` payload |

JSON 使用 UTF-8、排序 key、compact separators、禁止 NaN/Infinity，并以一个
LF 结尾。写入使用同目录短随机 temporary sibling、flush/fsync 和
`os.replace()`。

## Array artifact

NumPy array 使用 content-addressed `.npy` 文件；descriptor 记录 canonical
content hash、文件 hash、相对 POSIX 路径、shape 和 dtype。读取时拒绝：

- absolute path、`..`、symlink/junction 或逃逸 `.cbq` root 的路径；
- object、structured 或 subarray dtype；
- shape/dtype/hash 不一致；
- pickle 或非有限 manifest 数值。

array 以 `LazyNpyArray` 打开；项目关闭、adoption 失败或 decode 失败时必须关闭
已获得的 mmap ownership。

## 迁移

| 来源 | 读取行为 |
| --- | --- |
| v0.1 | 验证旧 top-level schema，补 source/diagnostic/topology 等新增 registry |
| v0.2 | 先验证原始 generation/header/manifest hash，再在副本中增量升级 |
| v1 | 先验证原始 hash/header；仅对已发布的 additive legacy payload 应用确定性缺省 |

v0.1/v0.2 的 Structure 内嵌 `MolecularTopology` 会确定性提升为
`TopologyRecord`；早期 Structure 缺失的 `atomic_identity` 和
`bond_lattice_shifts` 使用文档化缺省。迁移不修改旧 sidecar。迁移后的项目再次
保存时只产生 v1。

`expected_schema_version` 为 `0.1` 或 `0.2` 时，可以采用已迁移的 v1 项目；
其他未知版本 fail closed。迁移必须保留 entity UUID、scientific arrays、
provenance 和可验证 manifest metadata。

## 冻结策略

v1 的公开项目实体字段与 Reader API v1 RC schema 快照共同受兼容测试保护。
新增可选字段必须有确定性缺省和 migration test；删除、重命名或改变科学语义
需要 release-blocking ADR 与新 schema 版本。
