# Import Pipeline 与 Reader 开发

本文说明内置 reader、外部 Reader Extension 和 worker reader 如何进入同一
ChemBlender 项目事务。科学 parser 不创建 `bpy` 对象，也不直接写 `QCProject`
或 `.cbq`。

## 主流程

```text
ImportRequest
  -> bounded source hash + SniffRequest
  -> ReaderPluginRegistry selection/availability
  -> ParseRequest
  -> PublicImportBatch
  -> staged ImportPreview + ImportDiagnostic
  -> explicit ImportCommitDecisions
  -> commit_import_preview()
  -> verified .cbq publication
  -> optional Blender View plan
```

主进程入口是
[`preflight_reader_plugins()`](../../ChemBlender/reader_api/import_pipeline_bridge.py)。
它在 owned `StagedImportSession` 中完成 source hash、reader 选择、解析、来源
复验和 batch 图校验。确认阶段才调用
[`commit_import_preview()`](../../ChemBlender/core/import_pipeline/transaction.py)：
先在 disposable project candidate 中提交，再原子发布并重开验证。科学提交与
Blender View 创建是两个边界，后者失败不伪称前者已回滚。

## 添加内置 reader

1. 在 `ChemBlender/core/` 或 `ChemBlender/core/formats/` 实现纯 Python
   parser、bounded `sniff` 和 `ReaderDescriptor`。parser 返回内部
   `ImportBatch`；公共 registry 的 built-in wrapper 才把它投影为
   `PublicImportBatch`。
2. `ReaderDescriptor` 必须声明稳定 `reader_id`/version、扩展名、三态
   capability、priority、bounded `sniff` 和 `parse`。request-aware reader
   另外提供 `parse_request`，或成对提供 `preview_request` /
   `materialize_request`；`ReaderRuntimeDescriptor` 才声明 execution mode 和
   availability。不要创建第二套项目模型。
3. parser 产生科学实体、`ParserReport`、`ParserIssue` 和必要的
   `ImportDiagnostic`。`stage_import_batch()` 统一绑定 `SourceRecord`、
   `SourceRevision`、canonical parameters 和双向 diagnostic IDs；parser 不得
   自行解释项目冲突。
4. 将 descriptor 加入
   [`builtin_reader_descriptors()`](../../ChemBlender/core/reader_catalog.py)。
   built-in registry 会为全部内置 reader 合成一份
   `ReaderPluginManifest`；内置 reader 不另建插件 TOML。同步维护 optional
   dependency、extensionless basename、export maturity/loss policy 和 fixture
   family，`reader_capability_document()` 要求 fixture family 精确覆盖 catalog。
5. 在 `tests/fixtures/<format>/` 添加最小、可审计 fixture 和 provenance；规则见
   [测试 fixture](testing-fixtures.md)。覆盖 exact、partial/ambiguous、invalid
   和 cancellation 边界，而不是只测成功样例。
6. 如支持导出，复用 `ChemBlender/core/exporters/` 的原子 writer，先提供
   deterministic loss preview，再要求 UI 对 Partial/Ambiguous loss 显式确认。
   不支持导出时在 capability document 中保持 `F0`，不要放一个空按钮。
7. UI 只连接现有
   [`quick_import.py`](../../ChemBlender/ui/quick_import.py)、
   [`import_preview.py`](../../ChemBlender/ui/import_preview.py)、
   Project Browser 和 [`export.py`](../../ChemBlender/ui/export.py)。
   新 Blender module 必须成为显式 registration root，科学数组不得进入 RNA。

内置 parser 的公开边界仍须满足 Reader API conformance。至少运行：

```powershell
$pythonBin = 'C:\Program Files\Blender Foundation\Blender 5.1\5.1\python\bin\python.exe'
& $pythonBin -m unittest `
  tests.test_reader_conformance_v1 `
  tests.test_reader_api_import_bridge `
  tests.test_generated_docs_fresh -v
& $pythonBin ChemBlender/scripts/generate_format_docs.py --check
```

`tests.test_reader_conformance_v1` 验证 manifest/descriptor、bounded sniff、
来源身份、图引用、单位、质量/诊断、canonical round-trip、progress、
cancellation 和异常隔离。`generate_format_docs.py --check` 使 reader catalog
变更而 capability 文档未更新时 fail closed。

## 外部 Extension reader

外部 reader 只依赖 [Reader API v1](../reader-api-v1/README.md)。以
[`examples/reader-extension/`](../../examples/reader-extension/README.md) 为
可构建样例：

- registration bootstrap 从
  `bpy.app.driver_namespace["chemblender.reader_api.v1"]` 取得实际安装模块名；
- `reader.py` 的 `create_plugin(api)` 返回 manifest、descriptor、priority、
  `sniff()` 和 `parse()`；
- `ReaderPluginDiscovery` 只接受 handle 的显式 register/unregister，不扫描任意
  `sys.path`；
- `ReaderPluginRegistry` 拥有注册事务。重复或 reserved reader ID、manifest /
  descriptor 不一致及普通插件异常只产生 unavailable/reader diagnostic，不污染
  built-in registry；
- 插件缺失时只有 reparse unavailable；已提交 sidecar 和已有 View 仍可打开。

在安装前运行 example 单元测试和
[conformance CLI](../reader-api-v1/conformance.md)。外部 reader 必须返回
request 指定 revision UUID 的完整 `PublicImportBatch`，不能使用 built-in 的
绑定前私有转换。

## Worker reader

重型或不兼容 Python parser 使用固定 `reader.parse@0.1` operation。调用者只传
task directory 内的 source artifact、SHA-256、validation mode 和 canonical
parameters。worker 写 content-addressed NPY 与 canonical import document；
主进程通过
[`parse_with_worker()`](../../ChemBlender/reader_api/worker_bridge.py) 核对 request/result
UUID、source/bundle hash、operation/schema、inventory、dtype/shape 和完整 batch
图。reader/plugin/version/`parse_identity` 由固定 worker 构造，host 当前不
独立重算；精确信任边界见 [Worker API](../reader-api-v1/worker-api.md)。

worker request 不得包含任意 module、callable、argv、shell 或 pickle。启动、超时、
crash、cancel 和日志生命周期见 [Worker API](../reader-api-v1/worker-api.md)。

## 安全与依赖方向

- `core` / `reader_api` 不依赖 `bpy`；UI 可以依赖 core，反向依赖禁止。
- reader 不获得 `QCProject`、Scene、registry owner、credential value 或任意
  project directory 写权限。
- source 在 parse 前后都复验；canonical parameters 只能是稳定 string mapping。
- 普通 reader `Exception` 被隔离；`MemoryError`、`KeyboardInterrupt` 和
  `SystemExit` 原样传播。
- staging 只清理自身 ownership marker 对应的目录；取消或失败不得发布 partial
  artifact。

精确公共符号和兼容规则以
[Reader API Python 文档](../reader-api-v1/python-api.md)及
[compatibility policy](../reader-api-v1/compatibility.md)为准。
