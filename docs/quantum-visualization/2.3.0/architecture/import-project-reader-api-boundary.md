# 2.3.0 导入、项目与 Reader API 边界

## 1. 单一导入流水线

所有入口共享同一流水线：

```text
File Selector / Multi-select / Drag-and-drop / Legacy UI
                           ↓
                     ImportRequest
                           ↓
                Reader Discovery + Sniff
                           ↓
              Staged Parse in ImportSession
                           ↓
                     ImportPreview
              ┌────────────┼────────────┐
              ↓            ↓            ↓
         Diagnostics   Conflicts   Group Suggestions
              └────────────┼────────────┘
                           ↓ user confirms
                   ProjectTransaction
                           ↓
                     QCProject.commit
                           ↓
              Session Sidecar Publication
                           ↓
                  Default View Application
```

Parser 不得直接创建 `bpy` 对象。Blender view失败不回滚已经成功且复验通过的科学数据，但必须回滚本次创建的全部 view datablocks，并报告 `data_committed_view_failed`。

## 2. Source 身份

### `SourceRecord`

表示用户概念中的逻辑来源。它不是路径，也不是一次解析。SourceRecord不内嵌revision列表；QCProject通过`SourceRevision.source_id`建立索引，使新增revision不需要原地修改不可变SourceRecord。

```python
@dataclass(frozen=True, slots=True)
class SourceRecord:
    id: UUID
    display_name: str
    source_kind: str
    created_at_utc: str
```

### `SourceRevision`

表示不可变文件内容和解析条件：

```python
@dataclass(frozen=True, slots=True)
class SourceRevision:
    id: UUID
    source_id: UUID
    content_hash: str
    byte_size: int
    locator: str
    locator_kind: str
    original_filename: str
    reader_plugin_id: str
    reader_id: str
    reader_version: str
    reader_api_version: str
    import_parameters_hash: str
    parse_identity: str
    created_entity_ids: tuple[UUID, ...]
    diagnostic_ids: tuple[UUID, ...]
```

解析身份：

```text
SHA256(content_hash + plugin_id + reader_id + reader_version + canonical_parameters)
```

路径只作为 locator。内容相同但路径改变时可以重链接；路径相同但 hash改变时产生新 revision。

## 3. Import contracts

```python
@dataclass(frozen=True, slots=True)
class ImportRequest:
    sources: tuple[ImportSource, ...]
    validation_mode: ValidationMode
    reader_overrides: tuple[ReaderOverride, ...]
    duplicate_policy: str | None
    grouping_policy: str
    default_view_policy: str
```

```python
@dataclass(frozen=True, slots=True)
class ImportPreview:
    session_id: UUID
    source_previews: tuple[SourcePreview, ...]
    staged_batches: tuple[PublicImportBatch, ...]
    conflicts: tuple[ImportConflict, ...]
    grouping_suggestions: tuple[SourceGroupSuggestion, ...]
    diagnostic_ids: tuple[UUID, ...]
    default_view_plans: tuple[ScenePresetPlan, ...]
```

`ImportPreview` 是只读暂存结果。用户修改 reader、恢复模式、重复策略或归组决定后，必须重新计算受影响的 preview identity。

## 4. 重复策略

| 情况 | 默认 | 其他选项 |
| --- | --- | --- |
| 同 content/reader/params | Reuse Existing | Independent Copy, Locate Existing |
| 同 locator、内容改变 | New Revision | Independent Source, Ignore |
| 同内容、不同 locator | Link Existing | Independent Copy |

批量操作在一个确认窗口汇总。用户取消整个事务时，暂存数组目录删除，项目不变化。

## 5. Session Project

首次导入建立内存项目和临时 sidecar generation：

```text
{blender_temp}/chemblender/{session_uuid}/
├── manifest.json
├── arrays/
├── staging/
└── caches/
```

保存 `.blend` 或 `Save Project` 时写：

```text
scene.blend
scene.cbq/
```

发布过程：

1. 在目标同目录建立 `.{{project_name}}.cbq.{{generation_uuid}}.tmp/`。
2. 写 arrays、manifest、source records 与 generation metadata。
3. 关闭所有 writer，fsync 文件与目录。
4. 重新以 `verify_arrays=True` 打开并检查 project UUID/schema/hash。
5. 若旧 sidecar存在，先重命名为 generation backup。
6. 用同卷原子 rename 发布新 sidecar。
7. 更新 Scene link，保存 manifest hash。
8. 验证 Scene link后删除过期 backup；失败则恢复旧 generation。

Windows 目录替换行为必须通过专门测试，不假定 POSIX rename语义。

## 6. Reader Plugin API

### 执行模式

```text
built_in   → 随主扩展发布
extension  → 独立 Blender Extension，Python PublicImportBatch
worker     → 外部 Python，canonical JSON + safe artifacts
```

### 插件 manifest

```toml
schema_version = "1"
plugin_id = "org.example.reader"
plugin_version = "1.0.0"
chemblender_reader_api = ">=1.0,<2.0"
execution_mode = "extension"
license = ["SPDX:MIT"]

[[readers]]
reader_id = "example-format"
reader_version = "1"
extensions = [".example"]
capabilities = ["structure"]
```

### Python path

```python
class ReaderPlugin(Protocol):
    manifest: ReaderPluginManifest

    def sniff(self, request: SniffRequest) -> SniffResult
    def parse(self, request: ParseRequest) -> PublicImportBatch
```

### Worker path

Worker 结果只包含：

```text
import-batch.json
artifacts/{content_sha256}.npy
logs/stdout.txt
logs/stderr.txt
```

不允许 pickle、absolute path、`..`、动态 callable、任意 shell 或插件直接写项目目录。主进程重新校验 canonical document并构造 public entities。

## 6.1 Blender Extension 间的稳定 API 发现

Blender Extension 安装模块名包含 repository namespace，例如 `bl_ext.user_default.chemblender`，第三方插件不能硬编码该路径，也不能假定源码检出时的 `ChemBlender` 顶层包名。ChemBlender 在注册时发布一个最小 API handle：

```python
READER_API_HANDLE_KEY = "chemblender.reader_api.v1"

@dataclass(frozen=True, slots=True)
class ReaderAPIHandle:
    api_version: str
    module_name: str
    owner_token: str
    register_callback: object
    unregister_callback: object
```

Handle 存入 `bpy.app.driver_namespace[READER_API_HANDLE_KEY]`。`module_name` 是当前实际安装模块名加 `.reader_api`。第三方 Extension 的注册 bootstrap 读取 handle，再用 `importlib.import_module(handle.module_name)` 获得纯 Python public types；reader业务模块本身不依赖 `bpy`。ChemBlender卸载时仅在 owner token 匹配时移除 handle，防止删除其他实例。Alpha使用版本化实验key，beta.1发布v1 key。

缺少或版本不兼容的ChemBlender时，第三方插件只报告依赖不可用，不应使Blender启动失败。

## 7. API 冻结

| 版本阶段 | Reader API |
| --- | --- |
| alpha.1/alpha.2 | 0.x，可根据 built-in reader反馈调整 |
| beta.1 | v1 RC，sidecar schema同时冻结 |
| beta.2 | 只增加可选字段，发布 conformance kit |
| 2.3.0 | v1 stable，2.x执行兼容/废弃政策 |

旧插件不兼容时只禁用该插件，不阻止主扩展启用。缺插件时 `.cbq` 仍可打开和显示，只有 reparse不可用。
